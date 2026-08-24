"""网文创作相关 API 接口。"""

import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body, Form
from pydantic import BaseModel

from repositories import (
    get_writing_tasks, get_writing_task, add_writing_task, update_writing_task,
    delete_writing_task, get_running_tasks,
    get_script,
)
from webnovel.repositories import (
    get_webnovel_project_by_script, get_volume_outlines_by_project,
    add_volume_outline, get_volume_outline, update_volume_outline, delete_volume_outline,
    get_chapter_meta_list, get_chapter_meta, add_chapter_meta, update_chapter_meta,
    get_review_records, get_chapter_review_summary, add_review_record,
    delete_review_record, delete_chapter_review_records,
    get_worldview_by_project, add_worldview, get_worldview,
    get_worldview_factions, get_worldview_history,
    get_timelines_by_project, add_timeline, add_timeline_chapter, add_timeline_countdown,
    get_timeline_chapters, get_timeline_countdowns,
    get_open_loops_by_project, get_active_open_loops, get_cool_points_by_project,
    get_cool_points_by_chapter, get_cool_points_count_by_type,
    get_rag_chunks_by_project, delete_rag_chunks_by_project,
    get_master_setting, get_anti_patterns,
    get_all_chapter_plans_for_project,
    get_chapter_plan, delete_chapter_plan, get_chapter_plans_by_volume,
    update_chapter_plan, add_chapter_plan,
    get_character_cards_by_project, get_character_relationships,
    get_character_growths, get_character_power,
    get_character_group_by_project, get_character_group_members,
    get_character_group_arcs,
    get_golden_finger_by_project, get_golden_finger_upgrades,
    get_golden_finger_payoffs, get_golden_finger_feedbacks,
    get_villains_by_project, get_villain_hierarchy,
    get_villain_plot_nodes,
    get_power_system_by_project, get_power_levels,
    get_power_feedbacks
)
from webnovel.services.webnovel_service import get_webnovel_service

router = APIRouter(prefix="/api/books/scripts")


@router.get("/genres")
def list_genres():
    """获取所有题材模板列表。"""
    import os
    genres_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'genres_json')
    genres_dir = os.path.abspath(genres_dir)
    
    genres = []
    if os.path.exists(genres_dir):
        for filename in os.listdir(genres_dir):
            if filename.endswith('.json'):
                genre_name = filename[:-5]
                genres.append(genre_name)
    
    genres.sort()
    return {"success": True, "genres": genres}


@router.get("/genre-template")
def get_genre_template(genre: str):
    """获取指定题材的模板内容。"""
    import os
    genres_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'genres')
    genres_dir = os.path.abspath(genres_dir)
    
    filepath = os.path.join(genres_dir, f'{genre}.md')
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="题材模板不存在")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    return {"success": True, "genre": genre, "content": content}


@router.get("/genre-json-template")
def get_genre_json_template(genre: str):
    """获取指定题材的JSON模板内容。"""
    import os
    genres_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'genres_json')
    genres_dir = os.path.abspath(genres_dir)
    
    filepath = os.path.join(genres_dir, f'{genre}.json')
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="题材JSON模板不存在")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="JSON解析失败")
    
    return {"success": True, "genre": genre, "data": data}


