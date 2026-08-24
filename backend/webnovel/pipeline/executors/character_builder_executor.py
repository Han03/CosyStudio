"""执行器：角色构建执行器。

负责构建完整的角色设定：主角、女主、反派、角色组。
从 init_executor 中提取的角色构建逻辑，独立维护。
"""

import json
from typing import Dict, Any, Tuple, List, Optional

from ..base_executor import BaseExecutor, ExecutorResult
from core.model_executor import get_model_executor
from utils.logger import log_manager
from utils.llm_json_parser import parse_llm_json
from webnovel.repositories import (
    add_character_card, add_character_relationship, add_character_growth,
    add_character_power,
    add_character_group, add_character_group_member, add_character_group_arc,
    get_character_cards_by_project,
    add_villain, add_villain_hierarchy, add_villain_plot_node,
)
from .init_executor import _safe_items, _sanitize_value

_logger = log_manager.get_logger("character_builder")


class CharacterBuilderExecutor(BaseExecutor):
    """角色构建执行器。

    负责通过 LLM 生成完整的角色设定（主角、女主、反派、角色组），
    并将结果保存到数据库。
    """

    step_name = "character_builder"
    step_description = "构建角色设定"
    step_weight = 10

    async def _call_llm(self, prompt_name: str, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """调用LLM生成数据。"""
        executor = get_model_executor()
        prompt_data = self._load_prompt(prompt_name)

        _logger.info(f"[character_builder] 调用LLM生成 {prompt_name}，prompt加载: {'成功' if prompt_data['user_prompt'] else '失败'}")

        if not prompt_data["user_prompt"]:
            _logger.error(f"[character_builder] {prompt_name} 的user_prompt为空")
            return {}

        try:
            # ============== 安全 format：缺失字段自动填充空值，不再抛 KeyError ==============
            class _SafeAttr:
                """访问不存在的属性时返回空字符串，适配 {obj.missing_attr} 格式的占位符。"""
                def __getattr__(self, _name: str):
                    return ""
                def __getitem__(self, _idx):
                    return ""
                def __str__(self):
                    return ""
                def __repr__(self):
                    return ""
                def __bool__(self):
                    return False
                def __iter__(self):
                    return iter([])
                def __len__(self):
                    return 0

            class _SafeFormatMap(dict):
                """format_map 专用 dict：缺失 key 时自动返回 _SafeAttr()，避免 KeyError。"""
                def __missing__(self, key: str):
                    _logger.warning(
                        f"[character_builder] prompt={prompt_name} 引用了缺失的上下文字段: {{{key}}}，已用空值填充"
                    )
                    return _SafeAttr()

            user_prompt = prompt_data["user_prompt"].format_map(_SafeFormatMap(**context_data))
            _logger.info(f"[character_builder] 准备调用LLM，prompt长度: {len(user_prompt)}")

            project_id = 0
            try:
                from webnovel.repositories import get_webnovel_project_by_script
                _proj = get_webnovel_project_by_script(self.script_id)
                if _proj:
                    project_id = _proj.get("id", 0)
            except Exception:
                pass

            import time as _time
            _call_start = _time.time()

            result = await executor.execute_text_chat(
                prompt=user_prompt,
                system_prompt=prompt_data["system_prompt"],
                max_tokens=4000,
                script_id=self.script_id,
                project_id=project_id,
                executor_name="character_builder",
                prompt_name=prompt_name,
            )
            _latency_ms = int((_time.time() - _call_start) * 1000)

            _logger.info(f"[character_builder] LLM调用完成，结果类型: {type(result)}")
            content = result.get("content", "") if result else ""
            _logger.info(f"[character_builder] LLM返回内容长度: {len(content)}")
            _logger.info(f"[character_builder] LLM返回内容前300字符: {repr(content[:300])}")

            content = content.strip()

            json_result = parse_llm_json(
                content,
                script_id=self.script_id,
                project_id=project_id,
                executor_name="character_builder",
                prompt_name=prompt_name,
                model_name=result.get("model_name", "") if isinstance(result, dict) else "",
                system_prompt=prompt_data["system_prompt"],
                user_prompt=user_prompt,
                input_tokens=result.get("input_tokens", 0) if isinstance(result, dict) else 0,
                output_tokens=result.get("output_tokens", 0) if isinstance(result, dict) else 0,
                latency_ms=_latency_ms,
            )

            if json_result:
                _logger.info(f"[character_builder] JSON解析成功，键: {list(json_result.keys())}")
                return json_result
            else:
                _logger.error(f"[character_builder] JSON解析失败，所有策略均失败")
                _logger.error(f"[character_builder] 解析失败的内容: {repr(content[:500])}")
                return {"raw_content": content}
        except Exception as e:
            _logger.error(f"[character_builder] LLM调用异常: {e}")
            return {"error": str(e)}

    @staticmethod
    def _sanitize_age(age_val) -> int:
        """安全转换 age 字段为 int。"""
        if isinstance(age_val, bool):
            return 0
        if isinstance(age_val, int):
            return age_val
        if isinstance(age_val, str):
            try:
                return int(age_val)
            except ValueError:
                return 0
        try:
            return int(age_val)
        except Exception:
            return 0

    def _save_character_card(self, project_id: int, role: str, char_data: dict) -> Tuple[dict, Optional[int]]:
        """保存角色卡到数据库，处理字段映射、age 转换、关联表写入。

        返回 (处理后的 char_data, character_id)。
        """
        if not char_data or "error" in char_data:
            return char_data, None

        data = char_data.copy()
        growth_arc = data.pop("growth_arc", {})

        data["ability_limit"] = data.pop("_limit", data.get("ability_limit", ""))
        data["behavior_bottom_line"] = data.pop("_bottom_line", data.get("behavior_bottom_line", ""))

        # 字段映射：简略版字段 → 角色卡表字段
        if not data.get("true_desire") and data.get("desire"):
            data["true_desire"] = data["desire"]
        if not data.get("personality_flaw") and data.get("flaw"):
            data["personality_flaw"] = data["flaw"]
        if not data.get("long_term_goal") and data.get("desire"):
            data["long_term_goal"] = data["desire"]

        # 安全转换 age 为 int，其余字段为字符串
        if "age" in data:
            data["age"] = self._sanitize_age(data["age"])
        for key in list(data.keys()):
            if key == "age":
                continue
            data[key] = _sanitize_value(data[key], "")

        char = add_character_card(project_id, role, **data)
        char_id = char["id"]

        # 写入成长弧线
        if growth_arc:
            if isinstance(growth_arc, dict):
                for stage, desc in growth_arc.items():
                    add_character_growth(char_id, stage, desc)
            elif isinstance(growth_arc, list):
                for arc_item in growth_arc:
                    if isinstance(arc_item, dict):
                        add_character_growth(char_id, arc_item.get("stage", ""), arc_item.get("description", ""))

        return data, char_id

    async def build_protagonist(
        self, project_data: Dict[str, Any], llm_context: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Optional[int]]:
        """构建主角角色卡。

        收集用户已填基础信息，始终调用 LLM 生成完整角色卡（24 个详细字段）。
        返回 (protagonist_data, protagonist_id)。
        """
        project_id = llm_context.get("_project_id")

        # 收集用户已填的基础主角信息（来自前端表单或 AI 步骤生成）
        prot_flat = {
            "name": project_data.get("protagonist_name", ""),
            "desire": project_data.get("protagonist_desire", ""),
            "flaw": project_data.get("protagonist_flaw", ""),
            "archetype": project_data.get("protagonist_archetype", ""),
            "structure": project_data.get("protagonist_structure", "单主角")
        }
        # 前端 AI 步骤生成的主角数据也可能包含基础字段
        prot_step_data = project_data.get("protagonist") or {}
        if isinstance(prot_step_data, dict):
            for k in ("name", "desire", "flaw", "archetype", "structure"):
                if not prot_flat.get(k) and prot_step_data.get(k):
                    prot_flat[k] = prot_step_data[k]

        # 将基础主角信息注入 LLM 上下文，供 init_character prompt 引用
        from .init_executor import DictObj
        llm_context["protagonist_basic"] = DictObj(prot_flat)

        # 构建主角基础设定段落（主角生成时引用已确定的基础信息，姓名必须一致）
        character_basic_section = (
            "【已有角色基础设定】\n"
            f"姓名：{prot_flat.get('name', '')}\n"
            f"欲望/动机：{prot_flat.get('desire', '')}\n"
            f"性格缺陷：{prot_flat.get('flaw', '')}\n"
            f"角色原型：{prot_flat.get('archetype', '')}\n"
            "（注：以上为已确定的基础设定，请在此基础上展开详细角色卡，姓名必须保持一致）"
        )

        # 始终调用 init_character prompt 生成完整角色卡
        # 前端只提供 name/desire/flaw/archetype 等简略字段，
        # 角色卡表需要 core_personality/behavior_bottom_line/goals 等 24 个详细字段，
        # 必须由 init_character prompt 的 LLM 输出来填充。
        llm_prot_data = await self._call_llm("init_character", {**llm_context, "character_type": "主角", "character_basic_section": character_basic_section})
        if llm_prot_data and "error" not in llm_prot_data:
            protagonist_data = {**llm_prot_data, **prot_flat}
        elif prot_flat["name"] or prot_flat["desire"]:
            protagonist_data = prot_flat
        else:
            protagonist_data = None

        protagonist_id = None
        if protagonist_data and "error" not in protagonist_data:
            char_data, protagonist_id = self._save_character_card(project_id, "protagonist", protagonist_data)
            protagonist_data = char_data

            # 写入关系
            relationships = protagonist_data.pop("relationships", []) if isinstance(protagonist_data, dict) else []
            for rel in _safe_items(relationships):
                add_character_relationship(
                    protagonist_id,
                    rel.get("relation_type", ""),
                    rel.get("target_character_id", None),
                    rel.get("target_name", ""),
                    rel.get("description", "")
                )

            # 写入力量信息
            power_info = {}
            if isinstance(protagonist_data, dict):
                power_info = protagonist_data.pop("power", protagonist_data.pop("power_info", {}))
            if isinstance(power_info, dict) and (power_info.get("realm") or power_info.get("signature_skills")):
                add_character_power(
                    protagonist_id,
                    realm=power_info.get("realm", ""),
                    layer=power_info.get("layer", 0),
                    bottleneck=power_info.get("bottleneck", ""),
                    signature_skills=power_info.get("signature_skills", ""),
                    resources_equipment=power_info.get("resources_equipment", "")
                )

            # 注入上下文供后续步骤使用
            if char_data:
                llm_context["protagonist"] = DictObj(char_data)

        return protagonist_data or {}, protagonist_id

    async def build_heroine(
        self, project_data: Dict[str, Any], llm_context: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], List[Optional[int]]]:
        """构建女主角色卡。

        仅当 heroine_config != "无女主" 且用户未提供女主数据时调用 LLM。
        当 heroine_config == "多女主" 时，LLM 单次调用生成多个女主。
        返回 (heroine_data_list, heroine_id_list)。
        """
        project_id = llm_context.get("_project_id")
        is_multi = project_data.get("heroine_config") == "多女主"

        heroine_data = project_data.get("heroine")
        if not heroine_data and project_data.get("heroine_config") != "无女主":
            # 构建用户女主设定段落（若用户已指定名字偏好/角色定位，注入供 LLM 参考）
            user_heroine_section = ""
            user_heroine_names = project_data.get("heroine_names", "")
            user_heroine_role = project_data.get("heroine_role", "")
            if user_heroine_names or user_heroine_role:
                user_heroine_section = (
                    "\n\n【用户女主设定】\n"
                    f"女主姓名偏好：{user_heroine_names or '未指定'}\n"
                    f"女主角色定位：{user_heroine_role or '未指定'}\n"
                    "（注：以上为用户已确定的女主基础设定，请尽量保持一致）"
                )

            if is_multi:
                heroine_basic_section = (
                    "【女主创作要求】\n"
                    "本项目为多女主设定，请一次性创作 2~3 个不同的女性角色。\n"
                    "每个女主必须拥有独立的姓名、身份和性格设定，彼此之间有明显的差异化。\n"
                    "重要：女主姓名不能与主角相同，必须是全新的角色。\n\n"
                    "【输出格式覆盖】\n"
                    "多女主场景下，请输出如下 JSON 格式（用 heroines 数组包裹）：\n"
                    '{{"heroines": [{{"name": "女主1姓名", ...全部字段...}}, {{"name": "女主2姓名", ...全部字段...}}]}}\n'
                    "每个女主对象包含与单女主相同的全部字段。"
                    f"{user_heroine_section}"
                )
            else:
                heroine_basic_section = (
                    "【女主创作要求】\n"
                    "请独立创作一个与主角不同的女性角色，拥有独立的姓名、身份和性格设定。\n"
                    "重要：女主姓名不能与主角相同，必须是一个全新的角色。"
                    f"{user_heroine_section}"
                )
            heroine_data = await self._call_llm("init_character", {**llm_context, "character_type": "女主", "character_basic_section": heroine_basic_section})

        # 统一处理返回值：LLM 可能返回单个 dict 或包含 heroines 列表的 dict
        heroine_list = []
        if heroine_data and "error" not in heroine_data:
            if isinstance(heroine_data, dict) and "heroines" in heroine_data:
                heroine_list = [h for h in heroine_data["heroines"] if isinstance(h, dict)]
            elif isinstance(heroine_data, dict):
                heroine_list = [heroine_data]
            elif isinstance(heroine_data, list):
                heroine_list = [h for h in heroine_data if isinstance(h, dict)]

        # 逐个保存女主角色卡
        heroine_data_list = []
        heroine_id_list = []
        for h_data in heroine_list:
            char_data, heroine_id = self._save_character_card(project_id, "heroine", h_data)
            heroine_data_list.append(char_data)
            heroine_id_list.append(heroine_id)

        if heroine_data_list:
            _logger.info(f"[character_builder] 女主角色卡已保存，共 {len(heroine_data_list)} 个")

        return heroine_data_list, heroine_id_list

    async def build_villain(
        self, project_data: Dict[str, Any], llm_context: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Optional[int]]:
        """构建反派设定。

        用户未提供反派数据时调用 init_villain prompt。
        返回 (villain_data, villain_id)。
        """
        project_id = llm_context.get("_project_id")

        villain_data = project_data.get("villain")
        if not villain_data:
            villain_data = await self._call_llm("init_villain", llm_context)

        villain_id = None
        if villain_data and "error" not in villain_data:
            v_data = villain_data.copy()
            hierarchy = v_data.pop("hierarchy", [])
            plot_nodes = v_data.pop("plot_nodes", [])

            v_data["value_conflict_points"] = v_data.pop("value_conflict", v_data.get("value_conflict_points", ""))
            v_data["upgrade_rhythm"] = v_data.pop("_rhythm", v_data.get("upgrade_rhythm", ""))

            # 安全转换所有可能是 list/dict 的字段为 JSON 字符串，避免 SQLite 绑定错误
            for key in list(v_data.keys()):
                if key in ["can_be_redeemed", "has_higher_villain"]:
                    # 布尔/整数字段：转换为 0/1
                    val = v_data[key]
                    if isinstance(val, bool):
                        v_data[key] = 1 if val else 0
                    elif isinstance(val, str):
                        v_data[key] = 1 if val.lower() in ["true", "1", "yes", "是"] else 0
                    elif not isinstance(val, int):
                        v_data[key] = 0
                else:
                    # 其余字段：list/dict 转 JSON
                    v_data[key] = _sanitize_value(v_data[key], "")

            villain = add_villain(project_id, **v_data)
            villain_id = villain["id"]

            for tier in _safe_items(hierarchy):
                tier_data = {
                    "tier": tier.get("tier", ""),
                    "villain_name": tier.get("villain_name", tier.get("name", "")),
                    "stage": tier.get("stage", ""),
                    "goal": tier.get("goal", ""),
                    "protagonist_relation": tier.get("protagonist_relation", "")
                }
                add_villain_hierarchy(villain_id, **tier_data)

            for node in _safe_items(plot_nodes):
                node_data = {
                    "node_type": node.get("node_type", ""),
                    "chapter": node.get("chapter", 0),
                    "description": node.get("description", "")
                }
                add_villain_plot_node(villain_id, **node_data)

            villain_data = v_data

        return villain_data or {}, villain_id

    async def build_character_group(
        self, project_data: Dict[str, Any], llm_context: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Optional[int]]:
        """构建角色组（主角团）设定。

        用户未提供角色组数据时调用 init_character_group prompt。
        通过名称匹配关联已创建的角色卡 ID。
        返回 (character_group_data, character_group_id)。
        """
        project_id = llm_context.get("_project_id")

        character_group_data = project_data.get("character_group")
        if not character_group_data:
            character_group_data = await self._call_llm("init_character_group", llm_context)

        character_group_id = None
        if character_group_data and "error" not in character_group_data:
            cg_data = character_group_data.copy()
            members = cg_data.pop("members", [])
            arcs = cg_data.pop("arcs", [])

            # 指定字段强制转为字符串
            cg_string_keys = {
                "common_goal", "stage_goal", "decision_maker", "executor",
                "information_hub", "emotional_pivot", "pov_ratio", "rotation_rules",
                "anti_overpower_constraints", "value_conflicts", "resource_conflicts",
                "trust_cracks", "anti_trope_influence", "hard_constraint_cooperation"
            }
            for k in list(cg_data.keys()):
                if k in cg_string_keys:
                    cg_data[k] = _sanitize_value(cg_data[k], "")

            cg = add_character_group(project_id, **cg_data)
            character_group_id = cg["id"]

            # 构建角色卡 名称→ID 映射，用于基于成员名称匹配 character_id
            all_cards = get_character_cards_by_project(project_id)
            name_to_id = {}
            for card in all_cards:
                name = card.get("name", "")
                if name:
                    name_to_id[name] = card["id"]

            for member in _safe_items(members):
                member_name = member.get("name", "")
                # 优先精确匹配，回退子串匹配（处理 LLM 输出"张小帆（少年）"等情况）
                char_id = name_to_id.get(member_name)
                if char_id is None and member_name:
                    for card_name, card_id in name_to_id.items():
                        if member_name in card_name or card_name in member_name:
                            char_id = card_id
                            break
                # 匹配失败：为该成员创建新角色卡（supporting 类型）
                if char_id is None and member_name:
                    _logger.info(
                        f"[character_builder] 团队成员 '{member_name}' 未匹配到已有角色卡，创建新角色卡"
                    )
                    new_card_data = {
                        "name": _sanitize_value(member_name),
                        "identity": _sanitize_value(member.get("identity", "")),
                        "core_personality": _sanitize_value(member.get("role", "")),
                        "personality_flaw": _sanitize_value(member.get("key_flaw", "")),
                        "ability_limit": _sanitize_value(member.get("key_ability", "")),
                    }
                    new_card = add_character_card(project_id, "supporting", **new_card_data)
                    char_id = new_card.get("id")
                    # 更新映射表，避免后续同名成员重复创建
                    if char_id:
                        name_to_id[member_name] = char_id
                add_character_group_member(
                    character_group_id,
                    char_id,
                    _sanitize_value(member.get("role", "")),
                    _sanitize_value(member.get("main_line_contribution", "")),
                    _sanitize_value(member.get("key_flaw", "")),
                    _sanitize_value(member.get("key_ability", ""))
                )

            for arc in _safe_items(arcs):
                add_character_group_arc(
                    character_group_id,
                    _sanitize_value(arc.get("stage", "")),
                    _sanitize_value(arc.get("description", ""))
                )

            character_group_data = cg_data

        return character_group_data or {}, character_group_id

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """标准执行器接口（供 pipeline 直接调用时使用）。"""
        project_data = context.get("project_data", {})
        llm_context = context.get("llm_context", {})

        protagonist_data, protagonist_id = await self.build_protagonist(project_data, llm_context)
        heroine_data_list, heroine_id_list = await self.build_heroine(project_data, llm_context)
        villain_data, villain_id = await self.build_villain(project_data, llm_context)

        return ExecutorResult(
            success=True,
            step_summary="角色构建完成",
            output_data={
                "protagonist": protagonist_data,
                "protagonist_id": protagonist_id,
                "heroines": heroine_data_list,
                "heroine_ids": heroine_id_list,
                "villain": villain_data,
                "villain_id": villain_id,
            }
        )
