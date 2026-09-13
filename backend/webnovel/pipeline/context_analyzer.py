"""上下文分析器：LLM 驱动的按需上下文组装。

在每一步 executor 调用 LLM 生成前，先通过轻量级 LLM 分析确定当前步骤
需要哪些上下文条目，再从 DB 精准加载完整数据、执行 RAG 检索，
组装最终上下文供 executor 使用。

替代原有的"全量加载 + 硬编码裁剪"策略。
"""

import json
import os
import re
from typing import Dict, Any, List, Optional

from utils.logger import log_manager
from utils.llm_json_parser import parse_llm_json
from webnovel.repositories import (
    get_character_card, get_character_cards_by_project,
    get_character_items_by_project,
    get_worldview_by_project, get_worldview_factions,
    get_power_system_by_project,
    get_golden_finger_by_project,
    get_character_group_by_project, get_character_group_members,
)


# ── 步骤目标配置 ──────────────────────────────────────────────

STEP_GOALS = {
    "chapter_plot_generator": {
        "description": (
            "为第{chapter_index}章生成场景级剧情列表。"
            "需要理解章节规划目标、角色当前状态、活跃伏笔布局、前文衔接点。"
        ),
        "focus": "剧情规划覆盖、伏笔布局时机、角色弧线推进、前文自然衔接",
        "budget": 6000,
    },
    "draft_generator": {
        "description": (
            "根据剧情列表创作白描草稿。"
            "需要精确的角色行为参考、物品约束、前文衔接。"
        ),
        "focus": "角色行为与性格一致、物品清单约束、前文结尾自然承接、剧情完整覆盖",
        "budget": 5000,
    },
    "draft_reviewer": {
        "description": (
            "审查草稿质量。需要对照设定检查一致性、对照前文检查连贯性。"
        ),
        "focus": "设定一致性、角色行为合理性、剧情逻辑、前文连贯",
        "budget": 4000,
    },
    "draft_polisher": {
        "description": (
            "将白描草稿润色为完整小说。需要世界观氛围参考、力量体系描写参考。"
        ),
        "focus": "世界观细节准确、力量体系描写规范、文风统一",
        "budget": 3000,
    },
    "chapter_plot_reviewer": {
        "description": (
            "审查剧情列表质量。需要对照角色能力设定、世界观规则与伏笔布局检查合理性。"
        ),
        "focus": "设定匹配、伏笔布局合理性、剧情因果、信息揭示时机",
        "budget": 4000,
    },
}

# ── 节点级字段白名单（与各 executor 模板占位符消费对齐，None=全部）──
_STEP_FIELD_WHITELISTS = {
    # 剧情生成：消费 11 类全量
    "chapter_plot_generator": None,
    # 草稿生成：prompt 仅消费 角色/前文/RAG/notes（无伏笔/世界观/力量占位符）
    "draft_generator": ["character_ids", "previous_chapters", "rag_queries", "consistency_notes"],
    # 草稿审查：prompt 消费 角色/世界观/前文/notes（无 RAG/伏笔/力量占位符）
    "draft_reviewer": ["character_ids", "world_setting_ids", "previous_chapters", "consistency_notes"],
    # 润色：prompt 仅消费 世界观/notes
    "draft_polisher": ["previous_chapters", "world_setting_ids", "include_power_system", "include_golden_finger", "consistency_notes"],
    # 剧情审查：对照角色能力/金手指/世界观/伏笔检查剧情合理性（无需 RAG/前文细节）
    "chapter_plot_reviewer": ["character_ids", "world_setting_ids", "foreshadow_ids", "include_golden_finger"],
}

# ── 各节点一致性维度清单（引导 consistency_notes 输出方向）──
_STEP_DIMENSIONS = {
    "chapter_plot_generator": [
        "伏笔布局与回收时机", "角色弧线推进（性格/状态/关系）", "剧情因果与前文衔接",
        "信息揭示时机", "能力与剧情可行性", "时间空间落位",
    ],
    "draft_generator": [
        "角色行为与性格一致", "角色状态连续", "物品清单约束",
        "前文自然承接", "信息暴露边界", "能力行为边界",
    ],
    "draft_reviewer": [
        "设定一致", "角色行为合理", "剧情逻辑", "前文连贯",
        "状态与物品核对", "知识边界", "时间线",
    ],
    "draft_polisher": ["世界观细节准确", "力量体系描写规范", "文风统一"],
    "chapter_plot_reviewer": ["设定匹配（角色能力/金手指/世界观与剧情行为一致）", "伏笔布局合理性", "剧情因果与信息揭示时机"],
}