@router.get("/webnovel-outline")
def get_webnovel_outline(script_id: int):
    """获取webnovel项目的卷纲和规划信息。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": True, "outline": {}, "volumes": []}
    
    genre = project.get("genre", "")
    genre_label = project.get("genre_label", "")
    
    outline_data = {
        "title": project.get("title", ""),
        "genre": genre,
        "genre_label": genre_label,
        "target_words": project.get("target_words", 0),
        "target_chapters": project.get("target_chapters", 0),
        "core_selling_points": project.get("core_selling_points", ""),
        "one_liner": project.get("one_liner", ""),
        "story_summary": project.get("story_summary", ""),
        "golden_finger_name": project.get("golden_finger_name", ""),
        "golden_finger_type": project.get("golden_finger_type", ""),
    }
    
    volumes = get_volume_outlines_by_project(project["id"])
    
    return {"success": True, "outline": outline_data, "volumes": volumes}


@router.get("/webnovel-worldview")
def get_webnovel_worldview(script_id: int):
    """获取webnovel项目的世界观信息。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": True, "worldview": {}, "power_system": {}, "rules": []}
    
    worldview = get_worldview_by_project(project["id"]) or {}
    
    worldview_data = {
        "world_scale": project.get("world_scale", ""),
        "factions": project.get("factions", ""),
        "social_class": project.get("social_class", ""),
        "resource_distribution": project.get("resource_distribution", ""),
        "currency_system": project.get("currency_system", ""),
        "world_summary": worldview.get("world_summary", ""),
    }
    
    power_system_data = {
        "power_system_type": project.get("power_system_type", ""),
        "cultivation_chain": project.get("cultivation_chain", ""),
        "cultivation_subtiers": project.get("cultivation_subtiers", ""),
        "sect_hierarchy": project.get("sect_hierarchy", ""),
    }
    
    return {
        "success": True,
        "worldview": worldview_data,
        "power_system": power_system_data,
        "project": project
    }


@router.get("/webnovel-world-state")
def get_webnovel_world_state(script_id: int):
    """获取webnovel项目的完整世界状态数据（世界观 + 势力 + 历史）。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": False, "message": "项目不存在"}

    worldview = get_worldview_by_project(project["id"])
    if not worldview:
        return {"success": True, "worldview": None, "factions": [], "history_events": []}

    factions = get_worldview_factions(worldview["id"])
    history_events = get_worldview_history(worldview["id"])

    return {
        "success": True,
        "worldview": worldview,
        "factions": factions,
        "history_events": history_events,
    }


@router.get("/webnovel-character-cards")
def get_webnovel_character_cards(script_id: int):
    """获取项目下所有角色卡及其关联数据（关系、成长、战力 + 角色组）。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": False, "message": "项目不存在"}

    project_id = project["id"]
    cards = get_character_cards_by_project(project_id)

    characters = []
    for card in cards:
        cid = card["id"]
        characters.append({
            "card": card,
            "relationships": get_character_relationships(cid),
            "growths": get_character_growths(cid),
            "power": get_character_power(cid),
        })

    # 角色组（一个项目通常只有一个组）
    groups = []
    group = get_character_group_by_project(project_id)
    if group:
        gid = group["id"]
        groups.append({
            "group": group,
            "members": get_character_group_members(gid),
            "arcs": get_character_group_arcs(gid),
        })

    return {
        "success": True,
        "characters": characters,
        "groups": groups,
    }


@router.get("/webnovel-golden-finger")
def get_webnovel_golden_finger(script_id: int):
    """获取项目下金手指及其关联数据（升级、爽点、反馈）。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": False, "message": "项目不存在"}

    gf = get_golden_finger_by_project(project["id"])
    if not gf:
        return {"success": True, "golden_finger": None, "upgrades": [], "payoffs": [], "feedbacks": []}

    gf_id = gf["id"]
    return {
        "success": True,
        "golden_finger": gf,
        "upgrades": get_golden_finger_upgrades(gf_id),
        "payoffs": get_golden_finger_payoffs(gf_id),
        "feedbacks": get_golden_finger_feedbacks(gf_id),
    }


@router.get("/webnovel-timeline")
def get_webnovel_timeline(script_id: int):
    """获取项目下所有时间线及其关联数据（章节时间轴 + 倒计时事件）。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": False, "message": "项目不存在"}

    timelines = get_timelines_by_project(project["id"])
    result = []
    for tl in timelines:
        tid = tl["id"]
        result.append({
            "timeline": tl,
            "chapters": get_timeline_chapters(tid),
            "countdowns": get_timeline_countdowns(tid),
        })

    return {
        "success": True,
        "timelines": result,
    }


