"""webnovel-writer整合API接口。"""

import json
import asyncio
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

from repositories import get_script
from webnovel.repositories import (
    add_webnovel_project, get_webnovel_project_by_script, update_webnovel_project,
    delete_webnovel_project_by_script,
    add_golden_finger, get_golden_finger_by_project,
    add_character_card, get_character_cards_by_project,
    add_power_system, get_power_system_by_project,
    add_worldview, get_worldview_by_project,
    add_volume_outline, get_volume_outlines_by_project, get_volume_outline, update_volume_outline, delete_volume_outline,
    add_timeline, get_timelines_by_project,
    add_genre_fusion, get_genre_fusion_by_project,
    add_chapter_meta, get_chapter_meta_list,
    get_webnovel_state_by_project,
    get_chapter_plans_by_volume, add_chapter_plan, update_chapter_plan
)
from webnovel.pipeline.orchestrator import PipelineOrchestrator
from repositories import add_writing_task, get_writing_task, update_writing_task

router = APIRouter(prefix="/api/books/scripts/webnovel")


class InitRequest(BaseModel):
    title: str = ""
    genre: str = ""
    genre_label: str = ""
    target_words: int = 0
    target_chapters: int = 0
    one_liner: str = ""
    story_summary: str = ""
    core_conflict: str = ""
    target_reader: str = ""
    platform: str = ""
    anti_trope_rules: str = ""
    hard_constraints: str = ""
    core_selling_points: str = ""
    opening_hook: str = ""
    protagonist_name: str = ""
    protagonist_flaw: str = ""
    villain_mirror: str = ""
    protagonist_desire: str = ""
    protagonist_archetype: str = ""
    protagonist_structure: str = "单主角"
    heroine_config: str = ""
    heroine_names: str = ""
    heroine_role: str = ""
    co_protagonists: str = ""
    co_protagonist_roles: str = ""
    antagonist_tiers: str = ""
    antagonist_level: str = ""
    golden_finger_name: str = ""
    golden_finger_type: str = ""
    golden_finger_style: str = ""
    gf_visibility: str = ""
    gf_irreversible_cost: str = ""
    world_scale: str = ""
    factions: str = ""
    power_system_type: str = ""
    social_class: str = ""
    resource_distribution: str = ""
    currency_system: str = ""
    currency_exchange: str = ""
    sect_hierarchy: str = ""
    cultivation_chain: str = ""
    cultivation_subtiers: str = ""
    golden_finger: Optional[dict] = None
    protagonist: Optional[dict] = None
    heroine: Optional[dict] = None
    villain: Optional[dict] = None
    power_system: Optional[dict] = None
    worldview: Optional[dict] = None
    genre_fusion: Optional[dict] = None


class PlanRequest(BaseModel):
    volume_number: int = 1


class QueryRequest(BaseModel):
    query_question: str = ""


@router.post("/init")
async def webnovel_init(script_id: int, data: InitRequest):
    """深度初始化网文项目。"""
    script = get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    # 容错与重复初始化：清理旧数据
    script_status = script.get("status") or ""
    existing = get_webnovel_project_by_script(script_id)
    if existing:
        # 重复初始化：清除旧项目数据
        delete_webnovel_project_by_script(script_id)
        from utils.logger import log_manager
        log_manager.get_logger("webnovel_init").info(
            f"[webnovel_init] script_id={script_id} 检测到已有项目，清理后重新初始化"
        )
    elif script_status == "failed":
        # 上次初始化失败：清理残留脏数据
        if delete_webnovel_project_by_script(script_id):
            from utils.logger import log_manager
            log_manager.get_logger("webnovel_init").info(
                f"[webnovel_init] script_id={script_id} 检测到失败残留项目，已自动清理后重试"
            )

    task = add_writing_task(script_id, 0, "init")
    task_id = task["id"]

    asyncio.create_task(_execute_init_workflow(task_id, script_id, data.dict()))

    return {"success": True, "task_id": task_id, "message": "深度初始化任务已创建"}


