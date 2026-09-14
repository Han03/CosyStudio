"""执行器8：草稿审查器。

审查修改效果有限，最多修改1次。
上下文由 ContextAnalyzer 三段式装配（Analyze→Gather），executor 不再自行拼装；
草稿（draft）为循环内变动的任务输入，由模板占位符实时注入。
"""

import re
import json
from typing import Dict, Any, List, Optional
from ..base_executor import BaseExecutor, ExecutorResult
from ..context_analyzer import ContextAnalyzer
from utils.llm_json_parser import parse_llm_json
from utils.logger import log_manager
from webnovel.repositories import get_webnovel_project_by_script


class DraftReviewerExecutor(BaseExecutor):
    """草稿审查器执行器。"""

    step_name = "draft_reviewer"
    step_description = "草稿审查"
    step_weight = 15

    REVIEW_DIMENSIONS = [
        {"key": "excitement", "name": "爽点呈现", "description": "爽点是否在正文中得到充分展现，是否有足够的感染力"},
        {"key": "consistency", "name": "设定一致", "description": "人物性格、能力、世界观设定在正文中是否保持一致，角色行为是否符合性格；同时核对：角色状态连续（受伤/恢复/情绪）、物品持有与使用是否遵循清单（禁止凭空出现）、有无说出超出自身知识边界的信息"},
        {"key": "rhythm", "name": "节奏控制", "description": "文字节奏是否合理，场景详略是否得当"},
        {"key": "coherence", "name": "叙事连贯", "description": "叙事是否连贯流畅，有无突兀跳跃或断裂；时间线是否自洽（事件先后、日夜/季节）"},
        {"key": "retention", "name": "结尾自然度", "description": "章节是否收尾于自然节拍，让读者无感知地滑入下一章；设问收束、旁白预告、总结预言、公式化追加悬念应扣分；不要因缺少显式钩子扣分"},
    ]

    MAX_REVISIONS = 1

    def __init__(self, script_id: int, chapter_index: int, task_id: int):
        super().__init__(script_id, chapter_index, task_id)
        self._logger = log_manager.get_logger("draft_reviewer_executor")

    PASS_AVG_SCORE = 8

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行草稿审查，最多修改1次。"""
        try:
            script_id = self.script_id
            draft_content = context.get("draft_content", "")

            if not draft_content:
                return ExecutorResult(
                    success=False,
                    error_message="草稿内容为空",
                    step_summary="草稿审查失败"
                )

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="未找到项目信息",
                    step_summary="草稿审查失败"
                )
            project_id = project["id"]

            # ── 通过 ContextAnalyzer 三段式装配上下文（审查循环共用） ──
            analyzer = ContextAnalyzer(script_id, self.chapter_index)
            step_ctx = await analyzer.analyze_and_assemble(
                step_name="draft_reviewer",
                inventory=context.get("context_inventory", {}),
                structural_data=context.get("structural_data", {}),
                script_id=script_id,
                project_id=project_id,
                prev_selections=context.get("step_selections"),
            )

            # 记录本步骤的选择结果
            if "step_selections" not in context:
                context["step_selections"] = {}
            selection = step_ctx.get("_selection", {})
            context["step_selections"]["draft_reviewer"] = {
                "character_names": [
                    c.get("character_name", "") for c in step_ctx.get("characters", [])
                ],
                "consistency_notes": selection.get("custom_notes", []),
            }

            review_history = []
            current_draft = draft_content
            revision_count = 0

            # 最优版本保护
            best_draft = draft_content
            best_avg_score = -1.0
            best_review_result = []

            word_cfg = context.get("word_config") or {}

            while revision_count < self.MAX_REVISIONS:
                review_result = await self._review_draft(current_draft, step_ctx, project_id)
                review_history.append({
                    "revision": revision_count + 1,
                    "review_result": review_result
                })

                avg_score = sum(r["score"] for r in review_result) / len(review_result)

                has_actionable = any(
                    issue.get("worth_revising")
                    for r in review_result
                    for issue in r.get("issues", [])
                ) or any(
                    r.get("suggestions_actionable") and r.get("suggestions")
                    for r in review_result
                )

                if avg_score > best_avg_score:
                    best_avg_score = avg_score
                    best_draft = current_draft
                    best_review_result = review_result

                if not has_actionable:
                    break

                if revision_count > 0 and avg_score < best_avg_score:
                    self._logger.info(
                        f"第{revision_count + 1}轮审查均分{avg_score:.2f}低于最优{best_avg_score:.2f}，回退最优版本"
                    )
                    break

                revision_count += 1
                revised = await self._revise_draft(
                    current_draft, review_result, step_ctx, project_id, word_cfg)

                if revised and len(current_draft) > 0:
                    change_ratio = abs(len(revised) - len(current_draft)) / len(current_draft)
                    if change_ratio < 0.05:
                        self._logger.info(
                            f"第{revision_count}轮修改长度变化{change_ratio:.1%}<5%，视为收敛，提前退出"
                        )
                        current_draft = revised
                        break

                current_draft = revised
                if not current_draft.strip():
                    break

            final_avg_score = best_avg_score if best_avg_score >= 0 else 0

            summary = (
                f"草稿审查完成：经过{revision_count}次修改，"
                f"最优平均评分{final_avg_score:.1f}/10"
            )

            # 保存草稿修改历史
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "review_result": best_review_result,
                    "reviewed_draft": best_draft,
                    "review_history": review_history,
                    "avg_score": final_avg_score,
                }
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"草稿审查执行失败: {str(e)}",
                step_summary="草稿审查执行失败"
            )

    async def _review_draft(
        self, draft: str, step_ctx: Dict[str, Any], project_id: int
    ) -> List[Dict[str, Any]]:
        """审查草稿（单次LLM调用完成所有维度）。"""
        prompt_data = self._load_prompt("review_draft")
        prompt = prompt_data["user_prompt"].format(
            assembled_context=step_ctx.get("assembled_context", ""),
            draft=draft,
        )
        system_prompt = prompt_data["system_prompt"] or "你是一位资深网文编辑，擅长从多维度进行草稿质量审查，输出严格的JSON格式"

        from core.model_executor import get_model_executor
        executor = get_model_executor()

        result = await executor.execute_text_chat(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=3000,
            script_id=self.script_id,
            project_id=project_id,
            executor_name="draft_reviewer_score",
            prompt_name="review_all_dimensions",
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
            dim_name = review.get("name", "")
            score = review.get("score", 5)
            issues = review.get("issues", [])
            suggestions = review.get("suggestions", "")
            suggestions_actionable = bool(review.get("suggestions_actionable", False))

            for issue in issues:
                if not isinstance(issue, dict):
                    continue
                severity = issue.get("severity", "")
                worth = issue.get("worth_revising")
                if severity in ("critical", "high"):
                    worth = True
                elif not isinstance(worth, bool):
                    worth = severity == "medium"
                issue["worth_revising"] = worth

            matched_dim = None
            for d in self.REVIEW_DIMENSIONS:
                if d["key"] == dim_key or d["name"] == dim_name:
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

        for d in self.REVIEW_DIMENSIONS:
            if d["key"] not in reviewed_keys:
                results.append({
                    "dimension": d["key"],
                    "name": d["name"],
                    "score": 5,
                    "issues": [],
                    "suggestions": "",
                    "suggestions_actionable": False,
                })

        return results

    async def _revise_draft(
        self, draft: str, review_result: List[Dict[str, Any]],
        step_ctx: Dict[str, Any], project_id: int,
        word_cfg: Optional[Dict[str, Any]] = None,
    ) -> str:
        """根据审查结果修改草稿。"""
        issues = []
        suggestions = []

        for review in review_result:
            for issue in review.get("issues", []):
                if isinstance(issue, dict) and 'severity' in issue and 'description' in issue:
                    severity = issue.get('severity', '')
                    description = issue.get('description', '')
                    location = issue.get('location', '')
                    fix_hint = issue.get('fix_hint', '')

                    if severity in ("critical", "high") or issue.get("worth_revising"):
                        issues.append(f"【{severity}】{location}: {description}\n修复建议: {fix_hint}")

            if review.get("suggestions_actionable") and review.get("suggestions"):
                suggestions.append(f"- [{review['name']}] {review['suggestions']}")

        prompt_data = self._load_prompt("revise_draft")
        word_cfg = word_cfg or {}
        prompt = prompt_data["user_prompt"].format(
            issues_text=chr(10).join(issues),
            suggestions_text=chr(10).join(suggestions),
            draft=draft,
            assembled_context=step_ctx.get("assembled_context", ""),
            draft_word_min=int(word_cfg.get("draft_word_min", 1200)),
            draft_word_max=int(word_cfg.get("draft_word_max", 1800)),
        )
        system_prompt = prompt_data["system_prompt"] or "你是一位专业的网文编辑，擅长修改草稿，输出严格的JSON格式"

        from core.model_executor import get_model_executor
        executor = get_model_executor()

        result = await executor.execute_text_chat(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max(3000, int(word_cfg.get("draft_word_max", 1800)) * 3),
            script_id=self.script_id,
            project_id=project_id,
            executor_name="draft_reviewer_revise",
            prompt_name="revise_draft",
        )

        raw_content = result.get("content", "") if result else ""
        if not raw_content:
            return draft

        revised_data = parse_llm_json(
            raw_content,
            script_id=self.script_id,
            project_id=project_id,
            executor_name="draft_reviewer_revise",
            prompt_name="revise_draft",
        )

        if revised_data and "content" in revised_data:
            return revised_data["content"].strip()

        return raw_content.strip() if raw_content.strip() else draft