@router.get("/webnovel-villain")
def get_webnovel_villain_data(script_id: int):
    """获取项目下所有反派及其关联数据（层级 + 剧情节点）。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": False, "message": "项目不存在"}

    villains = get_villains_by_project(project["id"])
    result = []
    for v in villains:
        vid = v["id"]
        result.append({
            "villain": v,
            "hierarchy": get_villain_hierarchy(vid),
            "plot_nodes": get_villain_plot_nodes(vid),
        })

    return {
        "success": True,
        "villains": result,
    }


@router.get("/webnovel-power-system")
def get_webnovel_power_system_data(script_id: int):
    """获取项目下战力体系及其关联数据（等级体系 + 反馈节奏）。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": False, "message": "项目不存在"}

    ps = get_power_system_by_project(project["id"])
    if not ps:
        return {"success": True, "power_system": None, "levels": [], "feedbacks": []}

    ps_id = ps["id"]
    return {
        "success": True,
        "power_system": ps,
        "levels": get_power_levels(ps_id),
        "feedbacks": get_power_feedbacks(ps_id),
    }


@router.get("/webnovel-cool-points")
def get_webnovel_cool_points_data(script_id: int):
    """获取项目下所有爽点记录。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": False, "message": "项目不存在"}
    cool_points = get_cool_points_by_project(project["id"])
    return {"success": True, "cool_points": cool_points}


@router.get("/webnovel-open-loops")
def get_webnovel_open_loops_data(script_id: int):
    """获取项目下所有开放悬念。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": False, "message": "项目不存在"}
    loops = get_open_loops_by_project(project["id"])
    return {"success": True, "loops": loops}


class WorldSettingCreate(BaseModel):
    name: str
    content: str = ""
    category: str = ""


class WorldSettingUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None


class VolumeOutlineCreate(BaseModel):
    volume_number: int = 1
    volume_title: str = ""
    summary: str = ""
    start_chapter: int = 0
    end_chapter: int = 0
    timeline_order: int = 0


class VolumeOutlineUpdate(BaseModel):
    volume_number: Optional[int] = None
    volume_title: Optional[str] = None
    summary: Optional[str] = None
    start_chapter: Optional[int] = None
    end_chapter: Optional[int] = None
    status: Optional[str] = None


class ChapterPlanCreate(BaseModel):
    chapter_index: int = 0
    chapter_title: str = ""
    summary: str = ""
    key_events: str = ""
    foreshadowing: str = ""


class ChapterPlanUpdate(BaseModel):
    chapter_title: Optional[str] = None
    summary: Optional[str] = None
    key_events: Optional[str] = None
    foreshadowing: Optional[str] = None
    status: Optional[str] = None


class ReorderRequest(BaseModel):
    outline_ids: List[int]


class WritingTaskCreate(BaseModel):
    chapter_index: int = 0
    task_type: str = "continue"
    prompt: str = ""


# ========== 世界观设定 ==========

@router.get("/world-settings")
def list_world_settings(script_id: int, category: str = Query("")):
    """获取世界观设定列表。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": True, "settings": []}
    worldview = get_worldview_by_project(project["id"])
    if worldview:
        return {"success": True, "settings": [worldview]}
    return {"success": True, "settings": []}


@router.get("/world-settings/categories")
def list_world_setting_categories(script_id: int):
    """获取世界观设定分类列表。"""
    return {"success": True, "categories": ["世界观"]}


@router.get("/world-settings/detail")
def get_world_setting_detail(script_id: int, setting_id: int):
    """获取单个世界观设定。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    worldview = get_worldview_by_project(project["id"])
    if worldview:
        return {"success": True, "setting": worldview}
    raise HTTPException(status_code=404, detail="设定不存在")


