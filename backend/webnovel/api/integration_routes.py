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


class LearnRequest(BaseModel):
    learning_content: str = ""
    current_chapter: int = 0


class ReviewRequest(BaseModel):
    chapter_index: int = 0
    draft: str = ""


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


@router.post("/review")
async def webnovel_review(script_id: int, data: ReviewRequest):
    """质量审查。"""
    script = get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    task = add_writing_task(script_id, data.chapter_index, "review")
    task_id = task["id"]

    asyncio.create_task(_execute_review_workflow(task_id, script_id, data.chapter_index, data.draft))

    return {"success": True, "task_id": task_id, "message": "审查任务已创建"}


async def _execute_review_workflow(task_id: int, script_id: int, chapter_index: int, draft: str):
    """执行审查工作流。"""
    try:
        update_writing_task(task_id, status="running", progress=10, progress_message="开始质量审查...")

        orchestrator = PipelineOrchestrator(script_id, chapter_index, task_id)
        result = await orchestrator.execute_workflow("review", {"draft": draft})

        if result["success"]:
            review_result = result.get("context", {}).get("review_result", [])
            avg_score = result.get("context", {}).get("average_score", 0)
            update_writing_task(
                task_id,
                status="completed",
                progress=100,
                progress_message=f"审查完成，平均评分{avg_score:.1f}",
                review_result=json.dumps(review_result)
            )
        else:
            update_writing_task(task_id, status="failed", progress=0, progress_message=f"审查失败: {result.get('failed_steps', 0)}个步骤出错")

    except Exception as e:
        update_writing_task(task_id, status="failed", error_message=str(e), progress_message=f"执行失败: {str(e)[:100]}")


@router.post("/query")
async def webnovel_query(script_id: int, data: QueryRequest):
    """状态查询（基于RAG语义检索）。

    按分类返回相似度超过95%的内容，每种分类最多返回5条。
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
    try:
        from core.model_executor import get_model_executor
        executor = get_model_executor()
        result = await executor.execute_text_to_vector([query])
        embeddings = result.get("embeddings", [])
        if embeddings:
            from services.vector_store import get_rag_service
            # 获取足够多的候选结果，以便按分类过滤后仍有充足数据
            all_results = get_rag_service().search(project_id, embeddings[0], limit=50)

            # 按相似度 > 0.95 过滤，再按 chunk_type 分组，每组最多 5 条
            # 注：Qwen3-Embedding 在高维空间中所有文档对的余弦相似度普遍偏高（0.90~1.0），
            # 因此阈值需设为 0.95 才能有效区分相关与无关内容
            SCORE_THRESHOLD = 0.95
            MAX_PER_CATEGORY = 5
            grouped: Dict[str, list] = {}
            for chunk in all_results:
                if chunk.get("score", 0) <= SCORE_THRESHOLD:
                    continue
                cat = chunk.get("chunk_type", "unknown")
                if cat not in grouped:
                    grouped[cat] = []
                if len(grouped[cat]) < MAX_PER_CATEGORY:
                    grouped[cat].append(chunk)

            # 转为有序列表返回（按每组首条的相似度降序排列分类）
            chunks = []
            for cat in sorted(grouped, key=lambda c: grouped[c][0]["score"], reverse=True):
                chunks.extend(grouped[cat])
        else:
            return {"success": False, "chunks": [], "error": "Embedding计算失败"}
    except Exception as e:
        return {"success": False, "chunks": [], "error": f"检索失败: {str(e)}"}

    return {"success": True, "chunks": chunks}


@router.get("/doctor")
async def webnovel_doctor(script_id: int, deep: bool = Query(False)):
    """项目体检。"""
    script = get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    task = add_writing_task(script_id, 0, "doctor")
    task_id = task["id"]

    asyncio.create_task(_execute_doctor_workflow(task_id, script_id, deep))

    return {"success": True, "task_id": task_id, "message": "体检任务已创建"}


async def _execute_doctor_workflow(task_id: int, script_id: int, deep: bool):
    """执行体检工作流。"""
    try:
        update_writing_task(task_id, status="running", progress=10, progress_message="开始项目体检...")

        orchestrator = PipelineOrchestrator(script_id, 0, task_id)
        result = await orchestrator.execute_workflow("doctor", {"deep": deep})

        if result["success"]:
            doctor_report = result.get("context", {}).get("doctor_report", {})
            update_writing_task(
                task_id,
                status="completed",
                progress=100,
                progress_message=f"体检完成: {doctor_report.get('total_issues', 0)}个问题",
                context=json.dumps(doctor_report)
            )
        else:
            update_writing_task(task_id, status="failed", progress=0, progress_message="体检失败")

    except Exception as e:
        update_writing_task(task_id, status="failed", error_message=str(e), progress_message=f"执行失败: {str(e)[:100]}")


@router.post("/learn")
async def webnovel_learn(script_id: int, data: LearnRequest):
    """项目学习。"""
    script = get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=400, detail="项目未初始化")

    task = add_writing_task(script_id, data.current_chapter, "learn")
    task_id = task["id"]

    asyncio.create_task(_execute_learn_workflow(task_id, script_id, data.learning_content, data.current_chapter))

    return {"success": True, "task_id": task_id, "message": "学习任务已创建"}


async def _execute_learn_workflow(task_id: int, script_id: int, learning_content: str, current_chapter: int):
    """执行学习工作流。"""
    try:
        update_writing_task(task_id, status="running", progress=10, progress_message="开始项目学习...")

        orchestrator = PipelineOrchestrator(script_id, current_chapter, task_id)
        result = await orchestrator.execute_workflow("learn", {"learning_content": learning_content, "current_chapter": current_chapter})

        if result["success"]:
            learned_patterns = result.get("context", {}).get("learned_patterns", [])
            update_writing_task(
                task_id,
                status="completed",
                progress=100,
                progress_message=f"学习完成，新增{len(learned_patterns)}个写作模式",
                context=json.dumps({"learned_patterns": learned_patterns})
            )
        else:
            update_writing_task(task_id, status="failed", progress=0, progress_message="学习失败")

    except Exception as e:
        update_writing_task(task_id, status="failed", error_message=str(e), progress_message=f"执行失败: {str(e)[:100]}")


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
