"""执行器6：上下文构建器。

参考webnovel-writer的webnovel-write SKILL，实现完整的上下文构建流程。
包括：项目数据加载、角色卡片、金手指、力量体系、世界观、时间线、前文回顾等。

输出内容：
1. 项目核心设定（书名、题材、一句话简介）
2. 角色卡片（主角、配角、反派）
3. 金手指设定
4. 力量体系
5. 世界观设定
6. 卷章规划（当前卷纲、章节规划）
7. 前文回顾（上一章整章注入，更早 2 章用结构化摘要）
8. 时间线信息
9. 反套路规则和硬性约束
"""

from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from repositories import get_script_characters, get_script_lines
from webnovel.repositories import (
    get_webnovel_project_by_script, get_volume_outlines_by_project,
    get_chapter_meta, get_worldview_by_project, get_power_system_by_project,
    get_golden_finger_by_project, get_villain_by_project,
    get_character_cards_by_project, get_timeline_by_project,
    get_idea_bank_by_project, get_chapter_plans_by_volume,
    get_active_open_loops,
    get_character_group_by_project, get_character_group_members,
    get_active_character_ids,
    get_worldview_factions, get_worldview_history,
    get_character_items_by_project
)


def _content_fingerprint(content: str) -> str:
    """生成内容指纹用于去重。

    取内容的前50字+后50字组合，比单纯取前N字更能区分不同段落，
    同时避免滑动窗口切片因前段相同而被误判为重复。
    """
    c = content.strip()
    if len(c) <= 100:
        return c
    return c[:50] + "|" + c[-50:]


# 上一章整章注入的安全上限（约每章 3000 字的体量留有余量）；
# 超出时取头尾各半，保住最关键的章尾承接信息。
PREV_CHAPTER_MAX_CHARS = 4000


def _truncate_head_tail(content: str, max_chars: int = PREV_CHAPTER_MAX_CHARS) -> str:
    """超长章节取头尾各半截断，优先保留章尾（续写承接最需要）。"""
    if len(content) <= max_chars:
        return content
    half = max_chars // 2
    return content[:half] + "\n……（中间内容省略）……\n" + content[-half:]


def _normalize_plan_list_fields(plan):
    """将章节规划中 repository 解析为列表的字段归一化为字符串。

    key_events/cpns/must_cover_nodes/forbidden_zones 在 repository 层经
    json.loads 后为列表，而下游执行器（剧情生成/审查等）均按字符串使用；
    不归一化会导致 ' '.join / [:300] 等字符串操作抛 TypeError 或静默产出错误内容。
    """
    if not isinstance(plan, dict):
        return plan
    for key in ("key_events", "cpns", "must_cover_nodes", "forbidden_zones"):
        val = plan.get(key)
        if isinstance(val, list):
            import json as _json
            plan[key] = "；".join(str(v) for v in val) if key == "key_events" \
                else _json.dumps(val, ensure_ascii=False)
    return plan