@router.post("/world-settings")
def create_world_setting(script_id: int, data: WorldSettingCreate):
    """添加世界观设定。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    worldview = add_worldview(
        project_id=project["id"],
        world_summary=data.content or "",
    )
    return {"success": True, "setting": worldview}


@router.put("/world-settings")
def update_world_setting_detail(script_id: int, setting_id: int, data: WorldSettingUpdate):
    """更新世界观设定。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    worldview = get_worldview_by_project(project["id"])
    if not worldview:
        raise HTTPException(status_code=404, detail="设定不存在")
    return {"success": True, "setting": worldview}


@router.delete("/world-settings")
def remove_world_setting(script_id: int, setting_id: int):
    """删除世界观设定。"""
    return {"success": True}








@router.post("/volume-outlines/split-chapter")
async def split_volume_to_chapters(
    script_id: int,
    outline_id: int,
    start_chapter: Optional[int] = Query(None),
    end_chapter: Optional[int] = Query(None)
):
    """智能拆章：使用 PlanExecutor 生成章节规划，异步执行并通过 WebSocket 通知前端。"""
    import asyncio
    from webnovel.repositories import (
        get_character_cards_by_project, delete_chapter_plans_in_range,
        get_chapter_plans_by_volume, get_character_group_by_project,
        get_character_group_members
    )

    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    outline = get_volume_outline(project["id"], outline_id)
    if not outline:
        raise HTTPException(status_code=404, detail="卷纲不存在")

    vo_start = int(outline.get("chapter_start", 1))
    vo_end = int(outline.get("chapter_end", vo_start + 29))

    # 校验并夹紧章节范围
    actual_start = max(int(start_chapter), vo_start) if start_chapter is not None else vo_start
    actual_end = min(int(end_chapter), vo_end) if end_chapter is not None else vo_end

    if actual_start > actual_end:
        raise HTTPException(
            status_code=400,
            detail=f"章节范围无效：{actual_start}-{actual_end}，卷纲范围为 {vo_start}-{vo_end}"
        )

    # 校验起始章节的连续性：必须是卷首、已规划章节、或已规划章节+1
    existing_plans = get_chapter_plans_by_volume(outline_id)
    if existing_plans:
        planned_indices = {p.get("chapter_index") for p in existing_plans}
        max_planned = max(planned_indices)
        valid_start = (actual_start == vo_start
                       or actual_start in planned_indices
                       or actual_start == max_planned + 1)
        if not valid_start:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"起始章节第{actual_start}章不连续："
                    f"必须为卷首({vo_start})、已规划章节、或已规划最大章节+1({max_planned + 1})"
                )
            )

    # 只删除指定范围内的章节规划，保留范围外的旧数据（合并模式）
    delete_chapter_plans_in_range(outline_id, actual_start, actual_end)

    async def _do_generate():
        from webnovel.pipeline.executors.plan_executor import PlanExecutor
        from infrastructure.websocket_broadcast import ws_broadcast_manager

        executor = PlanExecutor(script_id, 0, 0)
        protagonist_list = get_character_cards_by_project(project["id"], "protagonist")
        protagonist = protagonist_list[0] if protagonist_list else {}
        volume_number = outline.get("volume_number", 1)

        # 加载角色组数据，确保拆章 prompt 中包含主角团信息
        char_group = get_character_group_by_project(project["id"])
        char_group_members = []
        if char_group:
            char_group_members = get_character_group_members(char_group["id"])

        try:
            chapter_plans = await executor._generate_chapter_plans(
                project, outline, protagonist, volume_number,
                start_chapter=actual_start, end_chapter=actual_end,
                char_group=char_group, char_group_members=char_group_members
            )
            plan_count = 0
            if chapter_plans:
                plan_count = executor._save_chapter_plans(outline_id, chapter_plans)

            success = plan_count > 0
            message = f"智能拆章完成：生成{plan_count}章规划" if success else "智能拆章失败：未生成有效章节规划"

            await ws_broadcast_manager.broadcast_chapter_plans_generated(
                script_id, outline_id, success, message, plan_count
            )
        except Exception as e:
            from utils.logger import logger
            logger.error(f"[split-chapter] 异步生成章节规划失败: {e}")
            await ws_broadcast_manager.broadcast_chapter_plans_generated(
                script_id, outline_id, False, f"智能拆章异常: {str(e)}", 0
            )

    asyncio.create_task(_do_generate())

    return {
        "success": True,
        "message": f"智能拆章已启动，正在生成第{actual_start}-{actual_end}章规划",
        "start_chapter": actual_start,
        "end_chapter": actual_end
    }


