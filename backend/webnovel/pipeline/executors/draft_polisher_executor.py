"""执行器9：草稿润色器。

将白描草稿还原成小说。上下文由 ContextAnalyzer 三段式装配（Analyze→Gather），
executor 不再自行拼装；草稿（draft_content）为任务输入，由模板占位符实时注入。
"""

from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from ..context_analyzer import ContextAnalyzer
from core.model_executor import get_model_executor
from utils.llm_json_parser import parse_llm_json
from webnovel.repositories import get_webnovel_project_by_script


class DraftPolisherExecutor(BaseExecutor):
    """草稿润色器执行器。"""

    step_name = "draft_polisher"
    step_description = "草稿润色"
    step_weight = 20

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行草稿润色，将草稿还原成小说。"""
        try:
            script_id = self.script_id

            draft_content = context.get("revised_draft") or context.get("draft_content", "")

            if not draft_content:
                return ExecutorResult(
                    success=False,
                    error_message="草稿内容为空",
                    step_summary="草稿润色失败"
                )

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="未找到项目信息",
                    step_summary="草稿润色失败"
                )
            project_id = project["id"]

            # ── 通过 ContextAnalyzer 三段式装配上下文 ──
            analyzer = ContextAnalyzer(script_id, self.chapter_index)
            step_ctx = await analyzer.analyze_and_assemble(
                step_name="draft_polisher",
                inventory=context.get("context_inventory", {}),
                structural_data=context.get("structural_data", {}),
                script_id=script_id,
                project_id=project_id,
                prev_selections=context.get("step_selections"),
                task_inputs={"review_result": context.get("review_result", [])},
            )

            # 从 .md 文件加载 prompt 模板
            prompt_data = self._load_prompt("draft_polish")
            word_cfg = context.get("word_config") or {}
            full_prompt = prompt_data["user_prompt"].format(
                assembled_context=step_ctx["assembled_context"],
                draft_content=draft_content,
                polish_word_min=int(word_cfg.get("polish_word_min", 3000)),
                polish_word_max=int(word_cfg.get("polish_word_max", 5000)),
            )
            system_prompt = prompt_data["system_prompt"] or "你是一位资深网文润色师，精通各种题材的小说润色，输出严格的JSON格式"

            from core.model_executor import get_model_executor
            executor = get_model_executor()

            result = await executor.execute_text_chat(
                prompt=full_prompt,
                system_prompt=system_prompt,
                max_tokens=int(word_cfg.get("polish_max_tokens", 8000)),
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="draft_polish",
            )

            raw_content = result.get("content", "") if result else ""

            # 尝试JSON解析，提取正文内容
            polished_data = parse_llm_json(
                raw_content,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="draft_polish",
                expect_json=False,
            )

            if polished_data and "content" in polished_data:
                polished_content = polished_data["content"].strip()
            else:
                polished_content = raw_content.strip()
                if polished_content.startswith("```"):
                    lines = polished_content.split("\n")
                    if lines and lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    polished_content = "\n".join(lines).strip()

            if not polished_content:
                polished_content = draft_content

            # 润色职责是扩写（白描稿1200-1800字 → 成品3000-5000字），
            # 若输出反而短于草稿，说明模型压缩而非扩写，采用草稿保底。
            if len(polished_content) < len(draft_content):
                polished_content = draft_content

            # 超长截断保底
            MAX_POLISH_LEN = 5500
            if len(polished_content) > MAX_POLISH_LEN:
                cut_pos = polished_content.rfind("\n", 0, MAX_POLISH_LEN)
                if cut_pos > MAX_POLISH_LEN * 0.8:
                    polished_content = polished_content[:cut_pos].rstrip()

            summary = f"草稿润色完成：润色后{len(polished_content)}字"

            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "polished_content": polished_content,
                    "polished_word_count": len(polished_content)
                }
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"草稿润色执行失败: {str(e)}",
                step_summary="草稿润色执行失败"
            )
