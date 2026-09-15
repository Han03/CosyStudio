# -*- coding: utf-8 -*-
"""知识库问答服务（/query 接口核心）。

问答接入智能创作上下文分析器（ContextAnalyzer）：用户问题 = 分析任务，
LLM 选择需要注入的资源（结构化 selectable + RAG 查询），只装配选中的数据
交给回答 LLM。与写作节点共用同一引擎、同一资源注册表、同一失败策略；
每次问答同时是一次上下文分析演练（llm 日志 executor_name=context_analyzer）。
"""

import logging
from typing import Dict, List, Any

from webnovel.repositories import (
    get_webnovel_project_by_script,
    get_character_cards_by_project,
    get_open_loops_by_project,
    get_worldview_by_project,
    get_power_system_by_project,
    get_golden_finger_by_project,
    get_character_group_by_project,
    get_character_group_members,
    get_chapter_meta_list,
    get_volume_outlines_by_project,
)
from webnovel.repositories.character_state_repository import (
    get_character_states_before_chapter,
)

logger = logging.getLogger("webnovel_knowledge_qa")


def _char_type_label(raw_type: str) -> str:
    """character_type 英文 → 中文标签（与写作侧 resource_registry 一致）。"""
    labels = {
        'protagonist': '主角', 'co_protagonist': '主角团核心',
        'heroine': '女主', 'villain': '反派',
        'supporting': '配角', 'minor': '龙套',
    }
    return labels.get(raw_type, raw_type)


def _char_summary(c: dict) -> str:
    """角色一行摘要（与写作侧 context_builder 对齐）。"""
    parts = []
    if c.get("identity"):
        parts.append(str(c["identity"])[:30])
    if c.get("core_personality"):
        parts.append(str(c["core_personality"])[:30])
    if c.get("true_desire") or c.get("long_term_goal"):
        parts.append(str(c.get("true_desire") or c.get("long_term_goal"))[:30])
    return "，".join(parts) if parts else ""

_QA_SYSTEM_PROMPT = """你是一位小说知识库问答助手。基于提供的信息回答用户问题。

回答规则：
1. 结构化事实（角色状态、持有物品、角色关系、未回收伏笔等）直接引用提供的信息中的对应区块回答
2. 正文细节（具体场景、对话、行为原文）引用区块中标注的章节号/片段类型
3. 提供的信息中没有依据时，明确说明"未找到相关信息"，不得编造
4. 回答使用中文，简洁准确，直接给结论"""