async def _execute_init_workflow(task_id: int, script_id: int, project_data: dict):
    """执行初始化工作流。"""
    try:
        update_writing_task(task_id, status="running", progress=10, progress_message="开始深度初始化...")

        orchestrator = PipelineOrchestrator(script_id, 0, task_id)
        result = await orchestrator.execute_workflow("init", {"project_data": project_data})

        if result["success"]:
            update_writing_task(task_id, status="completed", progress=100, progress_message="深度初始化完成")
            # 初始化完成后，将项目设定数据索引到 RAG 向量库
            try:
                from webnovel.services.webnovel_service import WebnovelService
                service = WebnovelService()
                project = get_webnovel_project_by_script(script_id)
                if project:
                    await service._index_project_settings(project["id"])
            except Exception as e:
                from utils.logger import log_manager
                log_manager.get_logger("webnovel_init").warning(f"RAG索引失败: {e}")
        else:
            update_writing_task(task_id, status="failed", progress=0, progress_message=f"初始化失败: {result.get('failed_steps', 0)}个步骤出错")

    except Exception as e:
        update_writing_task(task_id, status="failed", error_message=str(e), progress_message=f"执行失败: {str(e)[:100]}")


@router.get("/init/status")
def get_init_status(script_id: int, task_id: int):
    """获取初始化任务状态。"""
    task = get_writing_task(script_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "task": task}


@router.post("/plan")
async def webnovel_plan(script_id: int, data: PlanRequest):
    """卷纲规划。"""
    script = get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=400, detail="项目未初始化，请先执行深度初始化")

    task = add_writing_task(script_id, 0, "plan")
    task_id = task["id"]

    asyncio.create_task(_execute_plan_workflow(task_id, script_id, data.volume_number))

    return {"success": True, "task_id": task_id, "message": f"第{data.volume_number}卷规划任务已创建"}


async def _execute_plan_workflow(task_id: int, script_id: int, volume_number: int):
    """执行规划工作流。"""
    try:
        update_writing_task(task_id, status="running", progress=10, progress_message=f"开始第{volume_number}卷规划...")

        orchestrator = PipelineOrchestrator(script_id, 0, task_id)
        result = await orchestrator.execute_workflow("plan", {"volume_number": volume_number})

        if result["success"]:
            update_writing_task(task_id, status="completed", progress=100, progress_message=f"第{volume_number}卷规划完成")
        else:
            update_writing_task(task_id, status="failed", progress=0, progress_message=f"规划失败: {result.get('failed_steps', 0)}个步骤出错")

    except Exception as e:
        update_writing_task(task_id, status="failed", error_message=str(e), progress_message=f"执行失败: {str(e)[:100]}")