# ========== 卷纲规划 ==========

@router.get("/volume-outlines")
def list_volume_outlines(script_id: int):
    """获取卷纲规划列表。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": True, "outlines": []}
    outlines = get_volume_outlines_by_project(project["id"])
    return {"success": True, "outlines": outlines}


@router.get("/volume-outlines/detail")
def get_volume_outline_detail(script_id: int, outline_id: int):
    """获取单个卷纲规划。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    outline = get_volume_outline(project["id"], outline_id)
    if not outline:
        raise HTTPException(status_code=404, detail="卷纲规划不存在")
    return {"success": True, "outline": outline}


@router.post("/volume-outlines")
def create_volume_outline(script_id: int, data: VolumeOutlineCreate):
    """添加卷纲规划。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    outline = add_volume_outline(
        project_id=project["id"],
        volume_number=data.volume_number,
        volume_name=data.volume_title or "",
        chapter_start=data.start_chapter or 0,
        chapter_end=data.end_chapter or 0,
        core_conflict=data.summary or "",
        promise_description=data.summary or ""
    )
    return {"success": True, "outline": outline}


@router.put("/volume-outlines")
def modify_volume_outline(script_id: int, outline_id: int, data: VolumeOutlineCreate):
    """更新卷纲规划。"""
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
        core_conflict=data.summary or "",
        volume_climax=data.summary or ""
    )
    return {"success": True}


@router.delete("/volume-outlines")
def remove_volume_outline(script_id: int, outline_id: int):
    """删除卷纲规划。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    outline = get_volume_outline(project["id"], outline_id)
    if not outline:
        raise HTTPException(status_code=404, detail="卷纲规划不存在")
    delete_volume_outline(outline_id)
    return {"success": True}


# ========== 章节规划 ==========

@router.get("/chapter-plans/all")
def list_all_chapter_plans(script_id: int):
    """获取项目下所有章节规划（按卷分组），用于章节选择器。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": True, "volumes": []}
    volumes = get_all_chapter_plans_for_project(project["id"])
    # 查询已完成创作任务的章节索引，用于前端显示状态标记
    completed_tasks = get_writing_tasks(script_id, None, "completed")
    chapters_with_result = set()
    for task in completed_tasks:
        if task.get("task_type") == "continue":
            ch = task.get("chapter_index")
            if ch is not None:
                chapters_with_result.add(ch)
    for vol in volumes:
        for plan in vol.get("chapter_plans", []):
            plan["has_result"] = plan.get("chapter_index") in chapters_with_result
    return {"success": True, "volumes": volumes}


@router.get("/chapter-plans")
def list_chapter_plans(script_id: int, outline_id: int = Query(None)):
    """获取章节规划列表。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": True, "chapter_plans": []}
    if outline_id:
        plans = get_chapter_plans_by_volume(outline_id)
    else:
        # 无 outline_id 时返回项目下所有卷的章节规划
        all_volumes = get_volume_outlines_by_project(project["id"])
        plans = []
        for vol in all_volumes:
            plans.extend(get_chapter_plans_by_volume(vol["id"]))
    return {"success": True, "chapter_plans": plans}


