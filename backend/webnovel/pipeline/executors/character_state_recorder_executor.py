"""执行器：角色状态记录器（写完一章后提取本章末角色状态）。

从本章成品/草稿内容中提取主要角色章末状态快照，写入 webnovel_character_state，
供下一章上下文分析注入（角色状态连续性）。
"""

import json
from typing import Dict, Any, List

from ..base_executor import BaseExecutor, ExecutorResult
from webnovel.repositories import (
    get_webnovel_project_by_script, get_character_cards_by_project,
    upsert_character_state,
)

EXTRACT_SYSTEM = (
    "你是一位小说章节状态分析助手。阅读给定章节正文，提取各主要角色在本章"
    "【结束时】的状态快照，输出严格的 JSON。只提取正文中实际出场的角色，每角色一条。"
)

EXTRACT_USER = """【角色清单（含ID，仅限清单内角色）】
{char_list}

【章节正文】
{content}

请输出 JSON（不要输出其他内容）：
{{
  "states": [
    {{
      "character_id": 1,
      "character_name": "李承言",
      "location": "章末所在位置",
      "state_summary": "章末身体/处境状态（受伤/体力/得失/异常）",
      "emotion": "章末情绪",
      "knowledge": "本章新获得的信息与认知（无则空字符串）",
      "notes": "其他关键状态变化（无则空字符串）"
    }}
  ]
}}
要求：state_summary/emotion 用一句话概括；knowledge 描述角色本章知晓了哪些新信息（决定知识边界）。持有物品信息统一由 webnovel_character_item 权威清单提供，不要在本块输出。"""


class CharacterStateRecorderExecutor(BaseExecutor):
    """角色状态记录器执行器。"""

    step_name = "character_state_recorder"
    step_description = "角色状态记录"
    step_weight = 5

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """提取本章末角色状态并写入状态表。"""
        try:
            script_id = self.script_id
            chapter_index = self.chapter_index

            content = (context.get("polished_content") or
                       context.get("draft_content") or "")
            if not content:
                return ExecutorResult(
                    success=True,
                    step_summary="角色状态记录跳过：无本章内容",
                    output_data={"state_count": 0},
                )

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="未找到项目信息",
                    step_summary="角色状态记录失败",
                )
            project_id = project["id"]
            cards = get_character_cards_by_project(project_id)
            char_list = "\n".join(
                f"{c.get('name', '')}(id={c.get('id')})" for c in cards if c.get("name")
            )

            prompt = EXTRACT_USER.format(
                char_list=char_list, content=content[:6000])

            from core.model_executor import get_model_executor
            executor = get_model_executor()
            result = await executor.execute_text_chat(
                prompt=prompt,
                system_prompt=EXTRACT_SYSTEM,
                max_tokens=2000,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="character_state_extract",
            )
            raw = (result or {}).get("content", "") if result else ""
            states = self._parse_states(raw)

            count = 0
            for s in states:
                name = s.get("character_name", "")
                cid = s.get("character_id")
                if not cid:
                    continue
                upsert_character_state(
                    project_id=project_id,
                    character_id=cid,
                    character_name=name,
                    chapter_number=chapter_index,
                    location=s.get("location", ""),
                    state_summary=s.get("state_summary", ""),
                    emotion=s.get("emotion", ""),
                    knowledge=s.get("knowledge", ""),
                    notes=s.get("notes", ""),
                )
                count += 1

            return ExecutorResult(
                success=True,
                step_summary=f"角色状态记录完成：{count} 条（第{chapter_index}章）",
                output_data={"state_count": count},
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"角色状态记录执行失败: {str(e)}",
                step_summary="角色状态记录执行失败",
            )

    def _parse_states(self, raw: str) -> List[Dict]:
        """容错解析 LLM 输出 JSON。"""
        if not raw:
            return []
        text = raw.strip()
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < 0:
            return []
        try:
            obj = json.loads(text[start:end + 1])
            states = obj.get("states", [])
            return states if isinstance(states, list) else []
        except Exception:
            return []
