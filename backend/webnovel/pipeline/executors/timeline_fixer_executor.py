"""执行器4：时间线修补器。

参考webnovel-writer，检查和修补时间线一致性。
"""

from typing import Dict, Any, Optional
from ..base_executor import BaseExecutor, ExecutorResult
from repositories import get_script_lines
from webnovel.repositories import (
    get_webnovel_project_by_script, get_timelines_by_project, add_timeline,
    get_volume_outlines_by_project, upsert_timeline_chapter
)


class TimelineFixerExecutor(BaseExecutor):
    """时间线修补器执行器。"""

    step_name = "timeline_fixer"
    step_description = "时间线修补"
    step_weight = 5

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行时间线修补。"""
        try:
            script_id = self.script_id
            chapter_index = self.chapter_index

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=True,
                    step_summary="未找到webnovel项目，跳过时间线修补",
                    output_data={}
                )
            project_id = project["id"]

            # 加载卷纲和时间线，用于按卷匹配正确的 timeline
            volume_outlines = get_volume_outlines_by_project(project_id)
            timelines = get_timelines_by_project(project_id)

            previous_chapters = []
            for i in range(max(1, chapter_index - 3), chapter_index):
                lines = get_script_lines(script_id, i)
                if lines:
                    content = "\n".join(line["content"] for line in lines)
                    previous_chapters.append({
                        "chapter_index": i,
                        "content": content[:1000]
                    })

            new_events = []

            for prev_chapter in previous_chapters:
                prev_index = prev_chapter["chapter_index"]
                prev_content = prev_chapter["content"]

                # 根据章节号匹配所属卷的 timeline
                timeline = self._find_timeline_for_chapter(project_id, prev_index, volume_outlines, timelines)

                time_markers = ["凌晨", "清晨", "上午", "中午", "下午", "傍晚", "夜晚", "深夜"]
                found_markers = [m for m in time_markers if m in prev_content]
                if found_markers:
                    # 取第一个匹配的时间标记作为该章的时间锚点
                    event = upsert_timeline_chapter(
                        timeline_id=timeline["id"],
                        chapter_number=prev_index,
                        time_anchor=found_markers[0],
                        notes=f"时间标记：{','.join(found_markers)}"
                    )
                    new_events.append(event)

            # 检测时间跳跃
            if previous_chapters:
                last_chapter = previous_chapters[-1]
                last_content = last_chapter["content"]

                if "三年后" in last_content or "五年后" in last_content:
                    timeline = self._find_timeline_for_chapter(
                        project_id, last_chapter["chapter_index"], volume_outlines, timelines
                    )
                    event = upsert_timeline_chapter(
                        timeline_id=timeline["id"],
                        chapter_number=last_chapter["chapter_index"],
                        time_anchor="时间跳跃",
                        notes="时间跳跃标记"
                    )
                    new_events.append(event)

            all_timelines = get_timelines_by_project(project_id)

            summary = f"时间线修补完成：更新{len(new_events)}个章节时间轴，总计{len(all_timelines)}个时间线"

            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "timeline_events": all_timelines,
                    "new_events_count": len(new_events)
                }
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"时间线修补执行失败: {str(e)}",
                step_summary="时间线修补执行失败"
            )

    def _find_timeline_for_chapter(
        self, project_id: int, chapter_number: int,
        volume_outlines: list, timelines: list
    ) -> dict:
        """根据章节号匹配所属卷的 timeline。找不到时回退到第一条或自动创建。"""
        # 通过卷纲的 chapter_start~chapter_end 范围确定章节所属卷
        target_volume = None
        for vo in volume_outlines:
            if vo.get("chapter_start", 1) <= chapter_number <= vo.get("chapter_end", 9999):
                target_volume = vo.get("volume_number")
                break

        # 在 timelines 中查找对应卷号
        if target_volume is not None:
            for tl in timelines:
                if tl.get("volume_number") == target_volume:
                    return tl

        # 回退：取第一条 timeline
        if timelines:
            return timelines[0]

        # 兜底：自动创建
        return add_timeline(project_id=project_id, volume_number=1)
