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
    get_chapter_meta, update_chapter_meta, upsert_character_state,
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

            characters_text = []
            for c in inventory.get('characters', []):
                if isinstance(c, dict):
                    if c.get('name'):
                        characters_text.append(c['name'])
                    elif c.get('type'):
                        characters_text.append(c['type'])
                    else:
                        characters_text.append("角色")

            # 从 .md 文件加载 prompt 模板
            prompt_data = self._load_prompt("fact_record")
            # 事实提取需要覆盖全章内容，截断过短会遗漏核心事件（如升级突破、物品消耗）。
            # 成品章节 3000-5000 字，取前 4000 字可覆盖大部分关键事件。
            chapter_content = polished_content[:4000] if len(polished_content) > 4000 else polished_content

            from core.model_executor import get_model_executor
            executor = get_model_executor()

            project = get_webnovel_project_by_script(script_id)
            project_id = project["id"] if project else 0

            # 前一章时间轴（基于原文的章节时间轴证据，供 chapter_timeline 块衔接）
            prev_timeline = self._build_prev_timeline_text(project_id, self.chapter_index)

            prompt = prompt_data["user_prompt"].format(
                chapter_content=chapter_content,
                world_settings=json.dumps(world_settings_text, ensure_ascii=False),
                characters=json.dumps(characters_text, ensure_ascii=False),
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

            # 2.5 角色卡 RAG 增量重建（物品/身份/改名涉及的角色）
            if rag_affected and project_id:
                try:
                    from webnovel.services.webnovel_service import WebnovelService
                    await WebnovelService().reindex_character_cards(project_id, list(rag_affected))
                except Exception:
                    pass  # 索引失败不阻断主流程

            # 2. 爽点落库（含标签补充+去重）+ 3. 结尾钩子 + 4. 角色状态 + 5. 世界观设定
            if project_id:
                await self._save_cool_points(project_id, self.chapter_index, cool_points, polished_content)
                await self._save_hook(project_id, self.chapter_index, hook)
                await self._save_character_states(project_id, self.chapter_index, character_states)
                await self._save_world_settings(project_id, self.chapter_index, world_settings)
                # 5.5 章节时间轴（基于原文补写 webnovel_timeline_chapter）
                await self._save_chapter_timeline(project_id, self.chapter_index, chapter_timeline)
            # 跨章节事件（开放悬念/倒计时 提取+回收）由 apply 后处理中独立执行器处理

            # 6. 检测并创建新角色
            await self._create_new_characters(script_id, polished_content, inventory)

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
        """构建前一章时间轴文本（当前章所属卷时间轴中，本章之前的最近 3 章锚点）。"""
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
            chapters = get_timeline_chapters(tl["id"]) or []
            prev = [c for c in chapters if (c.get("chapter_number") or 0) < chapter_index][-3:]
            if not prev:
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
            upsert_timeline_chapter(
                timeline_id=tl["id"],
                chapter_number=chapter_index,
                time_anchor=chapter_timeline.get("time_anchor", ""),
                chapter_duration=chapter_timeline.get("chapter_duration", ""),
                interval_from_prev=chapter_timeline.get("interval_from_prev", ""),
                countdown_status=chapter_timeline.get("countdown_status", ""),
                notes=chapter_timeline.get("notes", ""),
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
        """落库结尾钩子到 chapter_meta（不回写 hook_type，该字段由调用方标记状态）。"""
        try:
            if not hook or not hook.get("hook_content"):
                return
            chapter_meta = get_chapter_meta(project_id, chapter_index)
            if not chapter_meta:
                return
            update_chapter_meta(
                chapter_meta["id"],
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
            for s in states:
                cid = s.get("character_id")
                if not cid:
                    continue
                upsert_character_state(
                    project_id=project_id,
                    character_id=cid,
                    character_name=s.get("character_name", ""),
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

    async def _create_new_characters(
        self, script_id: int, draft_content: str, inventory: Dict[str, Any]
    ):
        """检测正文中的新角色并自动创建角色卡。"""
        try:
            project = get_webnovel_project_by_script(script_id)
            if not project:
                return
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
            existing_chars_text = json.dumps(
                [{"name": c.get("name", "") or c.get("character_name", ""),
                  "alias": c.get("alias", ""),
                  "identity": c.get("identity", ""),
                  "type": c.get("character_type", "")}
                 for c in existing_chars if (c.get("name", "") or c.get("character_name", ""))],
                ensure_ascii=False
            ) if existing_chars else "[]"

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
                return

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
                return

            char_data = parse_llm_json(
                content,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="create_new_characters",
            )

            if not char_data or "new_characters" not in char_data:
                return

            # 创建新角色卡（收集新卡 id 用于增量索引）
            created = []
            created_ids = []
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
                created.append(name)
                if new_card and new_card.get("id"):
                    created_ids.append(new_card["id"])
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

            # 写作中自动创建的角色卡即时写入 RAG，无需等待全量重建索引
            if created_ids:
                try:
                    from webnovel.services.webnovel_service import WebnovelService
                    await WebnovelService().reindex_character_cards(project_id, created_ids)
                except Exception:
                    pass  # 索引失败不阻断主流程

            if created:
                from utils.logger import log_manager
                logger = log_manager.get_logger("fact_recorder")
                logger.info(f"[fact_recorder] 自动创建新角色卡: {created}")

        except Exception:
            pass

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