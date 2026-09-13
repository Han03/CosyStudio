"""执行器：章节剧情审查器。

在剧情生成后、草稿生成前，对剧情列表进行多维度质量审查。
采用标记驱动决策：LLM 对问题/建议显式标记是否值得修正，
存在标记项则触发修正（最多2轮），确保好建议被真正落实。
"""

import json
import re
from typing import Dict, Any, List, Optional
from ..base_executor import BaseExecutor, ExecutorResult
from core.model_executor import get_model_executor
from utils.llm_json_parser import parse_llm_json
from webnovel.repositories import (
    get_webnovel_project_by_script, get_character_cards_by_project,
    get_volume_outlines_by_project, add_chapter_plot
)


class ChapterPlotReviewerExecutor(BaseExecutor):
    """章节剧情审查器执行器。"""

    step_name = "chapter_plot_reviewer"
    step_description = "剧情审查"
    step_weight = 8

    REVIEW_DIMENSIONS = [
        {"key": "completeness", "name": "规划覆盖", "description": "是否覆盖了章节规划中的所有关键事件和必须覆盖节点"},
        {"key": "logic", "name": "因果逻辑", "description": "剧情节点之间的因果关系是否合理，有无逻辑断裂或跳跃"},
        {"key": "conflict", "name": "冲突张力", "description": "剧情结构中的冲突设计是否充分，是否有足够的转折和悬念"},
        {"key": "setting_match", "name": "设定匹配", "description": "剧情点行为是否符合角色能力、金手指与世界观规则，有无超出设定边界的行为"},
    ]

    MAX_REVISIONS = 1

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行剧情审查。"""
        try:
            script_id = self.script_id
            chapter_index = self.chapter_index

            chapter_plot = context.get("chapter_plot", [])
            if not chapter_plot:
                return ExecutorResult(
                    success=False,
                    error_message="剧情列表为空，无法审查",
                    step_summary="剧情审查失败"
                )

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="未找到项目信息",
                    step_summary="剧情审查失败"
                )

            project_id = project["id"]
            # 章节规划位于 structural_data（context_builder 输出），不在顶层键
            chapter_plan = (context.get("structural_data") or {}).get("current_chapter_plan") or context.get("current_chapter_plan")

            # 通过 ContextAnalyzer 组装对照上下文（角色能力/金手指/世界观/伏笔）
            from webnovel.pipeline.context_analyzer import ContextAnalyzer
            analyzer = ContextAnalyzer(script_id, chapter_index)
            step_ctx = await analyzer.analyze_and_assemble(
                step_name="chapter_plot_reviewer",
                inventory=context.get("context_inventory", {}),
                structural_data=context.get("structural_data", {}),
                script_id=script_id,
                project_id=project_id,
                prev_selections=context.get("step_selections"),
            )
            current_plot = list(chapter_plot)
            revision_count = 0
            last_review = []

            while revision_count < self.MAX_REVISIONS:
                review_result = await self._review_plot(current_plot, chapter_plan, chapter_index, step_ctx)
                last_review = review_result

                # 标记驱动：存在值得修正的问题或可落实的建议才触发修正，分数仅作观测指标
                has_actionable = any(
                    issue.get("worth_revising")
                    for r in review_result
                    for issue in r.get("issues", [])
                ) or any(
                    r.get("suggestions_actionable") and r.get("suggestions")
                    for r in review_result
                )

                # 无值得修正项 → 通过（分数仅供摘要展示）
                if not has_actionable:
                    break

                # 触发修正
                revised_plot = await self._revise_plot(current_plot, review_result)
                if revised_plot:
                    # 提前终止：修正后与修正前几乎相同（LLM 未做实质修改），继续循环无意义
                    old_text = json.dumps(current_plot, ensure_ascii=False, sort_keys=True)
                    new_text = json.dumps(revised_plot, ensure_ascii=False, sort_keys=True)
                    if len(old_text) > 0 and abs(len(new_text) - len(old_text)) / len(old_text) < 0.05:
                        # 长度变化小于 5%，视为无实质修改，提前退出
                        current_plot = revised_plot
                        break
                    current_plot = revised_plot
                revision_count += 1

            # 更新数据库
            add_chapter_plot(project_id, chapter_index, current_plot)

            avg_score = sum(r["score"] for r in last_review) / len(last_review) if last_review else 0
            summary = f"剧情审查完成：{len(current_plot)}个剧情点，评分{avg_score:.1f}/10"
            if revision_count > 0:
                summary += f"，修正{revision_count}轮"

            # 将修正后的剧情写入 context，供下游 draft_generator 使用
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "chapter_plot": current_plot,
                    "plot_review_score": avg_score,
                    "plot_revision_count": revision_count,
                }
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"剧情审查执行失败: {str(e)}",
                step_summary="剧情审查执行失败"
            )

    def _format_characters(self, characters: list) -> str:
        """构建角色详情文本（含能力/目标/物品）。"""
        if not characters:
            return "（无角色信息）"
        lines = []
        for c in characters:
            if not isinstance(c, dict):
                continue
            name = c.get("character_name", "") or c.get("name", "")
            if not name:
                continue
            line = f"- {name}"
            personality = c.get("personality", "") or c.get("core_personality", "")
            if personality:
                line += f" | 性格: {personality[:80]}"
            flaw = c.get("flaw", "") or c.get("personality_flaw", "")
            if flaw:
                line += f" | 缺陷: {flaw[:60]}"
            identity = c.get("identity", "")
            if identity:
                line += f" | 身份: {identity[:60]}"
            abilities = c.get("abilities", "") or ""
            if abilities:
                line += f" | 能力: {str(abilities)[:100]}"
            goals = c.get("goals", "") or ""
            if goals:
                line += f" | 目标: {str(goals)[:60]}"
            items = c.get("items", []) or []
            item_names = [it.get("name", "") for it in items if isinstance(it, dict) and it.get("name")]
            if item_names:
                line += f" | 持有物品: {'、'.join(item_names[:6])}"
            lines.append(line)
        return "\n".join(lines) if lines else "（无角色信息）"

    def _format_world_settings(self, world_settings: list) -> str:
        """格式化世界观规则文本。"""
        if not world_settings:
            return ""
        parts = []
        for s in world_settings:
            if isinstance(s, dict):
                summary = s.get("world_summary", "") or s.get("content", "")
                if summary:
                    parts.append(f"- 世界简介: {str(summary)[:200]}")
                social = s.get("social_common_sense", "")
                if social:
                    parts.append(f"- 社会常识: {str(social)[:200]}")
                factions = s.get("factions_list", [])
                if factions:
                    names = "、".join(f.get("faction_name", "") for f in factions[:5])
                    parts.append(f"- 主要势力: {names}")
        return "\n".join(parts) if parts else ""

    def _format_foreshadows(self, foreshadows: list) -> str:
        """格式化活跃伏笔文本（含埋设章节）。"""
        if not foreshadows:
            return ""
        lines = []
        for f in foreshadows[:8]:
            tier = f.get("tier", "")
            content = f.get("content", "")
            planted = f.get("planted_chapter") or f.get("planted_ch") or 0
            lines.append(f"- [{tier}] {content} (第{planted}章埋下)")
        return "\n".join(lines) if lines else ""

    async def _review_plot(
        self, plot_list: list, chapter_plan: dict, chapter_index: int,
        step_ctx: Optional[dict] = None,
    ) -> List[Dict[str, Any]]:
        """单次 LLM 调用完成所有维度审查。"""
        project = get_webnovel_project_by_script(self.script_id)
        project_id = project["id"] if project else 0

        # 章节规划信息
        summary = chapter_plan.get("summary", "") if chapter_plan else ""
        key_events = chapter_plan.get("key_events", "") if chapter_plan else ""
        must_cover = ""
        if chapter_plan:
            nodes = chapter_plan.get("must_cover_nodes", [])
            must_cover = json.dumps(nodes, ensure_ascii=False) if nodes else ""

        # 卷纲
        volume_outlines = get_volume_outlines_by_project(project_id)
        current_volume = None
        for vo in volume_outlines:
            if vo.get("chapter_start") <= chapter_index <= vo.get("chapter_end", chapter_index):
                current_volume = vo
                break
        volume_conflict = (current_volume.get("core_conflict", "") or "（未设定）")[:200] if current_volume else ""
        volume_goal = (current_volume.get("protagonist_goal", "") or "（未设定）")[:200] if current_volume else ""

        # 角色（含能力）与金手指，来自 ContextAnalyzer step_ctx；无 ctx 时兜底仅主角三字段
        characters_detail = ""
        world_settings_text = ""
        foreshadow_text = ""
        if step_ctx:
            characters_detail = self._format_characters(step_ctx.get("characters", []))
            undisclosed_text = self._format_undisclosed(
                step_ctx.get("undisclosed_foreshadows", []))
            golden = step_ctx.get("golden_finger") or {}
            if golden:
                gf_lines = [f"- 金手指类型: {golden.get('type', '')}"]
                core = golden.get("core_function") or ""
                if core:
                    gf_lines.append(f"- 核心能力: {core[:200]}")
                cost = golden.get("irreversible_cost") or ""
                if cost:
                    gf_lines.append(f"- 代价: {str(cost)[:150]}")
                characters_detail += "\n【主角金手指】\n" + "\n".join(gf_lines)
            world_settings_text = self._format_world_settings(step_ctx.get("world_settings", []))
            foreshadow_text = self._format_foreshadows(step_ctx.get("foreshadows", []))
        else:
            protagonists = get_character_cards_by_project(project_id, "protagonist")
            if protagonists:
                p = protagonists[0]
                characters_detail = (
                    f"- {p.get('name', '')} | 性格: {p.get('core_personality', '')} | 缺陷: {p.get('personality_flaw', '')}"
                )

        # 维度说明
        dimension_lines = []
        for d in self.REVIEW_DIMENSIONS:
            dimension_lines.append(f"- {d['name']}({d['key']})：{d['description']}")
        dimensions_text = "\n".join(dimension_lines)

        # 剧情文本
        plot_text = json.dumps(plot_list, ensure_ascii=False, indent=2)

        prompt_data = self._load_prompt("chapter_plot_review")
        prompt = prompt_data["user_prompt"].format(
            chapter_index=chapter_index,
            summary=summary,
            key_events=key_events,
            must_cover_nodes=must_cover,
            volume_conflict=volume_conflict,
            volume_goal=volume_goal,
            characters_detail=characters_detail,
            world_settings_text=world_settings_text,
            foreshadow_text=foreshadow_text,
            undisclosed_text=undisclosed_text,
            dimensions_text=dimensions_text,
            plot_text=plot_text,
        )
        system_prompt = prompt_data["system_prompt"]

        executor = get_model_executor()
        result = await executor.execute_text_chat(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=2000,
            script_id=self.script_id,
            project_id=project_id,
            executor_name="chapter_plot_reviewer_score",
            prompt_name=f"plot_review_{chapter_index}",
        )

        content = result.get("content", "") if result else ""
        return self._parse_review_response(content)

    def _parse_review_response(self, content: str) -> List[Dict[str, Any]]:
        """解析审查 LLM 返回的 JSON。"""
        results = []
        try:
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'\s*```', '', content)
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                review_data = json.loads(json_match.group())
            else:
                review_data = {"reviews": []}
        except Exception:
            review_data = {"reviews": []}

        reviews = review_data.get("reviews", [])
        reviewed_keys = set()

        for review in reviews:
            dim_key = review.get("dimension", "")
            score = review.get("score", 5)
            issues = []
            for issue in review.get("issues", []):
                if not isinstance(issue, dict):
                    continue
                severity = issue.get("severity", "")
                # 标记缺省兜底：critical/high/medium 默认值得修正，low 默认不修正；
                # critical/high 无论标记一律强制修正，保底不漏严重问题
                worth = issue.get("worth_revising")
                if severity in ("critical", "high"):
                    worth = True
                elif not isinstance(worth, bool):
                    worth = severity == "medium"
                issue["worth_revising"] = worth
                issues.append(issue)
            suggestions = review.get("suggestions", "")
            suggestions_actionable = bool(review.get("suggestions_actionable", False))

            matched_dim = None
            for d in self.REVIEW_DIMENSIONS:
                if d["key"] == dim_key or d["name"] == review.get("name", ""):
                    matched_dim = d
                    break

            if matched_dim:
                reviewed_keys.add(matched_dim["key"])
                results.append({
                    "dimension": matched_dim["key"],
                    "name": matched_dim["name"],
                    "score": score,
                    "issues": issues,
                    "suggestions": suggestions,
                    "suggestions_actionable": suggestions_actionable,
                })

        # 补全未被 LLM 返回的维度
        for d in self.REVIEW_DIMENSIONS:
            if d["key"] not in reviewed_keys:
                results.append({
                    "dimension": d["key"],
                    "name": d["name"],
                    "score": 5,
                    "issues": [],
                    "suggestions": "",
                })

        return results

    async def _revise_plot(
        self, plot_list: list, review_result: List[Dict[str, Any]]
    ) -> list:
        """根据审查反馈修正剧情列表。"""
        issues = []
        for review in review_result:
            for issue in review.get("issues", []):
                if isinstance(issue, dict):
                    severity = issue.get("severity", "")
                    desc = issue.get("description", "")
                    fix_hint = issue.get("fix_hint", "")
                    # critical/high 无条件收集保底；其余按 worth_revising 标记收集
                    if severity in ("critical", "high") or issue.get("worth_revising"):
                        issues.append(f"【{review['name']}·{severity}】{desc}\n修复建议: {fix_hint}")
            if review.get("suggestions_actionable") and review.get("suggestions"):
                issues.append(f"【{review['name']}】{review['suggestions']}")

        if not issues:
            return None

        original_plot_text = json.dumps(plot_list, ensure_ascii=False, indent=2)
        issues_text = "\n".join(issues)

        prompt_data = self._load_prompt("chapter_plot_revise")
        prompt = prompt_data["user_prompt"].format(
            original_plot_text=original_plot_text,
            issues_text=issues_text,
        )
        system_prompt = prompt_data["system_prompt"]

        project = get_webnovel_project_by_script(self.script_id)
        project_id = project["id"] if project else 0

        executor = get_model_executor()
        result = await executor.execute_text_chat(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=2500,
            script_id=self.script_id,
            project_id=project_id,
            executor_name="chapter_plot_reviewer_revise",
            prompt_name=f"plot_revise_{self.chapter_index}",
        )

        raw_content = result.get("content", "") if result else ""
        if not raw_content:
            return None

        revised_data = parse_llm_json(
            raw_content,
            script_id=self.script_id,
            project_id=project_id,
            executor_name="chapter_plot_reviewer_revise",
            prompt_name=f"plot_revise_{self.chapter_index}",
        )

        if revised_data and "plots" in revised_data:
            return revised_data["plots"]

        return None
