"""执行器9：草稿润色器（出成果）。

按润色相关性分层组织 prompt：
  第一层：润色指令（合并润色要求与技巧，消除重复）
  第二层：审查反馈（问题+建议，润色的核心依据）
  第三层：世界观参考（保持设定一致性的辅助信息）
  第四层：草稿内容（紧贴输出指令，最高注意力）
"""

from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from webnovel.repositories import get_webnovel_project_by_script
from utils.llm_json_parser import parse_llm_json


class DraftPolisherExecutor(BaseExecutor):
    """草稿润色器执行器。"""

    step_name = "draft_polisher"
    step_description = "草稿润色"
    step_weight = 15

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

            writing_context = context.get("writing_context", {})
            review_result = context.get("review_result", [])

            issues = []
            suggestions = []

            if review_result:
                for review in review_result:
                    for issue in review.get("issues", []):
                        if isinstance(issue, dict) and 'severity' in issue and 'description' in issue:
                            severity = issue.get('severity', '')
                            description = issue.get('description', '')
                            location = issue.get('location', '')
                            fix_hint = issue.get('fix_hint', '')

                            if severity in ["critical", "high", "medium"]:
                                issues.append(f"- [{severity}] {location}: {description}")

                    if review.get("suggestions"):
                        suggestions.append(f"- [{review['name']}] {review['suggestions']}")

            # ── 预计算动态 section ──
            issues_section = ""
            if issues:
                issues_section = f"\n\n【审查问题】\n{chr(10).join(issues)}"

            suggestions_section = ""
            if suggestions:
                suggestions_section = f"\n\n【修改建议】\n{chr(10).join(suggestions)}"

            worldview_section = ""
            if writing_context.get("world_settings"):
                world_items = []
                for setting in writing_context["world_settings"][:3]:
                    if isinstance(setting, dict):
                        text = (setting.get('name') and setting.get('content')
                                and f"{setting['name']}: {setting['content'][:150]}") \
                            or (setting.get('world_summary')
                                and f"世界观: {setting['world_summary'][:150]}") \
                            or (setting.get('core_creed')
                                and f"核心信条: {setting['core_creed'][:150]}")
                        if text:
                            world_items.append(f"- {text}")
                if world_items:
                    worldview_section = f"\n\n【世界观】\n" + "\n".join(world_items)

            # 从 .md 文件加载 prompt 模板
            prompt_data = self._load_prompt("draft_polish")
            full_prompt = prompt_data["user_prompt"].format(
                issues_section=issues_section,
                suggestions_section=suggestions_section,
                worldview_section=worldview_section,
                draft_content=draft_content,
            )
            system_prompt = prompt_data["system_prompt"] or "你是一位资深网文润色师，精通各种题材的小说润色，输出严格的JSON格式"

            from core.model_executor import get_model_executor
            executor = get_model_executor()

            project = get_webnovel_project_by_script(script_id)
            project_id = project["id"] if project else 0

            result = await executor.execute_text_chat(
                prompt=full_prompt,
                system_prompt=system_prompt,
                max_tokens=8000,
                script_id=script_id,
                project_id=project_id,
                executor_name="draft_polisher_executor",
                prompt_name="draft_polish",
            )

            raw_content = result.get("content", "") if result else ""

            # 尝试JSON解析，提取正文内容
            polished_data = parse_llm_json(
                raw_content,
                script_id=script_id,
                project_id=project_id,
                executor_name="draft_polisher_executor",
                prompt_name="draft_polish",
            )

            if polished_data and "content" in polished_data:
                polished_content = polished_data["content"].strip()
            else:
                # JSON解析失败，回退到原始文本（去除可能的markdown代码围栏）
                polished_content = raw_content.strip()
                if polished_content.startswith("```"):
                    lines = polished_content.split("\n")
                    # 去掉首尾的 ``` 行
                    if lines and lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    polished_content = "\n".join(lines).strip()

            if not polished_content:
                polished_content = draft_content

            # 润色职责是扩写（白描稿1200-1800字 → 成品3000-5000字），
            # 若输出反而短于草稿，说明模型压缩而非扩写，采用草稿保底避免质量退化。
            if len(polished_content) < len(draft_content):
                polished_content = draft_content

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