import json
from typing import List, Dict, Any, Optional, Type
from datetime import datetime

from .base_executor import BaseExecutor, ExecutorResult
from .executors import EXECUTORS
from utils.logger import log_manager
from repositories import update_writing_task, get_writing_task
from infrastructure.websocket_broadcast import ws_broadcast_manager


class PipelineOrchestrator:
    """写作管道编排器。"""

    EXECUTOR_REGISTRY: Dict[str, Type[BaseExecutor]] = {}

    DEFAULT_STEPS = [
        "chapter_splitter",
        "timeline_fixer",
        "setting_recorder",
        "context_builder",
        "chapter_plot_generator",
        "chapter_plot_reviewer",
        "draft_generator",
        "draft_reviewer",
        "draft_polisher",
        "fact_recorder",
        "foreshadow_cool_point_extractor",
        "task_archiver",
    ]

    WORKFLOW_MODELS = {
        "init": ["init_executor"],
        "plan": ["plan_executor"],
        "write": [
            "context_builder",
            "chapter_plot_generator",
            "chapter_plot_reviewer",
            "draft_generator",
            "draft_reviewer",
            "draft_polisher",
            "fact_recorder",
            "setting_recorder",
            "foreshadow_cool_point_extractor",
        ],
        "write_fast": [
            "context_builder",
            "chapter_plot_generator",
            "chapter_plot_reviewer",
            "draft_generator",
            "draft_reviewer",
            "draft_polisher",
            "fact_recorder",
        ],
        "write_minimal": [
            "context_builder",
            "chapter_plot_generator",
            "chapter_plot_reviewer",
            "draft_generator",
            "draft_polisher",
            "fact_recorder",
        ],
        "review": ["review_executor"],
        "query": ["query_executor"],
        "doctor": ["doctor_executor"],
        "learn": ["learn_executor"],
        "story_system": ["story_system"],
    }

    @classmethod
    def register_executor(cls, name: str, executor_class: Type[BaseExecutor]):
        """注册执行器。"""
        cls.EXECUTOR_REGISTRY[name] = executor_class

    @classmethod
    def register_all_executors(cls):
        """注册所有执行器。"""
        for executor_class in EXECUTORS:
            cls.register_executor(executor_class.step_name, executor_class)

    def __init__(self, script_id: int, chapter_index: int, task_id: int, stop_check=None):
        self.script_id = script_id
        self.chapter_index = chapter_index
        self.task_id = task_id
        self._stop_check = stop_check
        self._logger = log_manager.get_logger("pipeline_orchestrator")
        self._execution_log: List[Dict[str, Any]] = []
        self._context: Dict[str, Any] = {
            "script_id": script_id,
            "chapter_index": chapter_index,
            "task_id": task_id,
            "start_time": datetime.now().isoformat(),
            "step_results": {},
        }

    async def execute_workflow(self, mode: str, context_data: Dict[str, Any] = None, user_prompt: str = "", enable_polish: bool = True) -> Dict[str, Any]:
        """根据模式执行对应工作流。"""
        if context_data:
            self._context.update(context_data)

        steps = list(self.WORKFLOW_MODELS.get(mode, self.DEFAULT_STEPS))
        if not enable_polish and "draft_polisher" in steps:
            steps.remove("draft_polisher")
        return await self.execute_pipeline(steps, user_prompt)

    async def execute_pipeline(self, steps: List[str] = None, user_prompt: str = "", enable_polish: bool = True) -> Dict[str, Any]:
        """执行完整管道。"""
        if steps is None:
            steps = list(self.DEFAULT_STEPS)
        else:
            steps = list(steps)

        if not enable_polish and "draft_polisher" in steps:
            steps.remove("draft_polisher")

        self._context["user_prompt"] = user_prompt

        total_weight = sum(
            self.EXECUTOR_REGISTRY.get(step, BaseExecutor).step_weight
            for step in steps
        )

        current_progress = 0
        completed_steps = 0
        failed_steps = 0

        for step_name in steps:
            # 中断检查
            if self._stop_check and self._stop_check():
                self._logger.info(f"任务被中断，停止执行（已完成 {completed_steps} 步）")
                await self._update_progress(
                    current_progress,
                    "任务已中断",
                    "interrupted"
                )
                break

            executor_class = self.EXECUTOR_REGISTRY.get(step_name)
            if not executor_class:
                self._logger.error(f"执行器 {step_name} 未注册")
                continue

            try:
                executor = executor_class(self.script_id, self.chapter_index, self.task_id)
                step_info = executor.get_step_info()
                step_display = step_info["description"]

                await self._update_progress(
                    current_progress,
                    f"{step_display}...",
                    step_display
                )

                start_time = datetime.now()
                self._logger.info(f"开始执行步骤: {step_name}")

                result = await executor.execute(self._context)

                end_time = datetime.now()
                duration_ms = int((end_time - start_time).total_seconds() * 1000)

                log_entry = {
                    "step": step_name,
                    "name": step_info["name"],
                    "success": result.success,
                    "duration_ms": duration_ms,
                    "summary": result.step_summary,
                    "error": result.error_message if not result.success else "",
                    "output_keys": list(result.output_data.keys()),
                    "timestamp": end_time.isoformat(),
                }
                self._execution_log.append(log_entry)

                if result.success:
                    completed_steps += 1
                    self._context["step_results"][step_name] = result.output_data
                    self._context.update(result.output_data)
                    self._logger.info(f"步骤 {step_name} 完成: {result.step_summary}")
                else:
                    failed_steps += 1
                    self._logger.error(f"步骤 {step_name} 失败: {result.error_message}")
                    await self._update_progress(
                        current_progress,
                        f"{step_display}失败: {result.error_message}",
                        step_display
                    )

                current_progress += step_info["weight"]

                await self._update_progress(
                    min(95, int((current_progress / total_weight) * 95)),
                    f"{step_display}完成",
                    step_display
                )

                # 步骤完成后再次检查中断
                if self._stop_check and self._stop_check():
                    self._logger.info(f"任务在步骤 {step_name} 完成后被中断")
                    await self._update_progress(
                        current_progress,
                        "任务已中断",
                        "interrupted"
                    )
                    break

            except Exception as e:
                failed_steps += 1
                error_msg = str(e)
                self._logger.error(f"步骤 {step_name} 执行异常: {error_msg}")

                log_entry = {
                    "step": step_name,
                    "name": step_info.get("name", step_name),
                    "success": False,
                    "duration_ms": 0,
                    "summary": "",
                    "error": error_msg,
                    "output_keys": [],
                    "timestamp": datetime.now().isoformat(),
                }
                self._execution_log.append(log_entry)

                await self._update_progress(
                    current_progress,
                    f"执行异常: {error_msg[:100]}",
                    step_info.get("description", step_name) if executor_class else step_name
                )

        self._context["end_time"] = datetime.now().isoformat()
        self._context["execution_log"] = self._execution_log
        self._context["completed_steps"] = completed_steps
        self._context["failed_steps"] = failed_steps

        # 检查是否因中断而退出
        interrupted = bool(self._stop_check and self._stop_check())

        return {
            "success": failed_steps == 0 and not interrupted,
            "interrupted": interrupted,
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
            "total_steps": len(steps),
            "context": self._context,
            "execution_log": self._execution_log,
        }

    async def _update_progress(self, progress: int, message: str, step_name: str = ""):
        """更新任务进度并广播。"""
        try:
            update_kwargs = {
                "progress": progress,
                "progress_message": message,
                "current_step": message,
            }
            # 将干净的步骤名称存入 step_result，供前端匹配和页面刷新恢复使用
            if step_name:
                update_kwargs["step_result"] = step_name
            update_writing_task(self.task_id, **update_kwargs)

            task_data = get_writing_task(None, self.task_id)
            if task_data:
                status = {
                    "id": task_data["id"],
                    "script_id": task_data["script_id"],
                    "chapter_index": task_data["chapter_index"],
                    "status": task_data["status"],
                    "progress": progress,
                    "progress_message": message,
                    "error_message": task_data.get("error_message", ""),
                    "current_step": message,
                    "step_result": message,
                    "step_name": step_name,
                    "draft": task_data.get("draft", ""),
                    "polished": task_data.get("polished", ""),
                    "review_result": task_data.get("review_result", ""),
                    "facts_recorded": task_data.get("facts_recorded", ""),
                    "context": task_data.get("context", ""),
                }
                await ws_broadcast_manager.broadcast_continue_task_update(
                    self.script_id, self.task_id, status
                )
        except Exception as e:
            self._logger.error(f"更新进度失败: {e}")


PipelineOrchestrator.register_all_executors()