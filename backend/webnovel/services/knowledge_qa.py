# -*- coding: utf-8 -*-
"""知识库问答服务（/query 接口核心）。

双源知识库问答：随时查询小说故事状态
- RAG 向量检索（正文细节 + CSV 创作知识）→ Reranker 精排
- 结构化状态快照（业务表当前故事状态，只读）
→ LLM 生成回答（含来源标注）

RAG 职责重定位后，设定类（角色/世界观/力量体系/金手指/卷纲/反派/伏笔）
已由 selectable 结构化资源注入提供给写作侧，不再进 RAG；
问答侧所需的"当前故事状态"结构化事实由本模块从业务表动态拉取快照。
"""

import json
import logging
from typing import Dict, List, Any, Optional

from webnovel.repositories import (
    get_webnovel_project_by_script,
    get_character_cards_by_project,
    get_character_items_by_project,
    get_character_relationships,
    get_open_loops_by_project,
    get_timelines_by_project,
    get_timeline_chapters,
    get_worldview_by_project,
)

logger = logging.getLogger("webnovel_knowledge_qa")

# 快照中保留的角色卡字段（精简，控制 token）
_CARD_FIELDS = [
    ("name", "姓名"), ("character_type", "类型"), ("identity", "身份"),
    ("alias", "曾用名"), ("age_stage", "年龄段"), ("protagonist_relation", "与主角关系"),
]

_QA_SYSTEM_PROMPT = """你是一位小说知识库问答助手。基于提供的【检索片段】与【故事当前状态快照】回答用户问题。

回答规则：
1. 结构化事实（角色状态、持有物品、角色关系、未回收伏笔等）优先用【故事当前状态快照】回答
2. 正文细节（具体场景、对话、行为原文）优先用【检索片段】回答，引用时标注来源（章节号/片段类型）
3. 快照与片段都没有依据时，明确说明"当前资料中未找到相关信息"，不得编造
4. 回答使用中文，简洁准确，直接给结论"""


def build_state_snapshot(project_id: int) -> str:
    """组装业务表当前故事状态快照（只读，单块失败降级不影响整体）。"""
    parts: List[str] = []

    # 1. 角色卡概要
    try:
        cards = get_character_cards_by_project(project_id) or []
        if cards:
            lines = []
            for c in cards:
                desc = "，".join(
                    f"{label}{c.get(key, '')}"
                    for key, label in _CARD_FIELDS
                    if c.get(key)
                )
                if desc:
                    lines.append(f"- {desc}")
            if lines:
                parts.append("【角色卡概要】\n" + "\n".join(lines))
    except Exception as e:
        logger.warning(f"快照-角色卡失败: {e}")

    # 2. 持有物品（当前持有）
    try:
        items_by_char = get_character_items_by_project(project_id, only_held=True) or {}
        if items_by_char:
            name_by_id = {c.get("id"): c.get("name", "?") for c in cards if cards}
            lines = []
            for char_id, items in items_by_char.items():
                if not items:
                    continue
                name = name_by_id.get(char_id, f"角色#{char_id}")
                item_strs = []
                for it in items:
                    qty = it.get("quantity", 1) or 1
                    item_strs.append(f"{it.get('item_name', '')}x{qty}" if qty > 1 else it.get("item_name", ""))
                if item_strs:
                    lines.append(f"- {name}持有：{'、'.join(item_strs)}")
            if lines:
                parts.append("【持有物品】\n" + "\n".join(lines))
    except Exception as e:
        logger.warning(f"快照-物品失败: {e}")

    # 3. 角色事实关系
    try:
        cards = get_character_cards_by_project(project_id) or []
        lines = []
        for c in cards:
            rels = get_character_relationships(c.get("id")) or []
            for r in rels:
                rel_type = r.get("relation_type", "")
                target = r.get("target_name", "") or ""
                desc = r.get("description", "") or ""
                if rel_type and target:
                    line = f"- {c.get('name', '?')}与{target}：{rel_type}"
                    if desc:
                        line += f"；{desc}"
                    lines.append(line)
        # 去重
        seen = set()
        uniq = []
        for l in lines:
            if l not in seen:
                seen.add(l)
                uniq.append(l)
        if uniq:
            parts.append("【角色关系】\n" + "\n".join(uniq))
    except Exception as e:
        logger.warning(f"快照-关系失败: {e}")

    # 4. 未回收伏笔
    try:
        loops = get_open_loops_by_project(project_id, status="open") or []
        if loops:
            lines = []
            for lp in loops[:15]:
                content = str(lp.get("content", "") or "").strip()
                if not content:
                    continue
                tier = lp.get("tier", "") or ""
                planted = lp.get("planted_chapter", "") or ""
                line = f"- 第{planted}章埋设：{content}" if planted else f"- {content}"
                if tier:
                    line += f"（{tier}）"
                lines.append(line)
            if lines:
                parts.append("【未回收伏笔】\n" + "\n".join(lines))
    except Exception as e:
        logger.warning(f"快照-伏笔失败: {e}")

    # 5. 章节时间轴（各卷最新若干章）
    try:
        timelines = get_timelines_by_project(project_id) or []
        lines = []
        for tl in timelines[:3]:
            vol = tl.get("volume_number", "?")
            chs = get_timeline_chapters(tl.get("id")) or []
            for ch in sorted(chs, key=lambda x: x.get("chapter_number", 0))[-3:]:
                anchor = ch.get("time_anchor", "") or ""
                dur = ch.get("chapter_duration", "") or ""
                line = f"- 第{ch.get('chapter_number', '?')}章：{anchor}"
                if dur:
                    line += f"（跨度{dur}）"
                lines.append(line)
        if lines:
            parts.append("【章节时间轴】\n" + "\n".join(lines))
    except Exception as e:
        logger.warning(f"快照-时间轴失败: {e}")

    # 6. 世界观摘要
    try:
        wv = get_worldview_by_project(project_id) or {}
        summary = wv.get("world_summary", "") or ""
        if summary:
            parts.append(f"【世界观摘要】\n{summary[:500]}")
    except Exception as e:
        logger.warning(f"快照-世界观失败: {e}")

    return "\n\n".join(parts)