class ContextBuilderExecutor(BaseExecutor):
    """上下文构建器执行器。"""

    step_name = "context_builder"
    step_description = "上下文构建"
    step_weight = 10

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行上下文构建。"""
        try:
            script_id = self.script_id
            chapter_index = self.chapter_index

            built_context = {}

            project = get_webnovel_project_by_script(script_id)
            if project:
                project_id = project["id"]

                worldview = get_worldview_by_project(project_id)
                if worldview:
                    worldview["factions_list"] = get_worldview_factions(worldview["id"])
                    worldview["history_list"] = get_worldview_history(worldview["id"])
                power_system = get_power_system_by_project(project_id)
                golden_finger = get_golden_finger_by_project(project_id)
                villain = get_villain_by_project(project_id)
                idea_bank = get_idea_bank_by_project(project_id)
                timelines = get_timeline_by_project(project_id)

                protagonists = get_character_cards_by_project(project_id, "protagonist")
                co_protagonists = get_character_cards_by_project(project_id, "co_protagonist")
                heroines = get_character_cards_by_project(project_id, "heroine")
                supporting_chars = get_character_cards_by_project(project_id, "supporting")
                minor_chars = get_character_cards_by_project(project_id, "minor")
                all_characters = protagonists + co_protagonists + heroines + supporting_chars + minor_chars

                # 过滤为活跃角色（核心角色 + 最近出场角色）
                active_ids = get_active_character_ids(project_id, chapter_index)
                if active_ids:
                    all_characters = [c for c in all_characters if c.get("id") in active_ids]

                volume_outlines = get_volume_outlines_by_project(project_id)

                current_volume = None
                volume_number = 1
                for vo in volume_outlines:
                    if vo.get("chapter_start") <= chapter_index <= vo.get("chapter_end", chapter_index):
                        current_volume = vo
                        volume_number = vo.get("volume_number", 1)
                        break

                chapter_plans = []
                if current_volume:
                    chapter_plans = get_chapter_plans_by_volume(current_volume["id"])

                current_chapter_plan = None
                for plan in chapter_plans:
                    if plan.get("chapter_index") == chapter_index:
                        current_chapter_plan = plan
                        break

                # 列表字段归一化为字符串，保证下游执行器按字符串消费不报错；
                # 直接改原 dict，writing_context 中引用同步生效，RAG 多轮查询一并受益。
                for _plan in chapter_plans:
                    _normalize_plan_list_fields(_plan)

                built_context["project"] = {
                    "title": project.get("title", ""),
                    "genre": project.get("genre", ""),
                    "one_liner": project.get("one_liner", ""),
                    "target_length": project.get("target_length", ""),
                    "total_volumes": project.get("total_volumes", 0),
                    "total_chapters": project.get("total_chapters", 0),
                }

                built_context["world_settings"] = [worldview] if worldview else []
                built_context["power_system"] = power_system or {}
                built_context["golden_finger"] = golden_finger or {}
                built_context["villain"] = villain or {}
                built_context["idea_bank"] = idea_bank or {}
                built_context["timelines"] = timelines or []

                # character_type 存储为英文，翻译为中文以便 LLM prompt 使用
                _char_type_labels = {
                    'protagonist': '主角', 'co_protagonist': '主角团核心',
                    'heroine': '女主', 'villain': '反派',
                    'supporting': '配角', 'minor': '龙套',
                }
                # 批量加载角色持有物品（写文物品一致性约束的数据源；失败时降级为空不阻断）
                try:
                    _items_by_char = get_character_items_by_project(project_id)
                except Exception:
                    _items_by_char = {}
                built_context["characters"] = []
                for char in all_characters:
                    raw_type = char.get("character_type", "")
                    built_context["characters"].append({
                        "role": _char_type_labels.get(raw_type, raw_type),
                        "character_name": char.get("name", ""),
                        "alias": char.get("alias", ""),
                        "identity": char.get("identity", ""),
                        "protagonist_relation": char.get("protagonist_relation", ""),
                        "personality": char.get("core_personality", ""),
                        "flaw": char.get("personality_flaw", ""),
                        "goals": char.get("true_desire", "") or char.get("long_term_goal", ""),
                        "abilities": char.get("ability_limit", ""),
                        "items": [
                            {"name": it.get("item_name", ""),
                             "quantity": it.get("quantity", 1) or 1,
                             "desc": it.get("source", "") or it.get("change_note", "")}
                            for it in _items_by_char.get(char.get("id"), [])
                            if it.get("item_name")
                        ],
                    })

                built_context["volume_outlines"] = volume_outlines
                built_context["current_volume"] = current_volume
                built_context["chapter_plans"] = chapter_plans
                built_context["current_chapter_plan"] = current_chapter_plan

                # 加载角色组及其成员，通过 character_id 关联角色卡信息
                char_group = get_character_group_by_project(project_id)
                if char_group:
                    group_members = get_character_group_members(char_group["id"])
                    card_map = {c["id"]: c for c in all_characters if c.get("id")}
                    enriched_members = []
                    for m in group_members:
                        member_info = {**m}
                        card = card_map.get(m.get("character_id"))
                        if card:
                            member_info["character_name"] = card.get("name", "")
                            member_info["personality"] = card.get("core_personality", "")
                            member_info["identity"] = card.get("identity", "")
                        enriched_members.append(member_info)
                    built_context["character_group"] = {
                        **char_group,
                        "enriched_members": enriched_members
                    }
                else:
                    built_context["character_group"] = None

            else:
                built_context["project"] = {}
                built_context["world_settings"] = []
                built_context["power_system"] = {}
                built_context["golden_finger"] = {}
                built_context["villain"] = {}
                built_context["idea_bank"] = {}
                built_context["timelines"] = []
                built_context["characters"] = get_script_characters(script_id)
                built_context["volume_outlines"] = []
                built_context["current_volume"] = None
                built_context["chapter_plans"] = []
                built_context["current_chapter_plan"] = None
                built_context["character_group"] = None

            built_context["previous_chapters"] = []
            # 优先从章节文件读取前文（script_chapters 表记录了文件路径）
            # 回退到 script_lines 表
            try:
                from services.script_service import ScriptService
                _script_svc = ScriptService()
            except Exception:
                _script_svc = None

            # 前文注入策略（按每章约 3000 字的体量设计）：
            # - 上一章：整章注入（截 2000 字开头会丢失章尾承接信息，而续写最依赖章尾）；
            # - 更早 2 章：优先用 RAG 中 LLM 生成的结构化摘要（概要/关键事件/角色变化），
            #   质量高于机械截开头，且篇幅短；无摘要时回退截取开头 500 字。
            _summaries_by_ch = {}
            if project:
                try:
                    from services.vector_store import get_rag_service
                    for _doc in get_rag_service().get_chunks(project_id, "chapter_summary"):
                        if _doc.get("chapter_number"):
                            _summaries_by_ch[_doc["chapter_number"]] = _doc.get("content", "")
                except Exception:
                    pass

            for i in range(max(0, chapter_index - 3), chapter_index):
                content = None
                # 1) 从章节文件读取
                if _script_svc:
                    try:
                        content = _script_svc._read_script_chapter_content(script_id, i)
                    except Exception:
                        content = None
                # 2) 回退到 script_lines
                if not content:
                    lines = get_script_lines(script_id, i)
                    if lines:
                        content = "\n".join(line["content"] for line in lines)
                if not content:
                    continue

                is_latest = (i == chapter_index - 1)
                if is_latest:
                    built_context["previous_chapters"].append({
                        "chapter_index": i,
                        "content": _truncate_head_tail(content),
                        "is_latest": True,
                    })
                else:
                    summary = _summaries_by_ch.get(i, "")
                    built_context["previous_chapters"].append({
                        "chapter_index": i,
                        "content": summary if summary else content[:500],
                        "is_summary": bool(summary),
                    })

            # 加载上一章的追读钩子
            if chapter_index > 0 and project:
                prev_meta = get_chapter_meta(project_id, chapter_index - 1)
                if prev_meta:
                    built_context["previous_hook"] = {
                        "hook_content": prev_meta.get("hook_content", ""),
                        "hook_type": prev_meta.get("hook_type", ""),
                        "hook_strength": prev_meta.get("hook_strength", ""),
                        "hook_pattern": prev_meta.get("hook_pattern", ""),
                        "ending_emotion": prev_meta.get("ending_emotion", ""),
                        "ending_location": prev_meta.get("ending_location", ""),
                    }
                else:
                    built_context["previous_hook"] = {}
            else:
                built_context["previous_hook"] = {}

            # 加载活跃伏笔
            if project:
                built_context["active_open_loops"] = get_active_open_loops(project_id)
            else:
                built_context["active_open_loops"] = []

            # 从章节规划汇总叙事线分布
            strand_summary = {}
            for plan in chapter_plans:
                s = plan.get("strand", "").strip() if isinstance(plan, dict) else ""
                if s:
                    strand_summary[s] = strand_summary.get(s, 0) + 1
            built_context["strand_summary"] = strand_summary

            current_lines = get_script_lines(script_id, chapter_index)
            if current_lines:
                built_context["current_content"] = "\n".join(line["content"] for line in current_lines)
            else:
                built_context["current_content"] = ""

            # RAG 语义检索：多轮查询策略 + 片段重排序精排
            built_context["rag_context"] = []
            built_context["rag_reranked"] = False
            if project:
                try:
                    # 通过 t2v 能力链编码：首次写文时本地 embedding 模型尚未加载，
                    # 执行器链会按需自动加载（此前直接检查 is_loaded() 导致模型未加载时
                    # 整个 RAG 检索被静默跳过，rag_context 永远为空）；同时兼容用户配置的云端向量能力。
                    from core.config_manager import get_model_capabilities
                    if get_model_capabilities().get("text_to_vector"):
                        from services.vector_store import get_rag_service
                        from core.model_executor import get_model_executor
                        vec_executor = get_model_executor()
                        rag_svc = get_rag_service()

                        # 构建多轮查询：(query_text, chunk_types, limit)
                        # limit 适度放大，为重排序提供足够的候选池（原 5/5/3~5/3）
                        queries = []

                        # 查询1：章节规划语义查询（最优先）
                        # 增强：加入角色名和卷目标作为语义锚点，提升查询区分度
                        current_plan = built_context.get("current_chapter_plan")
                        if current_plan:
                            plan_parts = [
                                current_plan.get('summary', ''),
                                current_plan.get('key_events', ''),
                            ]
                            # 加入本章涉及的角色名作为语义锚点
                            char_names = [
                                c.get('character_name', '')
                                for c in built_context.get('characters', [])[:3]
                            ]
                            char_names = [n for n in char_names if n]
                            if char_names:
                                plan_parts.append(' '.join(char_names))
                            plan_query = ' '.join(p for p in plan_parts if p).strip()
                            if plan_query:
                                queries.append((plan_query, ["chapter", "chapter_summary", "foreshadow", "character"], 8))

                        # 查询2：追读钩子查询
                        prev_hook = built_context.get("previous_hook", {})
                        if prev_hook and prev_hook.get("hook_content", "").strip():
                            queries.append((prev_hook["hook_content"].strip(), ["chapter", "chapter_paragraph", "foreshadow"], 6))

                        # 查询3：已有内容查询（续写场景）或前文末尾
                        if built_context.get("current_content"):
                            queries.append((built_context["current_content"][:300], ["chapter", "chapter_paragraph"], 5))
                        elif built_context.get("previous_chapters"):
                            last_ch = built_context["previous_chapters"][-1]
                            tail = last_ch.get("content", "")[-300:]
                            if tail:
                                queries.append((tail, ["chapter", "chapter_paragraph", "character"], 6))

                        # 查询4：伏笔回收查询（用活跃伏笔的 setup_content 构建）
                        active_loops = built_context.get("active_open_loops", [])
                        if active_loops:
                            loop_texts = [
                                loop.get("setup_content", "")[:100]
                                for loop in active_loops[:3]
                            ]
                            loop_query = ' '.join(t for t in loop_texts if t).strip()
                            if loop_query:
                                queries.append((loop_query, ["foreshadow", "chapter_summary"], 4))

                        # 通过 t2v 能力链批量编码所有查询文本：一次推理代替逐轮调用，
                        # 内部在工作线程执行不阻塞事件循环；失败返回 {"error": ...}
                        embeddings = []
                        if queries:
                            t2v_result = await vec_executor.execute_text_to_vector(
                                [q[0] for q in queries], is_query=True
                            )
                            if t2v_result and not t2v_result.get("error"):
                                embeddings = t2v_result.get("embeddings", []) or []

                        # 执行多轮查询，粗筛（章节邻近性衰减）+ 指纹去重，
                        # 按轮次保留候选供后续重排（跨轮次的向量余弦相似度不可比，
                        # 因为查询向量不同，不能直接混合排序）
                        # 前文回顾已覆盖的章节集合（上一章 + 更早 2 章），
                        # 用于 RAG 候选过滤，避免 chapter_summary 与前文回顾重复。
                        _prev_covered_chs = set(
                            range(max(0, chapter_index - 3), chapter_index)
                        )

                        seen_contents = set()
                        all_rag_results = []
                        per_round_candidates = []  # [(query_text, kept_results)]
                        for (query_text, chunk_types, limit), emb in zip(queries, embeddings):
                            if not emb:
                                continue
                            try:
                                results = rag_svc.search(
                                    project_id, emb,
                                    limit=limit, chunk_types=chunk_types,
                                )
                                kept = []
                                for r in results:
                                    ch_num = r.get("chapter_number", 0)
                                    chunk_type = r.get("chunk_type", "")

                                    # 上一章已整章注入前文回顾，其内容类片段（正文/摘要/
                                    # 段落）再进入 RAG 会重复挤占槽位，只保留远距离信息（
                                    # 伏笔/设定/更早章节）供下游注入，发挥 RAG 独特价值。
                                    if (ch_num == chapter_index - 1
                                            and chunk_type in (
                                                "chapter", "chapter_summary", "chapter_paragraph")):
                                        continue

                                    # 前文回顾已覆盖章节的结构化摘要（chapter_summary）
                                    # 在 RAG 中属于冗余，剔除后槽位专供伏笔/设定/段落
                                    # 细节等 RAG 独特价值内容。
                                    # 注意：chapter_paragraph 不过滤，因为前文回顾对更
                                    # 早章节只有精简摘要，段落级细节仍依赖 RAG 补充。
                                    if chunk_type == "chapter_summary" and ch_num in _prev_covered_chs:
                                        continue

                                    # 章节邻近性衰减：距离当前章节越远，要求越高。
                                    # 0.45 按 Qwen3-Embedding-0.6B 实测分布校准（相关片段约 0.30~0.51）；
                                    # 后续重排序会二次把关，远距离章节不必要求过高向量分数，
                                    # 否则超过 3 章前的伏笔/设定将永远无法被检索到
                                    distance = abs(ch_num - chapter_index)
                                    score = r.get("score", 0)
                                    if distance > 3 and score < 0.45:
                                        continue  # 远距离章节需要更高相似度

                                    # 内容指纹去重：取前50字+后50字组合
                                    content = r.get("content", "")
                                    dedup_key = _content_fingerprint(content)
                                    if dedup_key not in seen_contents:
                                        seen_contents.add(dedup_key)
                                        kept.append(r)
                                all_rag_results.extend(kept)
                                per_round_candidates.append((query_text, kept))
                            except Exception:
                                pass

                        # 片段重排序精排：每轮候选用各自的查询文本重排，保留该轮的语义意图；
                        # 重排分数是 query-doc 相关性概率（0-1），跨轮次可比，
                        # 因此可全局按重排分数统一排序，替代原来按查询轮次拼接的顺序。
                        # 未配置能力或调用失败时静默回退到原有合并顺序，不阻断流水线。
                        try:
                            from core.model_executor import get_model_executor
                            rerank_executor = get_model_executor()
                            for query_text, kept in per_round_candidates:
                                if not kept:
                                    continue
                                documents = [(r.get("content") or "")[:512] for r in kept]
                                rerank_result = await rerank_executor.execute_rerank(
                                    query_text, documents, top_k=len(documents)
                                )
                                if rerank_result.get("error"):
                                    continue
                                for item in rerank_result.get("results", []):
                                    idx = item.get("index", -1)
                                    if 0 <= idx < len(kept):
                                        kept[idx]["rerank_score"] = float(item.get("score", 0.0))
                            if any("rerank_score" in r for r in all_rag_results):
                                all_rag_results.sort(
                                    key=lambda r: r.get("rerank_score", -1.0),
                                    reverse=True,
                                )
                                built_context["rag_reranked"] = True
                        except Exception:
                            pass

                        built_context["rag_context"] = all_rag_results[:10]
                except Exception:
                    pass

            cg = built_context.get("character_group")
            cg_member_count = len(cg.get("enriched_members", [])) if cg else 0
            summary = (
                f"上下文构建完成：世界观设定{len(built_context['world_settings'])}条，"
                f"角色{len(built_context['characters'])}个，"
                f"前文{len(built_context['previous_chapters'])}章，"
                f"卷纲{len(built_context['volume_outlines'])}卷，"
                f"活跃伏笔{len(built_context['active_open_loops'])}个，"
                f"RAG片段{len(built_context['rag_context'])}条"
                + ("（已精排）" if built_context.get("rag_reranked") else "")
                + (f"，主角团{cg_member_count}人" if cg else "")
            )
            
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "writing_context": built_context,
                    "world_settings_count": len(built_context["world_settings"]),
                    "characters_count": len(built_context["characters"]),
                    "previous_chapters_count": len(built_context["previous_chapters"]),
                    "volume_count": len(built_context["volume_outlines"]),
                    "current_chapter_plan": built_context.get("current_chapter_plan")
                }
            )
            
        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"上下文构建执行失败: {str(e)}",
                step_summary="上下文构建执行失败"
            )
