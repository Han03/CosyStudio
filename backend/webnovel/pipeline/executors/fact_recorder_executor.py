"""执行器10：事实记录器。

完全参考webnovel-writer的记录事实。
"""

import json
import re
from typing import Dict, Any, List, Tuple
from ..base_executor import BaseExecutor, ExecutorResult
from utils.llm_json_parser import parse_llm_json
from webnovel.repositories import (
    get_webnovel_project_by_script,
    get_character_cards_by_project, add_character_relationship, update_character_card,
    add_character_growth, get_character_power, add_character_power, add_character_card,
    delete_character_card, reassign_character_data,
    upsert_character_item, mark_character_item_lost,
    add_cool_point, update_open_loop_urgency,
    add_chapter_meta, upsert_character_state,
    get_worldview_by_project,
    get_worldview_settings_by_project, add_worldview_setting,
    add_setting_change,
    get_volume_outlines_by_project, get_timelines_by_project,
    get_timeline_chapters, upsert_timeline_chapter,
)


# 物品变化事实的动作分类（与 fact_record_prompt 约定的动词集一致）
# 获得类动词 → 累加数量；其他动词（失去/损毁/赠予等）→ 扣减数量
_GAIN_ACTIONS = {"获得", "得到", "收下", "缴获", "抢得", "抢走", "夺得",
                 "买下", "买得", "拾得", "捡到", "接过"}

# 伏笔/爽点类型（与 extract_foreshadow_cool_point 定义一致）
COOL_POINT_TYPES = [
    "装逼打脸", "扮猪吃虎", "越级反杀", "打脸权威", "反派翻车",
    "甜蜜超预期", "突破", "升级", "寻宝", "奇遇",
    "逆袭", "情感", "解谜", "反转", "发现"
]

FORESHA_DOW_TIERS = ["核心", "支线", "装饰"]


_CN_NUM = {"零": 0, "一": 1, "元": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "廿": 20, "卅": 30}
_CN_DAYS = {"初一": 1, "初二": 2, "初三": 3, "初四": 4, "初五": 5, "初六": 6, "初七": 7,
            "初八": 8, "初九": 9, "初十": 10}


def _cn_num_to_int(text: str):
    """中文数字转 int（支持 一~三十/初X/廿X/卅X），失败返回 None。"""
    if not text:
        return None
    if text in _CN_DAYS:
        return _CN_DAYS[text]
    if text.startswith("初") and len(text) == 2 and text[1] in _CN_NUM:
        return _CN_NUM[text[1]]
    if text in _CN_NUM:
        return _CN_NUM[text]
    if text.startswith("十"):
        return 10 + _CN_NUM.get(text[1:], 0)
    if text.startswith("廿"):
        return 20 + _CN_NUM.get(text[1:], 0)
    if text.startswith("卅"):
        return 30 + _CN_NUM.get(text[1:], 0)
    if text.isdigit():
        return int(text)
    return None


def _int_to_cn_day(num: int) -> str:
    """int 转中文日（1→初一, 11→十一, 21→廿一, 30→三十）。"""
    if num <= 0:
        return ""
    if num <= 10:
        return "初" + ("十" if num == 10 else "一二三四五六七八九"[num - 1])
    if num < 20:
        return "十" + ("一二三四五六七八九"[num - 11] if num > 10 else "")
    if num % 10 == 0:
        return ("二十" if num == 20 else "三十")
    return ("廿" if num < 30 else "卅") + "一二三四五六七八九"[num % 10 - 1]


def _interval_to_days(interval: str):
    """解析时间间隔为天数（'一日'/'1日'/'一天'→1；'半日'/'连续'/'跨夜'→None）。"""
    if not interval:
        return None
    text = str(interval).strip()
    # 阿拉伯数字：N日/N天/N个月
    m = re.match(r"^([0-9]+)\s*(日|天)$", text)
    if m:
        return int(m.group(1))
    # 中文数字：X日/X天
    m = re.match(r"^([一二两三四五六七八九十廿卅]+)\s*(日|天)$", text)
    if m:
        n = _cn_num_to_int(m.group(1))
        return n if n and n > 0 else None
    # 连续/半日/跨夜/当夜/一夜等不跨日表述
    if any(k in text for k in ("半日", "连续", "跨夜", "当夜", "一夜", "当日", "同一天")):
        return None
    m = re.match(r"^([0-9一二两三四五六七八九十廿卅]+)\s*个月?$", text)
    if m:
        n = _cn_num_to_int(m.group(1))
        return n * 30 if n else None
    return None


def _advance_date(anchor: str, days: int) -> str:
    """按天数推进日期（小说虚构历法简化：月内推进，跨月按 30 天/月进位）。"""
    if not anchor or not days or days <= 0:
        return anchor
    m = re.match(r"^(.*?)([一二三四五六七八九十]+|[0-9]+)月([初一二三四五六七八九十廿卅]+|[0-9]+)(?:日)?$", anchor)
    if not m:
        return anchor
    year = m.group(1)
    month = _cn_num_to_int(m.group(2))
    day = _cn_num_to_int(m.group(3))
    if not month or not day:
        return anchor
    day += days
    while day > 30:
        day -= 30
        month += 1
    if month > 12:
        month = 1
        # 纪年推进：天启元年 +1 → 天启二年（仅当 year 可解析；否则保持）
        y = re.search(r"([一二三四五六七八九十百千零元]+|[0-9]+)年", year)
        if y:
            yv = _cn_num_to_int(y.group(1))
            if yv:
                year = year[:y.start()] + _int_to_cn_year(yv + 1) + "年"
    month_cn = _int_to_cn_month(month)
    day_cn = _int_to_cn_day(day)
    return f"{year}{month_cn}月{day_cn}"


def _int_to_cn_month(num: int) -> str:
    if num <= 0 or num > 12:
        return str(num)
    return "一二三四五六七八九十"[num - 1] if num <= 10 else ("十一" if num == 11 else "十二")


