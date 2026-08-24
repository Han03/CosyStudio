"""执行器11：任务归档器。

将当前流程的执行日志和每一步的成功归档记录，并且将成果应用到原文里。
"""

import json
import time
from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult


class TaskArchiverExecutor(BaseExecutor):
    """任务归档器执行器。"""

    step_name = "task_archiver"
    step_description = "任务归档"
    step_weight = 10

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行任务归档，将成果应用到原文。"""
        try:
            script_id = self.script_id
            chapter_index = self.chapter_index
            task_id = self.task_id

            execution_log = context.get("execution_log", [])
            polished_content = context.get("polished_content", "") or context.get("revised_draft", "") or context.get("draft_content", "")
            
            for log_entry in execution_log:
                from repositories import add_pipeline_log
                add_pipeline_log(
                    script_id=script_id,
                    chapter_index=chapter_index,
                    task_id=task_id,
                    step_name=log_entry.get("name", log_entry.get("step", "")),
                    step_result=log_entry.get("summary", ""),
                    success=log_entry.get("success", True),
                    error_message=log_entry.get("error", ""),
                    duration_ms=log_entry.get("duration_ms", 0)
                )

            applied = False
            if polished_content and polished_content.strip():
                # 内容由 webnovel_service._save_continue_result 统一保存，
                # 此处仅记录日志，避免双重保存导致索引错位
                applied = True

            all_logs = self._get_all_step_results(context)

            summary = f"任务归档完成：执行日志已记录，成果{'已' if applied else '未'}应用到章节"
            
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "archived": True,
                    "applied_to_chapter": applied,
                    "execution_log": execution_log,
                    "step_results": all_logs,
                    "final_content": polished_content
                }
            )
            
        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"任务归档执行失败: {str(e)}",
                step_summary="任务归档执行失败"
            )

    def _get_all_step_results(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """获取所有步骤的结果。"""
        step_results = {}
        
        for key in context:
            if key.endswith("_result") or key.endswith("_content") or key.endswith("_count"):
                step_results[key] = context.get(key)
        
        return step_results

    async def _apply_to_chapter(self, script_id: int, chapter_index: int, content: str) -> bool:
        """将成果应用到章节。"""
        try:
            from services.script_service import ScriptService
            from repositories import get_script_chapter, delete_script_chapter
            
            script_service = ScriptService()
            chapter = get_script_chapter(script_id, chapter_index)

            if chapter and chapter.get("file_path"):
                success = script_service.update_chapter_content(script_id, chapter_index, content)
                if success:
                    return True
                else:
                    delete_script_chapter(script_id, chapter_index)
                    title = f"第{chapter_index}章"
                    script_service.add_chapter(script_id, title, content)
                    return True
            else:
                if chapter:
                    delete_script_chapter(script_id, chapter_index)
                title = f"第{chapter_index}章"
                script_service.add_chapter(script_id, title, content)
                return True

        except Exception as e:
            from utils.logger import log_manager
            logger = log_manager.get_logger("task_archiver")
            logger.error(f"应用成果到章节失败: {e}")
            return False