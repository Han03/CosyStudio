"""执行器：项目学习执行器。

参考webnovel-writer的webnovel-learn SKILL，实现项目学习功能。
"""

import json
import os
from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from core.model_executor import get_model_executor
from webnovel.repositories import get_webnovel_project_by_script, add_webnovel_state


class LearnExecutor(BaseExecutor):
    """项目学习执行器。"""

    step_name = "learn_executor"
    step_description = "项目学习"
    step_weight = 5

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行项目学习。"""
        try:
            script_id = self.script_id
            learning_content = context.get("learning_content", "")

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="项目不存在",
                    step_summary="项目不存在"
                )
            project_id = project["id"]

            current_chapter = context.get("current_chapter", 0)

            executor = get_model_executor()

            # 从 .md 文件加载 prompt 模板
            prompt_data = self._load_prompt("learn_pattern")
            prompt = prompt_data["user_prompt"].format(
                project_title=project['title'],
                genre=project['genre'],
                current_chapter=current_chapter,
                learning_content=learning_content,
            )
            system_prompt = prompt_data["system_prompt"] or "你是一位专业的网文写作模式分析专家，擅长从成功案例中提取可复用的写作模式"

            result = await executor.execute_text_chat(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=1000,
                script_id=script_id,
                project_id=project_id,
                executor_name="learn_executor",
                prompt_name="learn_patterns",
            )

            content = result.get("content", "") if result else ""
            try:
                content = content.replace("```json", "").replace("```", "")
                learn_result = json.loads(content)
            except:
                learn_result = {
                    "patterns": [
                        {
                            "pattern_type": "other",
                            "description": learning_content[:500],
                            "category": "",
                            "importance": "medium",
                            "applicable_scenarios": []
                        }
                    ]
                }

            project_memory_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "cache", f"project_memory_{project_id}.json"
            )

            if os.path.exists(project_memory_path):
                with open(project_memory_path, "r", encoding="utf-8") as f:
                    memory_data = json.load(f)
            else:
                memory_data = {"patterns": []}

            new_patterns = []
            for pattern in learn_result.get("patterns", []):
                exists = False
                for existing in memory_data["patterns"]:
                    if existing.get("pattern_type") == pattern.get("pattern_type") and \
                       existing.get("description") == pattern.get("description"):
                        exists = True
                        break
                if not exists:
                    memory_data["patterns"].append(pattern)
                    new_patterns.append(pattern)

            with open(project_memory_path, "w", encoding="utf-8") as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=2)

            summary = f"学习完成：新增{len(new_patterns)}个写作模式"
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={"learned_patterns": new_patterns, "total_patterns": len(memory_data["patterns"])}
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"项目学习执行失败: {str(e)}",
                step_summary="项目学习执行失败"
            )