@router.post("/query")
async def webnovel_query(script_id: int, data: QueryRequest):
    """状态查询（基于RAG语义检索）。

    按分类返回相似度超过阈值的内容，每种分类最多返回5条。
    阈值由 RAGService 分级阈值自动管理（按 chunk_type 差异化）。
    若配置了片段重排序（text_rerank）能力，向量粗排后会对候选片段做二次精排，
    结果按重排序分数降序排列；重排序不可用时回退到向量相似度顺序。
    若检测到项目设定未索引到 RAG 向量库，自动触发索引重建。
    """
    script = get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=400, detail="项目未初始化")

    query = data.query_question.strip()
    if not query:
        return {"success": False, "chunks": [], "error": "请输入查询问题"}

    project_id = project["id"]

    # 兜底：检查项目设定是否已索引到 RAG 向量库，若缺失则自动触发索引重建
    try:
        from services.vector_store import get_rag_service
        if not get_rag_service().has_settings_chunks(project_id):
            from webnovel.services.webnovel_service import WebnovelService
            service = WebnovelService()
            await service._index_project_settings(project_id)
    except Exception:
        pass  # 索引重建失败不阻断查询，继续用已有数据检索

    chunks = []
    reranked = False
    try:
        from core.model_executor import get_model_executor
        executor = get_model_executor()
        # query 文本用 is_query=True 添加 instruction prefix
        result = await executor.execute_text_to_vector([query], is_query=True)
        embeddings = result.get("embeddings", [])
        if embeddings:
            from services.vector_store import get_rag_service
            # 获取足够多的候选结果，以便按分类过滤后仍有充足数据
            # min_score=0 禁用分级阈值过滤，避免细节查询被误杀
            # （如"主角身上有哪些物品"等细节查询，段落 chunk 中语义被前后叙事稀释，
            #   相似度可能低于分级阈值，但结果仍具参考价值）
            # 每类最多返回 5 条，总量可控
            all_results = get_rag_service().search(
                project_id, embeddings[0], limit=50, min_score=0
            )

            # Reranker 二次精排：向量相似度只反映语义距离，无法区分"话题相关"
            # 与"真正回答问题"。对向量粗排的前 30 条候选调用片段重排序能力，
            # 按 query-doc 相关性重新打分排序，提升命中片段的优先级。
            # 未配置能力或调用失败时静默回退到向量相似度顺序，不阻断查询。
            RERANK_CANDIDATES = 30
            try:
                candidates = all_results[:RERANK_CANDIDATES]
                # 截断过长文档，控制重排序推理开销（tokenizer 侧也会按 max_length 截断）
                documents = [(c.get("content") or "")[:512] for c in candidates]
                if documents:
                    rerank_result = await executor.execute_rerank(
                        query, documents, top_k=len(documents)
                    )
                    if not rerank_result.get("error"):
                        rerank_items = rerank_result.get("results", [])
                        for item in rerank_items:
                            idx = item.get("index", -1)
                            if 0 <= idx < len(candidates):
                                candidates[idx]["rerank_score"] = float(item.get("score", 0.0))
                        if any("rerank_score" in c for c in candidates):
                            # 有分数的片段按重排序分数降序在前，其余保持向量顺序在后
                            candidates.sort(
                                key=lambda c: c.get("rerank_score", -1.0), reverse=True
                            )
                            all_results = candidates + all_results[RERANK_CANDIDATES:]
                            reranked = True
            except Exception:
                pass  # 重排序失败回退到向量相似度顺序

            # 对 chapter_paragraph 结果扩展前后段落上下文
            # 存储时每个 chunk 只含单段（精准 embedding），
            # 查询时取回相邻段落供用户阅读，兼顾匹配精度与上下文完整性
            rag_svc = get_rag_service()
            for chunk in all_results:
                if chunk.get("chunk_type") != "chapter_paragraph":
                    continue
                try:
                    meta = json.loads(chunk["metadata"]) if chunk.get("metadata") else {}
                    para_idx = meta.get("para_index")
                    ch_num = chunk.get("chapter_number", 0)
                    if para_idx is None or not ch_num:
                        continue
                    # get_paragraphs_context 返回 [(text, para_index), ...] 按序排列
                    ctx_tuples = rag_svc.get_paragraphs_context(
                        project_id, ch_num, para_idx, context_range=1,
                    )
                    ctx_before = []
                    ctx_after = []
                    for text, idx in ctx_tuples:
                        if idx < para_idx:
                            ctx_before.append(text)
                        elif idx > para_idx:
                            ctx_after.append(text)
                    chunk["context_before"] = "\n".join(ctx_before)
                    chunk["context_after"] = "\n".join(ctx_after)
                except Exception:
                    pass

            # 按 chunk_type 分组，每组最多 5 条
            MAX_PER_CATEGORY = 5
            grouped: Dict[str, list] = {}
            for chunk in all_results:
                cat = chunk.get("chunk_type", "unknown")
                if cat not in grouped:
                    grouped[cat] = []
                if len(grouped[cat]) < MAX_PER_CATEGORY:
                    grouped[cat].append(chunk)

            # 转为有序列表返回（按每组首条分数降序排列分类）
            # 重排序后用相关性分数排序，否则沿用向量相似度分数（两者量纲不同，不可混用）
            def _cat_score(c):
                return c.get("rerank_score", 0.0) if reranked else c.get("score", 0.0)

            chunks = []
            for cat in sorted(grouped, key=lambda c: _cat_score(grouped[c][0]), reverse=True):
                chunks.extend(grouped[cat])
        else:
            return {"success": False, "chunks": [], "error": "Embedding计算失败"}
    except Exception as e:
        return {"success": False, "chunks": [], "error": f"检索失败: {str(e)}"}

    return {"success": True, "chunks": chunks, "reranked": reranked}


