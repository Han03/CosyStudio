"""执行器9：草稿润色器（出成果）。

按润色相关性分层组织 prompt：
  第一层：润色指令（合并润色要求与技巧，消除重复）
  第二层：审查反馈（问题+建议，润色的核心依据）
  第三层：世界观参考（保持设定一致性的辅助信息）
  第四层：草稿内容（紧贴输出指令，最高注意力）

上下文通过 ContextAnalyzer 按需组装。
"""

from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from ..context_analyzer import ContextAnalyzer
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

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="未找到项目信息",
                    step_summary="草稿润色失败"
                )
            project_id = project["id"]

            review_result = context.get("review_result", [])

            # ── 通过 ContextAnalyzer 按需组装上下文 ──
            analyzer = ContextAnalyzer(script_id, self.chapter_index)
            step_ctx = await analyzer.analyze_and_assemble(
                step_name="draft_polisher",
                inventory=context.get("context_inventory", {}),
                structural_data=context.get("structural_data", {}),
                script_id=script_id,
                project_id=project_id,
                prev_selections=context.get("step_selections"),
            )

            # ── 预计算动态 section ──
            issues_section = ""
            suggestions_section = ""
            if review_result:
                issues = []
                suggestions = []
                for review in review_result:
                    for issue in review.get("issues", []):
                        if isinstance(issue, dict) and 'severity' in issue and 'description' in issue:
                            severity = issue.get('severity', '')
                            description = issue.get('description', '')
                            location = issue.get('location', '')

                            if severity in ["critical", "high", "medium"]:
                                issues.append(f"- [{severity}] {location}: {description}")

                    if review.get("suggestions"):
                        suggestions.append(f"- [{review['name']}] {review['suggestions']}")

                if issues:
                    issues_section = f"\n\n【审查问题】\n{chr(10).join(issues)}"
                if suggestions:
                    suggestions_section = f"\n\n【修改建议】\n{chr(10).join(suggestions)}"

            # 世界观参考（来自 step_ctx 精选的世界观）
            worldview_section = self._format_worldview(step_ctx.get("world_settings", []))

            # 文风锚点（前文代表性片段）
            style_anchor = self._format_style_anchor(step_ctx.get("previous_chapters", []))

            # 力量体系描写规范
            power_spec = self._format_power_spec(step_ctx.get("power_system"))

            # 一致性约束
            consistency_notes = step_ctx.get("consistency_notes", [])
            consistency_text = "\n".join(f"- {note}" for note in consistency_notes) if consistency_notes else ""

            # 从 .md 文件加载 prompt 模板
            prompt_data = self._load_prompt("draft_polish")
            word_cfg = (step_ctx.get("word_config") or {})
            full_prompt = prompt_data["user_prompt"].format(
                issues_section=issues_section,
                suggestions_section=suggestions_section,
                worldview_section=worldview_section,
                style_anchor=style_anchor,
                power_spec=power_spec,
                draft_content=draft_content,
                consistency_notes=consistency_text,
                polish_word_min=int(word_cfg.get("polish_word_min", 3000)),
                polish_word_max=int(word_cfg.get("polish_word_max", 5000)),
            )
            system_prompt = prompt_data["system_prompt"] or "你是一位资深网文润色师，精通各种题材的小说润色，输出严格的JSON格式"

            from core.model_executor import get_model_executor
            executor = get_model_executor()

            result = await executor.execute_text_chat(
                prompt=full_prompt,
                system_prompt=system_prompt,
                max_tokens=max(8000, int((step_ctx.get("word_config") or {}).get("polish_word_max", 5000)) * 2),
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

    # ── 格式化方法 ──────────────────────────────────────────

    def _format_style_anchor(self, previous_chapters: list) -> str:
        """从前文片段提取文风锚点（最多 2 段代表性文字）。"""
        if not previous_chapters:
            return ""
        parts = []
        for prev in previous_chapters[:2]:
            content = prev.get("content", "") if isinstance(prev, dict) else str(prev)
            if not content:
                continue
            idx = prev.get("chapter_index", "?") if isinstance(prev, dict) else "?"
            parts.append(f"--- 第{idx}章片段（风格参照，仅模仿其语言节奏，不得照抄情节） ---\n{content[:320]}")
        return "\n\n".join(parts) if parts else ""

    def _format_worldview(self, world_settings: list) -> str:
        """格式化世界观信息。"""
        if not world_settings:
            return ""
        parts = []
        for s in world_settings:
            if isinstance(s, dict):
                summary = s.get("world_summary", "") or s.get("content", "")
                if summary:
                    parts.append(f"- 世界简介: {summary[:200]}")
                social = s.get("social_common_sense", "")
                if social:
                    parts.append(f"- 社会常识: {social[:200]}")
                factions = s.get("factions_list", [])
                if factions:
                    faction_text = "、".join([f.get("faction_name", "") for f in factions[:5]])
                    parts.append(f"- 主要势力: {faction_text}")
        return "\n".join(parts) if parts else ""

    def _format_power_spec(self, power_system) -> str:
        """格式化力量体系描写规范。"""
        if not power_system or not isinstance(power_system, dict):
            return ""
        lines = []
        system_type = power_system.get("system_type", "")
        if system_type:
            lines.append(f"- 体系类型: {system_type}")
        creed = power_system.get("core_creed", "") or ""
        if creed:
            lines.append(f"- 核心理念: {creed[:200]}")
        cost = power_system.get("cost_rules", "") or ""
        if cost:
            lines.append(f"- 代价规则: {cost[:200]}")
        if lines:
            lines.append("- 描写要求：涉及修炼/战斗/能力使用时，须体现过程与代价，不得超出设定边界")
        return "\n".join(lines) if lines else ""


        """格式化世界观参考文本。"""
        if not world_settings:
            return ""
        world_items = []
        for setting in world_settings[:3]:
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
            return f"\n\n【世界观】\n" + "\n".join(world_items)
        return ""