@router.get("/chapter-plans/detail")
def get_chapter_plan_detail(script_id: int, outline_id: int = Query(None), plan_id: int = Query(None)):
    """获取单个章节规划。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if plan_id:
        plan = get_chapter_plan(plan_id)
    else:
        plan = None
    if not plan:
        raise HTTPException(status_code=404, detail="章节规划不存在")
    return {"success": True, "plan": plan}


@router.post("/chapter-plans")
def create_chapter_plan(script_id: int, outline_id: int = Query(None), data: ChapterPlanCreate = None):
    """添加章节规划。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    if data and outline_id:
        plan = add_chapter_plan(
            volume_outline_id=outline_id,
            chapter_index=data.chapter_index,
            chapter_title=data.chapter_title or "",
            summary=data.summary or "",
            key_events=data.key_events or "",
            foreshadowing=data.foreshadowing or "",
        )
        return {"success": True, "plan": plan}
    return {"success": False, "error": "缺少参数"}


@router.put("/chapter-plans")
def update_chapter_plan_detail(script_id: int, outline_id: int = Query(None), plan_id: int = Query(None), data: ChapterPlanUpdate = None):
    """更新章节规划。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    if plan_id and data:
        plan = get_chapter_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="章节规划不存在")
        
        update_data = {}
        if data.chapter_title is not None:
            update_data["chapter_title"] = data.chapter_title
        if data.summary is not None:
            update_data["summary"] = data.summary
        if data.key_events is not None:
            update_data["key_events"] = data.key_events
        if data.foreshadowing is not None:
            update_data["foreshadowing"] = data.foreshadowing
        
        if update_data:
            update_chapter_plan(plan_id, **update_data)
        
        updated = get_chapter_plan(plan_id)
        return {"success": True, "plan": updated}
    
    return {"success": False, "error": "缺少参数"}


@router.delete("/chapter-plans")
def remove_chapter_plan(script_id: int, outline_id: int = Query(None), plan_id: int = Query(None)):
    """删除章节规划。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not plan_id:
        raise HTTPException(status_code=400, detail="缺少 plan_id 参数")
    plan = get_chapter_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="章节规划不存在")
    delete_chapter_plan(plan_id)
    return {"success": True}


# ========== 写作任务 ==========

@router.get("/writing-tasks")
def list_writing_tasks(script_id: int, chapter_index: int = Query(-1), status: str = Query("")):
    """获取写作任务列表。"""
    # chapter_index=-1 表示不过滤，传 None
    filter_chapter = chapter_index if chapter_index >= 0 else None
    tasks = get_writing_tasks(script_id, filter_chapter, status)
    return {"success": True, "tasks": tasks}


@router.get("/writing-tasks/detail")
def get_writing_task_detail(script_id: int, task_id: int):
    """获取单个写作任务。"""
    task = get_writing_task(script_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "task": task}


@router.post("/writing-tasks")
def create_writing_task_api(script_id: int, data: WritingTaskCreate):
    """创建写作任务。"""
    script = get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    running_tasks = get_writing_tasks(script_id, data.chapter_index, "running")
    if running_tasks:
        raise HTTPException(status_code=400, detail="该章节已有正在运行的任务")

    task = add_writing_task(script_id, data.chapter_index, data.task_type, data.prompt)
    return {"success": True, "task": task}


@router.put("/writing-tasks")
def update_writing_task_api(script_id: int, task_id: int, data: dict = Body(...)):
    """更新写作任务。"""
    task = get_writing_task(script_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    update_writing_task(task_id, **data)
    updated = get_writing_task(script_id, task_id)
    return {"success": True, "task": updated}


@router.delete("/writing-tasks")
def remove_writing_task(script_id: int, task_id: int):
    """删除写作任务。"""
    task = get_writing_task(script_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    delete_writing_task(task_id)
    return {"success": True}


# ========== 创作任务 ==========

class ContinueRequest(BaseModel):
    prompt: str = ""
    enable_polish: bool = True
    auto_apply: bool = False

@router.post("/chapters/continue")
async def continue_chapter(script_id: int, data: ContinueRequest, chapter_index: Optional[int] = None):
    """创作章节。"""
    service = get_webnovel_service()
    result = await service.continue_chapter(script_id, chapter_index, data.prompt, enable_polish=data.enable_polish, auto_apply=data.auto_apply)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "创作失败"))
    return result


