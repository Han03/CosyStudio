"""执行器：跨章节事件处理器。

提取器 + 回收器一体：基于本章原文，一次 LLM 调用同时完成
  - 提取：本章新出现的开放悬念（webnovel_open_loops）、倒计时事件（webnovel_timeline_countdown）
  - 回收：活跃开放悬念被解决、活跃倒计时事件被触发/取消

执行时机：apply 后处理（fact_recorder 之后）。失败降级不阻断 apply。
以后所有跨章节内容（悬念/倒计时）统一通过本机制提取与回收。
"""

import json
from typing import Any, Dict, List, Optional
from utils.logger import log_manager
from ..base_executor import BaseExecutor, ExecutorResult
from core.model_executor import get_model_executor
from utils.llm_json_parser import parse_llm_json
from webnovel.repositories import (
    get_webnovel_project_by_script,
    get_volume_outlines_by_project,
    get_timelines_by_project,
    get_timeline_countdowns, add_timeline_countdown, update_timeline_countdown,
    add_open_loop, get_active_open_loops, get_open_loops_by_project,
    update_open_loop_resolved, update_open_loop_urgency,
)

_logger = log_manager.get_logger("cross_chapter_event")


class CrossChapterEventProcessorExecutor(BaseExecutor):
    """跨章节事件处理器（提取 + 回收一体）。"""

    step_name = "cross_chapter_event"
    step_description = "跨章节事件处理"
    step_weight = 10

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行跨章节事件提取与回收。失败降级不阻断 apply。"""
        try:
            script_id = self.script_id
            chapter_index = self.chapter_index

            content = (
                context.get("polished_content", "")
                or context.get("filtered_content", "")
                or context.get("draft_content", "")
            )
            if not content:
                return ExecutorResult(
                    success=True,
                    step_summary="章节内容为空，跳过跨章节事件处理",
                    output_data={},
                )

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=True,
                    step_summary="未找到webnovel项目，跳过跨章节事件处理",
                    output_data={},
                )
            project_id = project["id"]

            # 1. 加载活跃开放悬念（序号化）
            active_loops = get_active_open_loops(project_id) or []
            loops_text = "\n".join([
                f"[{i}] [{loop.get('tier', '')}] {loop.get('content', '')} "
                f"(第{loop.get('planted_chapter', 0)}章埋下)"
                for i, loop in enumerate(active_loops)
            ]) if active_loops else "（无活跃开放悬念）"

            # 2. 加载活跃倒计时事件（当前卷，未触发/进行中）
            active_countdowns, countdowns_text = self._load_active_countdowns(project_id, chapter_index)

            # 3. LLM 一次判断：新提取 + 回收
            data = await self._call_llm(project_id, content, loops_text, countdowns_text)

            # 4. 提取落库：新开放悬念（LLM 提取 + 跨章去重）
            new_loops = [l for l in (data.get("new_open_loops") or [])
                         if isinstance(l, dict) and l.get("content")]
            new_loops = self._deduplicate_against_existing(new_loops, project_id)
            planted_count = 0
            for loop in new_loops:
                saved = add_open_loop(
                    project_id=project_id,
                    content=loop["content"],
                    tier=loop.get("tier", ""),
                    planted_chapter=chapter_index,
                    target_chapter=loop.get("target_chapter", 0),
                    evidence=loop.get("evidence", ""),
                )
                if saved and saved.get("id"):
                    planted_count += 1

            # 5. 提取落库：新倒计时事件（挂当前卷 timeline_id）
            new_countdowns = [c for c in (data.get("new_countdowns") or [])
                              if isinstance(c, dict) and c.get("event_name")]
            countdown_count = self._save_new_countdowns(project_id, chapter_index, new_countdowns)

            # 6. 回收：开放悬念被解决
            resolved_loop_count = 0
            resolved_loop_indices = data.get("resolved_open_loop_indices") or []
            for idx in resolved_loop_indices:
                if isinstance(idx, int) and 0 <= idx < len(active_loops):
                    update_open_loop_resolved(active_loops[idx]["id"], chapter_index)
                    resolved_loop_count += 1
            update_open_loop_urgency(project_id, chapter_index)

            # 7. 触发：倒计时事件被兑现/取消
            resolved_countdown_count = 0
            resolved_countdown_indices = data.get("resolved_countdown_indices") or []
            for idx in resolved_countdown_indices:
                if isinstance(idx, int) and 0 <= idx < len(active_countdowns):
                    update_timeline_countdown(
                        active_countdowns[idx]["id"],
                        current_status="已触发",
                        trigger_chapter=chapter_index,
                        result="",
                    )
                    resolved_countdown_count += 1

            summary = (f"跨章节事件处理完成：新埋{planted_count}个悬念，"
                       f"回收{resolved_loop_count}个悬念，"
                       f"新倒计时{countdown_count}个，触发{resolved_countdown_count}个倒计时")
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "open_loops_planted": planted_count,
                    "open_loops_resolved": resolved_loop_count,
                    "countdowns_added": countdown_count,
                    "countdowns_resolved": resolved_countdown_count,
                },
            )
        except Exception as e:
            _logger.warning(f"[CrossChapterEvent] 执行失败（不阻断apply）: {e}")
            return ExecutorResult(
                success=False,
                error_message=f"跨章节事件处理失败: {str(e)}",
                step_summary="跨章节事件处理失败",
            )

    # ── 活跃倒计时加载 ────────────────────────────────────

    def _load_active_countdowns(self, project_id: int, chapter_index: int):
        """加载当前卷活跃倒计时事件（未触发/进行中），返回 (列表, 文本)。"""
        try:
            volume_outlines = get_volume_outlines_by_project(project_id)
            cur_vol = None
            for vo in volume_outlines:
                if vo.get("chapter_start", 1) <= chapter_index <= vo.get("chapter_end", 9999):
                    cur_vol = vo
                    break
            timelines = get_timelines_by_project(project_id)
            tl = None
            if cur_vol:
                tl = next(
                    (t for t in timelines if t.get("volume_number") == cur_vol.get("volume_number")),
                    None,
                )
            if not tl:
                return [], "（当前卷无倒计时事件）"
            countdowns = get_timeline_countdowns(tl["id"]) or []
            active = [c for c in countdowns if c.get("current_status", "") in ("", "未触发", "进行中")]
            text = "\n".join([
                f"[{i}] {c.get('event_name', '')}（倒计时：{c.get('start_countdown', '')}）"
                for i, c in enumerate(active)
            ]) if active else "（无活跃倒计时事件）"
            return active, text
        except Exception:
            return [], "（无活跃倒计时事件）"

    # ── 新倒计时落库 ──────────────────────────────────────

    def _save_new_countdowns(self, project_id: int, chapter_index: int,
                             new_countdowns: List[Dict]) -> int:
        """新倒计时事件落库（挂当前卷 timeline_id）。无主记录时跳过。"""
        if not new_countdowns:
            return 0
        try:
            volume_outlines = get_volume_outlines_by_project(project_id)
            cur_vol = None
            for vo in volume_outlines:
                if vo.get("chapter_start", 1) <= chapter_index <= vo.get("chapter_end", 9999):
                    cur_vol = vo
                    break
            timelines = get_timelines_by_project(project_id)
            tl = None
            if cur_vol:
                tl = next(
                    (t for t in timelines if t.get("volume_number") == cur_vol.get("volume_number")),
                    None,
                )
            if not tl:
                _logger.warning(
                    f"[CrossChapterEvent] 第{chapter_index}章新倒计时跳过：当前卷无 timeline 主记录"
                )
                return 0
            count = 0
            existing = {c.get("event_name", "") for c in get_timeline_countdowns(tl["id"]) or []}
            for c in new_countdowns:
                name = str(c.get("event_name", "")).strip()
                if not name or name in existing:
                    continue
                add_timeline_countdown(
                    timeline_id=tl["id"],
                    event_name=name,
                    start_countdown=str(c.get("start_countdown", "")).strip(),
                    current_status="未触发",
                    trigger_chapter=0,
                    result="",
                )
                existing.add(name)
                count += 1
            return count
        except Exception as e:
            _logger.warning(f"[CrossChapterEvent] 新倒计时落库失败（不阻断）: {e}")
            return 0

    # ── 跨章去重（自 fact_recorder 迁移）───────────────────

    def _deduplicate_against_existing(self, loops: List[Dict], project_id: int) -> List[Dict]:
        """跨章去重：与数据库中已有开放悬念比对，过滤重复埋线。"""
        if not loops or not project_id:
            return loops
        try:
            existing = get_open_loops_by_project(project_id)
        except Exception:
            return loops
        if not existing:
            return loops
        existing_contents = [e.get("content", "") for e in existing if e.get("content")]
        result = []
        for loop in loops:
            new_key = loop.get("content", "")[:50]
            if not new_key:
                continue
            is_dup = any(new_key in ec or ec[:50] in new_key for ec in existing_contents)
            if not is_dup:
                result.append(loop)
        return result

    # ── LLM 调用 ─────────────────────────────────────────

    async def _call_llm(self, project_id: int, content: str,
                        loops_text: str, countdowns_text: str) -> Dict[str, Any]:
        prompt_data = self._load_prompt("cross_chapter_event")
        if not prompt_data["user_prompt"]:
            raise RuntimeError("cross_chapter_event prompt 模板加载为空")
        prompt = prompt_data["user_prompt"].format(
            chapter_content=content[:3500],
            active_loops=loops_text,
            active_countdowns=countdowns_text,
        )
        system_prompt = prompt_data["system_prompt"] or (
            "你是一位专业的故事分析助手，擅长识别跨章节事件的埋设与回收")

        executor = get_model_executor()
        result = await executor.execute_text_chat(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=1200,
            script_id=self.script_id,
            project_id=project_id,
            executor_name=self.step_name,
            prompt_name="cross_chapter_event",
        )
        response_content = result.get("content", "") if result else ""
        try:
            data = parse_llm_json(
                response_content,
                script_id=self.script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="cross_chapter_event",
            ) or {}
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return data