def _format_chunks_for_prompt(chunks: List[Dict[str, Any]]) -> str:
    """将精排后的 RAG 片段格式化为 prompt 注入文本。"""
    lines = []
    for i, c in enumerate(chunks, 1):
        ctype = c.get("chunk_type", "")
        ch = c.get("chapter_number", 0)
        content = str(c.get("content", "") or "").strip()
        if not content:
            continue
        src = f"类型={ctype} 章节={ch}" if ch else f"类型={ctype}"
        # chapter_paragraph 命中时附带前后段落上下文，便于完整理解细节
        ctx_before = str(c.get("context_before", "") or "").strip()
        ctx_after = str(c.get("context_after", "") or "").strip()
        body = content
        if ctx_before:
            body = f"（上文）{ctx_before}\n{body}"
        if ctx_after:
            body = f"{body}\n（下文）{ctx_after}"
        lines.append(f"[片段{i}][{src}]\n{body}")
    return "\n\n".join(lines)


async def answer_question(script_id: int, question: str) -> Dict[str, Any]:
    """执行知识库问答完整流程：召回 → 快照 → 重排 → 生成。

    返回 {answer, sources, chunks, reranked}。
    任何一步失败都返回明确错误，不静默兜底。
    """
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": False, "answer": "", "error": "项目未初始化，请先执行深度初始化"}

    project_id = project["id"]

    try:
        from services.vector_store import get_rag_service
        from core.model_executor import get_model_executor
        executor = get_model_executor()
        rag_svc = get_rag_service()

        # ── ① RAG 向量召回（正文类 + CSV 创作知识，白名单）──
        t2v_result = await executor.execute_text_to_vector([question], is_query=True)
        embeddings = t2v_result.get("embeddings", []) if t2v_result else []
        if not embeddings:
            return {"success": False, "answer": "", "error": "Embedding计算失败"}
        all_results = rag_svc.search(
            project_id, embeddings[0], limit=50, min_score=0,
            chunk_types=list(rag_svc.ALLOWED_QUERY_TYPES),
        )

        # ── ② Reranker 二次精排 ──
        reranked = False
        rerank_candidates = all_results[:30]
        try:
            documents = [(c.get("content") or "")[:512] for c in rerank_candidates]
            if documents:
                rr = await executor.execute_rerank(question, documents, top_k=len(documents))
                if not rr.get("error"):
                    items = rr.get("results", [])
                    for item in items:
                        idx = item.get("index", -1)
                        if 0 <= idx < len(rerank_candidates):
                            rerank_candidates[idx]["rerank_score"] = float(item.get("score", 0.0))
                    if any("rerank_score" in c for c in rerank_candidates):
                        rerank_candidates.sort(
                            key=lambda c: c.get("rerank_score", -1.0), reverse=True)
                        all_results = rerank_candidates + all_results[30:]
                        reranked = True
        except Exception:
            pass  # 重排失败回退向量顺序

        top_chunks = all_results[:10]

        # chapter_paragraph 命中时扩展前后段落上下文（供 prompt 与前端展示）
        try:
            for chunk in top_chunks:
                if chunk.get("chunk_type") != "chapter_paragraph":
                    continue
                meta = json.loads(chunk["metadata"]) if chunk.get("metadata") else {}
                para_idx = meta.get("para_index")
                ch_num = chunk.get("chapter_number", 0)
                if para_idx is None or not ch_num:
                    continue
                ctx_tuples = rag_svc.get_paragraphs_context(
                    project_id, ch_num, para_idx, context_range=1)
                before = [t for t, i in ctx_tuples if i < para_idx]
                after = [t for t, i in ctx_tuples if i > para_idx]
                if before:
                    chunk["context_before"] = "\n".join(before)
                if after:
                    chunk["context_after"] = "\n".join(after)
        except Exception as e:
            logger.warning(f"段落上下文扩展失败（不阻断）: {e}")

        # ── ③ 结构化状态快照（只读业务表）──
        snapshot_text = build_state_snapshot(project_id)

        # ── ④ 组装 prompt → ⑤ LLM 生成 ──
        chunks_text = _format_chunks_for_prompt(top_chunks)
        if not chunks_text.strip() and not snapshot_text.strip():
            return {"success": False, "answer": "", "error": "当前知识库为空，请先完成深度初始化与章节创作"}

        user_prompt = (
            f"问题：{question}\n\n"
            f"【检索片段】\n{chunks_text if chunks_text.strip() else '（无）'}\n\n"
            f"【故事当前状态快照】\n{snapshot_text if snapshot_text.strip() else '（无）'}"
        )

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

        answer = result.get("content", "").strip()
        if not answer:
            return {"success": False, "answer": "", "error": "生成结果为空"}

        # 来源标注
        sources = []
        for c in top_chunks:
            sources.append({
                "type": "rag",
                "chunk_type": c.get("chunk_type", ""),
                "chapter_number": c.get("chapter_number", 0),
                "id": c.get("id", 0),
            })

        return {
            "success": True,
            "answer": answer,
            "sources": sources,
            "chunks": top_chunks,
            "reranked": reranked,
        }

    except Exception as e:
        logger.error(f"知识库问答失败: {e}", exc_info=True)
        return {"success": False, "answer": "", "error": f"问答失败: {str(e)[:100]}"}
