"""执行器6：上下文构建器（轻量盘点模式）。

不再全量加载所有数据，而是产出两类轻量输出：
1. context_inventory：所有可用数据的摘要清单，供 ContextAnalyzer 的 LLM 分析选择
2. structural_data：始终需要的结构性数据（当前章节规划、卷纲、追读钩子等）

RAG 只执行 1 轮宽泛预检索（~15条候选），精确查询由各 executor 的
ContextAnalyzer 按需执行。
"""

import json
from typing import Dict, Any, List, Optional

from ..base_executor import BaseExecutor, ExecutorResult
from repositories import get_script_lines
from webnovel.repositories import (
    get_webnovel_project_by_script, get_volume_outlines_by_project,
    get_chapter_meta, get_worldview_by_project, get_power_system_by_project,
    get_golden_finger_by_project, get_villain_by_project,
    get_character_cards_by_project, get_timeline_by_project,
    get_idea_bank_by_project, get_chapter_plans_by_volume,
    get_active_open_loops,
    get_character_group_by_project, get_character_group_members,
    get_character_items_by_project,
    get_worldview_factions, get_worldview_history,
    get_open_loops_by_project,
    get_character_states_before_chapter,
)


def _normalize_plan_list_fields(plan):
    """将章节规划中 repository 解析为列表的字段归一化为字符串。"""
    if not isinstance(plan, dict):
        return plan
    for key in ("key_events", "cpns", "must_cover_nodes", "forbidden_zones"):
        val = plan.get(key)
        if isinstance(val, list):
            plan[key] = "；".join(str(v) for v in val) if key == "key_events" \
                else json.dumps(val, ensure_ascii=False)
    return plan


# character_type 英文 → 中文标签
_CHAR_TYPE_LABELS = {
    'protagonist': '主角', 'co_protagonist': '主角团核心',
    'heroine': '女主', 'villain': '反派',
    'supporting': '配角', 'minor': '龙套',
}


