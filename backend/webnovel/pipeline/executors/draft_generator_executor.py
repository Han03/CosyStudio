"""执行器7：草稿生成器（剧情创作）。

基于章节剧情生成器输出的详细剧情列表创作白描草稿。
上下文由 ContextAnalyzer 三段式装配（Analyze→Gather），executor 不再自行拼装。
"""

from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from ..context_analyzer import ContextAnalyzer
from core.model_executor import get_model_executor
from utils.llm_json_parser import parse_llm_json
from webnovel.repositories import get_webnovel_project_by_script


class DraftGeneratorExecutor(BaseExecutor):
    """草稿生成器执行器。"""

    step_name = "draft_generator"
    step_description = "草稿生成"
    step_weight = 15

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行草稿生成。"""
        try:
            script_id = self.script_id
            chapter_index = self.chapter_index

            user_prompt = context.get("user_prompt", "")
            chapter_plan = context.get("current_chapter_plan")

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="未找到项目信息",
                    step_summary="草稿生成失败"
                )

            project_id = project["id"]

            # ── 通过 ContextAnalyzer 三段式装配上下文 ──
            analyzer = ContextAnalyzer(script_id, chapter_index)
            step_ctx = await analyzer.analyze_and_assemble(
                step_name="draft_generator",
                inventory=context.get("context_inventory", {}),
                structural_data=context.get("structural_data", {}),
                script_id=script_id,
                project_id=project_id,
                prev_selections=context.get("step_selections"),
                task_inputs={"plot_list": context.get("chapter_plot", [])},
            )

            # 记录本步骤的选择结果
            if "step_selections" not in context:
                context["step_selections"] = {}
            selection = step_ctx.get("_selection", {})
            context["step_selections"]["draft_generator"] = {
                "character_names": [
                    c.get("character_name", "") for c in step_ctx.get("characters", [])
                ],
                "consistency_notes": selection.get("custom_notes", []),
            }

            # ── 构建 prompt 动态 section ──
            continue_prev = "开篇直接承接上一章结尾，不要有剧情中断感觉;" if chapter_index > 1 else ""
            user_prompt_section = f"\n\n【用户要求】\n{user_prompt}" if user_prompt else ""

            prompt_data = self._load_prompt("draft_generate")
            word_cfg = context.get("word_config") or {}
            full_prompt = prompt_data["user_prompt"].format(
                continue_prev=continue_prev,
                user_prompt_section=user_prompt_section,
                assembled_context=step_ctx["assembled_context"],
                draft_word_min=int(word_cfg.get("draft_word_min", 1200)),
                draft_word_max=int(word_cfg.get("draft_word_max", 1800)),
            )
            system_prompt = prompt_data["system_prompt"] or "你是一位畅销网文作家，擅长创作精彩的网络小说章节"

            executor = get_model_executor()
            result = await executor.execute_text_chat(
                prompt=full_prompt,
                system_prompt=system_prompt,
                max_tokens=max(3500, int(word_cfg.get("draft_word_max", 1800)) * 3),
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name=f"draft_chapter_{chapter_index}",
            )

            response_content = result.get("content", "") if result else ""

            draft_data = parse_llm_json(
                response_content,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name=f"draft_chapter_{chapter_index}",
            )

            if not draft_data or "content" not in draft_data:
                draft_data = {
                    "content": response_content.strip(),
                    "chapter_title": chapter_plan.get("chapter_title", "") if chapter_plan else f"第{chapter_index}章",
                }

            if not draft_data["content"]:
                return ExecutorResult(
                    success=False,
                    error_message="草稿生成结果为空",
                    step_summary="草稿生成失败"
                )

            word_count = len(draft_data["content"])
            summary = f"草稿生成完成：{word_count}字"

            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "draft_content": draft_data["content"],
                    "chapter_title": draft_data.get("chapter_title", f"第{chapter_index}章"),
                    "word_count": word_count,
                }
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"草稿生成执行失败: {str(e)}",
                step_summary="草稿生成执行失败"
            )