@router.get("/chapters/continue/status")
async def get_continue_status(script_id: int, chapter_index: int, task_id: int):
    """获取创作任务状态。"""
    service = get_webnovel_service()
    status = await service.get_task_status(script_id, task_id)
    if not status:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "status": status}


@router.post("/chapters/continue/cancel")
async def cancel_continue_task(script_id: int, chapter_index: int, task_id: int):
    """取消创作任务。"""
    service = get_webnovel_service()
    result = await service.cancel_task(script_id, task_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "取消失败"))
    return result


class ApplyContinueResultRequest(BaseModel):
    task_id: int
    chapter_index: int


@router.post("/chapters/continue/apply")
async def apply_continue_result(script_id: int, data: ApplyContinueResultRequest):
    """应用创作结果到章节。

    后端统一处理：
    - 过滤章节标题行和尾部非正文内容
    - 提取实际章节标题并回写
    - 章节不存在时自动创建
    - 完成后通过 WebSocket 通知前端刷新
    """
    service = get_webnovel_service()
    result = await service.apply_continue_result(script_id, data.chapter_index, data.task_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "应用失败"))
    return result


@router.get("/chapters/continue/latest")
async def get_latest_continue_task(script_id: int):
    """获取最新的创作任务（用于重新打开模态框时恢复进度）。"""
    # 先查 running 任务，再查 completed 任务
    running = get_writing_tasks(script_id, None, "running")
    continue_running = [t for t in running if t.get("task_type") == "continue"]
    if continue_running:
        return {"success": True, "task": continue_running[0]}

    completed = get_writing_tasks(script_id, None, "completed")
    continue_completed = [t for t in completed if t.get("task_type") == "continue"]
    if continue_completed:
        return {"success": True, "task": continue_completed[0]}

    return {"success": True, "task": None}


@router.get("/chapters/continue/results")
async def get_continue_results(script_id: int, chapter_index: Optional[int] = Query(None)):
    """获取已完成的创作任务结果。

    - 不传 chapter_index: 仅返回各章节的结果摘要（不含正文），用于下拉框标记哪些章节有结果
    - 传 chapter_index: 返回该章节的完整创作结果 + 章节当前是否有内容
    """
    from repositories import get_script_chapter

    if chapter_index is not None:
        # 单章节查询：返回完整结果
        tasks = get_writing_tasks(script_id, chapter_index, "completed")
        continue_tasks = [t for t in tasks if t.get("task_type") == "continue"]
        if not continue_tasks:
            return {"success": True, "result": None}

        task = continue_tasks[0]  # 最新一条
        chapter = get_script_chapter(script_id, chapter_index)
        chapter_has_content = bool(chapter and (chapter.get("word_count") or 0) > 0)

        return {
            "success": True,
            "result": {
                "chapter_index": chapter_index,
                "task_id": task["id"],
                "polished": task.get("polished", ""),
                "draft": task.get("draft", ""),
                "created_at": task.get("created_at", ""),
                "chapter_has_content": chapter_has_content,
            },
        }

    # 全量摘要：不含正文，仅标记哪些章节有结果
    completed = get_writing_tasks(script_id, None, "completed")
    continue_tasks = [t for t in completed if t.get("task_type") == "continue"]

    results_by_chapter = {}
    for task in continue_tasks:
        ch = task.get("chapter_index")
        if ch is not None and ch not in results_by_chapter:
            results_by_chapter[ch] = {
                "chapter_index": ch,
                "task_id": task["id"],
                "has_result": True,
                "created_at": task.get("created_at", ""),
            }

    return {"success": True, "results": list(results_by_chapter.values())}


# ========== 审查功能 ==========

@router.get("/chapters/review")
async def get_chapter_review(script_id: int, chapter_index: int):
    """获取章节审查结果。"""
    service = get_webnovel_service()
    result = await service.get_chapter_review(script_id, chapter_index)
    return {"success": True, "review": result}