_STEP_NOTES_LIMITS = {
    "chapter_plot_generator": 5, "draft_generator": 5,
    "draft_reviewer": 3, "draft_polisher": 3,
    "chapter_plot_reviewer": 3,
}

# ── 选择字段：JSON 示例行 + 说明 ──
_SELECTION_FIELD_LINES = {
    "character_ids": '"character_ids": [选中的角色id列表]',
    "foreshadow_ids": '"foreshadow_ids": [选中的伏笔id列表]',
    "include_power_system": '"include_power_system": true或false',
    "include_golden_finger": '"include_golden_finger": true或false',
    "world_setting_ids": '"world_setting_ids": [选中的世界观设定id列表]',
    "previous_chapters": '"previous_chapters": [{"index": 章节索引数字, "load_full": true或false}]',
    "rag_queries": '"rag_queries": [{"text": "针对性查询文本", "types": ["chunk_type1"], "limit": 数字}]',
    "consistency_notes": '"consistency_notes": ["一致性要点1", "要点2"]',
}
_SELECTION_FIELD_DESCS = {
    "character_ids": "从清单中选择的角色id，只写id数字",
    "foreshadow_ids": "从清单中选择的伏笔id",
    "include_power_system": "本章是否涉及力量体系/修炼/战斗描写",
    "include_golden_finger": "本章是否涉及金手指能力使用",
    "world_setting_ids": "需要参考的世界观设定id",
    "previous_chapters": "需要的前文，load_full=true加载全文，false只用摘要",
    "rag_queries": "针对当前步骤的RAG语义检索查询，每条必须按【RAG查询要求】构造（含实体与限定、禁止复制原文）；types可选值：chapter/chapter_summary/chapter_paragraph/foreshadow/character",
    "consistency_notes": "一致性要点，按【本节点一致性维度】检查，每条格式为「[维度名] 主体: 规则」，如「[角色状态] 苏瑶: 保持受伤未愈状态」「[物品] 铜钱: 已交给李承言保管」，不超过50字",
}
_ALL_SELECTION_FIELDS = list(_SELECTION_FIELD_LINES.keys())

# character_type 英文 → 中文标签
_CHAR_TYPE_LABELS = {
    'protagonist': '主角', 'co_protagonist': '主角团核心',
    'heroine': '女主', 'villain': '反派',
    'supporting': '配角', 'minor': '龙套',
}