def _int_to_cn_year(num: int) -> str:
    if num <= 0:
        return str(num)
    digits = "零一二三四五六七八九"
    if num < 10:
        return digits[num]
    if num < 20:
        return "十" + (digits[num - 10] if num > 10 else "")
    parts = []
    s = str(num)
    for i, ch in enumerate(s):
        d = int(ch)
        place = len(s) - i
        if d == 0:
            parts.append("零")
        elif place == 4:
            parts.append(digits[d] + "千")
        elif place == 3:
            parts.append(digits[d] + "百")
        elif place == 2:
            parts.append(digits[d] + "十")
        else:
            parts.append(digits[d])
    return "".join(parts).replace("零", "零") if num < 1000 else "".join(parts)


class FactRecorderExecutor(BaseExecutor):
    """事实记录器执行器。"""

    step_name = "fact_recorder"
    step_description = "事实记录"
    step_weight = 10

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行事实记录（归口：事实/爽点/结尾钩子/角色状态/世界观设定/章节时间轴 一次提取 + 新角色建卡）。"""
        try:
            script_id = self.script_id

            polished_content = context.get("polished_content", "") or context.get("revised_draft", "") or context.get("draft_content", "")

            if not polished_content:
                return ExecutorResult(
                    success=True,
                    step_summary="润色内容为空，跳过事实记录",
                    output_data={"facts": []}
                )

            inventory = context.get("context_inventory", {})

            world_settings_text = []
            for s in inventory.get('world_settings', []):
                if isinstance(s, dict):
                    if s.get('name'):
                        world_settings_text.append(s['name'])
                    elif s.get('world_summary'):
                        world_settings_text.append(s['world_summary'][:50])
                    else:
                        world_settings_text.append("世界观设定")

            # 0. 先检测并创建新角色（建卡入库后，事实提取的角色清单才包含本章新角色，
            #    character_updates 关系 / character_states 能匹配新卡真实 id）
            await self._create_new_characters(script_id, polished_content, inventory)

            project = get_webnovel_project_by_script(script_id)
            project_id = project["id"] if project else 0

            # 角色清单（带真实 id 文本）与物品清单（item 名称对齐依据）
            characters_text = self._build_characters_text(project_id)
            character_items_text = self._build_character_items_text(project_id)

            # 从 .md 文件加载 prompt 模板
            prompt_data = self._load_prompt("fact_record")
            # 事实提取需要覆盖全章内容，截断过短会遗漏核心事件（如升级突破、物品消耗）。
            # 成品章节 3000-5000 字，取前 4000 字可覆盖大部分关键事件。
            chapter_content = polished_content[:4000] if len(polished_content) > 4000 else polished_content

            from core.model_executor import get_model_executor
            executor = get_model_executor()

            # 前一章时间轴（基于原文的章节时间轴证据，供 chapter_timeline 块衔接）
            prev_timeline = self._build_prev_timeline_text(project_id, self.chapter_index)

            prompt = prompt_data["user_prompt"].format(
                chapter_content=chapter_content,
                world_settings=json.dumps(world_settings_text, ensure_ascii=False),
                characters=characters_text,
                character_items=character_items_text,
                prev_timeline=prev_timeline,
            )
            system_prompt = prompt_data["system_prompt"] or "你是一位专业的内容分析助手，擅长提取文本中的关键信息，输出严格的JSON格式"

            result = await executor.execute_text_chat(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=3000,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="fact_record",
            )

            content = result.get("content", "") if result else ""
            (item_changes, character_updates, cool_points, hook,
             character_states, world_settings, chapter_timeline) = self._parse_all(
                content, script_id, project_id)

            # 1. 结构化物品变化落库（item_changes）
            rag_affected = set()
            if item_changes:
                rag_affected.update(self._save_item_changes(script_id, self.chapter_index, item_changes))

            # 2. 结构化角色更新落库（关系/身份揭露/成长/能力）
            if character_updates:
                rag_affected.update(await self._save_character_updates(
                    script_id, self.chapter_index, character_updates))

            # 2. 爽点落库（含标签补充+去重）+ 3. 结尾钩子 + 4. 角色状态 + 5. 世界观设定
            if project_id:
                await self._save_cool_points(project_id, self.chapter_index, cool_points, polished_content)
                await self._save_hook(project_id, self.chapter_index, hook)
                await self._save_character_states(project_id, self.chapter_index, character_states)
                await self._save_world_settings(project_id, self.chapter_index, world_settings)
                # 5.5 章节时间轴（基于原文补写 webnovel_timeline_chapter）
                await self._save_chapter_timeline(project_id, self.chapter_index, chapter_timeline)
            # 跨章节事件（开放悬念/倒计时 提取+回收）由 apply 后处理中独立执行器处理

            item_change_count = len(item_changes)
            char_update_count = len(character_updates)
            item_tail = f"，{item_change_count}条物品变化" if item_change_count else ""
            char_tail = f"，{char_update_count}条角色更新" if char_update_count else ""
            timeline_tail = ""
            if chapter_timeline and chapter_timeline.get("time_anchor"):
                timeline_tail = f"，时间轴:{chapter_timeline.get('time_anchor', '')[:20]}"
            summary = (f"事实记录完成："
                       f"{len(cool_points)}个爽点，{len(character_states)}条角色状态"
                       f"{item_tail}{char_tail}"
                       + (f"，{len(world_settings)}条设定" if world_settings else "")
                       + timeline_tail)

            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "item_changes": item_changes,
                    "item_changes_count": item_change_count,
                    "character_updates": character_updates,
                    "character_updates_count": char_update_count,
                    "cool_points_count": len(cool_points),
                    "character_states_count": len(character_states),
                    "world_settings_count": len(world_settings),
                    "chapter_timeline": chapter_timeline,
                }
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"事实记录执行失败: {str(e)}",
                step_summary="事实记录执行失败"
            )

    def _parse_all(self, content: str, script_id: int, project_id: int):
        """解析七块提取结果：item_changes / character_updates / cool_points / hook / character_states / world_settings / chapter_timeline（容错）。"""
        item_changes, character_updates, cool_points, hook, character_states, world_settings = [], [], [], {}, [], []
        chapter_timeline: Dict[str, Any] = {}
        if not content:
            return (item_changes, character_updates, cool_points, hook,
                    character_states, world_settings, chapter_timeline)

        fact_data = parse_llm_json(
            content,
            script_id=script_id,
            project_id=project_id,
            executor_name=self.step_name,
            prompt_name="fact_record",
        )
        if fact_data and isinstance(fact_data, dict):
            item_changes = [i for i in (fact_data.get("item_changes") or [])
                           if isinstance(i, dict) and i.get("character") and i.get("item")]
            character_updates = [u for u in (fact_data.get("character_updates") or [])
                                if isinstance(u, dict) and u.get("type")]
            cool_points = [c for c in (fact_data.get("cool_points") or [])
                           if isinstance(c, dict) and c.get("content")]
            hook = fact_data.get("hook") or {}
            if not isinstance(hook, dict):
                hook = {}
            character_states = [s for s in (fact_data.get("character_states") or [])
                                if isinstance(s, dict) and s.get("character_id")]
            world_settings = [w for w in (fact_data.get("world_settings") or [])
                              if isinstance(w, dict) and w.get("name") and w.get("content")]
            ct = fact_data.get("chapter_timeline") or {}
            if isinstance(ct, dict):
                chapter_timeline = {
                    k: str(v).strip() if isinstance(v, str) else v
                    for k, v in ct.items()
                    if k in ("time_anchor", "chapter_duration", "interval_from_prev",
                             "countdown_status", "notes")
                }
        # JSON 解析失败或缺失：全部结构化块为空（无文本兜底）
        return (item_changes, character_updates, cool_points, hook,
                character_states, world_settings, chapter_timeline)

    def _build_prev_timeline_text(self, project_id: int, chapter_index: int) -> str:
        """构建前一章时间轴文本（当前章所属卷时间轴中，本章之前的最近 3 章锚点）。

        始终注入本卷时间基准（time_base/time_span），起始章无前一章锚点时
        以卷基准为起点，保证 time_anchor 能推算到具体日期而非只有时刻。
        """
        if not project_id:
            return "（暂无前一章时间轴）"
        try:
            volume_outlines = get_volume_outlines_by_project(project_id)
            cur_vol = None
            for vo in volume_outlines:
                if vo.get("chapter_start", 1) <= chapter_index <= vo.get("chapter_end", 9999):
                    cur_vol = vo
                    break
            if not cur_vol:
                return "（暂无前一章时间轴）"
            timelines = get_timelines_by_project(project_id)
            tl = next(
                (t for t in timelines if t.get("volume_number") == cur_vol.get("volume_number")),
                None
            )
            if not tl:
                return "（本卷暂无时间轴数据）"
            # 卷时间基准：始终注入，供本章 time_anchor 推算完整日期
            base_bits = []
            if tl.get("time_base"):
                base_bits.append(f"时间基准:{tl['time_base']}")
            if tl.get("time_span"):
                base_bits.append(f"卷跨度:{tl['time_span']}")
            base_line = f"- 本卷 | {' | '.join(base_bits)}" if base_bits else ""
            chapters = get_timeline_chapters(tl["id"]) or []
            prev = [c for c in chapters if (c.get("chapter_number") or 0) < chapter_index][-3:]
            if not prev:
                if base_line:
                    return ("（本章为该卷起始章，无前一章时间轴；"
                            "本章时间应以上述本卷时间基准为起点推算）\n" + base_line)
                return "（本章为该卷起始章，无前一章时间轴）"
            lines = []
            for c in prev:
                bits = []
                if c.get("time_anchor"):
                    bits.append(f"锚点:{c['time_anchor']}")
                if c.get("chapter_duration"):
                    bits.append(f"章内跨度:{c['chapter_duration']}")
                if c.get("interval_from_prev"):
                    bits.append(f"距上章:{c['interval_from_prev']}")
                if c.get("countdown_status") and c.get("countdown_status") != "无":
                    bits.append(f"倒计时:{c['countdown_status']}")
                line = f"- 第{c.get('chapter_number', '?')}章"
                if bits:
                    line += " | " + " | ".join(bits)
                lines.append(line)
            if base_line:
                lines.insert(0, base_line)
            return "\n".join(lines)
        except Exception:
            return "（暂无前一章时间轴）"

    async def _save_chapter_timeline(
        self, project_id: int, chapter_index: int, chapter_timeline: Dict[str, Any]
    ) -> None:
        """落库章节时间轴到 webnovel_timeline_chapter（upsert，按卷匹配主记录）。

        卷主记录由卷首时间轴生成器在每卷第一章创作前创建；此处缺失时记警告跳过，
        不阻断事实记录主流程（时间轴为辅助数据）。
        """
        from utils.logger import log_manager
        logger = log_manager.get_logger("fact_recorder")
        try:
            if not chapter_timeline or not isinstance(chapter_timeline, dict):
                return
            if not chapter_timeline.get("time_anchor"):
                return
            volume_outlines = get_volume_outlines_by_project(project_id)
            cur_vol = None
            for vo in volume_outlines:
                if vo.get("chapter_start", 1) <= chapter_index <= vo.get("chapter_end", 9999):
                    cur_vol = vo
                    break
            if not cur_vol:
                return
            timelines = get_timelines_by_project(project_id)
            tl = next(
                (t for t in timelines if t.get("volume_number") == cur_vol.get("volume_number")),
                None
            )
            if not tl:
                logger.warning(
                    f"[FactRecorder] 第{chapter_index}章时间轴落库跳过：第{cur_vol.get('volume_number')}卷无主记录"
                )
                return
            time_anchor = str(chapter_timeline.get("time_anchor", "") or "").strip()
            interval = str(chapter_timeline.get("interval_from_prev", "") or "").strip()
            notes = str(chapter_timeline.get("notes", "") or "").strip()

            # 锚点校验：与前一章相同且间隔为明确天数时，按间隔自动推进。
            # LLM 在正文无明确时间时常直接复制前一章锚点，导致时间轴停滞且与
            # interval_from_prev（如"一日"）自相矛盾。
            prev_row = None
            prev_chapters = get_timeline_chapters(tl["id"]) or []
            for pc in prev_chapters:
                if (pc.get("chapter_number") or 0) == chapter_index - 1:
                    prev_row = pc
                    break
            if (prev_row and prev_row.get("time_anchor")
                    and time_anchor == prev_row["time_anchor"]):
                days = _interval_to_days(interval)
                if days and days > 0:
                    new_anchor = _advance_date(prev_row["time_anchor"], days)
                    if new_anchor and new_anchor != prev_row["time_anchor"]:
                        logger.info(
                            f"[FactRecorder] 第{chapter_index}章锚点与上章相同且间隔'{interval}'，"
                            f"自动推进 {prev_row['time_anchor']} → {new_anchor}"
                        )
                        time_anchor = new_anchor
                        if notes and "自动推进" not in notes:
                            notes += f"；锚点与上章相同，按间隔{interval}自动推进"
                        elif not notes:
                            notes = f"锚点与上章相同，按间隔{interval}自动推进"
            upsert_timeline_chapter(
                timeline_id=tl["id"],
                chapter_number=chapter_index,
                time_anchor=time_anchor,
                chapter_duration=chapter_timeline.get("chapter_duration", ""),
                interval_from_prev=interval,
                countdown_status=chapter_timeline.get("countdown_status", ""),
                notes=notes,
            )
        except Exception as e:
            logger.warning(f"[FactRecorder] 章节时间轴落库失败（不阻断）: {e}")


    async def _save_cool_points(
        self, project_id: int, chapter_index: int,
        cool_points: List[Dict], content: str
    ) -> None:
        """落库爽点（含标签补充、去重）。"""
        cool_points = list(cool_points) + self._extract_cool_points_from_tags(content)
        cool_points = self._deduplicate_cool_points(cool_points)

        for cp in cool_points:
            add_cool_point(
                project_id=project_id,
                chapter_number=chapter_index,
                content=cp["content"],
                cool_point_type=cp.get("cool_point_type", ""),
                execution_mode=cp.get("execution_mode", ""),
                structure_stage=cp.get("structure_stage", ""),
                pressure_level=cp.get("pressure_level", 0),
                release_level=cp.get("release_level", 0),
                reader_emotion=cp.get("reader_emotion", ""),
                impact_score=cp.get("impact_score", 0),
                evidence=cp.get("evidence", "")
            )

        update_open_loop_urgency(project_id, chapter_index)

    async def _save_hook(self, project_id: int, chapter_index: int, hook: Dict):
        """落库结尾钩子到 chapter_meta（每次应用结果插入一条新版本，保留历史）。

        hook_type 一并落库（fact_record 结构化输出字段，此前被丢弃）。
        """
        try:
            if not hook or not hook.get("hook_content"):
                return
            add_chapter_meta(
                project_id=project_id,
                chapter_number=chapter_index,
                hook_type=str(hook.get("hook_type", "") or "").strip(),
                hook_content=hook.get("hook_content", ""),
                hook_strength=hook.get("hook_strength", "中"),
                hook_pattern=hook.get("hook_pattern", ""),
                ending_emotion=hook.get("ending_emotion", ""),
                ending_time=hook.get("ending_time", ""),
                ending_location=hook.get("ending_location", ""),
            )
            from utils.logger import log_manager
            logger = log_manager.get_logger("fact_recorder")
            logger.info(f"[fact_recorder] 已保存第{chapter_index}章结尾钩子")
        except Exception:
            pass

    async def _save_character_states(
        self, project_id: int, chapter_index: int, states: List[Dict]
    ) -> int:
        """落库章末角色状态到 character_state（每章覆盖 upsert）。"""
        count = 0
        try:
            # 角色名 → 真实 id 映射（LLM 可能自造序号，落库前按名字兜底修正）
            card_id_map = {}
            try:
                for c in get_character_cards_by_project(project_id) or []:
                    nm = c.get("name", "") or c.get("character_name", "")
                    if nm:
                        card_id_map[nm] = c.get("id")
            except Exception:
                pass
            for s in states:
                cname = str(s.get("character_name", "") or "").strip()
                cid = s.get("character_id")
                if not cid or cid not in set(card_id_map.values()):
                    cid = card_id_map.get(cname)
                if not cid:
                    continue
                upsert_character_state(
                    project_id=project_id,
                    character_id=cid,
                    character_name=cname,
                    chapter_number=chapter_index,
                    location=s.get("location", ""),
                    state_summary=s.get("state_summary", ""),
                    emotion=s.get("emotion", ""),
                    knowledge=s.get("knowledge", ""),
                    notes=s.get("notes", ""),
                )
                count += 1
            if count:
                from utils.logger import log_manager
                logger = log_manager.get_logger("fact_recorder")
                logger.info(f"[fact_recorder] 角色状态记录完成：{count} 条（第{chapter_index}章）")
        except Exception:
            pass
        return count

    async def _save_world_settings(
        self, project_id: int, chapter_index: int, world_settings: List[Dict]
    ) -> int:
        """落库本章新交代的世界观设定（逐条写入 webnovel_worldview_setting）。

        不再追加进 webnovel_worldview.world_summary（总纲保持初始化内容）；
        独立条目支持按章查询/删除（取消应用结果时回退）。
        返回新增条目数。单条失败不阻断。
        """
        count = 0
        try:
            from utils.logger import log_manager
            logger = log_manager.get_logger("fact_recorder")

            if not project_id or not world_settings:
                return 0

            # 查重基准：初始化总纲 + 新表历史条目（避免跨章重复记录）
            existing_summary = ((get_worldview_by_project(project_id) or {}).get("world_summary", "") or "")
            existing_keys = set()
            for it in (get_worldview_settings_by_project(project_id) or []):
                n = str(it.get("name", "") or "").strip()
                c = str(it.get("content", "") or "").strip()
                if n:
                    existing_keys.add(n)
                if c:
                    existing_keys.add(c[:30])

            for ws in world_settings:
                try:
                    name = str(ws.get("name", "") or "").strip()
                    content = str(ws.get("content", "") or "").strip()
                    category = str(ws.get("category", "") or "").strip()
                    if not name or not content or len(name) > 40 or len(content) > 600:
                        continue
                    # 简单查重：名称或内容前缀已存在于总纲或历史条目则不重复记录
                    if name in existing_summary or content[:30] in existing_summary:
                        continue
                    if name in existing_keys or content[:30] in existing_keys:
                        continue
                    add_worldview_setting(
                        project_id=project_id, chapter_number=chapter_index,
                        name=name, content=content, category=category,
                    )
                    count += 1
                except Exception:
                    continue

            if count:
                logger.info(f"[fact_recorder] 世界观设定新增完成：{count} 条（第{chapter_index}章）")
        except Exception:
            pass
        return count

    @staticmethod
    def _extract_cool_points_from_tags(content: str) -> List[Dict]:
        """从内容中的[爽点: ...]标记提取爽点。"""
        pattern = r'\[爽点:\s*(.*?)\]'
        matches = re.findall(pattern, content)
        cool_points = []
        for match in matches:
            parts = match.strip().split('/')
            cp_type = parts[0].strip() if len(parts) > 0 else ""
            cp_desc = parts[1].strip() if len(parts) > 1 else cp_type
            cool_points.append({
                "content": cp_desc,
                "cool_point_type": cp_type,
                "execution_mode": cp_type,
                "structure_stage": "爆发",
                "pressure_level": 3,
                "release_level": 4,
                "reader_emotion": "爽",
                "impact_score": 7,
                "evidence": f"[爽点: {match}]"
            })
        return cool_points

    @staticmethod
    def _deduplicate_cool_points(cool_points: List[Dict]) -> List[Dict]:
        """去重爽点列表。"""
        seen = set()
        result = []
        for cp in cool_points:
            key = cp.get("content", "")[:100]
            if key not in seen:
                seen.add(key)
                result.append(cp)
        return result

    def _build_characters_text(self, project_id: int) -> str:
        """构建角色清单文本（带真实 id），供事实提取识别角色与 character_id 使用。

        直接从角色卡表读取（含本章刚建的新卡），id 为数据库真实主键，
        避免 LLM 自造序号导致 character_states.character_id 断链。
        """
        try:
            cards = get_character_cards_by_project(project_id) or []
        except Exception:
            cards = []
        if not cards:
            return "（暂无角色）"
        lines = []
        for c in cards:
            name = c.get("name", "") or c.get("character_name", "")
            if not name:
                continue
            identity = (c.get("identity") or "").strip()
            parts = [f"id={c.get('id', 0)}", f"姓名：{name}"]
            if identity:
                parts.append(f"身份：{identity[:30]}")
            lines.append("- " + " ｜ ".join(parts))
        return "\n".join(lines) if lines else "（暂无角色）"

    def _build_character_items_text(self, project_id: int) -> str:
        """构建角色物品清单文本（各角色当前持有物品及数量），供 item_changes 名称对齐。

        同一物品跨章提取时名称不稳定（玉简/青元剑诀玉简/残篇玉简），
        注入已持有清单并要求 LLM 沿用清单名称，从源头防分裂。
        """
        try:
            from repositories.base_repository import _get_conn
            conn = _get_conn()
            card_rows = conn.execute(
                "SELECT id, name FROM webnovel_character_card WHERE project_id=?",
                (project_id,),
            ).fetchall()
            item_rows = conn.execute(
                "SELECT character_id, item_name, quantity FROM webnovel_character_item "
                "WHERE character_id IN (SELECT id FROM webnovel_character_card WHERE project_id=?)",
                (project_id,),
            ).fetchall()
        except Exception:
            return "（暂无物品持有记录）"
        if not item_rows:
            return "（暂无物品持有记录）"
        name_map = {r["id"]: (r["name"] or str(r["id"])) for r in card_rows}
        by_char: Dict[str, List[str]] = {}
        for r in item_rows:
            cname = name_map.get(r["character_id"], f"id={r['character_id']}")
            by_char.setdefault(cname, []).append(f"{r['item_name']}x{r['quantity']}")
        lines = [f"- {name} 持有：" + "、".join(by_char[name]) for name in sorted(by_char)]
        return "\n".join(lines)

    def _format_existing_chars_text(self, existing_chars: list) -> str:
        """将已有角色列表渲染为易读文本（替代 JSON 注入）。

        每角色一行：姓名/曾用名/身份/类型 带中文标签，`｜` 分隔；
        曾用名为空显示 "-"（明确表示无别名，避免 LLM 误判重复）；
        无角色时返回占位提示。
        """
        if not existing_chars:
            return "（暂无已有角色）"
        lines = []
        for c in existing_chars:
            name = c.get("name", "") or c.get("character_name", "")
            if not name:
                continue
            alias = (c.get("alias") or "").strip()
            identity = (c.get("identity") or "").strip()
            ctype = (c.get("character_type") or "").strip()
            parts = [f"姓名：{name}"]
            parts.append(f"曾用名：{alias}" if alias else "曾用名：-")
            if identity:
                parts.append(f"身份：{identity}")
            if ctype:
                parts.append(f"类型：{ctype}")
            lines.append("- " + " ｜ ".join(parts))
        return "\n".join(lines) if lines else "（暂无已有角色）"

    async def _create_new_characters(
        self, script_id: int, draft_content: str, inventory: Dict[str, Any]
    ) -> List[Tuple[str, int]]:
        """检测正文中的新角色并自动创建角色卡。返回新卡 [(name, id), ...]。"""
        try:
            project = get_webnovel_project_by_script(script_id)
            if not project:
                return []
            project_id = project["id"]

            # 获取已有角色名与曾用名（曾用名命中同样视为已有角色）
            existing_chars = get_character_cards_by_project(project_id)
            existing_names = set()
            existing_aliases = set()
            for c in existing_chars:
                name = c.get("name", "") or c.get("character_name", "")
                if name:
                    existing_names.add(name)
                for a in re.split(r"[,，、]", c.get("alias", "") or ""):
                    if a.strip():
                        existing_aliases.add(a.strip())

            # 构建已有角色列表文本（包含身份和曾用名信息，帮助 LLM 判断是否为同一角色）
            # 用易读文本而非 JSON：每角色一行，姓名/曾用名/身份/类型带中文标签，便于 LLM 对照防重复
            existing_chars_text = self._format_existing_chars_text(existing_chars)

            # 正文截断策略：首尾各取一半，确保覆盖全章角色
            if len(draft_content) > 6000:
                content_sample = draft_content[:3000] + "\n...(中间省略)...\n" + draft_content[-3000:]
            else:
                content_sample = draft_content

            # 从外置 .md 模板加载 prompt（按角色类型分级输出字段，键名与角色卡表列名一致）
            prompt_data = self._load_prompt("create_new_characters")
            prompt = prompt_data["user_prompt"].format(
                existing_chars=existing_chars_text,
                content_sample=content_sample,
            )
            system_prompt = prompt_data["system_prompt"] or "你是一位专业的网文编辑，擅长识别和分析角色。输出严格的JSON格式。"
            if not prompt.strip():
                from utils.logger import log_manager
                log_manager.get_logger("fact_recorder").warning(
                    "[fact_recorder] create_new_characters prompt 模板加载为空，跳过新角色检测"
                )
                return []

            from core.model_executor import get_model_executor
            executor = get_model_executor()
            result = await executor.execute_text_chat(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=2000,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="create_new_characters",
            )

            content = result.get("content", "") if result else ""
            if not content:
                return []

            char_data = parse_llm_json(
                content,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="create_new_characters",
            )

            if not char_data or "new_characters" not in char_data:
                return []

            # 创建新角色卡（收集新卡 name/id 供后续事实提取引用）
            created_pairs: List[Tuple[str, int]] = []
            for char in char_data["new_characters"]:
                if not isinstance(char, dict):
                    continue
                name = char.get("name", "").strip()
                if not name:
                    continue
                # 精确匹配去重：名字或曾用名命中已有卡则跳过（包含子串匹配，防变体）
                if name in existing_names or any(name in a for a in existing_aliases):
                    continue
                if any(name in existing or existing in name for existing in existing_names):
                    continue
                # 过滤常见非角色名词（含泛称、动物、尸体等非人物实体）
                skip_terms = {"主角", "反派", "女主", "男主", "配角", "路人", "群众", "弟子", "长老",
                              "妖兽", "猛兽", "妖兵", "妖丹", "灵兽", "凶兽", "幻兽",
                              "尸体", "遗骸", "骸骨", "残骸", "尸傀", "尸虫"}
                if name in skip_terms or len(name) > 10:
                    continue
                # 过滤含动物/尸体关键词的名称（如"铁背狼""散修遗骸"）
                _non_char_keywords = ("狼", "虎", "蛇", "熊", "鹰", "兽", "尸", "骸", "傀")
                if any(kw in name for kw in _non_char_keywords):
                    continue

                # 按 LLM 返回的类型建卡；非法/缺失时兜底 minor，避免龙套污染配角层
                raw_type = str(char.get("character_type", "")).strip().lower()
                char_type = raw_type if raw_type in ("villain", "supporting", "minor") else "minor"
                
                # 白名单字段直传：键名与 prompt 输出及角色卡表列名完全一致，
                # 避免二次映射导致的字段错位/丢失（minor 无深化字段，缺失自动为空）
                card_fields = (
                    "age_stage", "identity", "protagonist_relation", "core_personality", "core_tags", "first_impression",
                    "short_term_goal", "true_desire", "personality_flaw", "starting_state",
                    "long_term_goal", "behavior_pattern", "ability_limit",
                )
                card_kwargs = {k: str(char.get(k, "") or "").strip() for k in card_fields}
                
                new_card = add_character_card(
                    project_id,
                    char_type,
                    name=name,
                    **card_kwargs,
                )
                existing_names.add(name)
                if new_card and new_card.get("id"):
                    created_pairs.append((name, new_card["id"]))
                    # 记录基础设定变更（回退用）：新建角色卡
                    try:
                        add_setting_change(
                            project_id=project_id, chapter_number=self.chapter_index,
                            entity_type="character_card", entity_id=new_card["id"],
                            change_type="create",
                            before_data="",
                            after_data=json.dumps({"name": name, "character_type": char_type,
                                                   **card_kwargs}, ensure_ascii=False),
                        )
                    except Exception:
                        pass

            if created_pairs:
                from utils.logger import log_manager
                logger = log_manager.get_logger("fact_recorder")
                logger.info(f"[fact_recorder] 自动创建新角色卡: {[n for n, _ in created_pairs]}")

            return created_pairs
        except Exception:
            return []

    async def _save_character_updates(
        self, script_id: int, chapter_index: int,
        character_updates: List[Dict[str, Any]]
    ) -> set:
        """落库结构化角色更新（character_updates 主通道）。

        type 枚举：关系 / 身份揭露 / 成长 / 能力。
        返回受影响 char_id 集合（供 RAG 增量重建）。单条失败不阻断，记日志。
        """
        changed = set()
        try:
            from utils.logger import log_manager
            logger = log_manager.get_logger("fact_recorder")

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return changed
            project_id = project["id"]
            all_chars = get_character_cards_by_project(project_id)
            char_name_map = {}
            for c in all_chars:
                name = c.get("name", "") or c.get("character_name", "")
                if name:
                    char_name_map[name] = c
            sorted_names = sorted(char_name_map.keys(), key=len, reverse=True)

            for cu in character_updates:
                try:
                    utype = str(cu.get("type", "") or "").strip()
                    if utype not in ("关系", "身份揭露", "成长", "能力"):
                        logger.warning(f"[fact_recorder] character_updates 非法类型已跳过: {cu}")
                        continue
                    desc = str(cu.get("description", "") or "").strip()

                    if utype == "关系":
                        character = str(cu.get("character", "") or "").strip()
                        target = str(cu.get("target", "") or "").strip()
                        if character in char_name_map and target in char_name_map:
                            add_character_relationship(
                                character_id=char_name_map[character]["id"],
                                relation_type=utype,
                                target_character_id=char_name_map[target]["id"],
                                target_name=target,
                                description=f"第{chapter_index}章: {desc[:100]}",
                                source_chapter=chapter_index,
                            )
                            changed.add(char_name_map[character]["id"])
                            changed.add(char_name_map[target]["id"])
                            logger.info(f"[fact_recorder] 角色关系：'{character}' ↔ '{target}'")
                        else:
                            logger.warning(f"[fact_recorder] 关系角色未匹配: {character!r}/{target!r}")
                        continue

                    if utype == "身份揭露":
                        alias_name = str(cu.get("alias", "") or "").strip()
                        real_name = self._extract_name(str(cu.get("real_name", "") or ""))
                        affected = await self._handle_identity_reveal(
                            project_id, char_name_map, alias_name, real_name, desc, chapter_index
                        )
                        changed.update(affected)
                        continue

                    character = str(cu.get("character", "") or "").strip()
                    matched = (character if character in char_name_map
                               else next((n for n in sorted_names if n in character), None))
                    if matched is None:
                        logger.warning(f"[fact_recorder] character_updates 角色未匹配: {character!r}")
                        continue
                    char_id = char_name_map[matched]["id"]

                    if utype == "成长":
                        add_character_growth(
                            character_id=char_id, stage=f"第{chapter_index}章",
                            description=desc[:200], source_chapter=chapter_index,
                        )
                        logger.info(f"[fact_recorder] 角色成长：'{matched}'")
                    else:  # 能力：直接追加 ability_limit（不再依赖 power 记录存在）
                        ability = str(cu.get("ability", "") or "").strip()
                        card = char_name_map[matched]
                        existing = str(card.get("ability_limit", "") or "").strip()
                        piece = f"{ability}: {desc[:80]}" if ability else desc[:100]
                        if piece not in existing:
                            new_limit = (f"{existing}；第{chapter_index}章 {piece}"[:500]
                                         if existing else f"第{chapter_index}章 {piece}"[:500])
                            add_setting_change(
                                project_id=project_id, chapter_number=chapter_index,
                                entity_type="character_card", entity_id=char_id,
                                change_type="update_ability",
                                before_data=json.dumps({"ability_limit": existing}, ensure_ascii=False),
                                after_data=json.dumps({"ability_limit": new_limit}, ensure_ascii=False),
                            )
                            update_character_card(char_id, ability_limit=new_limit)
                            card["ability_limit"] = new_limit
                            logger.info(f"[fact_recorder] 角色能力更新：'{matched}' + {ability or desc[:20]}")
                    changed.add(char_id)
                except Exception as e:
                    logger.warning(f"[fact_recorder] character_updates 处理失败: {cu} -> {e}")
        except Exception:
            pass
        return changed

    @staticmethod
    def _extract_name(text: str) -> str:
        """从文本中提取角色名：去除引号、括号及尾随说明。"""
        text = (text or "").strip().strip("「」『』\"'“”")
        text = re.split(r"[（(，,。]", text, 1)[0]
        return text.strip()

    @staticmethod
    def _net_item_changes(item_changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """同章净合并物品变化：按 (角色, 物品) 汇总获得/失去数量，抵消后输出净变化。

        - 获得 > 失去 → 一条"获得"（净数量）
        - 失去 > 获得 → 一条"失去"（净数量）
        - 相等或含"全部失去"（quantity=0）且获得存在 → 净 0，不改变账目（获得又全部失去）
        - 仅单方向 → 原样透传
        """
        net: Dict[Tuple[str, str], Dict[str, Any]] = {}
        order: List[Tuple[str, str]] = []
        for ic in item_changes:
            key = (str(ic.get("character", "") or "").strip(), str(ic.get("item", "") or "").strip())
            if not key[0] or not key[1]:
                continue
            action = str(ic.get("action", "") or "").strip()
            if action not in ("获得", "失去"):
                continue
            try:
                qty = int(float(ic.get("quantity") or 1))
            except (TypeError, ValueError):
                qty = 1
            if key not in net:
                net[key] = {"获得": 0, "失去": 0, "all_lost": False, "notes": []}
                order.append(key)
            if action == "失去" and qty <= 0:
                net[key]["all_lost"] = True
                net[key]["失去"] = max(net[key]["失去"], 0)
            else:
                net[key][action] += max(qty, 1)
            note = str(ic.get("note", "") or "").strip()
            if note:
                net[key]["notes"].append(note)

        out: List[Dict[str, Any]] = []
        for key in order:
            entry = net[key]
            gain, lose = entry["获得"], entry["失去"]
            note = "；".join(entry["notes"])
            if gain > 0 and (lose > 0 or entry["all_lost"]):
                # 获得又（部分/全部）失去：净抵消；全部失去 → 不改账
                net_qty = gain - lose
                if net_qty > 0 and not entry["all_lost"]:
                    out.append({"character": key[0], "item": key[1], "action": "获得",
                                "quantity": net_qty, "note": note})
                # 净 0 或全部失去：不产出
            elif gain > lose:
                out.append({"character": key[0], "item": key[1], "action": "获得",
                            "quantity": gain - lose, "note": note})
            elif lose > gain:
                out.append({"character": key[0], "item": key[1], "action": "失去",
                            "quantity": lose - gain, "note": note})
            # gain==lose==0 或仅失去0：不产出
        return out

    def _save_item_changes(
        self, script_id: int, chapter_index: int,
        item_changes: List[Dict[str, Any]]
    ) -> set:
        """落库结构化物品变化（item_changes 主通道）。

        action=获得 → upsert_character_item 累加；失去 → mark_character_item_lost 扣减
        （quantity=0 表示全部失去）。单条失败不阻断，记日志。
        返回受影响 char_id 集合（供调用方 RAG 增量重建）。
        """
        affected = set()
        try:
            from utils.logger import log_manager
            logger = log_manager.get_logger("fact_recorder")

            # 同章净合并：同一角色+同一物品 获得/失去 抵消，避免"获得又失去"造成
            # 账目虚增；净 0（含全部失去）不改账，仅保留流水日志。
            item_changes = self._net_item_changes(item_changes)

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return affected
            all_chars = get_character_cards_by_project(project["id"])
            char_name_map = {}
            for c in all_chars:
                name = c.get("name", "") or c.get("character_name", "")
                if name:
                    char_name_map[name] = c
            sorted_names = sorted(char_name_map.keys(), key=len, reverse=True)

            for ic in item_changes:
                try:
                    character = str(ic.get("character", "") or "").strip()
                    action = str(ic.get("action", "") or "").strip()
                    item = str(ic.get("item", "") or "").strip()
                    note = str(ic.get("note", "") or "").strip()
                    qty = ic.get("quantity")
                    if qty is None or (isinstance(qty, str) and not qty.strip()):
                        qty = 1  # 缺失默认 1（绝不默认全部失去）
                    else:
                        try:
                            qty = int(float(qty))
                        except (TypeError, ValueError):
                            qty = 1
                    if action not in ("获得", "失去") or not character or not item:
                        logger.warning(f"[fact_recorder] item_changes 非法项已跳过: {ic}")
                        continue
                    matched_name = (character if character in char_name_map
                                    else next((n for n in sorted_names if n in character), None))
                    if matched_name is None:
                        logger.warning(f"[fact_recorder] item_changes 角色未匹配: {character!r}")
                        continue
                    char_id = char_name_map[matched_name]["id"]
                    if action == "获得":
                        upsert_character_item(
                            char_id, item, source=note[:200], chapter=chapter_index,
                            note=f"第{chapter_index}章获得: {note[:100]}",
                            quantity=max(qty, 1),
                        )
                        logger.info(f"[fact_recorder] 角色 '{matched_name}' 获得物品 '{item}' x{max(qty, 1)}")
                    else:
                        ok = mark_character_item_lost(
                            char_id, item, chapter=chapter_index,
                            note=f"第{chapter_index}章: {note[:100]}",
                            quantity=max(qty, 0),
                        )
                        if not ok:
                            logger.warning(
                                f"[fact_recorder] 角色 '{matched_name}' 失去未持有物品 '{item}'"
                                f"（第{chapter_index}章），疑似正文不一致"
                            )
                            continue
                        logger.info(f"[fact_recorder] 角色 '{matched_name}' 失去物品 '{item}' x{qty}")
                    affected.add(char_id)
                except Exception as e:
                    logger.warning(f"[fact_recorder] item_changes 处理失败: {ic} -> {e}")
        except Exception:
            pass
        return affected

    async def _handle_identity_reveal(
        self, project_id: int, char_name_map: Dict[str, dict],
        alias_name: str, real_name: str, identity_desc: str, chapter_index: int
    ) -> List[int]:
        """处理身份揭露（结构化参数）：真名卡已存在则合并并删除旧卡，否则将化名卡改名。

        返回受影响的 char_id 列表（含已删除卡，供增量重建 RAG 索引时清理旧片段）。
        """
        try:
            from utils.logger import log_manager
            logger = log_manager.get_logger("fact_recorder")

            if not alias_name or not real_name or alias_name == real_name:
                return []
            if len(real_name) > 10:
                return []

            # 定位化名卡：精确匹配优先，回退子串匹配（处理"黑袍男人"→"神秘黑袍男人"等变体）
            old_card = char_name_map.get(alias_name)
            if old_card is None:
                for name, card in char_name_map.items():
                    if alias_name in name or name in alias_name:
                        old_card = card
                        break
            if old_card is None:
                return []
            # 仅处理 supporting/minor 类型的化名卡，避免误动核心角色卡
            if old_card.get("character_type") not in ("supporting", "minor"):
                return []

            old_id = old_card["id"]
            old_name = old_card.get("name", "")
            # 化名卡自身的曾用名一并传承（支持多次改名链）
            old_aliases = [a.strip() for a in re.split(r"[,，、]", old_card.get("alias", "") or "") if a.strip()]
            merged_alias_parts = [old_name] + old_aliases

            real_card = char_name_map.get(real_name)
            if real_card is not None and real_card.get("id") != old_id:
                # 真名卡已存在：合并曾用名与身份后删除化名卡，关系/成长/能力数据迁移至真名卡
                new_id = real_card["id"]
                existing_parts = [a.strip() for a in re.split(r"[,，、]", real_card.get("alias", "") or "") if a.strip()]
                alias_parts = []
                for p in existing_parts + merged_alias_parts:
                    if p and p != real_name and p not in alias_parts:
                        alias_parts.append(p)
                updates = {"alias": "、".join(alias_parts)}
                if identity_desc and not (real_card.get("identity") or "").strip():
                    updates["identity"] = identity_desc[:200]
                update_character_card(new_id, **updates)
                reassign_character_data(old_id, new_id)
                # 记录基础设定变更（回退用）：身份揭露合并（旧卡被删除，数据迁至真名卡）
                try:
                    add_setting_change(
                        project_id=project_id, chapter_number=chapter_index,
                        entity_type="character_card", entity_id=old_id,
                        change_type="reveal",
                        before_data=json.dumps({"name": old_name,
                                                "alias": old_card.get("alias", ""),
                                                "identity": old_card.get("identity", ""),
                                                "character_type": old_card.get("character_type", "")},
                                               ensure_ascii=False),
                        after_data=json.dumps({"merged_to": new_id, "alias": alias_parts,
                                               "identity": updates.get("identity", "")},
                                              ensure_ascii=False),
                    )
                except Exception:
                    pass
                delete_character_card(old_id)
                char_name_map.pop(old_name, None)
                logger.info(
                    f"[fact_recorder] 第{chapter_index}章身份揭露：化名卡 '{old_name}'(id={old_id}) "
                    f"已合并至 '{real_name}'(id={new_id})"
                )
                return [new_id, old_id]

            # 真名卡不存在：化名卡改名为真名，曾用名记入 alias 字段，补充揭露的身份信息
            new_identity = old_card.get("identity", "") or ""
            if identity_desc and identity_desc not in new_identity:
                new_identity = (new_identity + "；" + identity_desc)[:500] if new_identity else identity_desc[:200]
            alias_parts = []
            for p in merged_alias_parts:
                if p and p != real_name and p not in alias_parts:
                    alias_parts.append(p)
            new_alias = "、".join(alias_parts)
            # 记录基础设定变更（回退用）：身份揭露改名
            try:
                add_setting_change(
                    project_id=project_id, chapter_number=chapter_index,
                    entity_type="character_card", entity_id=old_id,
                    change_type="reveal",
                    before_data=json.dumps({"name": old_name,
                                            "alias": old_card.get("alias", ""),
                                            "identity": old_card.get("identity", ""),
                                            "character_type": old_card.get("character_type", "")},
                                           ensure_ascii=False),
                    after_data=json.dumps({"name": real_name, "alias": new_alias,
                                           "identity": new_identity},
                                          ensure_ascii=False),
                )
            except Exception:
                pass
            update_character_card(old_id, name=real_name, alias=new_alias, identity=new_identity)
            # 同步更新内存映射，保证同批次后续事实能命中真名
            char_name_map.pop(old_name, None)
            old_card.update({"name": real_name, "alias": new_alias, "identity": new_identity})
            char_name_map[real_name] = old_card
            logger.info(
                f"[fact_recorder] 第{chapter_index}章身份揭露：角色卡 '{old_name}'(id={old_id}) "
                f"已改名为 '{real_name}'，曾用名保留在 alias 字段"
            )
            return [old_id]
        except Exception:
            return []