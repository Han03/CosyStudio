"""执行器：章节剧情生成器。

在草稿生成前，基于章节规划和上下文生成详细的场景级剧情列表，
存入 webnovel_chapter_plot 表，供草稿生成器作为核心输入。

上下文由 ContextAnalyzer 三段式装配（Analyze→Gather），executor 不再自行拼装。
"""

import json
from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from ..context_analyzer import ContextAnalyzer
from core.model_executor import get_model_executor
from utils.llm_json_parser import parse_llm_json
from webnovel.repositories import (
    get_webnovel_project_by_script,
    add_chapter_plot, get_chapter_plot,
)


class ChapterPlotGeneratorExecutor(BaseExecutor):
    """章节剧情生成器执行器。"""

    step_name = "chapter_plot_generator"
    step_description = "剧情生成"
    step_weight = 10

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行章节剧情生成。"""
        try:
            script_id = self.script_id
            chapter_index = self.chapter_index

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="未找到项目信息",
                    step_summary="剧情生成失败"
                )

            project_id = project["id"]

            # 检查是否已有本章剧情（避免重复生成）
            existing_plot = get_chapter_plot(project_id, chapter_index)
            if existing_plot and existing_plot.get("plot_list"):
                plot_list = existing_plot["plot_list"]
                return ExecutorResult(
                    success=True,
                    step_summary=f"使用已有剧情：{len(plot_list)}个剧情点",
                    output_data={
                        "chapter_plot": plot_list,
                        "chapter_plot_source": "cache"
                    }
                )

            # ── 通过 ContextAnalyzer 三段式装配上下文 ──
            analyzer = ContextAnalyzer(script_id, chapter_index)
            step_ctx = await analyzer.analyze_and_assemble(
                step_name="chapter_plot_generator",
                inventory=context.get("context_inventory", {}),
                structural_data=context.get("structural_data", {}),
                script_id=script_id,
                project_id=project_id,
                prev_selections=context.get("step_selections"),
            )

            # 记录本步骤的选择结果，供下游步骤参考
            if "step_selections" not in context:
                context["step_selections"] = {}
            selection = step_ctx.get("_selection", {})
            context["step_selections"]["chapter_plot_generator"] = {
                "character_names": [
                    c.get("character_name", "") for c in step_ctx.get("characters", [])
                ],
                "foreshadow_contents": [
                    f.get("content", "")[:40] for f in step_ctx.get("foreshadows", [])
                ],
                "consistency_notes": selection.get("custom_notes", []),
            }

            # ── 构建 prompt 动态 section ──
            continue_prev = "开篇需承接上一章结尾，保持剧情连贯;" if chapter_index > 1 else ""

            # 加载 prompt 模板并填充
            prompt_data = self._load_prompt("chapter_plot_generate")
            full_prompt = prompt_data["user_prompt"].format(
                chapter_index=chapter_index,
                continue_prev=continue_prev,
                assembled_context=step_ctx["assembled_context"],
            )
            system_prompt = prompt_data["system_prompt"] or "你是一位资深网文策划编辑，擅长将章节规划拆解为详细的场景级剧情列表"

            executor = get_model_executor()
            result = await executor.execute_text_chat(
                prompt=full_prompt,
                system_prompt=system_prompt,
                max_tokens=3000,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name=f"chapter_plot_{chapter_index}",
            )

            response_content = result.get("content", "") if result else ""

            plot_data = parse_llm_json(
                response_content,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name=f"chapter_plot_{chapter_index}",
            )

            plot_list = []
            if plot_data and "plots" in plot_data:
                plot_list = plot_data["plots"]
            elif plot_data and isinstance(plot_data, list):
                plot_list = plot_data

            if not plot_list:
                return ExecutorResult(
                    success=False,
                    error_message="剧情生成结果为空",
                    step_summary="剧情生成失败"
                )

            # 存入数据库
            add_chapter_plot(project_id, chapter_index, plot_list)

            plot_count = len(plot_list)
            return ExecutorResult(
                success=True,
                step_summary=f"剧情生成完成：{plot_count}个剧情点",
                output_data={
                    "chapter_plot": plot_list,
                    "chapter_plot_source": "generated"
                }
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"剧情生成执行失败: {str(e)}",
                step_summary="剧情生成执行失败"
            )
