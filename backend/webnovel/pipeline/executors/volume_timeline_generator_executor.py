"""执行器：卷首时间轴生成器。

每卷第一章生成前调用 LLM，以本卷卷纲 + 第一章章节规划（+ 前一章时间轴）
为证据，生成 webnovel_timeline 主记录（time_base / time_span），一卷一条、幂等。
失败即报错中断（由编排器处理）。
"""

from typing import Any, Dict, Optional
from types import SimpleNamespace

from ..base_executor import BaseExecutor, ExecutorResult
from core.model_executor import get_model_executor
from utils.llm_json_parser import parse_llm_json
from utils.logger import log_manager
from webnovel.repositories import (
    get_webnovel_project_by_script,
    get_volume_outlines_by_project,
    get_chapter_plans_by_volume,
    get_timelines_by_project,
    get_timeline_chapters,
    add_timeline,
)

_logger = log_manager.get_logger("volume_timeline_generator")


class VolumeTimelineGeneratorExecutor(BaseExecutor):
    """卷首时间轴生成器执行器。"""

    step_name = "volume_timeline_generator"
    step_description = "卷首时间轴"
    step_weight = 3

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行卷首时间轴生成。"""
        try:
            project = get_webnovel_project_by_script(self.script_id)
            if not project:
                return ExecutorResult(
                    success=True,
                    step_summary="未找到webnovel项目，跳过卷首时间轴",
                    output_data={},
                )
            project_id = project["id"]

            # 1. 定位当前章所属卷
            volume_outlines = get_volume_outlines_by_project(project_id)
            cur_vol = None
            for vo in volume_outlines:
                if vo.get("chapter_start", 1) <= self.chapter_index <= vo.get("chapter_end", 9999):
                    cur_vol = vo
                    break
            if not cur_vol:
                return ExecutorResult(
                    success=True,
                    step_summary="未找到当前章所属卷，跳过卷首时间轴",
                    output_data={},
                )
            volume_number = cur_vol.get("volume_number")

            # 2. 非卷首章：跳过（不调用 LLM）
            if self.chapter_index != cur_vol.get("chapter_start", 1):
                return ExecutorResult(
                    success=True,
                    step_summary=f"第{self.chapter_index}章非卷首章，跳过卷首时间轴",
                    output_data={"volume_number": volume_number, "skipped": True},
                )

            # 3. 幂等：该卷已有主记录则跳过
            timelines = get_timelines_by_project(project_id)
            if any(tl.get("volume_number") == volume_number for tl in timelines):
                return ExecutorResult(
                    success=True,
                    step_summary=f"第{volume_number}卷时间轴已存在，跳过",
                    output_data={"volume_number": volume_number, "skipped": True},
                )

            # 4. 证据：第一章章节规划
            plans = get_chapter_plans_by_volume(cur_vol["id"])
            first_plan = next(
                (p for p in plans if p.get("chapter_index") == cur_vol.get("chapter_start")), None
            )
            first_plan_text = self._format_first_plan(first_plan)

            # 5. 证据：前一章时间轴（第二卷及以后）
            prev_timeline_end = self._build_prev_timeline_end(volume_number, timelines)

            # 6. LLM 生成卷级时间设定
            tl_data = await self._call_llm("volume_timeline", {
                "project": project,
                "volume_outline": cur_vol,
                "volume_number": volume_number,
                "first_chapter_plan_text": first_plan_text,
                "prev_timeline_end": prev_timeline_end,
            })
            if not tl_data or "error" in tl_data:
                raise RuntimeError(f"卷首时间轴生成失败：LLM未返回有效数据: {tl_data}")
            time_base = str(tl_data.get("time_base", "")).strip()
            time_span = str(tl_data.get("time_span", "")).strip()
            if not time_base:
                raise RuntimeError(f"卷首时间轴生成失败：time_base 为空: {tl_data}")

            # 7. 落库（一卷一条）
            tl = add_timeline(
                project_id,
                volume_number,
                time_base=time_base,
                time_span=time_span,
                countdown_events="",
            )
            return ExecutorResult(
                success=True,
                step_summary=f"第{volume_number}卷时间轴生成：{time_base} ~ {time_span}",
                output_data={"volume_number": volume_number, "timeline_id": tl["id"]},
            )
        except Exception as e:
            _logger.error(f"[VolumeTimelineGenerator] 执行失败: {e}")
            return ExecutorResult(
                success=False,
                error_message=f"卷首时间轴生成失败: {str(e)}",
                step_summary="卷首时间轴生成失败",
            )

    def _format_first_plan(self, plan: Optional[Dict]) -> str:
        """格式化第一章章节规划。"""
        if not plan:
            return "（暂无第一章章节规划）"
        parts = []
        if plan.get("chapter_title"):
            parts.append(f"标题: {plan['chapter_title']}")
        if plan.get("summary"):
            parts.append(f"概要: {str(plan['summary'])[:200]}")
        if plan.get("key_events"):
            parts.append(f"关键事件: {str(plan['key_events'])[:300]}")
        return "\n".join(parts) if parts else "（暂无第一章章节规划）"

    def _build_prev_timeline_end(self, volume_number: int, timelines: list) -> str:
        """构建前一章时间轴证据（上一卷末章时间锚点）。"""
        if volume_number and volume_number > 1:
            prev_tl = next(
                (tl for tl in timelines if tl.get("volume_number") == volume_number - 1), None
            )
            if prev_tl:
                prev_chapters = get_timeline_chapters(prev_tl["id"]) or []
                if prev_chapters:
                    last = prev_chapters[-1]
                    anchor = last.get("time_anchor") or "（无）"
                    interval = last.get("interval_from_prev") or "（无）"
                    return (
                        f"第{last.get('chapter_number', '?')}章 时间锚点:{anchor} "
                        f"距上章:{interval}"
                    )
                return f"第{volume_number - 1}卷时间轴存在，但暂无章节锚点数据"
            return f"（未找到第{volume_number - 1}卷时间轴）"
        return "（本卷为起始卷，无前一章时间轴）"

    async def _call_llm(self, prompt_name: str, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """调用LLM生成卷首时间设定。"""
        prompt_data = self._load_prompt(prompt_name)
        if not prompt_data["user_prompt"]:
            raise RuntimeError(f"prompt加载失败: {prompt_name}")

        obj_context = {
            k: self._dict_to_obj(v) if isinstance(v, dict) else v
            for k, v in context_data.items()
        }
        user_prompt = prompt_data["user_prompt"].format(**obj_context)

        executor = get_model_executor()
        result = await executor.execute_text_chat(
            prompt=user_prompt,
            system_prompt=prompt_data["system_prompt"],
            max_tokens=800,
            script_id=self.script_id,
            project_id=self._get_project_id(),
            executor_name="volume_timeline_generator",
            prompt_name=prompt_name,
        )
        content = result.get("content", "") if result else ""
        content = content.strip()
        if not content:
            raise RuntimeError(f"{prompt_name} 返回为空")

        json_result = parse_llm_json(
            content,
            script_id=self.script_id,
            project_id=self._get_project_id(),
            executor_name="volume_timeline_generator",
            prompt_name=prompt_name,
        )
        if not json_result or not isinstance(json_result, dict):
            raise RuntimeError(f"{prompt_name} 返回非JSON: {content[:200]}")
        return json_result

    def _get_project_id(self) -> int:
        try:
            proj = get_webnovel_project_by_script(self.script_id)
            return proj.get("id", 0) if proj else 0
        except Exception:
            return 0

    @staticmethod
    def _dict_to_obj(d: Dict) -> Any:
        """将 dict 转为属性访问对象，供 prompt 模板 {obj.attr} 使用。"""
        return SimpleNamespace(**d)