class ContextBuilderExecutor(BaseExecutor):
    """上下文构建器执行器（轻量盘点模式）。"""

    step_name = "context_builder"
    step_description = "上下文盘点"
    step_weight = 10

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行上下文盘点：构建轻量清单 + 结构数据。"""
        try:
            script_id = self.script_id
            chapter_index = self.chapter_index

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="未找到项目信息",
                    step_summary="上下文盘点失败"
                )

            project_id = project["id"]

            # ── 1. 加载基础数据（轻量级） ──
            worldview = get_worldview_by_project(project_id)
            if worldview:
                worldview["factions_list"] = get_worldview_factions(worldview["id"])
                worldview["history_list"] = get_worldview_history(worldview["id"])
            power_system = get_power_system_by_project(project_id)
            golden_finger = get_golden_finger_by_project(project_id)
            villain = get_villain_by_project(project_id)
            timelines = get_timeline_by_project(project_id)

            # 角色卡：只提取 id + 摘要
            all_characters = get_character_cards_by_project(project_id)
            try:
                items_by_char = get_character_items_by_project(project_id)
            except Exception:
                items_by_char = {}

            # 卷纲 & 章节规划
            volume_outlines = get_volume_outlines_by_project(project_id)
            current_volume = None
            for vo in volume_outlines:
                if vo.get("chapter_start") <= chapter_index <= vo.get("chapter_end", chapter_index):
                    current_volume = vo
                    break

            chapter_plans = []
            if current_volume:
                chapter_plans = get_chapter_plans_by_volume(current_volume["id"])
            for _plan in chapter_plans:
                _normalize_plan_list_fields(_plan)

            current_chapter_plan = None
            for plan in chapter_plans:
                if plan.get("chapter_index") == chapter_index:
                    current_chapter_plan = plan
                    break

            # 主角组（轻量）
            char_group = get_character_group_by_project(project_id)
            char_group_summary = None
            if char_group:
                group_members = get_character_group_members(char_group["id"])
                card_map = {c["id"]: c for c in all_characters if c.get("id")}
                members_summary_parts = []
                for m in group_members[:8]:
                    card = card_map.get(m.get("character_id"))
                    name = card.get("name", "") if card else f"成员{m.get('id', '')}"
                    role = m.get("role", "")
                    members_summary_parts.append(f"{name}({role})" if role else name)
                char_group_summary = {
                    "name": char_group.get("name", ""),
                    "goal": char_group.get("common_goal", "")[:100],
                    "members_summary": "、".join(members_summary_parts),
                }

            # 活跃伏笔（轻量摘要）
            active_loops = get_active_open_loops(project_id)

            # ── 2. 构建 context_inventory ──
            inventory = self._build_inventory(
                all_characters, items_by_char, active_loops,
                worldview, power_system, golden_finger, villain,
                char_group_summary, chapter_index, project_id,
                current_chapter_plan,
            )

            # ── 3. 构建 structural_data ──
            structural = self._build_structural_data(
                project, current_volume, current_chapter_plan,
                chapter_index, chapter_index,
            )

            # ── 3.5 上章末角色状态 + 不可提前揭示的伏笔（始终需要的结构数据） ──
            structural["last_character_states"] = get_character_states_before_chapter(
                project_id, chapter_index)
            structural["undisclosed_foreshadows"] = self._build_undisclosed_foreshadows(
                active_loops, chapter_index)

            # ── 4. 追读钩子（始终需要的结构数据） ──
            if chapter_index > 0:
                prev_meta = get_chapter_meta(project_id, chapter_index - 1)
                if prev_meta:
                    structural["previous_hook"] = {
                        "hook_content": prev_meta.get("hook_content", ""),
                        "hook_type": prev_meta.get("hook_type", ""),
                        "hook_strength": prev_meta.get("hook_strength", ""),
                        "hook_pattern": prev_meta.get("hook_pattern", ""),
                        "ending_emotion": prev_meta.get("ending_emotion", ""),
                        "ending_location": prev_meta.get("ending_location", ""),
                    }
                else:
                    structural["previous_hook"] = {}
            else:
                structural["previous_hook"] = {}

            # ── 5. RAG 预检索（1 轮宽泛查询） ──
            rag_candidates = await self._rag_pre_retrieve(
                project_id, current_chapter_plan, script_id)
            inventory["rag_candidates"] = rag_candidates

            summary = (
                f"上下文盘点完成：角色{len(inventory['characters'])}个，"
                f"伏笔{len(inventory['foreshadows'])}个，"
                f"前文{len(inventory['previous_chapters'])}章，"
                f"RAG候选{len(rag_candidates)}条"
            )

            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "context_inventory": inventory,
                    "structural_data": structural,
                }
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"上下文盘点执行失败: {str(e)}",
                step_summary="上下文盘点执行失败"
            )

    # ── 清单构建 ────────────────────────────────────────────

    def _build_inventory(
        self,
        all_characters: list,
        items_by_char: dict,
        active_loops: list,
        worldview, power_system, golden_finger, villain,
        char_group_summary,
        chapter_index: int,
        project_id: int,
        current_chapter_plan: dict,
    ) -> dict:
        """构建轻量级数据清单。"""

        # 角色清单：id + 一行摘要
        characters_inv = []
        for char in all_characters:
            cid = char.get("id")
            if not cid:
                continue
            raw_type = char.get("character_type", "")
            type_label = _CHAR_TYPE_LABELS.get(raw_type, raw_type)
            name = char.get("name", "")
            identity = char.get("identity", "")[:30]
            personality = char.get("core_personality", "")[:30]
            goals = (char.get("true_desire", "") or char.get("long_term_goal", ""))[:30]
            # 物品摘要
            items = items_by_char.get(cid, [])
            item_names = [it.get("item_name", "") for it in items if it.get("item_name")]
            items_str = "、".join(item_names[:3]) if item_names else "无"
            # 组装一行摘要
            summary_parts = []
            if identity:
                summary_parts.append(f"身份:{identity}")
            if personality:
                summary_parts.append(f"性格:{personality}")
            if goals:
                summary_parts.append(f"目标:{goals}")
            summary_parts.append(f"持有:{items_str}")
            characters_inv.append({
                "id": cid,
                "name": name,
                "type": type_label,
                "summary": ", ".join(summary_parts)[:80],
            })

        # 伏笔清单：id + 摘要
        foreshadows_inv = []
        for loop in active_loops:
            foreshadows_inv.append({
                "id": loop.get("id"),
                "content": loop.get("content", "")[:80],
                "tier": loop.get("tier", ""),
                "planted_chapter": loop.get("planted_chapter", 0),
                "urgency": loop.get("urgency", ""),
            })

        # 世界观清单
        world_inv = []
        if worldview:
            world_inv.append({
                "id": worldview.get("id"),
                "name": worldview.get("name", "") or worldview.get("world_summary", "")[:30],
                "summary": (worldview.get("world_summary", "") or "")[:150],
            })

        # 力量体系摘要
        ps_summary = {}
        if power_system:
            ps_summary = {
                "name": power_system.get("system_type", "") or "未命名",
                "summary": f"体系类型:{power_system.get('system_type', '')}, 核心理念:{(power_system.get('core_creed', '') or '')[:60]}",
            }

        # 金手指摘要
        gf_summary = {}
        if golden_finger:
            gf_summary = {
                "name": golden_finger.get("main_role", "") or "未命名",
                "summary": f"类型:{golden_finger.get('type', '')}, 核心能力:{(golden_finger.get('core_function', '') or '')[:60]}, 代价:{(golden_finger.get('irreversible_cost', '') or '')[:40]}",
            }

        # 反派摘要
        villain_summary = {}
        if villain:
            villain_summary = {
                "name": villain.get("name", "") or "未命名",
                "summary": f"身份:{(villain.get('identity', '') or '')[:40]}, 动机:{(villain.get('motivation', '') or '')[:40]}",
            }

        # 前文章节摘要（只取摘要，不加载全文）
        prev_chapters_inv = self._build_prev_chapters_inventory(
            project_id, chapter_index)

        # 时间线事件摘要
        timeline_inv = []
        timelines = get_timeline_by_project(project_id)
        if timelines:
            from webnovel.repositories import get_timeline_chapters
            tl_chapters = get_timeline_chapters(timelines.get("id"))
            for tc in (tl_chapters or [])[:10]:
                timeline_inv.append({
                    "chapter": tc.get("chapter_number", 0),
                    "event": (tc.get("event", "") or "")[:80],
                    "characters": (tc.get("characters", "") or "")[:60],
                })

        return {
            "characters": characters_inv,
            "foreshadows": foreshadows_inv,
            "world_settings": world_inv,
            "power_system": ps_summary,
            "golden_finger": gf_summary,
            "villain": villain_summary,
            "character_group": char_group_summary,
            "previous_chapters": prev_chapters_inv,
            "timeline_events": timeline_inv,
            "rag_candidates": [],  # 由 _rag_pre_retrieve 填充
        }

    def _build_undisclosed_foreshadows(self, active_loops: list, chapter_index: int) -> list:
        """构建不可提前揭示的伏笔清单：已埋设（planted_chapter <= 本章）且未回收的伏笔。

        这些伏笔的答案不能在本章提前暴露，供剧情生成/审查约束。
        """
        result = []
        for loop in active_loops:
            planted = loop.get("planted_chapter") or 0
            if planted <= chapter_index:
                result.append({
                    "content": loop.get("content", "")[:120],
                    "planted_chapter": planted,
                    "target_chapter": loop.get("target_chapter", 0),
                    "tier": loop.get("tier", ""),
                    "urgency": loop.get("urgency", ""),
                })
        return result

    def _build_prev_chapters_inventory(
        self, project_id: int, chapter_index: int
    ) -> list:
        """构建前文章节摘要清单（只含摘要，不含全文）。"""
        result = []
        # 获取章节摘要（从 RAG 中）
        summaries_by_ch = {}
        try:
            from services.vector_store import get_rag_service
            for doc in get_rag_service().get_chunks(project_id, "chapter_summary"):
                if doc.get("chapter_number"):
                    summaries_by_ch[doc["chapter_number"]] = doc.get("content", "")
        except Exception:
            pass

        for i in range(max(0, chapter_index - 5), chapter_index):
            summary = summaries_by_ch.get(i, "")
            if not summary:
                # 回退：截取 script_lines 的前 200 字
                lines = get_script_lines(None, i)
                # script_lines 需要 script_id，这里用 project_id 查不到
                # 简化处理：标记为 has_full=True，由 ContextAnalyzer 按需加载
                summary = f"第{i}章（摘要待生成）"
            result.append({
                "index": i,
                "summary": summary[:200],
                "has_full": True,  # 全文可由 ContextAnalyzer 按需加载
            })

        return result

    # ── 结构数据构建 ────────────────────────────────────────

    def _build_structural_data(
        self, project, current_volume, current_chapter_plan,
        chapter_index, script_id,
    ) -> dict:
        """构建始终需要的结构性数据。"""
        return {
            "project": {
                "title": project.get("title", ""),
                "genre": project.get("genre", ""),
                "one_liner": project.get("one_liner", ""),
                "target_length": project.get("target_length", ""),
                "total_volumes": project.get("total_volumes", 0),
                "total_chapters": project.get("total_chapters", 0),
            },
            "current_chapter_plan": current_chapter_plan,
            "current_volume": current_volume,
            "chapter_index": chapter_index,
        }

    # ── RAG 预检索 ──────────────────────────────────────────

    async def _rag_pre_retrieve(
        self,
        project_id: int,
        current_chapter_plan: Optional[dict],
        script_id: int,
    ) -> list:
        """1 轮宽泛 RAG 预检索，为 LLM 提供候选池。"""
        if not current_chapter_plan:
            return []

        try:
            from core.config_manager import get_model_capabilities
            if not get_model_capabilities().get("text_to_vector"):
                return []

            from services.vector_store import get_rag_service
            from core.model_executor import get_model_executor

            vec_executor = get_model_executor()
            rag_svc = get_rag_service()

            # 构建宽泛查询文本
            plan_parts = [
                current_chapter_plan.get('summary', ''),
                current_chapter_plan.get('key_events', ''),
            ]
            query_text = ' '.join(p for p in plan_parts if p).strip()
            if not query_text:
                return []

            # 编码
            t2v_result = await vec_executor.execute_text_to_vector(
                [query_text], is_query=True)
            if not t2v_result or t2v_result.get("error"):
                return []
            embedding = (t2v_result.get("embeddings", []) or [[]])[0]
            if not embedding:
                return []

            # 宽泛检索（不限类型，取 15 条）
            results = rag_svc.search(
                project_id, embedding,
                limit=15,
                chunk_types=None,
                min_score=0,  # 不设阈值，让 LLM 判断相关性
            )

            # 格式化为候选清单
            candidates = []
            for r in results:
                content = r.get("content", "")
                candidates.append({
                    "doc_id": r.get("id", ""),
                    "type": r.get("chunk_type", ""),
                    "chapter": r.get("chapter_number", 0),
                    "preview": content[:80],
                })

            return candidates

        except Exception as e:
            from utils.logger import log_manager
            log_manager.get_logger("context_builder").warning(
                f"RAG 预检索失败（不阻断流程）: {e}")
            return []
