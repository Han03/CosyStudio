"""执行器：卷纲规划执行器。

参考webnovel-writer的webnovel-plan SKILL，实现完整的卷纲规划流程。
流程包括：
1. 加载项目数据并确认前置条件
2. 补齐设定基线
3. 选择目标卷并确认范围
4. 生成卷节拍表
5. 生成卷时间线表
6. 生成卷纲骨架
7. 批量生成章纲
8. 验证、保存并更新状态
"""

import os
import json
from typing import Dict, Any, Optional
from ..base_executor import BaseExecutor, ExecutorResult
from core.model_executor import get_model_executor
from utils.llm_json_parser import parse_llm_json
from webnovel.repositories import (
    get_webnovel_project_by_script, get_character_cards_by_project,
    get_volume_outlines_by_project, get_golden_finger_by_project,
    get_power_system_by_project, get_worldview_by_project,
    get_villain_by_project, get_idea_bank_by_project,
    add_volume_outline, add_volume_crisis, update_volume_outline,
    add_timeline, add_timeline_chapter, add_timeline_countdown,
    add_chapter_plan, get_chapter_plans_by_volume,
    update_webnovel_state, get_webnovel_state_by_project,
    update_worldview, update_power_system, update_character_card,
    update_villain, add_worldview_faction, add_worldview_history,
    get_worldview_factions, get_worldview_history,
    add_power_level, add_character_growth, add_villain_hierarchy,
    add_open_loop, add_foreshadow,
    get_character_group_by_project, get_character_group_members
)