def _build_qa_env(project: dict, script_id: int, project_id: int) -> Dict[str, Any]:
    """构造问答模式的 env（inventory + structural_data），与写作流程结构兼容。

    关键差异：
    - character_state：用"最新章节末状态"（get_character_states_before_chapter 回退最近记录章）
    - previous_hook：用最新章节 chapter_meta 的结尾字段
    - previous_chapters：全部已创作章节摘要（与 context_builder 同源：RAG chapter_summary）
    - current_volume：最新卷
    """
    cards = get_character_cards_by_project(project_id) or []
    metas = get_chapter_meta_list(project_id) or []
    latest_chapter = max([m.get("chapter_number") or 0 for m in metas] or [0])

    # 未回收伏笔：兼容 open/active 两种状态值
    loops = [
        f for f in (get_open_loops_by_project(project_id) or [])
        if f.get("status") in ("open", "active")
    ]

    # 世界观（适配渲染契约：id/name/summary，与 context_builder 同构）
    worldview = get_worldview_by_project(project_id)
    world_settings = []
    if worldview:
        world_settings = [{
            "id": worldview.get("id"),
            "name": worldview.get("name", "") or (worldview.get("world_summary", "") or "")[:30],
            "summary": (worldview.get("world_summary", "") or "")[:150],
        }]

    # 力量体系摘要（渲染契约：name/summary，字段对齐业务表）
    ps_raw = get_power_system_by_project(project_id)
    power_system = {}
    if ps_raw:
        power_system = {
            "name": ps_raw.get("system_type", "") or "未命名",
            "summary": f"体系类型:{ps_raw.get('system_type', '')}, 核心理念:{(ps_raw.get('core_creed', '') or '')[:60]}",
        }

    # 金手指摘要（渲染契约：name/summary，字段对齐业务表）
    gf_raw = get_golden_finger_by_project(project_id)
    golden_finger = {}
    if gf_raw:
        golden_finger = {
            "name": gf_raw.get("main_role", "") or "未命名",
            "summary": f"类型:{gf_raw.get('type', '')}, 核心能力:{(gf_raw.get('core_function', '') or '')[:60]}, 代价:{(gf_raw.get('irreversible_cost', '') or '')[:40]}",
        }

    # 主角团摘要（渲染契约：name/goal/members_summary）
    char_group_raw = get_character_group_by_project(project_id)
    char_group = None
    if char_group_raw:
        group_members = get_character_group_members(char_group_raw["id"]) or []
        card_map = {c["id"]: c for c in cards if c.get("id")}
        members_parts = []
        for gm in group_members[:8]:
            card = card_map.get(gm.get("character_id"))
            nm = card.get("name", "") if card else f"成员{gm.get('id', '')}"
            role = gm.get("role", "")
            members_parts.append(f"{nm}({role})" if role else nm)
        char_group = {
            "name": char_group_raw.get("name", ""),
            "goal": (char_group_raw.get("common_goal", "") or "")[:100],
            "members_summary": "，".join(members_parts)[:100],
        }

    # 前文章节摘要（与 context_builder 同源：RAG chapter_summary，回退占位）
    summaries_by_ch = {}
    try:
        from services.vector_store import get_rag_service
        for doc in get_rag_service().get_chunks(project_id, "chapter_summary"):
            if doc.get("chapter_number"):
                summaries_by_ch[doc["chapter_number"]] = doc.get("content", "")
    except Exception:
        pass
    prev_chapters = []
    # 前文窗口：最近 5 章（与写作侧一致，防随章节数膨胀；更早章节按章从 RAG 查摘要）
    for i in range(max(1, latest_chapter - 4), latest_chapter + 1):
        summary = summaries_by_ch.get(i, "")
        prev_chapters.append({
            "index": i,
            "summary": (summary or f"第{i}章（摘要待生成）")[:200],
            "has_full": True,
        })

    # 最新卷
    volumes = get_volume_outlines_by_project(project_id) or []
    current_volume = volumes[-1] if volumes else None

    # 最新章节结尾（previous_hook）
    latest_meta = None
    if latest_chapter > 0:
        for m in metas:
            if (m.get("chapter_number") or 0) == latest_chapter:
                latest_meta = m
                break
    previous_hook = {}
    if latest_meta:
        previous_hook = {
            "hook_content": latest_meta.get("hook_content", ""),
            "hook_type": latest_meta.get("hook_type", ""),
            "ending_emotion": latest_meta.get("ending_emotion", ""),
        }

    inventory = {
        "characters": [
            {
                "id": c.get("id"), "name": c.get("name"),
                "type": _char_type_label(c.get("character_type", "")),
                "summary": _char_summary(c)[:80],
            }
            for c in cards[:20]
        ],
        "foreshadows": loops,
        "world_settings": world_settings,
        "power_system": power_system,
        "golden_finger": golden_finger,
        "character_group": char_group,
        "previous_chapters": prev_chapters,
        "rag_candidates": [],
    }

    structural_data = {
        "project": {
            "title": project.get("title", ""),
            "genre": project.get("genre", ""),
            "one_liner": project.get("one_liner", ""),
        },
        "current_volume": current_volume,
        "current_chapter_plan": None,
        "last_character_states": (
            get_character_states_before_chapter(project_id, latest_chapter + 1) or []
        ),
        "previous_hook": previous_hook,
        "undisclosed_foreshadows": [],
    }
    return {"inventory": inventory, "structural_data": structural_data}


