"""执行器10：事实记录器。

完全参考webnovel-writer的记录事实。
"""

import json
from typing import Dict, Any, List
from ..base_executor import BaseExecutor, ExecutorResult
from utils.llm_json_parser import parse_llm_json
from webnovel.repositories import (
    get_webnovel_project_by_script,
    get_character_cards_by_project, add_character_relationship, update_character_card,
    add_character_growth, get_character_power, add_character_power, add_character_card
)


class FactRecorderExecutor(BaseExecutor):
    """事实记录器执行器。"""

    step_name = "fact_recorder"
    step_description = "事实记录"
    step_weight = 10

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行事实记录。"""
        try:
            script_id = self.script_id
            
            polished_content = context.get("polished_content", "") or context.get("revised_draft", "") or context.get("draft_content", "")
            
            if not polished_content:
                return ExecutorResult(
                    success=True,
                    step_summary="润色内容为空，跳过事实记录",
                    output_data={"facts": []}
                )

            writing_context = context.get("writing_context", {})

            world_settings_text = []
            for s in writing_context.get('world_settings', []):
                if isinstance(s, dict):
                    if s.get('name'):
                        world_settings_text.append(s['name'])
                    elif s.get('world_summary'):
                        world_settings_text.append(s['world_summary'][:50])
                    else:
                        world_settings_text.append("世界观设定")
            
            characters_text = []
            for c in writing_context.get('characters', []):
                if isinstance(c, dict):
                    if c.get('role'):
                        characters_text.append(c['role'])
                    elif c.get('character_name'):
                        characters_text.append(c['character_name'])
                    else:
                        characters_text.append("角色")

            # 从 .md 文件加载 prompt 模板
            prompt_data = self._load_prompt("fact_record")
            prompt = prompt_data["user_prompt"].format(
                chapter_content=polished_content[:2000],
                world_settings=json.dumps(world_settings_text, ensure_ascii=False),
                characters=json.dumps(characters_text, ensure_ascii=False),
            )
            system_prompt = prompt_data["system_prompt"] or "你是一位专业的内容分析助手，擅长提取文本中的关键信息，输出严格的JSON格式"

            from core.model_executor import get_model_executor
            executor = get_model_executor()

            project = get_webnovel_project_by_script(script_id)
            project_id = project["id"] if project else 0

            result = await executor.execute_text_chat(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=800,
                script_id=script_id,
                project_id=project_id,
                executor_name="fact_recorder_executor",
                prompt_name="fact_record",
            )

            content = result.get("content", "") if result else ""
            facts = []

            # 尝试JSON解析
            fact_data = parse_llm_json(
                content,
                script_id=script_id,
                project_id=project_id,
                executor_name="fact_recorder_executor",
                prompt_name="fact_record",
            )

            if fact_data and "facts" in fact_data:
                for fact in fact_data["facts"]:
                    if isinstance(fact, dict) and fact.get("type") and fact.get("content"):
                        facts.append({
                            "type": fact["type"],
                            "content": fact["content"]
                        })
            else:
                # JSON解析失败，回退到旧的文本格式解析
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith("- "):
                        parts = line[2:].split(":", 1)
                        if len(parts) == 2:
                            fact_type = parts[0].strip()
                            fact_content = parts[1].strip()
                            facts.append({
                                "type": fact_type,
                                "content": fact_content
                            })

            if facts:
                # 根据事实更新角色关系和角色卡片
                await self._update_characters_from_facts(script_id, self.chapter_index, facts, writing_context)

            # 检测并创建新角色
            await self._create_new_characters(script_id, polished_content, writing_context)

            summary = f"事实记录完成：共{len(facts)}条"
            
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "facts": facts,
                    "facts_count": len(facts)
                }
            )
            
        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"事实记录执行失败: {str(e)}",
                step_summary="事实记录执行失败"
            )

    async def _create_new_characters(
        self, script_id: int, draft_content: str, writing_context: Dict[str, Any]
    ):
        """检测正文中的新角色并自动创建角色卡。"""
        try:
            project = get_webnovel_project_by_script(script_id)
            if not project:
                return
            project_id = project["id"]

            # 获取已有角色名
            existing_chars = get_character_cards_by_project(project_id)
            existing_names = set()
            for c in existing_chars:
                name = c.get("name", "") or c.get("character_name", "")
                if name:
                    existing_names.add(name)

            # 构建已有角色列表文本（包含身份信息，帮助 LLM 判断是否为同一角色）
            existing_chars_text = json.dumps(
                [{"name": c.get("name", "") or c.get("character_name", ""),
                  "identity": c.get("identity", ""),
                  "type": c.get("character_type", "")}
                 for c in existing_chars if (c.get("name", "") or c.get("character_name", ""))],
                ensure_ascii=False
            ) if existing_chars else "[]"

            # 正文截断策略：首尾各取一半，确保覆盖全章角色
            if len(draft_content) > 6000:
                content_sample = draft_content[:3000] + "\n...(中间省略)...\n" + draft_content[-3000:]
            else:
                content_sample = draft_content

            # 调用 LLM 识别新角色并生成简要设定
            prompt = (
                "以下是一段小说正文和已有的全部角色列表。"
                "请识别正文中出现但不在已有角色列表中的新角色，"
                "并为每个新角色生成简要设定。\n"
                "重要：不要创建与已有角色同名、谐音或别名的角色，避免重复。\n"
                "注意：如果正文中的角色只是用称呼/别名/头衔指代已有角色，不要重复创建。\n\n"
                f"【已有角色（禁止重复）】\n{existing_chars_text}\n\n"
                f"【正文内容】\n{content_sample}\n\n"
                "【输出格式】\n"
                "请按照JSON格式输出：\n"
                '{"new_characters": [{"name": "角色名", "identity": "身份", '
                '"core_personality": "性格关键词", "role_in_story": "在故事中的作用"}]}\n'
                "如果没有新角色，输出 {\"new_characters\": []}"
            )

            from core.model_executor import get_model_executor
            executor = get_model_executor()
            result = await executor.execute_text_chat(
                prompt=prompt,
                system_prompt="你是一位专业的网文编辑，擅长识别和分析角色。输出严格的JSON格式。",
                max_tokens=500,
                script_id=script_id,
                project_id=project_id,
                executor_name="fact_recorder_executor",
                prompt_name="create_new_characters",
            )

            content = result.get("content", "") if result else ""
            if not content:
                return

            char_data = parse_llm_json(
                content,
                script_id=script_id,
                project_id=project_id,
                executor_name="fact_recorder_executor",
                prompt_name="create_new_characters",
            )

            if not char_data or "new_characters" not in char_data:
                return

            # 创建新角色卡
            created = []
            for char in char_data["new_characters"]:
                if not isinstance(char, dict):
                    continue
                name = char.get("name", "").strip()
                if not name:
                    continue
                # 精确匹配去重
                if name in existing_names:
                    continue
                # 子串匹配去重：防止 LLM 返回"张小凡（少年）"等变体
                if any(name in existing or existing in name for existing in existing_names):
                    continue
                # 过滤常见非角色名词
                skip_terms = {"主角", "反派", "女主", "男主", "配角", "路人", "群众", "弟子", "长老"}
                if name in skip_terms or len(name) > 10:
                    continue

                add_character_card(
                    project_id,
                    "supporting",
                    name=name,
                    identity=char.get("identity", ""),
                    core_personality=char.get("core_personality", ""),
                    first_impression=char.get("role_in_story", ""),
                    short_term_goal=char.get("role_in_story", ""),
                )
                existing_names.add(name)
                created.append(name)

            if created:
                from utils.logger import log_manager
                logger = log_manager.get_logger("fact_recorder")
                logger.info(f"[fact_recorder] 自动创建新角色卡: {created}")

        except Exception:
            pass

    async def _update_characters_from_facts(
        self, script_id: int, chapter_index: int,
        facts: List[Dict[str, Any]], writing_context: Dict[str, Any]
    ):
        """根据事实更新角色关系和角色卡片。"""
        try:
            project = get_webnovel_project_by_script(script_id)
            if not project:
                return
            project_id = project["id"]

            all_chars = get_character_cards_by_project(project_id)
            char_name_map = {}
            for c in all_chars:
                name = c.get("name", "") or c.get("character_name", "")
                if name:
                    char_name_map[name] = c

            # 按名字长度降序排列，确保最长匹配优先（"张小凡" 优先于 "张"）
            sorted_names = sorted(char_name_map.keys(), key=len, reverse=True)

            for fact in facts:
                fact_type = fact.get("type", "")
                fact_content = fact.get("content", "")

                # 角色关系变化
                if "关系" in fact_type or "关系" in fact_content:
                    matched_chars = [n for n in sorted_names if n in fact_content]
                    if len(matched_chars) >= 2:
                        add_character_relationship(
                            character_id=char_name_map[matched_chars[0]]["id"],
                            relation_type=fact_type,
                            target_character_id=char_name_map[matched_chars[1]]["id"],
                            target_name=matched_chars[1],
                            description=f"第{chapter_index}章: {fact_content[:100]}"
                        )

                # 角色成长/升级
                if "升级" in fact_type or "突破" in fact_type or "成长" in fact_type:
                    for name in sorted_names:
                        if name in fact_content:
                            add_character_growth(
                                character_id=char_name_map[name]["id"],
                                stage=f"第{chapter_index}章",
                                description=fact_content[:200]
                            )
                            break

                # 角色能力/状态更新
                if "能力" in fact_type or "技能" in fact_type or "实力" in fact_type:
                    for name in sorted_names:
                        if name in fact_content:
                            existing_power = get_character_power(char_name_map[name]["id"])
                            if existing_power:
                                update_notes = existing_power.get("signature_skills", "")
                                if fact_content[:50] not in update_notes:
                                    new_skills = update_notes + f"; 第{chapter_index}章: {fact_content[:100]}"
                                    update_character_card(char_name_map[name]["id"], ability_limit=new_skills[:500])
                            break

        except Exception:
            pass