@router.post("/chapters/review")
async def manual_review_chapter(script_id: int, chapter_index: int, content: str = Body("", description="章节内容")):
    """手动审查章节。"""
    service = get_webnovel_service()
    result = await service.manual_review(script_id, chapter_index, content)
    return result


@router.get("/review-records")
def list_review_records(script_id: int, chapter_index: int = Query(-1)):
    """获取审查记录列表。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": True, "records": []}
    chapter_number = chapter_index if chapter_index >= 0 else None
    records = get_review_records(project["id"], chapter_number)
    return {"success": True, "records": records}


@router.delete("/review-records")
def remove_review_record(script_id: int, record_id: int):
    """删除审查记录。"""
    delete_review_record(record_id)
    return {"success": True}


# ========== RAG检索 ==========

@router.get("/rag/search")
def search_rag(script_id: int, query: str = Query(""), limit: int = Query(10)):
    """搜索RAG索引。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": False, "chunks": []}
    chunks = []
    try:
        from core.global_manager import global_manager
        embedding_model = getattr(global_manager, 'qwen_embedding_model', None)
        if embedding_model and embedding_model.is_loaded() and query:
            embeddings = embedding_model.encode([query])
            if embeddings and len(embeddings) > 0:
                from webnovel.repositories import search_rag_chunks
                chunks = search_rag_chunks(project["id"], embeddings[0].tolist(), limit=limit)
    except Exception:
        pass
    return {"success": True, "chunks": chunks}


@router.get("/rag/chunks")
def list_rag_chunks(script_id: int, chunk_type: str = Query("")):
    """获取RAG索引块列表。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": True, "chunks": [], "count": 0}
    chunks = get_rag_chunks_by_project(project["id"], chunk_type)
    return {"success": True, "chunks": chunks, "count": len(chunks)}


@router.delete("/rag/chunks")
def clear_rag_chunks(script_id: int):
    """清除RAG索引。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": False, "error": "项目不存在"}
    ok = delete_rag_chunks_by_project(project["id"])
    return {"success": ok}


# ========== 伏笔和爽点 ==========

@router.get("/foreshadowing")
def list_foreshadowing(script_id: int, status: str = Query("")):
    """获取伏笔列表。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": True, "foreshadowing": []}
    
    if status == "active":
        loops = get_active_open_loops(project["id"])
    else:
        loops = get_open_loops_by_project(project["id"], status)
    
    return {"success": True, "foreshadowing": loops}


@router.get("/cool-points")
def list_cool_points(script_id: int, chapter_index: int = Query(-1)):
    """获取爽点列表。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": True, "cool_points": []}
    
    if chapter_index >= 0:
        cool_points = get_cool_points_by_chapter(project["id"], chapter_index)
    else:
        cool_points = get_cool_points_by_project(project["id"])
    
    return {"success": True, "cool_points": cool_points}


@router.get("/cool-points/stats")
def get_cool_points_stats(script_id: int):
    """获取爽点统计信息。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": True, "stats": {}}
    
    count_by_type = get_cool_points_count_by_type(project["id"])
    all_cool_points = get_cool_points_by_project(project["id"])
    
    stats = {
        "total_count": len(all_cool_points),
        "count_by_type": count_by_type,
        "chapters_with_cool_points": len(set(cp["chapter_number"] for cp in all_cool_points))
    }
    
    return {"success": True, "stats": stats}


@router.get("/master-setting")
def get_master_setting_api(script_id: int):
    """获取项目的 MASTER_SETTING 内容。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": True, "data": None}

    result = get_master_setting(project["id"])
    if not result:
        return {"success": True, "data": None}

    return {"success": True, "data": result.get("content", {})}


@router.get("/anti-patterns")
def get_anti_patterns_api(script_id: int):
    """获取项目的反套路模式列表。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": True, "data": []}

    patterns = get_anti_patterns(project["id"])
    return {"success": True, "data": patterns}