@router.get("/rag-chunks")
def list_rag_chunks(script_id: int, page: int = Query(1, ge=1),
                    page_size: int = Query(20, ge=1, le=100),
                    chunk_type: str = Query("")):
    """分页查看项目的所有 RAG 内容，便于用户审查。"""
    script = get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=400, detail="项目未初始化")

    from services.vector_store import get_rag_service
    result = get_rag_service().list_chunks_paginated(
        project["id"], page=page, page_size=page_size, chunk_type=chunk_type,
    )
    return {"success": True, **result}


@router.post("/reindex-rag")
async def reindex_rag(script_id: int):
    """重建 RAG 向量索引。

    当 embedding 模型或检索策略变更后，已有向量可能失效。
    本接口清空项目所有 RAG 向量后，重新索引项目设定和已有章节内容。
    """
    script = get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=400, detail="项目未初始化，请先执行深度初始化")

    task = add_writing_task(script_id, 0, "reindex")
    task_id = task["id"]
    asyncio.create_task(_execute_reindex_workflow(task_id, script_id))
    return {"success": True, "task_id": task_id, "message": "RAG重建索引任务已创建"}


async def _execute_reindex_workflow(task_id: int, script_id: int):
    """执行 RAG 重建索引工作流。"""
    from utils.logger import log_manager
    from infrastructure.websocket_broadcast import ws_broadcast_manager
    _log = log_manager.get_logger("webnovel_reindex")

    async def _broadcast(status: str, message: str, progress: int):
        try:
            await ws_broadcast_manager.broadcast_reindex_progress(script_id, status, message, progress)
        except Exception as e:
            _log.warning(f"[reindex] WS 广播失败: {e}")

    try:
        update_writing_task(task_id, status="running", progress=5, progress_message="清空旧 RAG 向量数据...")
        await _broadcast("running", "清空旧 RAG 向量数据...", 5)

        project = get_webnovel_project_by_script(script_id)
        if not project:
            update_writing_task(task_id, status="failed", progress_message="项目不存在")
            await _broadcast("failed", "项目不存在", 0)
            return
        project_id = project["id"]

        # 1. 清空项目所有 RAG 数据
        from services.vector_store import get_rag_service
        deleted = get_rag_service().clear_project(project_id)
        _log.info(f"[reindex] script_id={script_id} 已清空 {deleted} 条 RAG 数据")

        # 2. 重新索引项目设定
        update_writing_task(task_id, progress=20, progress_message="重新索引项目设定...")
        await _broadcast("running", "重新索引项目设定...", 20)
        from webnovel.services.webnovel_service import WebnovelService
        service = WebnovelService()
        await service._index_project_settings(project_id)

        # 3. 重新索引已有章节内容
        from repositories import get_script_chapters_all, get_writing_tasks, get_script_lines
        from services.script_service import ScriptService
        script_svc = ScriptService()

        # 从多个来源收集章节索引（webnovel 章节内容可能存在于不同位置）：
        # - script_chapters 表（用户已应用创作结果时）
        # - script_writing_tasks 表（创作完成后始终有 polished/draft）
        # - script_lines 表（剧本编辑器台词行）
        chapter_indices = set()
        for ch in get_script_chapters_all(script_id):
            if ch.get("chapter_index"):
                chapter_indices.add(ch["chapter_index"])
        for task in get_writing_tasks(script_id):
            if task.get("chapter_index") and task.get("status") == "completed":
                chapter_indices.add(task["chapter_index"])
        for line in get_script_lines(script_id):
            if line.get("chapter_index"):
                chapter_indices.add(line["chapter_index"])
        chapter_indices = sorted(chapter_indices)
        total_chapters = len(chapter_indices)
        _log.info(f"[reindex] script_id={script_id} 发现 {total_chapters} 个章节需要重建索引")

        for i, ch_idx in enumerate(chapter_indices):
            progress = 20 + int(75 * (i + 1) / total_chapters)
            msg = f"重建第{ch_idx}章索引 ({i+1}/{total_chapters})..."
            update_writing_task(task_id, progress=progress, progress_message=msg)
            await _broadcast("running", msg, progress)

            # 按优先级读取章节内容：
            # 1. 章节文件（script_chapters + 独立文件）
            # 2. 已完成的写作任务 polished 字段
            # 3. 写作任务 draft 字段（无 polished 时回退）
            # 4. script_lines 台词拼接（最终回退）
            content = None
            try:
                content = script_svc._read_script_chapter_content(script_id, ch_idx)
            except Exception:
                pass
            if not content:
                # 从 writing_tasks 中找该章节最新的已完成任务
                tasks = get_writing_tasks(script_id, ch_idx)
                for t in tasks:
                    if t.get("status") == "completed" and t.get("polished"):
                        content = t["polished"]
                        break
                if not content:
                    for t in tasks:
                        if t.get("draft"):
                            content = t["draft"]
                            break
            if not content:
                lines = get_script_lines(script_id, ch_idx)
                if lines:
                    content = "\n".join(line["content"] for line in lines)
            if content:
                await service._store_rag_chunk(project_id, ch_idx, content)

        done_msg = f"RAG索引重建完成，共索引 {total_chapters} 个章节"
        update_writing_task(
            task_id, status="completed", progress=100,
            progress_message=done_msg
        )
        await _broadcast("completed", done_msg, 100)

    except Exception as e:
        err_msg = f"RAG重建索引失败: {str(e)[:100]}"
        update_writing_task(
            task_id, status="failed", error_message=str(e),
            progress_message=err_msg
        )
        await _broadcast("failed", err_msg, 0)


