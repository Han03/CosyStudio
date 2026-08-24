import os
import asyncio

from fastapi import APIRouter, Request

from fastapi import  UploadFile, File, Form
from core import model_manager
from core.global_manager import global_manager

router = APIRouter(prefix="/api/models", tags=["模型管理"])


@router.post("/load-async")
async def load_models_async(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        return {"success": False, "error": f"请求体解析失败: {str(e)}"}

    cosyvoice_path = data.get("cosyvoice_model_path")
    qwen_path = data.get("qwen_model_path")
    dreamlite_path = data.get("dreamlite_model_path")
    qwen_embedding_path = data.get("qwen_embedding_model_path")

    tasks = []

    if dreamlite_path:
        if not os.path.exists(dreamlite_path):
            return {"success": False, "error": f"DreamLite模型路径不存在: {dreamlite_path}"}
        if global_manager.model_loading_status["dreamlite"]["status"] == "loading":
            return {"success": False, "error": "DreamLite模型正在加载中"}
        tasks.append(model_manager.async_load_dreamlite_model(dreamlite_path, force=True))

    if cosyvoice_path:
        if not os.path.exists(cosyvoice_path):
            return {"success": False, "error": f"CosyVoice模型路径不存在: {cosyvoice_path}"}
        if global_manager.model_loading_status["cosyvoice"]["status"] == "loading":
            return {"success": False, "error": "CosyVoice模型正在加载中"}
        tasks.append(model_manager.async_load_cosyvoice_model(cosyvoice_path, force=True))

    if qwen_path:
        if not os.path.exists(qwen_path):
            return {"success": False, "error": f"Qwen模型路径不存在: {qwen_path}"}
        if global_manager.model_loading_status["qwen"]["status"] == "loading":
            return {"success": False, "error": "Qwen模型正在加载中"}
        tasks.append(model_manager.async_load_qwen_model(qwen_path, force=True))

    if qwen_embedding_path:
        if not os.path.exists(qwen_embedding_path):
            return {"success": False, "error": f"Qwen3-Embedding模型路径不存在: {qwen_embedding_path}"}
        if global_manager.model_loading_status["qwen_embedding"]["status"] == "loading":
            return {"success": False, "error": "Qwen3-Embedding模型正在加载中"}
        tasks.append(model_manager.async_load_qwen_embedding_model(qwen_embedding_path, force=True))

    if tasks:
        for task in tasks:
            asyncio.create_task(task)
        return {"success": True, "message": "模型加载任务已启动"}

    return {"success": False, "error": "未指定要加载的模型"}


@router.get("/list")
async def list_models(category: str = None):
    models = model_manager.get_models(category)
    return {"models": models}


@router.get("/categories")
async def list_model_categories():
    categories = []
    for key in model_manager.get_loadable_categories():
        meta = model_manager.get_category(key) 
        if not meta:
            continue
        categories.append({
            "key": key,
            "name": meta.get("name", key),
            "description": meta.get("description", ""),
            "conversational": meta.get("conversational", False),
            "params_config_key": meta.get("params_config_key"),
            "loading_status_key": meta.get("loading_status_key"),
            "loaded_flag": meta.get("loaded_flag"),
        })
    return {"categories": categories}


@router.get("/loading-status")
async def get_loading_status():
    return global_manager.model_loading_status

@router.get("/detail")
async def get_model_detail(path: str):
    for cat_key in model_manager.MODEL_CATEGORIES.keys():
        cat_dir = os.path.join(model_manager.MODELS_DIR, cat_key)
        if path.startswith(cat_dir):
            model_info = model_manager._get_model_info(cat_key, os.path.basename(path), path)
            if model_info:
                return model_info
    
    return {"error": "模型不存在"}

@router.post("/download")
async def download_model(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        return {"success": False, "error": f"请求体解析失败：{e}"}
    
    model_name = data.get("model_name")
    category = data.get("category", "cosyvoice")
    source = data.get("source", "modelscope")
    
    if not model_name:
        return {"success": False, "error": "缺少model_name参数"}
    
    if category not in model_manager.MODEL_CATEGORIES:
        return {"success": False, "error": f"不支持的模型分类: {category}"}
    
    if source not in ["modelscope", "huggingface"]:
        return {"success": False, "error": f"不支持的下载源: {source}"}
    
    return model_manager.start_download(model_name, category, source)

@router.get("/download-status")
async def download_status():
    return model_manager.get_download_status()

@router.post("/download/cancel")
async def cancel_download():
    return model_manager.cancel_download()

@router.get("/recommended")
async def get_recommended_models(category: str = None):
    models = model_manager.get_recommended_models(category)
    return {"models": models}

@router.post("/import")
async def import_model(
    category: str = Form(...),
    name: str = Form(""),
    description: str = Form(""),
    source_path: str = Form(""),
    file: UploadFile = File(None)
):
    if file:
        import shutil
        temp_dir = os.path.join(model_manager.MODELS_DIR, "temp_import")
        os.makedirs(temp_dir, exist_ok=True)
        
        target_name = name if name else file.filename
        target_path = os.path.join(temp_dir, target_name)
        
        with open(target_path, 'wb') as f:
            shutil.copyfileobj(file.file, f)
        
        return model_manager.import_model(target_path, category, name, description)
    elif source_path:
        return model_manager.import_model(source_path, category, name, description)
    else:
        return {"success": False, "error": "请提供源路径或上传文件"}

@router.delete("/delete")
async def delete_model(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        return {"success": False, "error": f"请求体解析失败：{e}"}
    
    model_path = data.get("path")
    
    if not model_path:
        return {"success": False, "error": "缺少path参数"}
    
    return model_manager.delete_model(model_path)