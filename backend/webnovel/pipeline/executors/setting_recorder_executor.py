"""执行器5：设定记录器。

参考webnovel-writer，能更新和追加设定。
若是一些明确的需要给读者解读的知识点，要能联网搜索，避免错误信息。
整理搜索结果记录到名词解释里。
"""

import re
from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from webnovel.repositories import get_webnovel_project_by_script, get_worldview_by_project, add_worldview


class SettingRecorderExecutor(BaseExecutor):
    """设定记录器执行器。"""

    step_name = "setting_recorder"
    step_description = "设定记录"
    step_weight = 10

    KNOWLEDGE_KEYWORDS = [
        "历史事件", "历史人物", "地理位置", "科学概念", "文化习俗",
        "传统节日", "古代官职", "兵器名称", "诗词典故", "成语出处"
    ]

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行设定记录。"""
        try:
            script_id = self.script_id
            
            project = get_webnovel_project_by_script(script_id)
            if project:
                worldview = get_worldview_by_project(project["id"])
                world_settings = [worldview] if worldview else []
            else:
                world_settings = []

            user_prompt = context.get("user_prompt", "")
            draft_content = context.get("draft_content", "")
            writing_brief = context.get("writing_brief", "")
            
            combined_text = "\n".join([user_prompt, draft_content, writing_brief])
            
            new_settings = []

            for line in combined_text.split("\n"):
                line = line.strip()
                if not line:
                    continue

                if line.startswith("[设定]"):
                    parts = line[4:].split(":", 1)
                    if len(parts) == 2:
                        name = parts[0].strip()
                        content = parts[1].strip()
                        
                        if project:
                            worldview = get_worldview_by_project(project["id"])
                            if worldview:
                                new_summary = worldview.get("world_summary", "")
                                if new_summary:
                                    new_summary += f"\n\n{name}: {content}"
                                else:
                                    new_summary = f"{name}: {content}"
                                pass
                            else:
                                worldview = add_worldview(
                                    project_id=project["id"],
                                    world_summary=f"{name}: {content}",
                                )
                                new_settings.append(worldview)

                

            

            if project:
                worldview = get_worldview_by_project(project["id"])
                world_settings = [worldview] if worldview else []
            else:
                world_settings = []
            
            summary = f"设定记录完成：新增{len(new_settings)}条设定"
            
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "world_settings": world_settings,
                    "new_settings_count": len(new_settings),
                }
            )
            
        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"设定记录执行失败: {str(e)}",
                step_summary="设定记录执行失败"
            )

    async def _search_knowledge(self, term: str) -> str:
        """联网搜索知识点。"""
        try:
            from core.model_executor import get_model_executor
            
            project = get_webnovel_project_by_script(self.script_id)
            project_id = project["id"] if project else 0
            
            # 从 .md 文件加载 prompt 模板
            prompt_data = self._load_prompt("knowledge_explain")
            prompt = prompt_data["user_prompt"].format(term=term)
            system_prompt = prompt_data["system_prompt"] or "你是一位知识渊博的百科全书助手，擅长准确解释各种知识点"
            
            executor = get_model_executor()
            result = await executor.execute_text_chat(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=300,
                script_id=self.script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="knowledge_explain",
            )
            
            return result.get("content", "") if result else ""
        except Exception:
            return ""