@router.get("/dashboard")
def webnovel_dashboard(script_id: int):
    """获取可视化面板数据。"""
    script = get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {
            "success": True,
            "initialized": False,
            "project": None,
            "characters": [],
            "volume_outlines": [],
            "timelines": [],
            "state": None
        }

    project_id = project["id"]

    characters = get_character_cards_by_project(project_id)
    volume_outlines = get_volume_outlines_by_project(project_id)
    timelines = get_timelines_by_project(project_id)
    state = get_webnovel_state_by_project(project_id)
    golden_finger = get_golden_finger_by_project(project_id)
    power_system = get_power_system_by_project(project_id)
    worldview = get_worldview_by_project(project_id)
    genre_fusion = get_genre_fusion_by_project(project_id)
    chapter_meta = get_chapter_meta_list(project_id)

    return {
        "success": True,
        "initialized": True,
        "project": project,
        "characters": characters,
        "golden_finger": golden_finger,
        "power_system": power_system,
        "worldview": worldview,
        "genre_fusion": genre_fusion,
        "volume_outlines": volume_outlines,
        "timelines": timelines,
        "state": state,
        "chapter_meta": chapter_meta,
        "statistics": {
            "total_characters": len(characters),
            "total_volumes": len(volume_outlines),
            "total_chapters": state["current_chapter"] if state else 0,
            "total_words": state["total_words"] if state else 0
        }
    }


@router.get("/project")
def get_webnovel_project_detail(script_id: int):
    """获取项目详情。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"success": True, "project": project}


@router.get("/characters")
def get_webnovel_characters(script_id: int, character_type: str = Query("")):
    """获取角色列表。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    characters = get_character_cards_by_project(project["id"], character_type)
    return {"success": True, "characters": characters}