class ContextAnalyzer:
    """上下文分析器：根据步骤目标，从数据清单中选择最相关的上下文条目并组装。"""

    def __init__(self, script_id: int, chapter_index: int):
        self.script_id = script_id
        self.chapter_index = chapter_index
        self._logger = log_manager.get_logger("context_analyzer")

    # ── 主入口 ──────────────────────────────────────────────

    async def analyze_and_assemble(
        self,
        step_name: str,
        inventory: Dict[str, Any],
        structural_data: Dict[str, Any],
        script_id: int,
        project_id: int,
        prev_selections: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """分析 + 组装一步完成。返回精准上下文供 executor 使用。"""
        selection = await self._analyze(step_name, inventory, structural_data,
                                        project_id, prev_selections)
        if not selection:
            self._logger.warning(f"[ContextAnalyzer] LLM 分析失败，使用全量清单")
            selection = self._fallback_selection(inventory, step_name)

        step_ctx = await self._assemble_context(
            selection, inventory, structural_data, script_id, project_id)
        # 将选择结果附带回，供下游步骤参考
        step_ctx["_selection"] = selection
        return step_ctx

    # ── 分析阶段 ────────────────────────────────────────────

    async def _analyze(
        self,
        step_name: str,
        inventory: Dict[str, Any],
        structural_data: Dict[str, Any],
        project_id: int,
        prev_selections: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """调用 LLM 分析当前步骤需要哪些上下文，返回选择指令。"""
        goal = STEP_GOALS.get(step_name)
        if not goal:
            return None

        # 构建分析 prompt
        prompt_text = self._build_analysis_prompt(
            step_name, goal, inventory, structural_data, prev_selections)
        if not prompt_text:
            return None

        system_prompt = "你是一位小说创作的上下文管理专家，负责为每一步创作选择最相关的参考信息。输出严格的JSON格式。"

        try:
            from core.model_executor import get_model_executor
            executor = get_model_executor()
            result = await executor.execute_text_chat(
                prompt=prompt_text,
                system_prompt=system_prompt,
                max_tokens=600,
                script_id=self.script_id,
                project_id=project_id,
                executor_name="context_analyzer",
                prompt_name=f"ctx_analysis_{step_name}",
            )
            content = result.get("content", "") if result else ""
            if not content:
                return None

            # 解析 JSON
            selection = parse_llm_json(
                content,
                script_id=self.script_id,
                project_id=project_id,
                executor_name="context_analyzer",
                prompt_name=f"ctx_analysis_{step_name}",
            )
            if not selection or not isinstance(selection, dict):
                return None

            self._logger.info(
                f"[ContextAnalyzer] {step_name} 分析完成："
                f"角色{len(selection.get('character_ids', []))}个，"
                f"伏笔{len(selection.get('foreshadow_ids', []))}个，"
                f"RAG查询{len(selection.get('rag_queries', []))}条"
            )
            return selection

        except Exception as e:
            self._logger.error(f"[ContextAnalyzer] 分析失败: {e}")
            return None

    def _build_dimension_checklist(self, step_name: str) -> str:
        """按节点生成一致性维度清单文本。"""
        dims = _STEP_DIMENSIONS.get(step_name, [])
        if not dims:
            return ""
        limit = _STEP_NOTES_LIMITS.get(step_name, 5)
        lines = ["  【本节点一致性维度】"]
        for d in dims:
            lines.append(f"  - {d}")
        lines.append(f"  （本节点一致性要点请控制在 {limit} 条内）")
        return "\n".join(lines)

    def _build_output_schema(self, step_name: str) -> str:
        """按节点白名单生成 JSON 输出格式与字段说明。"""
        whitelist = _STEP_FIELD_WHITELISTS.get(step_name)
        fields = _ALL_SELECTION_FIELDS if whitelist is None else whitelist
        body = ["{"]
        for f in fields:
            body.append(f"    {_SELECTION_FIELD_LINES[f]},")
        body.append("}")
        desc = ["  字段说明："]
        for f in fields:
            key = _SELECTION_FIELD_LINES[f].split(":")[0].strip().strip('"')
            desc.append(f"  - {key}：{_SELECTION_FIELD_DESCS[f]}")
        return "\n".join(body + [""] + desc)

    def _build_analysis_prompt(
        self,
        step_name: str,
        goal: Dict[str, Any],
        inventory: Dict[str, Any],
        structural_data: Dict[str, Any],
        prev_selections: Optional[Dict[str, Any]] = None,
    ) -> str:
        """构建上下文分析 prompt。"""
        # 加载 prompt 模板
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts", "context_analysis_prompt.md"
        )
        if not os.path.exists(prompt_path):
            self._logger.error(f"[ContextAnalyzer] prompt 模板不存在: {prompt_path}")
            return ""

        with open(prompt_path, "r", encoding="utf-8") as f:
            raw = f.read().strip()

        # 去除 YAML front matter 分隔符
        if raw.startswith("---"):
            raw = raw[3:].strip()
        if raw.endswith("---"):
            raw = raw[:-3].strip()

        # 提取 user_prompt 部分
        user_prompt = ""
        in_user = False
        in_multi = False
        for line in raw.split("\n"):
            if line.startswith("user_prompt:"):
                in_user = True
                val = line.replace("user_prompt:", "").strip()
                if val.startswith("|"):
                    in_multi = True
                    user_prompt = ""
                else:
                    user_prompt = val
            elif in_user and in_multi:
                user_prompt += line + "\n"
            elif in_user and not in_multi:
                break

        user_prompt = user_prompt.strip()
        if not user_prompt:
            return ""

        chapter_index = self.chapter_index

        # ── 构建清单文本 ──
        character_inventory_text = self._format_char_inventory(inventory)
        foreshadow_inventory_text = self._format_foreshadow_inventory(inventory)
        world_settings_inventory_text = self._format_world_inventory(inventory)
        power_system_summary = self._format_summary_field(inventory.get("power_system"))
        golden_finger_summary = self._format_summary_field(inventory.get("golden_finger"))
        previous_chapters_inventory_text = self._format_prev_ch_inventory(inventory)
        rag_candidates_inventory_text = self._format_rag_candidates(inventory)

        # ── 章节规划摘要 ──
        plan = structural_data.get("current_chapter_plan") or {}
        plan_parts = []
        if plan.get("summary"):
            plan_parts.append(f"概要: {plan['summary'][:200]}")
        if plan.get("key_events"):
            ke = plan["key_events"]
            plan_parts.append(f"关键事件: {ke[:200] if isinstance(ke, str) else json.dumps(ke, ensure_ascii=False)[:200]}")
        chapter_plan_summary = "\n".join(plan_parts) if plan_parts else "（无章节规划）"

        # ── 前步选择信息 ──
        prev_step_selections_text = self._format_prev_selections(prev_selections)

        # ── 步骤描述 ──
        step_description = goal["description"].format(chapter_index=chapter_index)
        focus = goal["focus"]
        budget = goal["budget"]
        dimension_checklist_text = self._build_dimension_checklist(step_name)
        output_schema = self._build_output_schema(step_name)

        try:
            full_prompt = user_prompt.format(
                chapter_index=chapter_index,
                step_name=step_name,
                step_description=step_description,
                focus=focus,
                chapter_plan_summary=chapter_plan_summary,
                character_inventory_text=character_inventory_text,
                foreshadow_inventory_text=foreshadow_inventory_text,
                world_settings_inventory_text=world_settings_inventory_text,
                power_system_summary=power_system_summary,
                golden_finger_summary=golden_finger_summary,
                previous_chapters_inventory_text=previous_chapters_inventory_text,
                rag_candidates_inventory_text=rag_candidates_inventory_text,
                prev_step_selections_text=prev_step_selections_text,
                budget=budget,
                dimension_checklist_text=dimension_checklist_text,
                output_schema=output_schema,
            )
        except KeyError as e:
            self._logger.error(f"[ContextAnalyzer] prompt 占位符缺失: {e}")
            return ""

        return full_prompt

    # ── 组装阶段 ────────────────────────────────────────────

    async def _assemble_context(
        self,
        selection: Dict[str, Any],
        inventory: Dict[str, Any],
        structural_data: Dict[str, Any],
        script_id: int,
        project_id: int,
    ) -> Dict[str, Any]:
        """根据选择指令从 DB 加载完整数据，组装精准上下文。"""
        ctx: Dict[str, Any] = {}

        # 1. 结构数据直接透传
        ctx.update(structural_data)

        # 2. 按 character_ids 加载完整角色卡
        char_ids = selection.get("character_ids", [])
        ctx["characters"] = self._load_full_characters(char_ids, project_id)

        # 3. 按 foreshadow_ids 提取伏笔
        foreshadow_ids = selection.get("foreshadow_ids", [])
        ctx["foreshadows"] = self._extract_foreshadows(foreshadow_ids, inventory)

        # 4. 世界观
        world_ids = selection.get("world_setting_ids", [])
        ctx["world_settings"] = self._load_world_settings(world_ids, project_id)

        # 5. 力量体系 / 金手指
        if selection.get("include_power_system"):
            ctx["power_system"] = get_power_system_by_project(project_id) or {}
        else:
            ctx["power_system"] = {}

        if selection.get("include_golden_finger"):
            ctx["golden_finger"] = get_golden_finger_by_project(project_id) or {}
        else:
            ctx["golden_finger"] = {}

        # 6. 前文（按需加载全文或摘要）
        prev_ch_selections = selection.get("previous_chapters", [])
        ctx["previous_chapters"] = self._load_previous_chapters(
            prev_ch_selections, script_id, project_id, inventory)

        # 7. RAG 精确检索
        rag_queries = selection.get("rag_queries", [])
        ctx["rag_results"] = await self._execute_rag_queries(rag_queries, project_id)

        # 8. 一致性要点
        ctx["consistency_notes"] = selection.get("consistency_notes", [])

        # 9. 角色组（如果选中角色中包含组成员，加载角色组信息）
        ctx["character_group"] = self._maybe_load_character_group(
            char_ids, project_id)

        return ctx

    # ── 数据加载方法 ────────────────────────────────────────

    def _load_full_characters(
        self, char_ids: List[int], project_id: int
    ) -> List[Dict[str, Any]]:
        """按 id 列表加载完整角色卡（含物品）。"""
        if not char_ids:
            return []

        # 批量加载物品
        try:
            items_by_char = get_character_items_by_project(project_id)
        except Exception:
            items_by_char = {}

        characters = []
        for cid in char_ids:
            card = get_character_card(project_id, cid)
            if not card:
                continue
            raw_type = card.get("character_type", "")
            characters.append({
                "role": _CHAR_TYPE_LABELS.get(raw_type, raw_type),
                "character_name": card.get("name", ""),
                "alias": card.get("alias", ""),
                "identity": card.get("identity", ""),
                "protagonist_relation": card.get("protagonist_relation", ""),
                "personality": card.get("core_personality", ""),
                "flaw": card.get("personality_flaw", ""),
                "goals": card.get("true_desire", "") or card.get("long_term_goal", ""),
                "abilities": card.get("ability_limit", ""),
                "items": [
                    {"name": it.get("item_name", ""),
                     "quantity": it.get("quantity", 1) or 1,
                     "desc": it.get("source", "") or it.get("change_note", "")}
                    for it in items_by_char.get(cid, [])
                    if it.get("item_name")
                ],
            })
        return characters

    def _extract_foreshadows(
        self, foreshadow_ids: List[int], inventory: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """从 inventory 的伏笔清单中按 id 提取完整条目。"""
        if not foreshadow_ids:
            return []
        id_set = set(foreshadow_ids)
        return [
            f for f in inventory.get("foreshadows", [])
            if f.get("id") in id_set
        ]

    def _load_world_settings(
        self, world_ids: List[int], project_id: int
    ) -> List[Dict[str, Any]]:
        """加载完整世界观设定。"""
        worldview = get_worldview_by_project(project_id)
        if not worldview:
            return []
        worldview["factions_list"] = get_worldview_factions(worldview["id"])
        return [worldview]

    def _load_previous_chapters(
        self,
        selections: List[Dict[str, Any]],
        script_id: int,
        project_id: int,
        inventory: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """按需加载前文全文或摘要。"""
        if not selections:
            return []

        from repositories import get_script_lines

        # 获取章节摘要映射（用于 load_full=false 时）
        summaries_by_ch = {}
        for ch_info in inventory.get("previous_chapters", []):
            summaries_by_ch[ch_info["index"]] = ch_info.get("summary", "")

        result = []
        for sel in selections:
            ch_idx = sel.get("index")
            if ch_idx is None:
                continue
            load_full = sel.get("load_full", False)

            if load_full:
                # 加载全文
                content = self._read_chapter_content(script_id, ch_idx)
                if content:
                    # 截断保护：上一章取头尾各 2000 字
                    if len(content) > 4000:
                        content = (content[:2000]
                                   + "\n……（中间内容省略）……\n"
                                   + content[-2000:])
                    result.append({
                        "chapter_index": ch_idx,
                        "content": content,
                        "is_latest": True,
                    })
            else:
                # 只用摘要
                summary = summaries_by_ch.get(ch_idx, "")
                if summary:
                    result.append({
                        "chapter_index": ch_idx,
                        "content": summary,
                        "is_summary": True,
                    })

        return result

    def _read_chapter_content(self, script_id: int, chapter_index: int) -> Optional[str]:
        """读取章节全文。"""
        try:
            from services.script_service import ScriptService
            svc = ScriptService()
            content = svc._read_script_chapter_content(script_id, chapter_index)
            if content:
                return content
        except Exception:
            pass
        # 回退到 script_lines
        from repositories import get_script_lines
        lines = get_script_lines(script_id, chapter_index)
        if lines:
            return "\n".join(line["content"] for line in lines)
        return None

    async def _execute_rag_queries(
        self,
        queries: List[Dict[str, Any]],
        project_id: int,
    ) -> List[Dict[str, Any]]:
        """执行 LLM 生成的 RAG 查询，返回检索结果。"""
        if not queries:
            return []

        try:
            from services.vector_store import get_rag_service
            from core.model_executor import get_model_executor

            rag_svc = get_rag_service()
            vec_executor = get_model_executor()

            # 批量编码查询文本
            query_texts = [q.get("text", "") for q in queries if q.get("text")]
            if not query_texts:
                return []

            t2v_result = await vec_executor.execute_text_to_vector(
                query_texts, is_query=True)
            if not t2v_result or t2v_result.get("error"):
                return []
            embeddings = t2v_result.get("embeddings", [])

            all_results = []
            seen = set()
            for query, emb in zip(queries, embeddings):
                if not emb:
                    continue
                chunk_types = query.get("types") or None
                limit = query.get("limit", 5)
                try:
                    results = rag_svc.search(
                        project_id, emb,
                        limit=limit,
                        chunk_types=chunk_types,
                    )
                    for r in results:
                        content = r.get("content", "")
                        dedup = content[:50] + "|" + content[-50:] if len(content) > 100 else content
                        if dedup not in seen:
                            seen.add(dedup)
                            all_results.append(r)
                except Exception:
                    pass

            return all_results[:10]

        except Exception as e:
            self._logger.error(f"[ContextAnalyzer] RAG 查询失败: {e}")
            return []

    def _maybe_load_character_group(
        self, char_ids: List[int], project_id: int
    ) -> Optional[Dict[str, Any]]:
        """如果选中角色包含组成员，加载角色组信息。"""
        if not char_ids:
            return None
        char_group = get_character_group_by_project(project_id)
        if not char_group:
            return None
        group_members = get_character_group_members(char_group["id"])
        member_char_ids = {m.get("character_id") for m in group_members}
        # 如果选中的角色中有组成员，返回角色组信息
        if any(cid in member_char_ids for cid in char_ids):
            id_set = set(char_ids)
            all_chars = {c.get("id"): c for c in
                         get_character_cards_by_project(project_id)}
            enriched = []
            for m in group_members:
                info = {**m}
                card = all_chars.get(m.get("character_id"))
                if card:
                    info["character_name"] = card.get("name", "")
                    info["personality"] = card.get("core_personality", "")
                    info["identity"] = card.get("identity", "")
                enriched.append(info)
            return {**char_group, "enriched_members": enriched}
        return None

    # ── 清单格式化方法 ──────────────────────────────────────

    def _format_char_inventory(self, inventory: Dict[str, Any]) -> str:
        """格式化角色清单文本。"""
        chars = inventory.get("characters", [])
        if not chars:
            return "（无角色）"
        lines = []
        for c in chars[:20]:  # 限制最多展示 20 个
            cid = c.get("id", "?")
            name = c.get("name", "")
            ctype = c.get("type", "")
            summary = c.get("summary", "")[:60]
            lines.append(f"  [{cid}] {name}({ctype}): {summary}")
        return "\n".join(lines)

    def _format_foreshadow_inventory(self, inventory: Dict[str, Any]) -> str:
        """格式化伏笔清单文本。"""
        foreshadows = inventory.get("foreshadows", [])
        if not foreshadows:
            return "（无活跃伏笔）"
        lines = []
        for f in foreshadows[:15]:
            fid = f.get("id", "?")
            content = f.get("content", "")[:60]
            tier = f.get("tier", "")
            planted = f.get("planted_chapter") or f.get("planted_ch") or 0
            urgency = f.get("urgency", "")
            lines.append(f"  [{fid}] [{tier}] {content} (第{planted}章, {urgency})")
        return "\n".join(lines)

    def _format_world_inventory(self, inventory: Dict[str, Any]) -> str:
        """格式化世界观清单文本。"""
        worlds = inventory.get("world_settings", [])
        if not worlds:
            return "（无世界观设定）"
        lines = []
        for w in worlds[:5]:
            wid = w.get("id", "?")
            name = w.get("name", "")
            summary = w.get("summary", "")[:80]
            lines.append(f"  [{wid}] {name}: {summary}")
        return "\n".join(lines)

    def _format_summary_field(self, data: Optional[Dict]) -> str:
        """格式化单条摘要字段。"""
        if not data or not isinstance(data, dict):
            return "（未设定）"
        name = data.get("name", "")
        summary = data.get("summary", "")[:100]
        if name and summary:
            return f"{name}: {summary}"
        if summary:
            return summary
        return "（未设定）"

    def _format_prev_ch_inventory(self, inventory: Dict[str, Any]) -> str:
        """格式化前文章节清单文本。"""
        chapters = inventory.get("previous_chapters", [])
        if not chapters:
            return "（无前文）"
        lines = []
        for ch in chapters:
            idx = ch.get("index", "?")
            summary = ch.get("summary", "")[:80]
            has_full = "可加载全文" if ch.get("has_full") else "仅摘要"
            lines.append(f"  第{idx}章({has_full}): {summary}")
        return "\n".join(lines)

    def _format_rag_candidates(self, inventory: Dict[str, Any]) -> str:
        """格式化 RAG 候选清单文本。"""
        candidates = inventory.get("rag_candidates", [])
        if not candidates:
            return "（无RAG候选）"
        lines = []
        for i, c in enumerate(candidates[:15]):
            doc_id = c.get("doc_id", f"rag_{i}")
            ctype = c.get("type", "")
            chapter = c.get("chapter", 0)
            preview = c.get("preview", "")[:60]
            lines.append(f"  [{doc_id}] {ctype}/第{chapter}章: {preview}")
        return "\n".join(lines)

    def _format_prev_selections(
        self, prev_selections: Optional[Dict[str, Any]]
    ) -> str:
        """格式化前序步骤的选择信息。"""
        if not prev_selections:
            return ""

        step_labels = {
            "chapter_plot_generator": "剧情生成",
            "draft_generator": "草稿生成",
            "draft_reviewer": "草稿审查",
        }

        parts = ["【前序步骤已选择的上下文】"]
        for step_name, sel in prev_selections.items():
            if not isinstance(sel, dict):
                continue
            label = step_labels.get(step_name, step_name)

            # 角色（全量传递）
            char_names = sel.get("character_names", [])
            if char_names:
                parts.append(f"{label}选择了角色: {'、'.join(char_names)}")

            # 伏笔（全量传递）
            foreshadow_contents = sel.get("foreshadow_contents", [])
            if foreshadow_contents:
                parts.append(f"{label}选择了伏笔: {'、'.join(foreshadow_contents)}")

            # 一致性要点（全量传递 + 去重）
            notes = sel.get("consistency_notes", [])
            if notes:
                seen = set()
                for note in notes:
                    key = note if isinstance(note, str) else str(note)
                    if key in seen:
                        continue
                    seen.add(key)
                    parts.append(f"{label}标记的一致性要点: \"{note}\"")

        return "\n".join(parts) if len(parts) > 1 else ""

    # ── 降级选择指令 ────────────────────────────────────────

    def _fallback_selection(
        self, inventory: Dict[str, Any], step_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """LLM 分析失败时的降级策略：选择白名单字段内所有可用条目。"""
        whitelist = _STEP_FIELD_WHITELISTS.get(step_name)
        fields = _ALL_SELECTION_FIELDS if whitelist is None else whitelist
        sel: Dict[str, Any] = {}
        if "character_ids" in fields:
            sel["character_ids"] = [c.get("id") for c in inventory.get("characters", []) if c.get("id")]
        if "foreshadow_ids" in fields:
            sel["foreshadow_ids"] = [f.get("id") for f in inventory.get("foreshadows", []) if f.get("id")]
        if "include_power_system" in fields:
            sel["include_power_system"] = True
        if "include_golden_finger" in fields:
            sel["include_golden_finger"] = True
        if "world_setting_ids" in fields:
            sel["world_setting_ids"] = [w.get("id") for w in inventory.get("world_settings", []) if w.get("id")]
        if "previous_chapters" in fields:
            sel["previous_chapters"] = [
                {"index": ch.get("index"), "load_full": ch.get("has_full", False)}
                for ch in inventory.get("previous_chapters", [])
                if ch.get("index") is not None
            ]
        if "rag_queries" in fields:
            sel["rag_queries"] = []
        if "consistency_notes" in fields:
            sel["consistency_notes"] = []
        return sel
