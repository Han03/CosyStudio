"""执行器：质量审查执行器。

参考webnovel-writer的webnovel-review SKILL，实现质量审查功能。
"""

import json
import re
from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from core.model_executor import get_model_executor
from webnovel.repositories import get_webnovel_project_by_script, get_character_cards_by_project, get_worldview_by_project
from repositories import get_script_lines


class ReviewExecutor(BaseExecutor):
    """质量审查执行器。"""

    step_name = "review_executor"
    step_description = "质量审查"
    step_weight = 15

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行质量审查。"""
        try:
            script_id = self.script_id
            chapter_index = self.chapter_index
            draft = context.get("draft", "")

            if not draft:
                return ExecutorResult(
                    success=False,
                    error_message="草稿内容为空",
                    step_summary="草稿内容为空"
                )

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="项目不存在",
                    step_summary="项目不存在"
                )

            characters = get_character_cards_by_project(project["id"])
            worldview = get_worldview_by_project(project["id"])
            world_settings = [worldview] if worldview else []

            previous_content = ""
            for i in range(max(0, chapter_index - 2), chapter_index):
                lines = get_script_lines(script_id, i)
                if lines:
                    content = "\n".join(line["content"] for line in lines)
                    previous_content += content[:1000] + "\n"

            executor = get_model_executor()

            prompt = f"""请作为专业网文编辑，从多个维度审查以下章节内容：

【审查维度】
- 爽点设计：是否有足够的爽点，打脸、逆袭、升级是否爽快有力
- 设定一致性：人物性格、设定、世界观是否保持一致
- 节奏控制：情节推进是否合理，张弛有度，是否有拖沓
- OOC检查：人物行为是否符合其设定，是否有OOC行为
- 逻辑连贯：情节是否连贯，逻辑是否通顺
- 追读力：是否能吸引读者继续阅读，是否有悬念和钩子
- 对话质量：对话是否符合人物性格，是否有潜台词，是否生动
- 描写水平：场景、情感描写是否有画面感，是否调动五感

【上下文】
书名：{project['title']}
题材：{project['genre']}
世界观设定: {json.dumps([s['name'] for s in world_settings], ensure_ascii=False)}
角色列表: {json.dumps([c['name'] for c in characters], ensure_ascii=False)}
前文内容: {previous_content[:500]}

【章节内容】
{draft[:5000]}

【审查要求】
请按照以下格式输出JSON：
{{
    "reviews": [
        {{
            "dimension": "审查维度",
            "name": "维度名称",
            "score": 1-10的整数评分,
            "issues": [
                {{
                    "severity": "critical/high/medium/low",
                    "location": "问题位置描述",
                    "description": "问题详细描述",
                    "evidence": "原文引用或上下文对比",
                    "fix_hint": "修复建议"
                }}
            ],
            "strengths": ["优点1", "优点2"],
            "suggestions": "综合修改建议"
        }}
    ]
}}

注意：
- severity=critical 表示严重问题，需要强制修改
- severity=high 表示重要问题，建议修改
- severity=medium/low 表示一般问题，可选择性修改
- issues数组可以为空（如果没有问题）"""

            result = await executor.execute_text_chat(
                prompt=prompt,
                system_prompt="你是一位专业的网文编辑，擅长从多维度进行审查，输出严格的JSON格式",
                max_tokens=3000,
                script_id=script_id,
                project_id=project["id"],
                executor_name="review_executor",
                prompt_name="review_quality",
            )

            content = result.get("content", "") if result else ""
            try:
                content = content.replace("```json", "").replace("```", "")
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    review_data = json.loads(json_match.group())
                else:
                    review_data = {"reviews": []}
            except:
                review_data = {"reviews": []}

            reviews = review_data.get("reviews", [])
            blocking_issues = []
            total_score = 0
            count = 0

            for review in reviews:
                score = review.get("score", 5)
                total_score += score
                count += 1

                for issue in review.get("issues", []):
                    if isinstance(issue, dict) and issue.get("severity") == "critical":
                        blocking_issues.append(issue)

            avg_score = total_score / count if count > 0 else 0

            summary = f"审查完成：平均评分{avg_score:.1f}，{len(blocking_issues)}个严重问题"
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "review_result": reviews,
                    "average_score": avg_score,
                    "blocking_issues": blocking_issues,
                    "total_reviews": len(reviews)
                }
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"质量审查执行失败: {str(e)}",
                step_summary="质量审查执行失败"
            )