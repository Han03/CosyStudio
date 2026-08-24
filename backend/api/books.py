"""电子书服务 REST API 路由。

电子书库管理（上传/章节拆分）:
- POST /api/books/library/upload: 上传电子书入库
- GET /api/books/library: 获取电子书列表
- GET /api/books/library/{book_id}: 获取电子书详情
- GET /api/books/library/{book_id}/chapters: 获取章节列表
- GET /api/books/library/{book_id}/chapters/{chapter_index}: 获取章节内容
- DELETE /api/books/library/{book_id}: 删除电子书
- POST /api/books/library/create-empty: 创建空书本（用于创作）
"""
import asyncio
import time

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form, Request
from typing import Optional
from pydantic import BaseModel

from services.ebook_library import get_ebook_library_service
from services.script_service import get_script_service
from services.media_manager import get_media_manager
from core.global_manager import global_manager
from utils.logger import logger
from repositories import (
    add_chapter_sentences,
    get_chapter_sentences,
    get_chapter_sentence_count,
    get_audio_cache,
    save_audio_cache,
)

router = APIRouter()


def add_log(message: str, level: str = "INFO"):
    try:
        if level == "INFO":
            logger.info(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "ERROR":
            logger.error(message)
        else:
            logger.info(message)
    except:
        pass
    print(f"[LOG][{level}] {message}")

# ===================== 电子书库管理 =====================

@router.post("/api/books/library/upload")
async def upload_ebook(
    file: UploadFile = File(..., description="电子书文件"),
    title: Optional[str] = Form(None, description="书名（可选，默认从文件名推导）"),
    author: str = Form("", description="作者"),
    description: str = Form("", description="简介"),
):
    """上传电子书入库。

    流程：
    1. 通过媒体管理模块保存到 media/document/books/
    2. 计算文件 MD5（去重）
    3. 识别编码、统计字数
    4. 拆分章节并记录字节偏移位置
    5. 写入 SQLite（ebook_library + ebook_chapters）

    返回: {"success": bool, "book_id": int, "duplicated": bool, ...}
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    add_log(f"[Books] 上传电子书入库: {file.filename} ({len(content)} bytes)")
    service = get_ebook_library_service()
    result = service.ingest(
        filename=file.filename,
        content=content,
        title=title,
        author=author,
        description=description,
    )
    add_log(f"[Books] 入库完成: {result.get('message')}")
    return result


@router.get("/api/books/library")
async def list_library(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    keyword: str = Query(None, description="搜索关键词（书名/作者）"),
):
    """获取电子书库列表。

    返回: {"books": [...], "total": int, "page": int, "page_size": int, "total_pages": int}
    """
    service = get_ebook_library_service()
    result = service.list_books(page=page, page_size=page_size, keyword=keyword)
    return {"success": True, **result}


@router.get("/api/books/library")
async def get_library_book(book_id: int):
    """获取电子书详情。"""
    service = get_ebook_library_service()
    book = service.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="电子书不存在")
    return {"success": True, "book": book}


@router.get("/api/books/library/chapters")
async def list_chapters(book_id: int):
    """获取电子书的章节列表。"""
    service = get_ebook_library_service()
    book = service.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="电子书不存在")
    chapters = service.list_chapters(book_id)
    return {"success": True, "chapters": chapters, "count": len(chapters)}


@router.get("/api/books/library/chapters/content")
async def get_chapter_content(book_id: int, chapter_index: int):
    """获取指定章节的内容。

    通过章节记录的字节偏移位置直接读取原始文件对应段落。
    """
    service = get_ebook_library_service()
    result = service.get_chapter_content(book_id, chapter_index)
    if result is None:
        raise HTTPException(status_code=404, detail="电子书或章节不存在")
    return {"success": True, **result}


@router.delete("/api/books/library")
async def delete_library_book(book_id: int):
    """删除电子书（数据库记录 + 物理文件）。"""
    service = get_ebook_library_service()
    ok, message = service.delete_book(book_id)
    if not ok:
        raise HTTPException(status_code=404, detail=message)
    return {"success": True, "message": message}


@router.post("/api/books/library/create-empty")
async def create_empty_book(
    title: str = Form(..., description="书名"),
    author: str = Form("", description="作者"),
    description: str = Form("", description="简介"),
):
    """创建空的书本数据（用于直接打开剧本编辑页面进行智能创作）。
    
    返回: {"success": bool, "book_id": int, "message": str}
    """
    if not title.strip():
        raise HTTPException(status_code=400, detail="书名不能为空")
    
    add_log(f"[Books] 创建空书本: title={title}")
    
    import hashlib
    import uuid
    from services.media_manager import get_media_manager
    from repositories import add_ebook, add_chapters
    
    md5 = hashlib.md5(f"empty_book_{title}_{time.time()}".encode()).hexdigest()
    file_uuid = str(uuid.uuid4())[:8]
    filename = f"empty_book_{file_uuid}.txt"
    
    media_mgr = get_media_manager()
    empty_content = f"# {title}\n\n"
    if author:
        empty_content += f"作者: {author}\n\n"
    if description:
        empty_content += f"简介: {description}\n\n"
    empty_content += "这是一本空书，用于创作。\n"
    
    file_path = media_mgr.save_file("books", filename, empty_content.encode("utf-8"), "document")
    
    book_id = add_ebook(
        title=title,
        file_path=file_path,
        file_size=len(empty_content.encode("utf-8")),
        word_count=len(empty_content),
        md5=md5,
        fmt="txt",
        encoding="utf-8",
        author=author,
        description=description,
    )
    
    if book_id:
        add_chapters(book_id, [
            {"chapter_index": 1, "title": "第1章", "start_offset": 0, "end_offset": len(empty_content.encode("utf-8"))}
        ])
        add_log(f"[Books] 空书本创建成功: book_id={book_id}")
        return {"success": True, "book_id": book_id, "message": f"空书本《{title}》创建成功"}
    
    raise HTTPException(status_code=500, detail="创建空书本失败")


# ===================== 剧本管理 =====================

@router.post("/api/books/library/scripts")
async def create_script(
    book_id: int,
    name: str = Form("", description="剧本名称（可选）"),
    description: str = Form("", description="剧本描述（可选）"),
    auto_generate: bool = Form(True, description="是否自动生成台词"),
):
    """生成演播剧本。

    根据书籍 ID 创建剧本生成任务，后端通过 Qwen 大模型按章节生成演播剧本。
    返回: {"success": bool, "script_id": int, "task_id": str, "message": str}
    """
    add_log(f"[Books] 创建剧本生成任务: book_id={book_id}")
    service = get_script_service()
    if auto_generate:
        result = service.create_script_task(book_id, name=name, description=description)
    else:
        result = service.create_script(book_id, name=name, description=description)
    add_log(f"[Books] 剧本任务创建: {result.get('message')}")
    return result


@router.post("/api/books/scripts/create")
async def create_script_only(
    book_id: int = Form(..., description="书籍ID"),
    name: str = Form("", description="剧本名称（可选）"),
    description: str = Form("", description="剧本描述（可选）"),
):
    """创建剧本主体（仅创建剧本，不生成台词）。

    返回: {"success": bool, "script_id": int, "message": str}
    """
    add_log(f"[Books] 创建剧本主体: book_id={book_id}")
    service = get_script_service()
    result = service.create_script(book_id, name=name, description=description)
    add_log(f"[Books] 剧本创建: {result.get('message')}")
    return result


@router.post("/api/books/scripts/chapters/generate")
async def generate_chapter_script(
    script_id: int,
    chapter_index: int,
):
    """为单个章节生成台词（异步）。
    
    返回: {"success": bool, "message": str}
    """
    add_log(f"[Books] 开始生成章节台词: script_id={script_id}, chapter_index={chapter_index}")
    service = get_script_service()
    
    script = service.get_script(script_id)
    if script is None:
        raise HTTPException(status_code=404, detail="剧本不存在")
    
    chapter = service.get_script_chapters(script_id)
    ch = next((c for c in chapter if c["chapter_index"] == chapter_index), None)
    if ch is None:
        raise HTTPException(status_code=404, detail="章节不存在")
    
    asyncio.create_task(service.generate_chapter_script_stream(script_id, chapter_index))

    return {"success": True, "message": f"章节 {chapter_index} 台词生成任务已启动"}


@router.post("/api/books/scripts/chapters")
async def add_chapter(
    script_id: int,
    title: str = Form(..., description="章节标题"),
    content: str = Form("", description="章节正文"),
):
    """新增章节。"""
    service = get_script_service()
    script = service.get_script(script_id)
    if script is None:
        raise HTTPException(status_code=404, detail="剧本不存在")
    try:
        result = service.add_chapter(script_id, title, content)
        return {"success": True, "chapter": result, "message": f"章节「{title}」已添加"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/books/scripts/chapters")
async def delete_chapter(
    script_id: int,
    chapter_index: int,
):
    """删除章节（含文件和台词）。"""
    service = get_script_service()
    ok, message = service.delete_chapter(script_id, chapter_index)
    if not ok:
        raise HTTPException(status_code=404, detail=message)
    return {"success": True, "message": message}


@router.put("/api/books/scripts/chapters/content")
async def update_chapter_content(
    script_id: int,
    chapter_index: int,
    content: str = Form(..., description="章节正文"),
):
    """更新章节正文内容。"""
    service = get_script_service()
    ok = service.update_chapter_content(script_id, chapter_index, content)
    if not ok:
        raise HTTPException(status_code=404, detail="章节不存在或文件缺失")
    return {"success": True, "message": "章节内容已保存"}


class RenameChapterRequest(BaseModel):
    script_id: int
    chapter_index: int
    title: str


@router.post("/api/books/scripts/chapters/rename")
async def rename_chapter(req: RenameChapterRequest):
    """重命名章节标题。"""
    service = get_script_service()
    new_title = (req.title or "").strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="章节标题不能为空")
    ok = service.update_chapter_title(req.script_id, req.chapter_index, new_title)
    if not ok:
        raise HTTPException(status_code=404, detail="章节不存在")
    return {"success": True, "message": "章节标题已更新", "title": new_title}


@router.get("/api/books/scripts/chapters/content")
async def get_script_chapter_content(
    script_id: int,
    chapter_index: int,
):
    """获取剧本章节的正文内容。"""
    service = get_script_service()
    result = service.get_chapter_content(script_id, chapter_index)
    if result is None:
        raise HTTPException(status_code=404, detail="章节不存在")
    return {"success": True, **result}


@router.post("/api/books/scripts/regenerate")
async def regenerate_script(
    script_id: int,
):
    """清空已有台词并重新生成整个剧本（异步）。

    返回: {"success": bool, "message": str}
    """
    if global_manager.is_model_busy():
        raise HTTPException(status_code=400, detail="系统繁忙，请稍后再试")

    if not global_manager.try_acquire_model("qwen"):
        raise HTTPException(status_code=400, detail="系统繁忙，请稍后再试")

    add_log(f"[Books] 开始全剧本重新生成: script_id={script_id}")
    service = get_script_service()

    script = service.get_script(script_id)
    if script is None:
        global_manager.release_model()
        raise HTTPException(status_code=404, detail="剧本不存在")

    task = asyncio.create_task(service.regenerate_script_stream(script_id))
    service.register_task(script_id, task)

    return {"success": True, "message": "生成全部台词任务已启动"}


@router.post("/api/books/scripts/stop")
async def stop_script_generation(
    script_id: int,
):
    """停止剧本生成任务。

    用于服务重启或后端异常导致剧本永久处于生成状态的恢复。
    """
    add_log(f"[Books] 停止剧本生成: script_id={script_id}")
    service = get_script_service()
    result = service.stop_generation(script_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/api/books/scripts/chapters/clear")
async def clear_chapter_lines(
    script_id: int,
    chapter_index: int,
):
    """清空指定章节的所有台词。"""
    add_log(f"[Books] 清空章节台词: script_id={script_id}, chapter_index={chapter_index}")
    service = get_script_service()
    result = service.clear_chapter_lines(script_id, chapter_index)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/api/books/library/scripts")
async def list_scripts(book_id: int):
    """获取书籍的剧本列表。"""
    service = get_script_service()
    scripts = service.get_scripts(book_id)
    return {"success": True, "scripts": scripts, "count": len(scripts)}


@router.get("/api/books/scripts")
async def get_script_detail(script_id: int):
    """获取剧本详情（含任务状态和章节信息）。"""
    service = get_script_service()
    script = service.get_script(script_id)
    if script is None:
        raise HTTPException(status_code=404, detail="剧本不存在")
    chapters = service.get_script_chapters(script_id)
    return {"success": True, "script": script, "chapters": chapters}


@router.delete("/api/books/scripts")
async def delete_script(script_id: int):
    """删除剧本及其所有台词。"""
    service = get_script_service()
    ok, message = service.delete_script(script_id)
    if not ok:
        raise HTTPException(status_code=404, detail=message)
    return {"success": True, "message": message}


class RenameScriptRequest(BaseModel):
    script_id: int
    name: str


@router.post("/api/books/scripts/rename")
async def rename_script(req: RenameScriptRequest):
    """重命名剧本（更新书名）。"""
    from repositories.script_repository import get_script, update_script

    script = get_script(req.script_id)
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")
    new_name = (req.name or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="书名不能为空")
    update_script(req.script_id, name=new_name)
    return {"success": True, "message": "书名已更新"}


@router.get("/api/books/scripts/lines")
async def get_script_lines(
    script_id: int,
    chapter_index: Optional[int] = Query(None, description="章节序号，不传则返回全部"),
):
    """获取台词列表。"""
    service = get_script_service()
    lines = service.get_script_lines(script_id, chapter_index)
    return {"success": True, "lines": lines, "count": len(lines)}


@router.get("/api/books/scripts/lines/paged")
async def get_script_lines_paged(
    script_id: int,
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(50, ge=1, le=500, description="每页数量"),
    chapter_index: Optional[int] = Query(None, description="章节序号，不传则返回全部"),
):
    """分页获取台词列表。

    返回: {"success": true, "lines": [...], "total": int, "page": int, "page_size": int}
    """
    service = get_script_service()
    result = service.get_script_lines_paged(
        script_id, page=page, page_size=page_size, chapter_index=chapter_index
    )
    return {"success": True, **result}


@router.get("/api/books/scripts/characters")
async def get_script_characters(script_id: int):
    """获取剧本中所有角色（去重），含句数统计和配音配置。"""
    service = get_script_service()
    characters = service.get_characters(script_id)
    from repositories import get_character_configs
    configs = get_character_configs(script_id)
    config_map = {c["role"]: c for c in configs}
    for ch in characters:
        cfg = config_map.get(ch["role"], {})
        ch["agent_id"] = cfg.get("agent_id", "")
        ch["speed"] = cfg.get("speed", 1.0)
        ch["seed"] = cfg.get("seed", 0)
    return {"success": True, "characters": characters, "count": len(characters)}


@router.post("/api/books/scripts/characters")
async def add_script_character(script_id: int, request: Request):
    """新增角色到剧本。请求体: {"role": "角色名"}"""
    body = await request.json()
    role = body.get("role", "").strip()
    if not role:
        return {"success": False, "message": "角色名不能为空"}
    service = get_script_service()
    try:
        ch = service.add_character(script_id, role)
        return {"success": True, "character": ch, "message": "角色添加成功"}
    except ValueError as e:
        return {"success": False, "message": str(e)}


@router.delete("/api/books/scripts/characters")
async def delete_script_character(script_id: int, role: str):
    """删除剧本角色（仅当无台词时允许）。"""
    service = get_script_service()
    try:
        deleted = service.delete_character(script_id, role)
        return {"success": deleted, "message": "角色已删除" if deleted else "角色不存在"}
    except ValueError as e:
        return {"success": False, "message": str(e)}


@router.put("/api/books/scripts/characters/config")
async def update_character_config(script_id: int, role: str, request: Request):
    """更新角色配音配置。

    请求体: {"agent_id": "xxx", "speed": 1.0, "seed": 0}
    """
    body = await request.json()
    agent_id = body.get("agent_id", "")
    speed = float(body.get("speed", 1.0))
    seed = int(body.get("seed", 0))
    from repositories import upsert_character_config
    upsert_character_config(script_id, role, agent_id=agent_id, speed=speed, seed=seed)
    return {"success": True, "message": "角色配置已更新"}


@router.put("/api/books/scripts/lines")
async def update_script_lines(script_id: int, request: Request):
    """批量编辑台词。

    请求体: {"lines": [{"id": 1, "role": "旁白", "instruction": "用平静的语气朗读", "content": "..."}, ...]}
    """
    body = await request.json()
    lines = body.get("lines", [])
    service = get_script_service()
    count = service.update_lines_batch(lines)
    return {"success": True, "updated": count}


@router.post("/api/books/scripts/lines")
async def add_script_line(
    script_id: int,
    chapter_index: int = Form(..., description="章节序号"),
    role: str = Form("旁白", description="角色名"),
    instruction: str = Form("", description="语气指令"),
    content: str = Form(..., description="内容"),
    insert_after_id: int = Form(None, description="在该行之后插入"),
    insert_before_id: int = Form(None, description="在该行之前插入"),
):
    """新增单条台词。"""
    service = get_script_service()
    if insert_after_id or insert_before_id:
        line_data = service.add_line_at_position(
            script_id, chapter_index, role, instruction, content,
            insert_after_id, insert_before_id,
        )
        if line_data:
            return {"success": True, "line": line_data, "message": "台词已添加"}
        raise HTTPException(status_code=400, detail="插入位置无效")
    line_no = service.add_line(script_id, chapter_index, role, instruction, content)
    return {"success": True, "line_no": line_no, "message": "台词已添加"}


@router.delete("/api/books/scripts/lines")
async def delete_script_line(script_id: int, line_id: int):
    """删除单条台词。"""
    service = get_script_service()
    ok = service.delete_line(line_id)
    if not ok:
        raise HTTPException(status_code=404, detail="台词不存在")
    return {"success": True, "message": "台词已删除"}


@router.post("/api/books/scripts/lines/reorder")
async def reorder_script_lines_api(script_id: int, request: Request):
    """重新排序台词。
    
    请求体: {"line_id": 1, "chapter_index": 0, "target_prev_id": 2, "target_next_id": 3}
    target_prev_id: 目标位置的前一个语句ID（null表示移动到开头）
    target_next_id: 目标位置的后一个语句ID（null表示移动到末尾）
    """
    body = await request.json()
    line_id = body.get("line_id")
    chapter_index = body.get("chapter_index", 0)
    target_prev_id = body.get("target_prev_id")
    target_next_id = body.get("target_next_id")
    
    if line_id is None:
        raise HTTPException(status_code=400, detail="缺少line_id")
    
    from repositories import reorder_script_lines
    ok = reorder_script_lines(script_id, chapter_index, line_id, target_prev_id, target_next_id)
    
    if not ok:
        raise HTTPException(status_code=404, detail="台词不存在")
    
    return {"success": True, "message": "排序已更新"}


# ===================== 章节版本管理 =====================

@router.get("/api/books/scripts/chapters/versions")
async def get_chapter_versions_api(script_id: int, chapter_index: int):
    """获取章节的版本历史列表。"""
    from repositories import get_chapter_versions
    versions = get_chapter_versions(script_id, chapter_index)
    return {"success": True, "versions": versions, "count": len(versions)}


@router.get("/api/books/scripts/chapters/versions/detail")
async def get_chapter_version_detail_api(script_id: int, version_id: int):
    """获取单个版本详情。"""
    from repositories import get_chapter_version_detail
    version = get_chapter_version_detail(script_id, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    return {"success": True, "version": version}


@router.delete("/api/books/scripts/chapters/versions")
async def delete_chapter_version_api(script_id: int, version_id: int):
    """删除单个版本记录。"""
    from repositories import delete_chapter_version
    delete_chapter_version(script_id, version_id)
    return {"success": True, "message": "版本已删除"}


# ===================== 智能体朗读 =====================

def _split_chinese_sentences(text: str) -> list:
    """将中文文本拆分为句子列表。

    按句号、问号、感叹号、分号、换行符等拆分，保留标点。
    过短的段落会适当合并，避免句子太碎。
    """
    import re

    if not text:
        return []

    text = text.replace('\r\n', '\n').replace('\r', '\n')

    sentences = []
    # 按句号、问号、感叹号、分号拆分（保留标点）
    parts = re.split(r'([。！？!?；;])', text)

    current = ""
    for i in range(0, len(parts), 2):
        part = parts[i]
        punc = parts[i + 1] if i + 1 < len(parts) else ""

        if not part and not punc:
            continue

        segment = part + punc

        if current:
            current += segment
        else:
            current = segment

        # 遇到标点且当前句子长度合适，就断句
        if punc and len(current.strip()) >= 2:
            stripped = current.strip()
            if stripped:
                sentences.append(stripped)
            current = ""

    # 处理剩余内容
    remaining = current.strip()
    if remaining:
        sentences.append(remaining)

    # 过滤掉空句子和纯换行/空格
    sentences = [s for s in sentences if s.strip()]

    # 合并过短的句子（少于5个字）到下一句
    merged = []
    i = 0
    while i < len(sentences):
        s = sentences[i]
        if len(s) < 5 and i + 1 < len(sentences):
            merged.append(s + sentences[i + 1])
            i += 2
        else:
            merged.append(s)
            i += 1

    return merged if merged else sentences


@router.get("/api/books/library/chapters/sentences")
async def get_chapter_sentences(book_id: int, chapter_index: int):
    """获取章节拆分后的句子列表。

    若数据库中已有拆分结果，直接返回；否则拆分后存入数据库再返回。

    返回: {"success": True, "sentences": [{"sentence_index": 0, "content": "...", "char_count": 0}, ...]}
    """
    from repositories import get_chapter_sentences, add_chapter_sentences

    service = get_ebook_library_service()
    chapter = service.get_chapter_content(book_id, chapter_index)
    if chapter is None:
        raise HTTPException(status_code=404, detail="章节不存在")

    content = chapter.get("content", "")

    # 检查是否已有缓存
    cached = get_chapter_sentences(book_id, chapter_index)
    if cached and len(cached) > 0:
        sentences = [
            {"sentence_index": s["sentence_index"], "content": s["content"], "char_count": s["char_count"]}
            for s in cached
        ]
        return {"success": True, "sentences": sentences, "from_cache": True}

    # 拆分句子
    sentence_texts = _split_chinese_sentences(content)
    if not sentence_texts:
        return {"success": True, "sentences": [], "from_cache": False}

    # 存入数据库
    add_chapter_sentences(book_id, chapter_index, sentence_texts)

    # 再读取一次确保格式一致
    cached = get_chapter_sentences(book_id, chapter_index)
    sentences = [
        {"sentence_index": s["sentence_index"], "content": s["content"], "char_count": s["char_count"]}
        for s in cached
    ]
    return {"success": True, "sentences": sentences, "from_cache": False}


@router.post("/api/books/library/chapters/sentences/audio")
async def synthesize_sentence_audio(
    book_id: int,
    chapter_index: int,
    sentence_index: int,
    request: Request,
):
    """合成单句语音（带缓存）。

    请求体: {"agent_id": "...", "seed": 0, "instruction": "", "speed": 1.0}
    先查询缓存，命中则直接返回缓存的音频文件路径；否则生成新音频并缓存。

    返回 NDJSON 流：
    - {"type":"cached","audio_url":"...","duration":...,"sentence_index":...}
    - {"type":"start","sample_rate":24000,"sentence_index":...}
    - {"type":"pcm_chunk","sample_rate":24000,"chunk_index":0,"data":"<base64 int16 PCM>"}
    - {"type":"finish","sample_rate":24000,"chunk_count":N,"audio_url":"...","duration":...}
    - {"type":"error","message":"..."}
    """
    import base64
    import numpy as np
    from fastapi.responses import StreamingResponse

    from repositories import get_chapter_sentences, get_audio_cache, save_audio_cache
    from services.media_manager import get_media_manager
    from core.global_manager import global_manager
    from core.model_manager import ensure_cosyvoice_loaded
    from infrastructure.param_resolver import get_effective_params

    try:
        body = await request.json()
    except Exception:
        body = {}

    agent_id = body.get("agent_id", "")
    seed = int(body.get("seed", 0))
    instruction = body.get("instruction", "")
    speed = float(body.get("speed", 1.0))

    if not agent_id:
        raise HTTPException(status_code=400, detail="缺少agent_id")

    # 获取句子内容
    sentences = get_chapter_sentences(book_id, chapter_index)
    if not sentences or sentence_index >= len(sentences):
        raise HTTPException(status_code=404, detail="句子不存在")

    sentence = sentences[sentence_index]
    text = sentence["content"]

    if not text.strip():
        raise HTTPException(status_code=400, detail="句子内容为空")

    # 检查缓存
    cached = get_audio_cache(text, agent_id, seed, instruction, speed)
    if cached and cached.get("audio_path"):
        audio_url = f"/api/media/file/content?path={cached['audio_path']}"
        return {
            "success": True,
            "type": "cached",
            "sentence_index": sentence_index,
            "audio_url": audio_url,
            "duration": cached.get("duration", 0),
            "from_cache": True,
        }

    # 无缓存，需要生成
    if global_manager.is_model_busy():
        raise HTTPException(status_code=400, detail="系统繁忙，请稍后再试")

    if not global_manager.try_acquire_model("cosyvoice"):
        raise HTTPException(status_code=400, detail="系统繁忙，请稍后再试")

    try:
        if not await asyncio.to_thread(ensure_cosyvoice_loaded):
            global_manager.release_model()
            raise HTTPException(status_code=500, detail="CosyVoice模型加载失败")

        from core.model_executor import model_executor

        add_log(
            f"[朗读] 合成句子语音: sentence_index={sentence_index}, agent={agent_id}, "
            f"seed={seed}, text='{text[:30]}...'"
        )

        try:
            wav_data, sample_rate = await model_executor.execute_text_to_speech_wav(
                text, capability_id=None, agent_id=agent_id,
                tone="", instruction=instruction, seed=seed
            )
        except ValueError as e:
            global_manager.release_model()
            raise HTTPException(status_code=500, detail=str(e))

        duration = len(wav_data) / 2 / sample_rate

        media_mgr = get_media_manager()
        import time as _time
        filename = f"read_{book_id}_{chapter_index}_{sentence_index}_{int(_time.time())}.wav"
        saved_path = media_mgr.save_file(
            "tts", filename, wav_data, "audio"
        )

        file_size = len(wav_data)
        save_audio_cache(
            text, agent_id, seed, instruction, 1.0,
            saved_path, duration, file_size,
        )

        audio_url = f"/api/media/file/content?path={saved_path}"

        add_log(f"[朗读] 句子合成完成，时长 {duration:.2f}s")

        global_manager.release_model()

        return {
            "success": True,
            "type": "generated",
            "sentence_index": sentence_index,
            "audio_url": audio_url,
            "duration": duration,
            "from_cache": False,
        }

    except HTTPException:
        global_manager.release_model()
        raise
    except Exception as e:
        global_manager.release_model()
        raise HTTPException(status_code=500, detail=str(e))
