"""执行器10：事实记录器。

完全参考webnovel-writer的记录事实。
"""

import json
import re
from typing import Dict, Any, List, Tuple
from ..base_executor import BaseExecutor, ExecutorResult
from utils.llm_json_parser import parse_llm_json
from webnovel.repositories import (
    get_webnovel_project_by_script,
    get_character_cards_by_project, add_character_relationship, update_character_card,
    add_character_growth, get_character_power, add_character_power, add_character_card,
    delete_character_card, reassign_character_data,
    upsert_character_item, mark_character_item_lost
)


# 物品变化事实的动作分类（与 fact_record_prompt 约定的动词集一致）
# 获得类动词 → 累加数量；其他动词（失去/损毁/赠予等）→ 扣减数量
_GAIN_ACTIONS = {"获得", "得到", "收下", "缴获", "抢得", "抢走", "夺得",
                 "买下", "买得", "拾得", "捡到", "接过"}


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
                    if c.get('character_name'):
                        characters_text.append(c['character_name'])
                    elif c.get('role'):
                        characters_text.append(c['role'])
                    else:
                        characters_text.append("角色")

            # 从 .md 文件加载 prompt 模板
            prompt_data = self._load_prompt("fact_record")
            # 事实记录需要覆盖全章内容，截断过短会遗漏核心事件（如升级突破、物品消耗）。
            # 成品章节 3000-5000 字，取前 4000 字可覆盖大部分关键事件。
            chapter_content = polished_content[:4000] if len(polished_content) > 4000 else polished_content
            prompt = prompt_data["user_prompt"].format(
                chapter_content=chapter_content,
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
                executor_name=self.step_name,
                prompt_name="fact_record",
            )

            content = result.get("content", "") if result else ""
            facts = []

            # 尝试JSON解析
            fact_data = parse_llm_json(
                content,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
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

            # 获取已有角色名与曾用名（曾用名命中同样视为已有角色）
            existing_chars = get_character_cards_by_project(project_id)
            existing_names = set()
            existing_aliases = set()
            for c in existing_chars:
                name = c.get("name", "") or c.get("character_name", "")
                if name:
                    existing_names.add(name)
                for a in re.split(r"[,，、]", c.get("alias", "") or ""):
                    if a.strip():
                        existing_aliases.add(a.strip())

            # 构建已有角色列表文本（包含身份和曾用名信息，帮助 LLM 判断是否为同一角色）
            existing_chars_text = json.dumps(
                [{"name": c.get("name", "") or c.get("character_name", ""),
                  "alias": c.get("alias", ""),
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

            # 从外置 .md 模板加载 prompt（按角色类型分级输出字段，键名与角色卡表列名一致）
            prompt_data = self._load_prompt("create_new_characters")
            prompt = prompt_data["user_prompt"].format(
                existing_chars=existing_chars_text,
                content_sample=content_sample,
            )
            system_prompt = prompt_data["system_prompt"] or "你是一位专业的网文编辑，擅长识别和分析角色。输出严格的JSON格式。"
            if not prompt.strip():
                from utils.logger import log_manager
                log_manager.get_logger("fact_recorder").warning(
                    "[fact_recorder] create_new_characters prompt 模板加载为空，跳过新角色检测"
                )
                return

            from core.model_executor import get_model_executor
            executor = get_model_executor()
            result = await executor.execute_text_chat(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=2000,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="create_new_characters",
            )

            content = result.get("content", "") if result else ""
            if not content:
                return

            char_data = parse_llm_json(
                content,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="create_new_characters",
            )

            if not char_data or "new_characters" not in char_data:
                return

            # 创建新角色卡（收集新卡 id 用于增量索引）
            created = []
            created_ids = []
            for char in char_data["new_characters"]:
                if not isinstance(char, dict):
                    continue
                name = char.get("name", "").strip()
                if not name:
                    continue
                # 精确匹配去重：名字或曾用名命中已有卡则跳过（包含子串匹配，防变体）
                if name in existing_names or any(name in a for a in existing_aliases):
                    continue
                if any(name in existing or existing in name for existing in existing_names):
                    continue
                # 过滤常见非角色名词（含泛称、动物、尸体等非人物实体）
                skip_terms = {"主角", "反派", "女主", "男主", "配角", "路人", "群众", "弟子", "长老",
                              "妖兽", "猛兽", "妖兵", "妖丹", "灵兽", "凶兽", "幻兽",
                              "尸体", "遗骸", "骸骨", "残骸", "尸傀", "尸虫"}
                if name in skip_terms or len(name) > 10:
                    continue
                # 过滤含动物/尸体关键词的名称（如"铁背狼""散修遗骸"）
                _non_char_keywords = ("狼", "虎", "蛇", "熊", "鹰", "兽", "尸", "骸", "傀")
                if any(kw in name for kw in _non_char_keywords):
                    continue

                # 按 LLM 返回的类型建卡；非法/缺失时兜底 minor，避免龙套污染配角层
                raw_type = str(char.get("character_type", "")).strip().lower()
                char_type = raw_type if raw_type in ("villain", "supporting", "minor") else "minor"
                
                # 白名单字段直传：键名与 prompt 输出及角色卡表列名完全一致，
                # 避免二次映射导致的字段错位/丢失（minor 无深化字段，缺失自动为空）
                card_fields = (
                    "age_stage", "identity", "protagonist_relation", "core_personality", "core_tags", "first_impression",
                    "short_term_goal", "true_desire", "personality_flaw", "starting_state",
                    "long_term_goal", "behavior_pattern", "ability_limit",
                )
                card_kwargs = {k: str(char.get(k, "") or "").strip() for k in card_fields}
                
                new_card = add_character_card(
                    project_id,
                    char_type,
                    name=name,
                    **card_kwargs,
                )
                existing_names.add(name)
                created.append(name)
                if new_card and new_card.get("id"):
                    created_ids.append(new_card["id"])

            # 写作中自动创建的角色卡即时写入 RAG，无需等待全量重建索引
            if created_ids:
                try:
                    from webnovel.services.webnovel_service import WebnovelService
                    await WebnovelService().reindex_character_cards(project_id, created_ids)
                except Exception:
                    pass  # 索引失败不阻断主流程

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

            # 身份揭露/改名/合并涉及的角色卡，循环结束后统一增量重建 RAG 索引
            changed_char_ids = set()

            for fact in facts:
                fact_type = fact.get("type", "")
                fact_content = fact.get("content", "")

                # 身份揭露/别名揭晓：合并或重命名化名角色卡（优先处理，避免被关系类事实抢先消费）
                if any(k in fact_type for k in ("身份", "揭露", "别名", "真身", "揭晓")):
                    affected = await self._handle_identity_reveal(
                        project_id, char_name_map, fact_content, chapter_index
                    )
                    changed_char_ids.update(affected)
                    continue

                # 物品变化：更新角色持有物品清单（优先于"能力/技能获得"分支，
                # 避免"物品获得"被能力分支误消费；处理后 continue 防止被后续分支重复消费）
                if any(k in fact_type for k in ("物品", "武器", "装备", "道具", "宝物")):
                    affected = self._handle_item_change(
                        char_name_map, sorted_names, fact_content, chapter_index
                    )
                    changed_char_ids.update(affected)
                    continue

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

            # 角色卡变更后按 char_id 增量重建 RAG 片段（含已删除卡的旧片段清理）
            if changed_char_ids:
                try:
                    from webnovel.services.webnovel_service import WebnovelService
                    await WebnovelService().reindex_character_cards(project_id, list(changed_char_ids))
                except Exception:
                    pass  # 索引失败不阻断主流程

        except Exception:
            pass

    def _parse_identity_reveal(self, content: str) -> Tuple[str, str, str]:
        """解析身份揭露事实内容，返回 (曾用名, 真名, 身份说明)。

        主格式（prompt 约定）："曾用名 => 真名: 身份说明"；
        兜底支持 "A原来是B"、"A正是B" 等口语化表述。
        """
        content = (content or "").strip()
        if not content:
            return "", "", ""

        left, right = None, None
        for sep in ("=>", "→", "＝>", ">"):
            if sep in content:
                left, right = content.split(sep, 1)
                break

        if left is None:
            # 兜底：口语化表述，例如"神秘黑袍男人原来是李岩，总兵府护卫统领"
            m = re.search(
                r"([^，。；]{1,12}?)\s*(?:原来是|正是|其实是|真身是|真实身份是|本名是|就是)\s*([^，。；]{1,12})",
                content
            )
            if not m:
                return "", "", ""
            alias = m.group(1).strip()
            real_name = self._extract_name(m.group(2))
            desc = content[m.end():].strip().lstrip("，。；：: ")
            return alias, real_name, desc

        # 标准格式：右侧为 "真名: 身份说明" 或仅 "真名"
        parts = re.split(r"[：:]", right, 1)
        real_name = self._extract_name(parts[0])
        desc = parts[1].strip() if len(parts) > 1 else ""
        return left.strip(), real_name, desc

    @staticmethod
    def _extract_name(text: str) -> str:
        """从文本中提取角色名：去除引号、括号及尾随说明。"""
        text = (text or "").strip().strip("「」『』\"'“”")
        text = re.split(r"[（(，,。]", text, 1)[0]
        return text.strip()

    def _parse_item_change(self, content: str) -> Tuple[str, str, str, str, int]:
        """解析物品变化事实内容，返回 (角色名, 动作, 物品名, 说明, 数量)。

        主格式（prompt 约定）："角色名 获得|失去 物品名: 变化说明"；
        数量约定：说明中包含 "xN" 或 "×N" 表示数量（默认 1）。
        动词集与 _GAIN_ACTIONS/_GIFT_ACTIONS 及 prompt 约定保持一致。
        """
        content = (content or "").strip()
        if not content:
            return "", "", "", "", 1
        m = re.search(
            r"([^，。；:：]{1,12}?)[，,、\s]*"
            r"(获得|得到|收下|缴获|抢得|抢走|夺得|买下|买得|拾得|捡到|接过|"
            r"失去|丢失|遗失|损毁|损坏|赠予|赠送|送给|交给|交出|被夺|被抢|丢弃)"
            r"[，,、\s]*([^，。；:：]{1,20})\s*[：:]?\s*(.*)",
            content
        )
        if not m:
            return "", "", "", "", 1
        note_raw = m.group(4).strip()
        # 从说明中解析数量：匹配 xN、×N、XN、N个、N把、N枚 等
        qty = 1
        qty_m = re.search(r"[x×X](\d+)|(\d+)[个把枚枚块瓶壶柄支条颗粒袋份副套双箱桶包罐]|数量[：:]\s*(\d+)", note_raw)
        if qty_m:
            qty = int(qty_m.group(1) or qty_m.group(2) or qty_m.group(3) or 1)
            # 从说明中移除数量标记，保留其余说明文字
            note_raw = (note_raw[:qty_m.start()] + note_raw[qty_m.end():]).strip().strip("，,、:：")
        return m.group(1).strip(), m.group(2), m.group(3).strip(), note_raw, qty

    def _handle_item_change(
        self, char_name_map: Dict[str, dict], sorted_names: List[str],
        fact_content: str, chapter_index: int
    ) -> List[int]:
        """处理物品变化事实：获得→upsert 持有记录，失去→翻转状态。

        返回受影响的 char_id 列表（供增量重建 RAG 索引）。
        """
        try:
            from utils.logger import log_manager
            logger = log_manager.get_logger("fact_recorder")

            char_raw, action, item_name, note, quantity = self._parse_item_change(fact_content)
            if not action or not item_name:
                return []

            # 角色匹配：最长名字优先扫描事实全文（与其他事实分支策略一致）
            matched_name = next((n for n in sorted_names if n in fact_content), None)
            if matched_name is None:
                return []
            char_id = char_name_map[matched_name]["id"]

            qty_note = f"x{quantity}" if quantity > 1 else ""
            full_note = f"第{chapter_index}章{action}{qty_note}: {note[:100]}" if note else f"第{chapter_index}章{action}{qty_note}"

            if action in _GAIN_ACTIONS:
                upsert_character_item(
                    char_id, item_name,
                    source=note[:200],
                    chapter=chapter_index,
                    note=full_note,
                    quantity=quantity,
                )
                logger.info(f"[fact_recorder] 角色 '{matched_name}' 获得物品 '{item_name}' x{quantity}")
            else:
                ok = mark_character_item_lost(
                    char_id, item_name,
                    chapter=chapter_index, note=f"第{chapter_index}章: {fact_content[:100]}",
                    quantity=quantity,
                )
                if not ok:
                    # 角色没有该物品却"失去"：不一致信号，记日志不阻断，不凭空建记录
                    logger.warning(
                        f"[fact_recorder] 角色 '{matched_name}' 失去未持有物品 '{item_name}'"
                        f"（第{chapter_index}章），疑似正文不一致"
                    )
                    return []
                logger.info(f"[fact_recorder] 角色 '{matched_name}' 失去物品 '{item_name}' x{quantity}")
            return [char_id]
        except Exception:
            return []

    async def _handle_identity_reveal(
        self, project_id: int, char_name_map: Dict[str, dict],
        fact_content: str, chapter_index: int
    ) -> List[int]:
        """处理身份揭露事实：真名卡已存在则合并并删除旧卡，否则将化名卡改名。

        返回受影响的 char_id 列表（含已删除卡，供增量重建 RAG 索引时清理旧片段）。
        """
        try:
            from utils.logger import log_manager
            logger = log_manager.get_logger("fact_recorder")

            alias_name, real_name, identity_desc = self._parse_identity_reveal(fact_content)
            if not alias_name or not real_name or alias_name == real_name:
                return []
            if len(real_name) > 10:
                return []

            # 定位化名卡：精确匹配优先，回退子串匹配（处理"黑袍男人"→"神秘黑袍男人"等变体）
            old_card = char_name_map.get(alias_name)
            if old_card is None:
                for name, card in char_name_map.items():
                    if alias_name in name or name in alias_name:
                        old_card = card
                        break
            if old_card is None:
                return []
            # 仅处理 supporting/minor 类型的化名卡，避免误动核心角色卡
            if old_card.get("character_type") not in ("supporting", "minor"):
                return []

            old_id = old_card["id"]
            old_name = old_card.get("name", "")
            # 化名卡自身的曾用名一并传承（支持多次改名链）
            old_aliases = [a.strip() for a in re.split(r"[,，、]", old_card.get("alias", "") or "") if a.strip()]
            merged_alias_parts = [old_name] + old_aliases

            real_card = char_name_map.get(real_name)
            if real_card is not None and real_card.get("id") != old_id:
                # 真名卡已存在：合并曾用名与身份后删除化名卡，关系/成长/能力数据迁移至真名卡
                new_id = real_card["id"]
                existing_parts = [a.strip() for a in re.split(r"[,，、]", real_card.get("alias", "") or "") if a.strip()]
                alias_parts = []
                for p in existing_parts + merged_alias_parts:
                    if p and p != real_name and p not in alias_parts:
                        alias_parts.append(p)
                updates = {"alias": "、".join(alias_parts)}
                if identity_desc and not (real_card.get("identity") or "").strip():
                    updates["identity"] = identity_desc[:200]
                update_character_card(new_id, **updates)
                reassign_character_data(old_id, new_id)
                delete_character_card(old_id)
                char_name_map.pop(old_name, None)
                logger.info(
                    f"[fact_recorder] 第{chapter_index}章身份揭露：化名卡 '{old_name}'(id={old_id}) "
                    f"已合并至 '{real_name}'(id={new_id})"
                )
                return [new_id, old_id]

            # 真名卡不存在：化名卡改名为真名，曾用名记入 alias 字段，补充揭露的身份信息
            new_identity = old_card.get("identity", "") or ""
            if identity_desc and identity_desc not in new_identity:
                new_identity = (new_identity + "；" + identity_desc)[:500] if new_identity else identity_desc[:200]
            alias_parts = []
            for p in merged_alias_parts:
                if p and p != real_name and p not in alias_parts:
                    alias_parts.append(p)
            new_alias = "、".join(alias_parts)
            update_character_card(old_id, name=real_name, alias=new_alias, identity=new_identity)
            # 同步更新内存映射，保证同批次后续事实能命中真名
            char_name_map.pop(old_name, None)
            old_card.update({"name": real_name, "alias": new_alias, "identity": new_identity})
            char_name_map[real_name] = old_card
            logger.info(
                f"[fact_recorder] 第{chapter_index}章身份揭露：角色卡 '{old_name}'(id={old_id}) "
                f"已改名为 '{real_name}'，曾用名保留在 alias 字段"
            )
            return [old_id]
        except Exception:
            return []