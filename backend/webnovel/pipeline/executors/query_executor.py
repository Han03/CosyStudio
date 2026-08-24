"""执行器：状态查询执行器。

参考webnovel-writer的webnovel-query SKILL，实现状态查询功能。
"""

import json
from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from core.model_executor import get_model_executor
from webnovel.repositories import (
    get_webnovel_project_by_script, get_character_cards_by_project,
    get_golden_finger_by_project, get_power_system_by_project,
    get_worldview_by_project, get_volume_outlines_by_project,
    get_plot_threads
)


class QueryExecutor(BaseExecutor):
    """状态查询执行器。"""

    step_name = "query_executor"
    step_description = "状态查询"
    step_weight = 5

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行状态查询。"""
        try:
            script_id = self.script_id
            query_type = context.get("query_type", "")
            query_question = context.get("query_question", "")

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="项目不存在",
                    step_summary="项目不存在"
                )
            project_id = project["id"]

            characters = get_character_cards_by_project(project_id)
            golden_finger = get_golden_finger_by_project(project_id)
            power_system = get_power_system_by_project(project_id)
            worldview = get_worldview_by_project(project_id)

            executor = get_model_executor()

            foreshadowings = []
            # 从 .md 文件加载 prompt 模板
            prompt_data = self._load_prompt("query")
            prompt = prompt_data["user_prompt"].format(
                project_title=project['title'],
                genre=project['genre'],
                query_type=query_type,
                query_question=query_question,
                characters=json.dumps(characters, ensure_ascii=False, default=str),
                power_system=json.dumps(power_system, ensure_ascii=False, default=str) if power_system else '{}',
                worldview=json.dumps(worldview, ensure_ascii=False, default=str) if worldview else '{}',
                golden_finger=json.dumps(golden_finger, ensure_ascii=False, default=str) if golden_finger else '{}',
                foreshadowings=json.dumps(foreshadowings, ensure_ascii=False, default=str),
            )
            system_prompt = prompt_data["system_prompt"] or "你是一位专业的网文知识查询助手，擅长从项目设定中提取准确信息"

            result = await executor.execute_text_chat(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=1500,
                script_id=script_id,
                project_id=project_id,
                executor_name="query_executor",
                prompt_name="query_lookup",
            )

            content = result.get("content", "") if result else ""
            try:
                content = content.replace("```json", "").replace("```", "")
                query_result = json.loads(content)
            except:
                query_result = {
                    "query_type": query_type,
                    "query_question": query_question,
                    "answer": content,
                    "sources": [],
                    "related_info": {}
                }

            return ExecutorResult(
                success=True,
                step_summary=f"查询完成：{query_type}",
                output_data={"query_result": query_result}
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"状态查询执行失败: {str(e)}",
                step_summary="状态查询执行失败"
            )