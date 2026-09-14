"""执行器：章节剧情审查器。

在剧情生成后、草稿生成前，对剧情列表进行多维度质量审查。
采用标记驱动决策：LLM 对问题/建议显式标记是否值得修正，
存在标记项则触发修正（最多2轮），确保好建议被真正落实。

上下文由 ContextAnalyzer 三段式装配（Analyze→Gather），executor 不再自行拼装；
待审查剧情（plot_list）为循环内变动的任务输入，由模板占位符实时注入。
"""

import json
from typing import Dict, Any, List, Optional
from ..base_executor import BaseExecutor, ExecutorResult
from ..context_analyzer import ContextAnalyzer
from core.model_executor import get_model_executor
from utils.llm_json_parser import parse_llm_json
from webnovel.repositories import (
    get_webnovel_project_by_script, add_chapter_plot
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

            # 通过 ContextAnalyzer 三段式装配对照上下文（角色能力/金手指/世界观/伏笔）
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
                review_result = await self._review_plot(current_plot, chapter_index, step_ctx, context.get("word_config") or {})
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
                revised_plot = await self._revise_plot(
                    current_plot, review_result, context.get("word_config") or {})
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

    async def _review_plot(
        self, plot_list: list, chapter_index: int,
        step_ctx: Optional[Dict[str, Any]] = None,
        word_cfg: Dict[str, Any] = None,
    ) -> List[Dict[str, Any]]:
        """单次 LLM 调用完成所有维度审查。"""
        project = get_webnovel_project_by_script(self.script_id)
        project_id = project["id"] if project else 0

        # 待审查剧情文本（循环内实时，可能经修正更新）
        plot_text = json.dumps(plot_list, ensure_ascii=False, indent=2)

        prompt_data = self._load_prompt("chapter_plot_review")
        prompt = prompt_data["user_prompt"].format(
            chapter_index=chapter_index,
            assembled_context=step_ctx.get("assembled_context", "") if step_ctx else "",
            plot_text=plot_text,
        )
        system_prompt = prompt_data["system_prompt"]

        executor = get_model_executor()
        result = await executor.execute_text_chat(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=int((word_cfg or {}).get("review_max_tokens", 800)),
            script_id=self.script_id,
            project_id=project_id,
            executor_name="chapter_plot_reviewer_score",
            prompt_name=f"plot_review_{chapter_index}",
        )

        content = result.get("content", "") if result else ""
        return self._parse_review_response(
            content,
            project_id=project_id,
            executor_name="chapter_plot_reviewer_score",
            prompt_name=f"plot_review_{chapter_index}",
        )

    def _parse_review_response(
        self, content: str, *, project_id: int = 0,
        executor_name: str = "", prompt_name: str = ""
    ) -> List[Dict[str, Any]]:
        """解析审查 LLM 返回的 JSON。

        统一走 parse_llm_json：既复用其容错策略，也让日志里的 parse_success
        反映真实解析结果（此前自定义 json.loads 绕过统一解析，导致日志中
        plot_review_* 恒为 parse_ok=0% 的假象）。
        """
        results = []
        review_data = parse_llm_json(
            content,
            script_id=self.script_id,
            project_id=project_id,
            executor_name=executor_name,
            prompt_name=prompt_name,
        )
        if not review_data or not isinstance(review_data, dict):
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
        self, plot_list: list, review_result: List[Dict[str, Any]], word_cfg: Dict[str, Any] = None
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
            max_tokens=int((word_cfg or {}).get("plot_revise_max_tokens", 2500)),
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