@router.get("/volume-outlines")
def get_webnovel_volume_outlines(script_id: int):
    """获取卷纲列表。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    outlines = get_volume_outlines_by_project(project["id"])
    return {"success": True, "outlines": outlines}


class VolumeOutlineRequest(BaseModel):
    volume_number: int = 1
    volume_title: str = ""
    start_chapter: int = 0
    end_chapter: int = 0
    summary: str = ""


@router.post("/volume-outlines")
def create_webnovel_volume_outline(script_id: int, data: VolumeOutlineRequest):
    """添加卷纲。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    outline = add_volume_outline(
        project_id=project["id"],
        volume_number=data.volume_number,
        volume_name=data.volume_title or "",
        chapter_start=data.start_chapter or 0,
        chapter_end=data.end_chapter or 0,
        core_conflict=data.summary or ""
    )
    return {"success": True, "outline": outline}


@router.put("/volume-outlines")
def modify_webnovel_volume_outline(script_id: int, outline_id: int, data: VolumeOutlineRequest):
    """更新卷纲。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    outline = get_volume_outline(project["id"], outline_id)
    if not outline:
        raise HTTPException(status_code=404, detail="卷纲规划不存在")
    update_volume_outline(
        vo_id=outline_id,
        volume_number=data.volume_number,
        volume_name=data.volume_title or "",
        chapter_start=data.start_chapter or 0,
        chapter_end=data.end_chapter or 0,
        core_conflict=data.summary or ""
    )
    return {"success": True}


@router.delete("/volume-outlines")
def remove_webnovel_volume_outline(script_id: int, outline_id: int):
    """删除卷纲。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    outline = get_volume_outline(project["id"], outline_id)
    if not outline:
        raise HTTPException(status_code=404, detail="卷纲规划不存在")
    delete_volume_outline(outline_id)
    return {"success": True}


@router.get("/chapter-plans")
def get_webnovel_chapter_plans(script_id: int, volume_outline_id: int = Query(...)):
    """获取章纲列表。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    plans = get_chapter_plans_by_volume(volume_outline_id)
    return {"success": True, "chapter_plans": plans}


@router.put("/chapter-plan")
def update_webnovel_chapter_plan(script_id: int, plan_id: int, data: dict = Body(...)):
    """更新章纲。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    success = update_chapter_plan(plan_id, **data)
    return {"success": success}


class WriteRequest(BaseModel):
    chapter_index: int = 1
    mode: str = "write"


@router.post("/write")
async def webnovel_write(script_id: int, data: WriteRequest):
    """章节写作。"""
    script = get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=400, detail="项目未初始化，请先执行深度初始化")

    task = add_writing_task(script_id, data.chapter_index, "write")
    task_id = task["id"]

    asyncio.create_task(_execute_write_workflow(task_id, script_id, data.chapter_index, data.mode))

    return {"success": True, "task_id": task_id, "message": f"第{data.chapter_index}章写作任务已创建"}


async def _execute_write_workflow(task_id: int, script_id: int, chapter_index: int, mode: str):
    """执行写作工作流。"""
    try:
        update_writing_task(task_id, status="running", progress=10, progress_message=f"开始第{chapter_index}章写作...")

        orchestrator = PipelineOrchestrator(script_id, chapter_index, task_id)
        result = await orchestrator.execute_workflow(mode, {"chapter_index": chapter_index})

        if result["success"]:
            ctx = result.get("context", {})
            draft = ctx.get("draft", "") or ctx.get("draft_content", "")
            polished = ctx.get("polished", "") or ctx.get("polished_content", "")
            review_result = ctx.get("review_result", "")
            facts_recorded = ctx.get("facts", "")
            update_writing_task(
                task_id,
                status="completed",
                progress=100,
                progress_message=f"第{chapter_index}章写作完成",
                draft=draft,
                polished=polished,
                review_result=json.dumps(review_result) if isinstance(review_result, list) else str(review_result),
                facts_recorded=json.dumps(facts_recorded) if isinstance(facts_recorded, list) else str(facts_recorded)
            )
        else:
            update_writing_task(task_id, status="failed", progress=0, progress_message=f"写作失败: {result.get('failed_steps', 0)}个步骤出错")

    except Exception as e:
        update_writing_task(task_id, status="failed", error_message=str(e), progress_message=f"执行失败: {str(e)[:100]}")
