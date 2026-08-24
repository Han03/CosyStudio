import os
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, FileResponse

from utils.logger import logger
from services.media_manager import get_media_manager

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


@router.get("/api/media/categories")
async def get_categories():
    try:
        media_manager = get_media_manager()
        categories = media_manager.get_categories()
        return {
            "success": True,
            "categories": categories
        }
    except Exception as e:
        add_log(f"获取分类列表失败: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/media/modules")
async def get_modules(category: str = Query(None, description="分类，不传则返回所有分类的模块")):
    try:
        media_manager = get_media_manager()
        modules = media_manager.get_modules(category=category)
        return {
            "success": True,
            "modules": modules
        }
    except Exception as e:
        add_log(f"获取模块列表失败: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/media/files")
async def list_files(
    category: str = Query(None, description="分类：note/audio/image/video/document"),
    module: str = Query(None, description="模块名，如 bing/tts/chat 等"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    keyword: str = Query(None, description="搜索关键词"),
    sort_by: str = Query("modified_time", description="排序字段：name/size/modified_time"),
    sort_order: str = Query("desc", description="排序方式：asc/desc")
):
    try:
        media_manager = get_media_manager()
        files, total, total_pages = media_manager.list_files(
            category=category,
            module=module,
            page=page,
            page_size=page_size,
            keyword=keyword,
            sort_by=sort_by,
            sort_order=sort_order
        )

        for f in files:
            f.pop("absolute_path", None)

        return {
            "success": True,
            "files": files,
            "total": total,
            "total_pages": total_pages,
            "page": page,
            "page_size": page_size
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        add_log(f"获取文件列表失败: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/media/file/info")
async def get_file_info(path: str = Query(..., description="相对路径，例如 note/活着【作者余华】.txt")):
    try:
        media_manager = get_media_manager()
        file_info = media_manager.get_file_by_path(path)
        
        if not file_info:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        file_info.pop("absolute_path", None)
        
        return {
            "success": True,
            "file": file_info
        }
    except HTTPException:
        raise
    except Exception as e:
        add_log(f"获取文件信息失败: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/media/file/content")
async def get_file_content(path: str = Query(..., description="相对路径，例如 note/活着【作者余华】.txt")):
    try:
        media_manager = get_media_manager()
        file_info = media_manager.get_file_by_path(path)
        
        if not file_info:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        content = media_manager.get_file_content(path)
        if content is None:
            raise HTTPException(status_code=500, detail="读取文件失败")

        ext = file_info["extension"]
        content_type = "application/octet-stream"
        
        if ext == ".txt":
            content_type = "text/plain; charset=utf-8"
        elif ext in [".jpg", ".jpeg"]:
            content_type = "image/jpeg"
        elif ext == ".png":
            content_type = "image/png"
        elif ext == ".gif":
            content_type = "image/gif"
        elif ext == ".bmp":
            content_type = "image/bmp"
        elif ext == ".webp":
            content_type = "image/webp"
        elif ext == ".svg":
            content_type = "image/svg+xml"
        elif ext == ".wav":
            content_type = "audio/wav"
        elif ext == ".mp3":
            content_type = "audio/mpeg"
        elif ext == ".flac":
            content_type = "audio/flac"
        elif ext == ".mp4":
            content_type = "video/mp4"
        elif ext == ".pdf":
            content_type = "application/pdf"
        elif ext == ".md":
            content_type = "text/markdown; charset=utf-8"
        elif ext == ".srt":
            content_type = "application/x-subrip; charset=utf-8"

        return Response(content=content, media_type=content_type)
    except HTTPException:
        raise
    except Exception as e:
        add_log(f"获取文件内容失败: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/media/download")
async def download_file(path: str = Query(..., description="相对路径")):
    try:
        media_manager = get_media_manager()
        file_info = media_manager.get_file_by_path(path)
        
        if not file_info:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        return FileResponse(
            path=file_info["absolute_path"],
            filename=file_info["name"],
            media_type="application/octet-stream"
        )
    except HTTPException:
        raise
    except Exception as e:
        add_log(f"文件下载失败: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=str(e))