class PlanExecutor(BaseExecutor):
    """卷纲规划执行器。"""

    step_name = "plan_executor"
    step_description = "卷纲规划"
    step_weight = 15

    def _dict_to_obj(self, d: Dict) -> Any:
        """将dict转换为对象，支持属性访问，缺失属性返回空字符串。"""
        class Obj:
            def __init__(self, data):
                for k, v in data.items():
                    if isinstance(v, dict):
                        setattr(self, k, Obj(v))
                    else:
                        setattr(self, k, v)
            
            def __getattr__(self, name):
                return ""
        
        return Obj(d)
    
    async def _call_llm(self, prompt_name: str, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """调用LLM生成数据。"""
        from utils.logger import logger
        
        executor = get_model_executor()
        prompt_data = self._load_prompt(prompt_name)
        
        if not prompt_data["user_prompt"]:
            logger.error(f"[plan_executor] prompt加载失败: {prompt_name}")
            return {}
        
        try:
            obj_context = {k: self._dict_to_obj(v) if isinstance(v, dict) else v for k, v in context_data.items()}
            user_prompt = prompt_data["user_prompt"].format(**obj_context)
            logger.info(f"[plan_executor] 调用LLM生成 {prompt_name}，prompt长度: {len(user_prompt)}")

            project_id = 0
            try:
                from webnovel.repositories import get_webnovel_project_by_script
                _proj = get_webnovel_project_by_script(self.script_id)
                if _proj:
                    project_id = _proj.get("id", 0)
            except Exception:
                pass

            import time as _time
            _call_start = _time.time()

            result = await executor.execute_text_chat(
                prompt=user_prompt,
                system_prompt=prompt_data["system_prompt"],
                max_tokens=8000,
                script_id=self.script_id,
                project_id=project_id,
                executor_name="plan_executor",
                prompt_name=prompt_name,
            )
            _latency_ms = int((_time.time() - _call_start) * 1000)

            content = result.get("content", "") if result else ""
            content = content.strip()
            logger.info(f"[plan_executor] LLM返回内容长度: {len(content)}")

            json_result = parse_llm_json(
                content,
                script_id=self.script_id,
                project_id=project_id,
                executor_name="plan_executor",
                prompt_name=prompt_name,
                model_name=result.get("model_name", "") if isinstance(result, dict) else "",
                system_prompt=prompt_data["system_prompt"],
                user_prompt=user_prompt,
                input_tokens=result.get("input_tokens", 0) if isinstance(result, dict) else 0,
                output_tokens=result.get("output_tokens", 0) if isinstance(result, dict) else 0,
                latency_ms=_latency_ms,
            )
            if json_result:
                logger.info(f"[plan_executor] JSON解析成功，键: {list(json_result.keys())}")
                return json_result

            logger.error(f"[plan_executor] JSON解析失败，内容前500字符:\n{content[:500]}")
            logger.error(f"[plan_executor] JSON解析失败，内容后500字符:\n{content[-500:]}")
            logger.error(f"[plan_executor] JSON解析失败，完整内容长度: {len(content)}")

            import json
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"[plan_executor] 原生JSON解析错误: {e}")

            return {"error": "JSON解析失败"}
        except Exception as e:
            logger.error(f"[plan_executor] LLM调用异常: {str(e)}")
            return {"error": str(e)}

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行完整的卷纲规划流程。

        context 可选字段:
            volume_number: 目标卷号（默认1）
            regenerate_plans: True 表示为已有卷重新生成章节规划，跳过卷纲创建
        """
        try:
            script_id = self.script_id
            volume_number = context.get("volume_number", 1)
            regenerate_plans = context.get("regenerate_plans", False)

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="项目不存在，请先执行深度初始化",
                    step_summary="项目不存在"
                )
            project_id = project["id"]

            protagonists = get_character_cards_by_project(project_id, "protagonist")
            protagonist = protagonists[0] if protagonists else {}

            golden_finger = get_golden_finger_by_project(project_id)
            power_system = get_power_system_by_project(project_id)
            worldview = get_worldview_by_project(project_id)

            # 加载角色组数据
            char_group = get_character_group_by_project(project_id)
            char_group_members = []
            if char_group:
                char_group_members = get_character_group_members(char_group["id"])

            existing_outlines = get_volume_outlines_by_project(project_id)
            existing_max_volume = max([o["volume_number"] for o in existing_outlines]) if existing_outlines else 0

            # ── regenerate_plans 模式：为已有卷重新生成章节规划 ──
            if regenerate_plans:
                existing_vo = next(
                    (o for o in existing_outlines if o["volume_number"] == volume_number),
                    None
                )
                if not existing_vo:
                    return ExecutorResult(
                        success=False,
                        error_message=f"第{volume_number}卷不存在，无法重新生成章节规划",
                        step_summary="目标卷不存在"
                    )
                vo_id = existing_vo["id"]
                from utils.logger import log_manager
                _logger = log_manager.get_logger("plan_executor")
                _logger.info(f"[plan_executor] regenerate_plans 模式：为第{volume_number}卷重新生成章节规划，vo_id={vo_id}")

                chapter_plans = await self._generate_chapter_plans(
                    project, existing_vo, protagonist, volume_number,
                    char_group=char_group, char_group_members=char_group_members
                )
                if chapter_plans:
                    plan_count = self._save_chapter_plans(vo_id, chapter_plans)
                else:
                    plan_count = 0

                if plan_count == 0:
                    return ExecutorResult(
                        success=False,
                        error_message="重新生成章节规划失败，LLM未返回有效数据",
                        step_summary="章节规划生成失败"
                    )

                # 章节规划重新生成后，同步重新生成时间线
                timeline = await self._generate_timeline(
                    project, existing_vo, protagonist, volume_number,
                    chapter_plans=chapter_plans
                )
                tl_id = None
                if timeline:
                    # 删除旧时间线后重建
                    from webnovel.repositories import get_timelines_by_project
                    old_timelines = get_timelines_by_project(project_id)
                    tl_id = self._save_timeline(project_id, volume_number, timeline)

                summary = f"第{volume_number}卷章节规划已重新生成：{plan_count}章，时间线ID={tl_id}"
                return ExecutorResult(
                    success=True,
                    step_summary=summary,
                    output_data={
                        "volume_number": volume_number,
                        "volume_outline_id": vo_id,
                        "chapter_plans_count": plan_count,
                        "timeline_id": tl_id
                    }
                )

            # ── 正常模式：创建新卷并生成章节规划 ──
            if volume_number <= existing_max_volume:
                return ExecutorResult(
                    success=False,
                    error_message=f"第{volume_number}卷已存在，请选择更大的卷号",
                    step_summary="卷已存在"
                )

            prev_volume = None
            if volume_number > 1 and existing_max_volume >= volume_number - 1:
                prev_volume = next((o for o in existing_outlines if o["volume_number"] == volume_number - 1), None)

            start_chapter = prev_volume["chapter_end"] + 1 if prev_volume else 1
            end_chapter = start_chapter + 29

            result_data = {
                "volume_number": volume_number,
                "volume_outline_id": None,
                "timeline_id": None,
                "chapter_plans_count": 0
            }
            tl_id = None
            plan_count = 0

            volume_outline = await self._generate_volume_outline(
                project, protagonist, golden_finger, power_system, worldview,
                volume_number, start_chapter, end_chapter, prev_volume,
                char_group=char_group, char_group_members=char_group_members
            )
            if not volume_outline:
                return ExecutorResult(
                    success=False,
                    error_message="生成卷纲骨架失败",
                    step_summary="卷纲骨架生成失败"
                )
            vo_id = volume_outline["id"]
            result_data["volume_outline_id"] = vo_id

            beat_sheet = await self._generate_beat_sheet(
                project, volume_outline, protagonist, volume_number
            )
            if beat_sheet:
                self._update_volume_with_beat_sheet(vo_id, beat_sheet)

            chapter_plans = await self._generate_chapter_plans(
                project, volume_outline, protagonist, volume_number,
                char_group=char_group, char_group_members=char_group_members
            )
            if chapter_plans:
                plan_count = self._save_chapter_plans(vo_id, chapter_plans)
                result_data["chapter_plans_count"] = plan_count

            # 时间线在章节规划之后生成，基于实际章节内容设计时间锚点
            timeline = await self._generate_timeline(
                project, volume_outline, protagonist, volume_number,
                chapter_plans=chapter_plans
            )
            if timeline:
                tl_id = self._save_timeline(project_id, volume_number, timeline)
                result_data["timeline_id"] = tl_id

            self._writeback_settings(project_id, volume_outline, beat_sheet, chapter_plans)

            self._writeback_master_outline(project_id, vo_id, volume_number, volume_outline)

            self._update_project_state(project_id, volume_number, end_chapter)

            summary = f"第{volume_number}卷规划完成：卷纲ID={vo_id}，章纲{plan_count}章，时间线ID={tl_id}"
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data=result_data
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"卷纲规划执行失败: {str(e)}",
                step_summary="卷纲规划执行失败"
            )

    async def _generate_volume_outline(
        self, project: Dict, protagonist: Dict, golden_finger: Optional[Dict],
        power_system: Optional[Dict], worldview: Optional[Dict],
        volume_number: int, start_chapter: int, end_chapter: int,
        prev_volume: Optional[Dict],
        char_group: Optional[Dict] = None, char_group_members: Optional[list] = None
    ) -> Optional[Dict]:
        """生成卷纲骨架。"""
        from webnovel.repositories import get_timelines_by_project
        
        timelines = get_timelines_by_project(project["id"])
        current_timeline = ""
        if timelines:
            tl = timelines[0]
            timeline_parts = []
            if tl.get("time_base"):
                timeline_parts.append(f"时间基准: {tl['time_base']}")
            if tl.get("time_span"):
                timeline_parts.append(f"时间跨度: {tl['time_span']}")
            if tl.get("countdown_events"):
                timeline_parts.append(f"倒计时事件: {tl['countdown_events']}")
            current_timeline = "; ".join(timeline_parts)
        
        protagonist_power = {
            "realm": protagonist.get("current_power", "") or protagonist.get("power_level", "") or "未知"
        }

        master_volume = {
            "volume_name": f"第{volume_number}卷",
            "chapter_range": f"{start_chapter}-{end_chapter}",
            "core_conflict": project.get("core_conflict", "") or "主角成长与挑战",
            "volume_climax": ""
        }

        # 将角色组成员列表预格式化为字符串，供 prompt 模板使用
        cg_members_str = self._format_char_group_members(char_group, char_group_members, project.get("id", 0))

        # 预格式化势力文本，供世界观 section 使用
        factions_text = ""
        if worldview:
            factions = get_worldview_factions(worldview["id"])
            factions_text = "、".join([
                f.get("faction_name", "") + "(" + f.get("tier", "") + ")"
                for f in factions[:8] if f.get("faction_name")
            ])

        context = {
            "project": project,
            "protagonist": protagonist,
            "golden_finger": golden_finger or {},
            "world": worldview or {},
            "power_system": power_system or {},
            "volume_number": volume_number,
            "chapter_start": start_chapter,
            "chapter_end": end_chapter,
            "prev_volume": prev_volume or {},
            "master_volume": master_volume,
            "protagonist_power": protagonist_power,
            "current_timeline": current_timeline,
            "character_group": char_group or {},
            "character_group_members": cg_members_str,
            "factions_text": factions_text
        }

        volume_data = await self._call_llm("plan_volume_outline", context)
        if not volume_data or "error" in volume_data:
            return None

        vo_data = {
            "volume_number": volume_data.get("volume_number", volume_number),
            "volume_name": volume_data.get("volume_name", f"第{volume_number}卷"),
            "chapter_start": volume_data.get("chapter_start", start_chapter),
            "chapter_end": volume_data.get("chapter_end", end_chapter),
            "core_conflict": volume_data.get("core_conflict", ""),
            "volume_climax": volume_data.get("volume_climax", ""),
            "promise_description": volume_data.get("promise_description", ""),
            "promise_types": json.dumps(volume_data.get("promise_types", []), ensure_ascii=False),
            "catalyst_event": volume_data.get("catalyst_event", ""),
            "irreversible_change": volume_data.get("irreversible_change", ""),
            "protagonist_goal": volume_data.get("protagonist_goal", ""),
            "mid_reversal": volume_data.get("mid_reversal", ""),
            "reversal_insight": volume_data.get("reversal_insight", ""),
            "lowest_point_event": volume_data.get("lowest_point_event", ""),
            "lowest_point_cost": volume_data.get("lowest_point_cost", ""),
            "protagonist_choice": volume_data.get("protagonist_choice", ""),
            "payoff_items": json.dumps(volume_data.get("payoff_items", []), ensure_ascii=False),
            "new_hook": volume_data.get("new_hook", ""),
            "unresolved_issues": volume_data.get("unresolved_issues", "")
        }

        volume_outline = add_volume_outline(project["id"], **vo_data)

        crises = volume_data.get("crises", [])
        for crisis in crises:
            if isinstance(crisis, dict):
                add_volume_crisis(
                    volume_outline["id"],
                    crisis_order=crisis.get("crisis_order", 0),
                    crisis_event=crisis.get("crisis_event", ""),
                    cost_risk_upgrade=crisis.get("cost_risk_upgrade", ""),
                    result_change=crisis.get("result_change", "")
                )

        return volume_outline

    async def _generate_beat_sheet(
        self, project: Dict, volume_outline: Dict, protagonist: Dict, volume_number: int
    ) -> Optional[Dict]:
        """生成卷节拍表。"""
        context = {
            "project": project,
            "volume_outline": volume_outline,
            "protagonist": protagonist,
            "volume_number": volume_number
        }

        beat_data = await self._call_llm("plan_beat_sheet", context)
        if not beat_data or "error" in beat_data:
            return None

        return beat_data

    def _update_volume_with_beat_sheet(self, vo_id: int, beat_sheet: Dict):
        """用节拍表更新卷纲。"""
        updates = {}
        if beat_sheet.get("promise_description"):
            updates["promise_description"] = beat_sheet["promise_description"]
        if beat_sheet.get("promise_types"):
            updates["promise_types"] = json.dumps(beat_sheet["promise_types"], ensure_ascii=False)
        if beat_sheet.get("catalyst_event"):
            updates["catalyst_event"] = beat_sheet["catalyst_event"]
        if beat_sheet.get("irreversible_change"):
            updates["irreversible_change"] = beat_sheet["irreversible_change"]
        if beat_sheet.get("protagonist_goal"):
            updates["protagonist_goal"] = beat_sheet["protagonist_goal"]
        if beat_sheet.get("mid_reversal"):
            updates["mid_reversal"] = beat_sheet["mid_reversal"]
        if beat_sheet.get("reversal_insight"):
            updates["reversal_insight"] = beat_sheet["reversal_insight"]
        if beat_sheet.get("lowest_point_event"):
            updates["lowest_point_event"] = beat_sheet["lowest_point_event"]
        if beat_sheet.get("lowest_point_cost"):
            updates["lowest_point_cost"] = beat_sheet["lowest_point_cost"]
        if beat_sheet.get("protagonist_choice"):
            updates["protagonist_choice"] = beat_sheet["protagonist_choice"]
        if beat_sheet.get("payoff_items"):
            updates["payoff_items"] = json.dumps(beat_sheet["payoff_items"], ensure_ascii=False)
        if beat_sheet.get("new_hook"):
            updates["new_hook"] = beat_sheet["new_hook"]
        if beat_sheet.get("unresolved_issues"):
            updates["unresolved_issues"] = beat_sheet["unresolved_issues"]

        if updates:
            update_volume_outline(vo_id, **updates)

        crises = beat_sheet.get("crises", [])
        for crisis in crises:
            if isinstance(crisis, dict):
                add_volume_crisis(
                    vo_id,
                    crisis_order=crisis.get("crisis_order", 0),
                    crisis_event=crisis.get("crisis_event", ""),
                    cost_risk_upgrade=crisis.get("cost_risk_upgrade", ""),
                    result_change=crisis.get("result_change", "")
                )

    async def _generate_timeline(
        self, project: Dict, volume_outline: Dict, protagonist: Dict, volume_number: int,
        chapter_plans: Optional[Dict] = None
    ) -> Optional[Dict]:
        """生成卷时间线。基于章节规划内容设计时间锚点。"""
        # 将章节规划预格式化为文本，供 prompt 模板使用
        plans_list = chapter_plans.get("chapter_plans", []) if chapter_plans else []
        if plans_list:
            lines = []
            for plan in plans_list:
                if isinstance(plan, dict):
                    ch_idx = plan.get("chapter_index", "?")
                    title = plan.get("chapter_title", "")
                    summary = str(plan.get("summary", ""))[:60]
                    lines.append(f"第{ch_idx}章 {title}：{summary}")
            chapter_plans_text = "\n".join(lines)
        else:
            chapter_plans_text = "（暂无章节规划）"

        context = {
            "project": project,
            "volume_outline": volume_outline,
            "protagonist": protagonist,
            "volume_number": volume_number,
            "chapter_plans_text": chapter_plans_text
        }

        timeline_data = await self._call_llm("plan_timeline", context)
        if not timeline_data or "error" in timeline_data:
            return None

        return timeline_data

    def _save_timeline(self, project_id: int, volume_number: int, timeline: Dict) -> int:
        """保存时间线到数据库。"""
        tl_data = {
            "volume_number": volume_number,
            "time_base": timeline.get("time_base", ""),
            "time_span": timeline.get("time_span", ""),
            "countdown_events": json.dumps(timeline.get("countdown_events", []), ensure_ascii=False)
        }

        tl = add_timeline(project_id, **tl_data)
        tl_id = tl["id"]

        chapters = timeline.get("chapter_timeline", [])
        for chapter in chapters:
            if isinstance(chapter, dict):
                add_timeline_chapter(
                    tl_id,
                    chapter_number=chapter.get("chapter_number", 0),
                    time_anchor=chapter.get("time_anchor", ""),
                    chapter_duration=chapter.get("chapter_duration", ""),
                    interval_from_prev=chapter.get("interval_from_prev", ""),
                    countdown_status=chapter.get("countdown_status", ""),
                    notes=chapter.get("notes", "")
                )

        countdowns = timeline.get("countdown_tracking", [])
        for countdown in countdowns:
            if isinstance(countdown, dict):
                add_timeline_countdown(
                    tl_id,
                    event_name=countdown.get("event_name", ""),
                    start_countdown=countdown.get("start_countdown", ""),
                    # 初始化阶段强制覆写为"未触发"，避免 LLM 填入终态值
                    current_status="未触发",
                    trigger_chapter=countdown.get("trigger_chapter", 0),
                    result=countdown.get("result", "")
                )

        return tl_id

    # 每批生成的章节数上限（参考 webnovel-writer SKILL.md Step 7 批次规则）
    CHAPTER_BATCH_SIZE = 10

    async def _generate_chapter_plans(
        self, project: Dict, volume_outline: Dict, protagonist: Dict, volume_number: int,
        start_chapter: Optional[int] = None, end_chapter: Optional[int] = None,
        char_group: Optional[Dict] = None, char_group_members: Optional[list] = None
    ) -> Optional[Dict]:
        """分批生成章纲。

        按 CHAPTER_BATCH_SIZE（默认 10）将卷纲章节范围拆分为多个批次，
        每批独立调用 LLM 生成，前序批次的摘要注入后续批次上下文，
        最终合并为完整的 chapter_plans 列表。

        Args:
            start_chapter: 可选，指定生成起始章节号（1-based）。
            end_chapter: 可选，指定生成结束章节号（1-based）。
            指定范围不能超出卷纲自身的 chapter_start ~ chapter_end。
        """
        from utils.logger import logger

        vo_chapter_start = int(volume_outline.get("chapter_start", 1))
        vo_chapter_end = int(volume_outline.get("chapter_end", vo_chapter_start + 29))

        # 确定实际生成范围：优先使用指定参数，否则使用卷纲全范围
        if start_chapter is not None:
            chapter_start = max(int(start_chapter), vo_chapter_start)
        else:
            chapter_start = vo_chapter_start

        if end_chapter is not None:
            chapter_end = min(int(end_chapter), vo_chapter_end)
        else:
            chapter_end = vo_chapter_end

        # 安全检查
        if chapter_start > chapter_end:
            logger.error(
                f"[plan_executor] 无效的章节范围: {chapter_start}-{chapter_end}，"
                f"卷纲范围: {vo_chapter_start}-{vo_chapter_end}"
            )
            return None

        total_chapters = chapter_end - chapter_start + 1
        batch_size = self.CHAPTER_BATCH_SIZE

        # 计算批次列表: [(start, end), ...]
        batches = []
        for i in range(chapter_start, chapter_end + 1, batch_size):
            b_end = min(i + batch_size - 1, chapter_end)
            batches.append((i, b_end))
        total_batches = len(batches)

        logger.info(
            f"[plan_executor] 分批生成章纲：卷{volume_number}，"
            f"章节{chapter_start}-{chapter_end}，共{total_chapters}章，"
            f"分{total_batches}批（每批{batch_size}章）"
        )

        all_plans = []
        batch_summaries = []  # 每批的摘要，供后续批次参考

        # 将角色组成员列表预格式化为字符串，供 prompt 模板使用
        cg_members_str = self._format_char_group_members(char_group, char_group_members, project.get("id", 0))

        # 主角字段映射：DB 字段名 (true_desire/personality_flaw) → prompt 模板期望的键名 (desire/flaw)
        protagonist_ctx = dict(protagonist) if protagonist else {}
        if not protagonist_ctx.get("desire") and protagonist_ctx.get("true_desire"):
            protagonist_ctx["desire"] = protagonist_ctx["true_desire"]
        if not protagonist_ctx.get("flaw") and protagonist_ctx.get("personality_flaw"):
            protagonist_ctx["flaw"] = protagonist_ctx["personality_flaw"]

        # 危机链数据：从独立表查询并格式化为文本，注入 volume_outline context
        vo_ctx = dict(volume_outline)
        if not vo_ctx.get("crises"):
            from webnovel.repositories import get_volume_crises
            crises_list = get_volume_crises(vo_ctx.get("id", 0))
            if crises_list:
                crisis_parts = []
                for c in crises_list:
                    line = c.get("crisis_event", "")
                    if c.get("cost_risk_upgrade"):
                        line += f"（代价/升级：{c['cost_risk_upgrade']}）"
                    if c.get("result_change"):
                        line += f"→ {c['result_change']}"
                    if line:
                        crisis_parts.append(line)
                vo_ctx["crises"] = "；".join(crisis_parts) if crisis_parts else ""
            else:
                vo_ctx["crises"] = ""

        for batch_idx, (b_start, b_end) in enumerate(batches, start=1):
            b_size = b_end - b_start + 1

            # 构建前序批次摘要
            if batch_summaries:
                previous_batch_summary = "\n".join(batch_summaries[-3:])
            else:
                previous_batch_summary = "（首批，无前序摘要）"

            context = {
                "project": project,
                "volume_outline": vo_ctx,
                "protagonist": protagonist_ctx,
                "volume_number": volume_number,
                "batch_chapter_start": b_start,
                "batch_chapter_end": b_end,
                "batch_index": batch_idx,
                "total_batches": total_batches,
                "batch_size": b_size,
                "previous_batch_summary": previous_batch_summary,
                "character_group": char_group or {},
                "character_group_members": cg_members_str
            }

            logger.info(
                f"[plan_executor] 正在生成第{batch_idx}/{total_batches}批："
                f"第{b_start}-{b_end}章"
            )

            batch_data = await self._call_llm("plan_chapter_plan", context)
            if not batch_data or "error" in batch_data:
                logger.error(
                    f"[plan_executor] 第{batch_idx}批章纲生成失败: {batch_data}"
                )
                continue

            batch_plans = batch_data.get("chapter_plans", [])
            if not batch_plans:
                # 尝试修复：单个章纲对象
                if isinstance(batch_data, dict) and "chapter_index" in batch_data:
                    batch_plans = [batch_data]
                else:
                    logger.error(
                        f"[plan_executor] 第{batch_idx}批缺少 chapter_plans 键"
                    )
                    continue

            logger.info(
                f"[plan_executor] 第{batch_idx}批生成成功：{len(batch_plans)}章"
            )
            all_plans.extend(batch_plans)

            # 构建本批摘要供后续批次参考（取每章标题+概要的前 80 字）
            summary_lines = []
            for plan in batch_plans:
                if isinstance(plan, dict):
                    ch_idx = plan.get("chapter_index", "?")
                    title = plan.get("chapter_title", "")
                    summary = plan.get("summary", "")[:80]
                    summary_lines.append(f"第{ch_idx}章 {title}：{summary}")
            if summary_lines:
                batch_summaries.append(
                    f"【第{batch_idx}批（第{b_start}-{b_end}章）摘要】\n"
                    + "\n".join(summary_lines)
                )

        if not all_plans:
            logger.error("[plan_executor] 所有批次章纲生成均失败")
            return None

        logger.info(
            f"[plan_executor] 分批章纲生成完成：共{len(all_plans)}章"
        )
        return {"chapter_plans": all_plans}

    def _save_chapter_plans(self, vo_id: int, chapter_data: Dict) -> int:
        """保存章纲到数据库。"""
        chapter_plans = chapter_data.get("chapter_plans", [])
        count = 0

        for plan in chapter_plans:
            if not isinstance(plan, dict):
                continue

            add_chapter_plan(
                vo_id,
                chapter_index=plan.get("chapter_index", 0),
                chapter_title=plan.get("chapter_title", ""),
                summary=plan.get("summary", ""),
                key_events=plan.get("key_events", []),
                expected_cool_points=plan.get("expected_cool_points", ""),
                foreshadowing=plan.get("foreshadowing", ""),
                chapter_hook=plan.get("chapter_hook", ""),
                chapter_goal=plan.get("chapter_goal", ""),
                resistance=plan.get("resistance", ""),
                cost=plan.get("cost", ""),
                time_anchor=plan.get("time_anchor", ""),
                chapter_duration=plan.get("chapter_duration", ""),
                interval_from_prev=plan.get("interval_from_prev", ""),
                countdown_status=plan.get("countdown_status", ""),
                strand=plan.get("strand", ""),
                villain_tier=plan.get("villain_tier", ""),
                perspective=plan.get("perspective", ""),
                key_entities=plan.get("key_entities", ""),
                chapter_change=plan.get("chapter_change", ""),
                unresolved_questions=plan.get("unresolved_questions", ""),
                cbn=plan.get("cbn", ""),
                cpns=plan.get("cpns", []),
                cen=plan.get("cen", ""),
                must_cover_nodes=plan.get("must_cover_nodes", []),
                forbidden_zones=plan.get("forbidden_zones", [])
            )
            count += 1

        return count

    def _update_project_state(self, project_id: int, volume_number: int, end_chapter: int):
        """更新项目状态。"""
        state = get_webnovel_state_by_project(project_id)
        if state:
            volumes_completed = state.get("volumes_completed", "")
            if volumes_completed:
                volumes = json.loads(volumes_completed) if volumes_completed else []
            else:
                volumes = []
            
            volumes.append(volume_number)
            update_webnovel_state(
                project_id,
                volumes_completed=json.dumps(volumes, ensure_ascii=False),
                current_chapter=end_chapter,
                current_volume=volume_number
            )

    def _writeback_settings(
        self, project_id: int, volume_outline: Dict, beat_sheet: Dict, chapter_plans: Dict
    ):
        """把新增设定写回现有设定集。"""
        worldview = get_worldview_by_project(project_id)
        power_system = get_power_system_by_project(project_id)
        protagonists = get_character_cards_by_project(project_id, "protagonist")
        protagonist = protagonists[0] if protagonists else {}
        villain = get_villain_by_project(project_id)

        new_factions = []
        new_locations = []
        new_rules = []
        new_characters = []
        new_powers = []

        if beat_sheet:
            crisis_events = beat_sheet.get("crises", [])
            for crisis in crisis_events:
                if isinstance(crisis, dict):
                    event = crisis.get("crisis_event", "")
                    if "势力" in event or "宗门" in event or "家族" in event:
                        new_factions.append(event)

        if chapter_plans:
            plans = chapter_plans.get("chapter_plans", [])
            for plan in plans:
                if not isinstance(plan, dict):
                    continue

                key_entities = plan.get("key_entities", "")
                if key_entities:
                    if "势力" in key_entities or "宗门" in key_entities:
                        new_factions.append(key_entities)
                    if "地点" in key_entities or "城池" in key_entities or "秘境" in key_entities:
                        new_locations.append(key_entities)

                foreshadowing = plan.get("foreshadowing", "")
                if foreshadowing:
                    new_rules.append(foreshadowing)

                chapter_change = plan.get("chapter_change", "")
                if chapter_change:
                    if "突破" in chapter_change or "领悟" in chapter_change or "能力" in chapter_change:
                        new_powers.append(chapter_change)

        if new_factions and worldview:
            existing_factions = get_worldview_factions(worldview["id"])
            existing_names = {f.get("faction_name", "") for f in existing_factions}
            for faction in new_factions:
                if faction not in existing_names:
                    new_faction_item = {"faction_name": faction, "tier": "卷级新增", "relation": "中立", "hierarchy": ""}
                    add_worldview_faction(worldview["id"], **new_faction_item)

        if new_locations and worldview:
            existing_locations = self._parse_json_field(worldview.get("important_locations", ""))
            for location in new_locations:
                if location not in str(existing_locations):
                    existing_locations.append(location)
                    update_worldview(worldview["id"], important_locations=json.dumps(existing_locations, ensure_ascii=False))

        if new_rules and worldview:
            existing_rules = worldview.get("social_common_sense", "")
            for rule in new_rules[:3]:
                if rule not in existing_rules:
                    existing_rules += "\n- " + rule
                    update_worldview(worldview["id"], social_common_sense=existing_rules)

        if new_powers and power_system:
            existing_powers = self._parse_json_field(power_system.get("resource_types", ""))
            for power in new_powers[:3]:
                if power not in str(existing_powers):
                    existing_powers.append(power)
                    update_power_system(power_system["id"], resource_types=json.dumps(existing_powers, ensure_ascii=False))

        if protagonist and volume_outline:
            growth_desc = volume_outline.get("protagonist_goal", "")
            if growth_desc:
                stage = f"第{volume_outline['volume_number']}卷目标"
                add_character_growth(protagonist["id"], stage, growth_desc)

        if villain and volume_outline:
            new_villain_info = volume_outline.get("core_conflict", "")
            if new_villain_info and "反派" in new_villain_info:
                tier_info = {"tier": "卷级反派", "villain_name": new_villain_info[:20], "stage": f"第{volume_outline['volume_number']}卷", "goal": "阻碍主角", "protagonist_relation": "敌对"}
                add_villain_hierarchy(villain["id"], **tier_info)

    def _writeback_master_outline(self, project_id: int, vo_id: int, volume_number: int, volume_outline: Dict):
        """总纲写回：将锚点、铺垫碎片、开放线索写入数据库。"""
        # 1. 下一卷核心冲突锚点 → webnovel_volume_outline.core_conflict_anchor
        core_conflict_anchor = volume_outline.get("new_hook", "") or "待规划"
        update_volume_outline(vo_id, core_conflict_anchor=core_conflict_anchor)

        # 2. 铺垫碎片 → webnovel_foreshadow
        key_foreshadowing_raw = volume_outline.get("key_foreshadowing", "")
        if isinstance(key_foreshadowing_raw, str):
            key_foreshadowing = self._parse_json_field(key_foreshadowing_raw)
            if not key_foreshadowing and key_foreshadowing_raw:
                key_foreshadowing = [key_foreshadowing_raw]
        else:
            key_foreshadowing = key_foreshadowing_raw if isinstance(key_foreshadowing_raw, list) else []

        for item in key_foreshadowing[:5]:
            add_foreshadow(
                project_id=project_id,
                volume_outline_id=vo_id,
                content=item if isinstance(item, str) else str(item),
                buried_chapter=volume_outline.get("chapter_start", 0),
                payoff_chapter=0,
                level="卷级"
            )

        # 3. 开放线索 → webnovel_open_loops
        unresolved = volume_outline.get("unresolved_issues", "")
        if unresolved:
            add_open_loop(
                project_id=project_id,
                content=unresolved,
                tier="持续开放环",
                planted_chapter=volume_outline.get("chapter_end", 0),
                target_chapter=0
            )

    def _parse_json_field(self, field: str) -> Any:
        """解析JSON字段。"""
        if not field:
            return []
        try:
            return json.loads(field)
        except json.JSONDecodeError:
            return []

    def _format_char_group_members(
        self, char_group: Optional[Dict], char_group_members: Optional[list],
        project_id: int = 0
    ) -> str:
        """将角色组成员列表格式化为可读字符串，供 prompt 模板使用。

        通过 character_id 关联角色卡表获取姓名，使团队成员信息包含名称。
        """
        if not char_group or not char_group_members:
            return "无"

        # 批量获取成员对应的角色卡姓名
        name_map = {}
        if project_id:
            from webnovel.repositories import get_character_card
            for m in char_group_members:
                if isinstance(m, dict) and m.get("character_id"):
                    card = get_character_card(project_id, m["character_id"])
                    if card and card.get("name"):
                        name_map[m["character_id"]] = card["name"]

        parts = []
        for m in char_group_members[:8]:
            if not isinstance(m, dict):
                continue
            char_name = name_map.get(m.get("character_id"), "")
            role = m.get("role", "")
            ability = m.get("key_ability", "")
            flaw = m.get("key_flaw", "")
            contribution = m.get("main_line_contribution", "")

            # 姓名 + 角色定位作为开头
            if char_name and role:
                display = f"{char_name}({role})"
            elif char_name:
                display = char_name
            elif role:
                display = role
            else:
                display = "成员"

            line_parts = [display]
            if ability:
                line_parts.append(f"能力:{ability}")
            if flaw:
                line_parts.append(f"缺陷:{flaw}")
            if contribution:
                line_parts.append(f"贡献:{contribution[:40]}")
            parts.append("，".join(line_parts))
        return "；".join(parts) if parts else "无"