async def answer_question(script_id: int, question: str) -> Dict[str, Any]:
    """执行知识库问答完整流程：分析（选资源）→ 装配（只注入选中项）→ 回答。

    返回 {answer, sources, selected, chunks, reranked}。
    上下文分析/资源装配失败即返回明确错误，不做任何降级兜底。
    """
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": False, "answer": "", "error": "项目未初始化，请先执行深度初始化"}

    project_id = project["id"]
    question = (question or "").strip()
    if not question:
        return {"success": False, "answer": "", "error": "问题不能为空"}

    try:
        from webnovel.pipeline.context_analyzer import ContextAnalyzer
        from webnovel.pipeline.resource_registry import ContextAnalysisError

        # ① 构造问答 env（最新状态快照适配）
        env = _build_qa_env(project, script_id, project_id)

        # ② Analyze → Gather：与写作节点同一引擎，LLM 选择注入资源
        analyzer = ContextAnalyzer(script_id=script_id, chapter_index=None)
        step_ctx = await analyzer.analyze_and_assemble(
            step_name="qa_answer",
            inventory=env["inventory"],
            structural_data=env["structural_data"],
            script_id=script_id,
            project_id=project_id,
            task_inputs={"question": question},
        )

        assembled = (step_ctx.get("assembled_context") or "").strip()
        if not assembled:
            return {"success": False, "answer": "", "error": "上下文分析未装配出可用内容"}

        # ③ 组装回答 prompt（只注入选中项）→ LLM 生成
        from core.model_executor import get_model_executor
        executor = get_model_executor()
        user_prompt = f"问题：{question}\n\n{assembled}"

        result = await executor.execute_text_chat(
            user_prompt,
            system_prompt=_QA_SYSTEM_PROMPT,
            max_tokens=1200,
            executor_name="knowledge_qa",
            prompt_name="knowledge_qa",
            script_id=script_id,
            project_id=project_id,
        )
        if result.get("error"):
            return {"success": False, "answer": "", "error": f"生成失败: {result['error']}"}

        answer = (result.get("content") or "").strip()
        if not answer:
            return {"success": False, "answer": "", "error": "生成结果为空"}

        # ④ Reranker 二次精排：按用户问题对召回片段重排（取 top 5），
        # 使参考片段与问题强相关、弱相关/模板片段自然出局。
        # 增强项：rerank 失败（模型/网络不可用）回退向量顺序，不中断问答。
        rag_results = step_ctx.get("rag_results") or []
        reranked = False
        if rag_results:
            try:
                from core.model_executor import get_model_executor
                rk = await get_model_executor().execute_rerank(
                    query=question,
                    documents=[c.get("content", "") for c in rag_results],
                    top_k=5,
                )
                rk_results = (rk or {}).get("results") or []
                if rk_results:
                    score_map = {r.get("index"): r.get("score") for r in rk_results
                                 if r.get("index") is not None}
                    reranked = True
                    # 按 rerank 分数降序重排（仅保留有分数的片段，其余按原顺序追加）
                    indexed = [(i, c) for i, c in enumerate(rag_results)]
                    indexed.sort(key=lambda ic: score_map.get(ic[0], -1), reverse=True)
                    rag_results = [c for _, c in indexed]
                    for orig_idx, c in indexed:
                        if orig_idx in score_map:
                            c["rerank_score"] = score_map[orig_idx]
            except Exception as e:
                logger.warning(f"知识库问答 rerank 失败，回退向量顺序: {e}")

        # ⑤ 来源标注：rag 片段 + 结构化资源（同一类型+章节的 rag 片段去重）
        selection = step_ctx.get("_selection") or {}
        sources: List[Dict[str, Any]] = []
        seen_sources = set()
        for c in rag_results:
            key = ("rag", c.get("chunk_type", ""), c.get("chapter_number", 0))
            if key in seen_sources:
                continue
            seen_sources.add(key)
            sources.append({
                "type": "rag",
                "chunk_type": c.get("chunk_type", ""),
                "chapter_number": c.get("chapter_number", 0),
                "id": c.get("id", 0),
            })
        for ref in (selection.get("structured_refs") or []):
            if isinstance(ref, dict) and ref.get("resource"):
                key = ("state", ref["resource"], 0)
                if key in seen_sources:
                    continue
                seen_sources.add(key)
                sources.append({"type": "state", "resource": ref["resource"]})
        for q in (selection.get("structured_queries") or []):
            if isinstance(q, dict) and q.get("resource"):
                key = ("state_query", q["resource"], 0)
                if key in seen_sources:
                    continue
                seen_sources.add(key)
                sources.append({"type": "state_query", "resource": q["resource"]})

        return {
            "success": True,
            "answer": answer,
            "sources": sources,
            "selected": {
                "structured_refs": selection.get("structured_refs") or [],
                "structured_queries": selection.get("structured_queries") or [],
                "rag_queries": selection.get("rag_queries") or [],
                "custom_notes": selection.get("custom_notes") or [],
            },
            "chunks": rag_results,
            "reranked": reranked,
        }

    except ContextAnalysisError as e:
        logger.warning(f"知识库问答上下文分析失败: {e}")
        return {"success": False, "answer": "", "error": f"上下文分析失败: {e}"}
    except Exception as e:
        logger.error(f"知识库问答失败: {e}", exc_info=True)
        return {"success": False, "answer": "", "error": f"问答失败: {str(e)[:100]}"}
