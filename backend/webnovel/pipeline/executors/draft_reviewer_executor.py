"""执行器8：草稿审查器。

参考webnovel-writer。但是要能根据审查结果反复多次修改草稿，上限3次。
"""

import re
import json
from typing import Dict, Any, List
from ..base_executor import BaseExecutor, ExecutorResult
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
        {"key": "consistency", "name": "设定一致", "description": "人物性格、能力、世界观设定在正文中是否保持一致，角色行为是否符合性格"},
        {"key": "rhythm", "name": "节奏控制", "description": "文字节奏是否合理，场景详略是否得当"},
        {"key": "coherence", "name": "叙事连贯", "description": "叙事是否连贯流畅，有无突兀跳跃或断裂"},
        {"key": "retention", "name": "结尾自然度", "description": "章节是否收尾于自然节拍，让读者无感知地滑入下一章；设问收束、旁白预告、总结预言、公式化追加悬念应扣分；不要因缺少显式钩子扣分"},
    ]

    MAX_REVISIONS = 3

    def __init__(self, script_id: int, chapter_index: int, task_id: int):
        super().__init__(script_id, chapter_index, task_id)
        self._logger = log_manager.get_logger("draft_reviewer_executor")

    # 审查通过均分阈值：白描草稿不包含文笔细节，审查聚焦剧情/设定/结构，
    # 达标线相应提高，推动多轮修改直到骨架质量足够高再交给润色。
    PASS_AVG_SCORE = 8

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行草稿审查，支持最多3次修改。"""
        try:
            script_id = self.script_id
            draft_content = context.get("draft_content", "")
            
            if not draft_content:
                return ExecutorResult(
                    success=False,
                    error_message="草稿内容为空",
                    step_summary="草稿审查失败"
                )

            writing_context = context.get("writing_context", {})
            review_history = []
            current_draft = draft_content
            revision_count = 0

            # 最优版本保护：每轮审查后记录最高分版本，避免多轮修改后
            # 草稿反而退化（如修改环节压缩内容导致分数逐轮下降）时，
            # 最终采用的却是得分最低的最后版本。
            best_draft = draft_content
            best_avg_score = -1.0
            best_review_result = []

            while revision_count < self.MAX_REVISIONS:
                review_result = await self._review_draft(current_draft, writing_context)
                review_history.append({
                    "revision": revision_count + 1,
                    "review_result": review_result
                })

                avg_score = sum(r["score"] for r in review_result) / len(review_result)
                
                has_critical_issues = any(
                    issue.get("severity") == "critical"
                    for r in review_result
                    for issue in r.get("issues", [])
                )

                if avg_score > best_avg_score:
                    best_avg_score = avg_score
                    best_draft = current_draft
                    best_review_result = review_result

                if avg_score >= self.PASS_AVG_SCORE and not has_critical_issues:
                    break

                # 分数相对最优版本下降，继续修改难以收敛，回退到最优版本停止
                if revision_count > 0 and avg_score < best_avg_score:
                    self._logger.info(
                        f"第{revision_count + 1}轮审查均分{avg_score:.2f}低于最优{best_avg_score:.2f}，回退最优版本"
                    )
                    break

                revision_count += 1
                current_draft = await self._revise_draft(current_draft, review_result)

                if not current_draft.strip():
                    break

            final_avg_score = best_avg_score if best_avg_score >= 0 else 0
            
            summary = (
                f"草稿审查完成：经过{revision_count}次修改，"
                f"最优平均评分{final_avg_score:.1f}/10"
            )
            
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "review_result": best_review_result or (review_history[-1]["review_result"] if review_history else []),
                    "review_history": review_history,
                    "revised_draft": best_draft,
                    "revision_count": revision_count,
                    "final_avg_score": final_avg_score
                }
            )
            
        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"草稿审查执行失败: {str(e)}",
                step_summary="草稿审查执行失败"
            )

    async def _review_draft(self, draft: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """审查草稿（单次LLM调用完成所有维度）。"""
        # 构建上下文文本
        world_settings_text = []
        for s in context.get('world_settings', []):
            if isinstance(s, dict):
                if s.get('name'):
                    world_settings_text.append(s['name'])
                elif s.get('world_summary'):
                    world_settings_text.append(s['world_summary'][:50])
                else:
                    world_settings_text.append("世界观设定")

        characters_text = []
        for c in context.get('characters', []):
            if isinstance(c, dict):
                if c.get('role'):
                    characters_text.append(c['role'])
                elif c.get('character_name'):
                    characters_text.append(c['character_name'])
                else:
                    characters_text.append("角色")

        # 构建维度说明列表
        dimension_lines = []
        for d in self.REVIEW_DIMENSIONS:
            dimension_lines.append(f"- {d['name']}({d['key']})：{d['description']}")
        dimensions_text = "\n".join(dimension_lines)

        # 从 .md 文件加载 prompt 模板
        prompt_data = self._load_prompt("review_draft")
        prompt = prompt_data["user_prompt"].format(
            dimensions_text=dimensions_text,
            world_settings_text=json.dumps(world_settings_text, ensure_ascii=False),
            characters_text=json.dumps(characters_text, ensure_ascii=False),
            draft=draft[:3000],
        )
        system_prompt = prompt_data["system_prompt"] or "你是一位专业的网文编辑，擅长从多维度进行质量审查，输出严格的JSON格式"

        from core.model_executor import get_model_executor
        executor = get_model_executor()

        project = get_webnovel_project_by_script(self.script_id)
        project_id = project["id"] if project else 0

        result = await executor.execute_text_chat(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=2000,
            script_id=self.script_id,
            project_id=project_id,
            executor_name="draft_reviewer_executor",
            prompt_name="review_all_dimensions",
        )

        content = result.get("content", "") if result else ""
        results = []

        try:
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'\s*```', '', content)

            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                review_data = json.loads(json_match.group())
            else:
                review_data = {"reviews": []}
        except:
            review_data = {"reviews": []}

        reviews = review_data.get("reviews", [])

        # 将LLM返回的reviews映射到标准格式
        reviewed_keys = set()
        for review in reviews:
            dim_key = review.get("dimension", "")
            dim_name = review.get("name", "")
            score = review.get("score", 5)
            issues = review.get("issues", [])
            suggestions = review.get("suggestions", "")

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
                })

        # 补全未被LLM返回的维度
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

    async def _revise_draft(self, draft: str, review_result: List[Dict[str, Any]]) -> str:
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

                    if severity in ["critical", "high"]:
                        issues.append(f"【{severity}】{location}: {description}\n修复建议: {fix_hint}")

            if review.get("suggestions"):
                suggestions.append(f"- [{review['name']}] {review['suggestions']}")

        # 从 .md 文件加载 prompt 模板
        prompt_data = self._load_prompt("revise_draft")
        prompt = prompt_data["user_prompt"].format(
            issues_text=chr(10).join(issues),
            suggestions_text=chr(10).join(suggestions),
            draft=draft,
        )
        system_prompt = prompt_data["system_prompt"] or "你是一位专业的网文编辑，擅长修改草稿，输出严格的JSON格式"

        from core.model_executor import get_model_executor
        executor = get_model_executor()

        project = get_webnovel_project_by_script(self.script_id)
        project_id = project["id"] if project else 0

        result = await executor.execute_text_chat(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=3000,
            script_id=self.script_id,
            project_id=project_id,
            executor_name="draft_reviewer_executor",
            prompt_name="revise_draft",
        )

        raw_content = result.get("content", "") if result else ""
        if not raw_content:
            return draft

        # 尝试JSON解析，提取修改后的草稿内容
        revised_data = parse_llm_json(
            raw_content,
            script_id=self.script_id,
            project_id=project_id,
            executor_name="draft_reviewer_executor",
            prompt_name="revise_draft",
        )

        if revised_data and "content" in revised_data:
            return revised_data["content"].strip()

        # JSON解析失败，回退到原始文本
        return raw_content.strip() if raw_content.strip() else draft