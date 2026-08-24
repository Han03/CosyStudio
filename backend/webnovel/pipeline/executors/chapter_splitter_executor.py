"""执行器3：拆章器。

参考webnovel-writer，将卷纲拆分为多个章节。
支持批量拆章，已拆分的卷纲自动标记，下次拆章时跳过。
"""

from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from webnovel.repositories import (
    get_webnovel_project_by_script, get_volume_outlines_by_project,
    get_chapter_meta_list, add_chapter_meta
)


class ChapterSplitterExecutor(BaseExecutor):
    """拆章器执行器。"""

    step_name = "chapter_splitter"
    step_description = "拆章规划"
    step_weight = 5

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行拆章规划。"""
        try:
            script_id = self.script_id
            chapter_index = self.chapter_index

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="未找到webnovel项目",
                    step_summary="拆章执行失败：未找到项目"
                )
            project_id = project["id"]

            volume_outlines = context.get("volume_outlines") or get_volume_outlines_by_project(project_id)
            
            if not volume_outlines:
                return ExecutorResult(
                    success=False,
                    error_message="找不到卷纲",
                    step_summary="拆章执行失败"
                )

            existing_chapters = get_chapter_meta_list(project_id)
            existing_indices = {c["chapter_number"] for c in existing_chapters}

            target_outline = None
            for outline in volume_outlines:
                start_chapter = outline.get("chapter_start", 0)
                end_chapter = outline.get("chapter_end", 0)
                if start_chapter <= chapter_index <= end_chapter:
                    target_outline = outline
                    break
            if not target_outline:
                target_outline = volume_outlines[-1]

            new_chapters = []
            start_chapter = target_outline.get("chapter_start", 0)
            end_chapter = target_outline.get("chapter_end", 0)
            
            volume_summary = target_outline.get("core_conflict", "") or target_outline.get("promise_description", "")
            
            for i in range(start_chapter, end_chapter + 1):
                plan_index = i
                
                if plan_index in existing_indices:
                    continue

                chapter_title = f"第{plan_index + 1}章"
                
                chapter_meta = add_chapter_meta(
                    project_id=project_id,
                    chapter_number=plan_index,
                    hook_type="悬念式",
                    hook_content="",
                    hook_strength="中",
                    opening_pattern="场景切入",
                    hook_pattern="冲突前置",
                    emotion_rhythm="起承转合",
                    info_density="适中",
                    ending_time="白天",
                    ending_location="",
                    ending_emotion="期待"
                )
                new_chapters.append(chapter_meta)

            all_chapters = get_chapter_meta_list(project_id)
            current_chapter = next((c for c in all_chapters if c["chapter_number"] == chapter_index), None)
            
            summary = f"拆章完成：新增{len(new_chapters)}个章节规划，总计{len(all_chapters)}个"
            
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "chapter_plans": all_chapters,
                    "current_chapter_plan": current_chapter,
                    "new_plans_count": len(new_chapters)
                }
            )
            
        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"拆章执行失败: {str(e)}",
                step_summary="拆章执行失败"
            )
