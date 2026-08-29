import os
import sys
import json
import shutil
import subprocess
import threading
import time
import traceback
from typing import List, Dict, Optional
from utils.common_utils import get_directory_size

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import log_manager

MODEL_CATEGORIES = {
    "cosyvoice": {
        "name": "CosyVoice",
        "description": "语音合成模型",
        "extensions": [".yaml", ".pt", ".onnx"],
        "loadable": True,
        "conversational": True,
        "config_key": "cosyvoice",
        "params_config_key": "cosyvoice_config",
        "param_resolver_key": "cosyvoice",
        "loaded_flag": "cosyvoice_loaded",
        "loading_status_key": "cosyvoice",
        "model_attr": "cosyvoice_model",
        "reset_method": "reset_cosyvoice",
        "module": "models.cosyvoice_model",
        "class_name": "CosyVoiceModel",
    },
    "qwen": {
        "name": "Qwen",
        "description": "大语言模型",
        "extensions": [".bin", ".safetensors", ".json"],
        "loadable": True,
        "conversational": True,
        "config_key": "qwen",
        "params_config_key": "qwen_generate",
        "param_resolver_key": "qwen",
        "loaded_flag": "qwen_loaded",
        "loading_status_key": "qwen",
        "model_attr": "qwen_model",
        "reset_method": "reset_qwen",
        "module": "models.qwen_model",
        "class_name": "QwenModel",
    },
    "dreamlite": {
        "name": "DreamLite",
        "description": "图像生成模型",
        "extensions": [".bin", ".safetensors", ".json"],
        "loadable": True,
        "conversational": False,
        "config_key": "dreamlite",
        "params_config_key": "dreamlite_config",
        "param_resolver_key": "dreamlite",
        "loaded_flag": "dreamlite_loaded",
        "loading_status_key": "dreamlite",
        "model_attr": "dreamlite_model",
        "reset_method": "reset_dreamlite",
        "module": "models.dreamlite_model",
        "class_name": "DreamLiteModel",
    },
    "qwen_embedding": {
        "name": "Qwen3-Embedding",
        "description": "文本嵌入模型",
        "extensions": [".bin", ".safetensors", ".json"],
        "loadable": True,
        "conversational": False,
        "config_key": "qwen_embedding",
        "params_config_key": "qwen_embedding_config",
        "param_resolver_key": "qwen_embedding",
        "loaded_flag": "qwen_embedding_loaded",
        "loading_status_key": "qwen_embedding",
        "model_attr": "qwen_embedding_model",
        "reset_method": "reset_qwen_embedding",
        "module": "models.qwen_embedding_model",
        "class_name": "QwenEmbeddingModel",
    },
    "qwen_reranker": {
        "name": "Qwen3-Reranker",
        "description": "片段重排序模型",
        "extensions": [".bin", ".safetensors", ".json"],
        "loadable": True,
        "conversational": False,
        "config_key": "qwen_reranker",
        "params_config_key": "qwen_reranker_config",
        "param_resolver_key": "qwen_reranker",
        "loaded_flag": "qwen_reranker_loaded",
        "loading_status_key": "qwen_reranker",
        "model_attr": "qwen_reranker_model",
        "reset_method": "reset_qwen_reranker",
        "module": "models.qwen_reranker_model",
        "class_name": "QwenRerankerModel",
    },
    "other": {
        "name": "其他",
        "description": "其他模型",
        "extensions": [],
        "loadable": False,
        "conversational": False,
    },
}


def get_loadable_categories():
    """返回所有可加载的模型分类（loadable=True）"""
    return {k: v for k, v in MODEL_CATEGORIES.items() if v.get("loadable", False)}


def get_conversational_categories():
    """返回所有参与会话流程的模型分类（conversational=True）"""
    return {k: v for k, v in MODEL_CATEGORIES.items() if v.get("conversational", False)}


def get_category(key):
    """获取指定分类的元数据"""
    return MODEL_CATEGORIES.get(key)


RECOMMENDED_MODELS = {
    "cosyvoice": [
        {"name": "CosyVoice2-0.5B", "model_id": "iic/CosyVoice2-0.5B", "description": "轻量级语音合成模型，适合低资源环境"},
        {"name": "Fun-CosyVoice3-0.5B-2512", "model_id": "FunAudioLLM/Fun-CosyVoice3-0.5B-2512", "description": "最新版语音合成模型，支持多风格"},
    ],
    "qwen": [
        {"name": "Qwen3.5-4B", "model_id": "Qwen/Qwen3.5-4B", "description": "通义千问 4B 开源原生多模态大模型，低显存本地部署，适配文本图文长文生成与轻量 RAG"},
    ],
    "dreamlite": [
        {"name": "DreamLite-Mobile", "model_id": "carlofkl/DreamLite-mobile", "description": "轻量级图像生成模型"},
    ],
    "qwen_embedding": [
        {"name": "Qwen3-Embedding-0.6B", "model_id": "Qwen/Qwen3-Embedding-0.6B", "description": "通义千问轻量文本嵌入模型，低显存高速度，适配边缘与轻量 RAG 语义检索。"},
        {"name": "Qwen3-Embedding-8B", "model_id": "Qwen/Qwen3-Embedding-8B", "description": "通义千问 8B 高性能文本嵌入模型，用于长文档、多语言语义检索与向量知识库构建。"},
    ],
    "qwen_reranker": [
        {"name": "Qwen3-Reranker-0.6B", "model_id": "Qwen/Qwen3-Reranker-0.6B", "description": "通义千问轻量片段重排序模型，低显存高速度，适配边缘与轻量 RAG 检索结果精排。"},
        {"name": "Qwen3-Reranker-4B", "model_id": "Qwen/Qwen3-Reranker-4B", "description": "通义千问 4B 高性能片段重排序模型，用于长文档、多语言检索结果精排。"},
    ],
}

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELS_DIR = os.path.join(PROJECT_ROOT, "pretrained_models")
DOWNLOAD_STATUS_FILE = os.path.join(MODELS_DIR, "download_status.json")
MODEL_INDEX_FILE = os.path.join(MODELS_DIR, "model_index.json")

os.makedirs(MODELS_DIR, exist_ok=True)

_download_process = None
_download_lock = threading.Lock()

def _ensure_index_file():
    if not os.path.exists(MODEL_INDEX_FILE):
        with open(MODEL_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump({"pretrained_models": []}, f)

def _load_index():
    _ensure_index_file()
    try:
        with open(MODEL_INDEX_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"pretrained_models": []}

def _save_index(index):
    with open(MODEL_INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

def update_download_status(data):
    data["timestamp"] = time.time()
    _persist_data = {}
    if os.path.exists(DOWNLOAD_STATUS_FILE):
        try:
            with open(DOWNLOAD_STATUS_FILE, 'r', encoding='utf-8') as f:
                _persist_data = json.load(f)
        except Exception as e:
            _model_logger.error("读取状态文件失败: %s, file = %s", e, DOWNLOAD_STATUS_FILE)
            _persist_data = {}
    _persist_data.update(data)
    with open(DOWNLOAD_STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(_persist_data, f, indent=2, ensure_ascii=False)

def _load_download_status():
    if not os.path.exists(DOWNLOAD_STATUS_FILE):
        return {}
    try:
        with open(DOWNLOAD_STATUS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        _model_logger.error("读取状态文件失败: %s, file = %s", e, DOWNLOAD_STATUS_FILE)
        return {}

def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def _clean_temp_files(save_dir):
    if not os.path.exists(save_dir):
        return
    for item in os.listdir(save_dir):
        item_path = os.path.join(save_dir, item)
        if os.path.isdir(item_path) and item.startswith("."):
            try:
                shutil.rmtree(item_path, ignore_errors=True)
                _model_logger.info("[下载管理] 清理临时目录: %s", item_path)
            except Exception as e:
                _model_logger.warning("[下载管理] 清理临时目录失败: %s, 错误: %s", item_path, e)

def _get_model_info(category: str, name: str, path: str) -> Optional[Dict]:
    size = get_directory_size(path)
    model_files = []
    
    for root, dirs, files in os.walk(path):
        for f in files[:20]:
            ext = os.path.splitext(f)[1].lower()
            model_files.append({
                "name": f,
                "size": _format_size(os.path.getsize(os.path.join(root, f))),
                "extension": ext
            })
        break
    
    index = _load_index()
    indexed_model = next((m for m in index.get("models", []) if m.get("path") == path), None)

    model_status = "ready"
 
    return {
        "name": name,
        "category": category,
        "category_name": MODEL_CATEGORIES[category]["name"],
        "path": path,
        "status": model_status,
        "download_progress": 100,
        "size": _format_size(size),
        "size_bytes": size,
        "files": model_files,
        "file_count": sum([len(files) for _, _, files in os.walk(path)]),
        "imported": indexed_model is not None,
        "import_time": indexed_model.get("import_time") if indexed_model else None,
        "description": indexed_model.get("description") if indexed_model else ""
    }

def get_models(category: str = None) -> List[Dict]:
    models = []

    for cat_key, cat_info in MODEL_CATEGORIES.items():
        if category and cat_key != category:
            continue

        cat_dir = os.path.join(MODELS_DIR, cat_key)
        if not os.path.exists(cat_dir):
            continue

        for item in os.listdir(cat_dir):
            item_path = os.path.join(cat_dir, item)
            if os.path.isdir(item_path):
                model_info = _get_model_info(cat_key, item, item_path)
                if model_info:
                    models.append(model_info)

    downloading_model = {}
    downloading_model = _load_download_status()
    downloading_model_path = downloading_model.get("path", "")
    for model in models:
        if downloading_model_path != '' and downloading_model_path == model["path"]:
            model["status"] = downloading_model.get("status", "ready")
            model["download_progress"] = downloading_model.get("progress", 0)
            model["name"] = downloading_model.get("model_name", "")
        else:
            model["status"] = "ready"
    return models

def _add_to_index(name: str, path: str, category: str, description: str = ""):
    index = _load_index()
    existing = next((m for m in index.get("models", []) if m.get("path") == path), None)
    
    if existing:
        existing["name"] = name
        existing["description"] = description
        existing["update_time"] = time.time()
    else:
        index["models"].append({
            "name": name,
            "path": path,
            "category": category,
            "description": description,
            "import_time": time.time()
        })
    
    _save_index(index)

def _download_watcher(proc: subprocess.Popen, model_name: str, save_dir: str, category: str):
    """监控下载子进程退出，根据最终状态收尾（入索引/清理临时文件）。"""
    try:
        proc.wait()
        status = _load_download_status()
        final_status = status.get("status")
        if final_status == "ready":
            _add_to_index(model_name, save_dir, category)
            _model_logger.info("[下载管理] 下载完成，已写入模型索引")
        elif final_status == "canceled":
            _clean_temp_files(save_dir)
            _model_logger.info("[下载管理] 下载已取消，临时文件已清理")
        elif final_status == "error":
            _model_logger.error("[下载管理] 下载失败: %s", status.get("error", ""))
        else:
            # 子进程异常退出且未写入终态，补写错误状态避免前端卡在下载中
            update_download_status({
                "status": "error",
                "message": "下载进程异常退出",
                "error": "下载进程异常退出",
            })
            _model_logger.error("[下载管理] 下载进程异常退出，returncode=%s", proc.returncode)
    except Exception as e:
        _model_logger.error("[下载管理] 下载监控异常: %s", e)

def start_download(model_name: str, category: str, source: str = "modelscope") -> Dict:
    global _download_process

    with _download_lock:
        if _download_process and _download_process.poll() is None:
            return {"success": False, "error": "已有下载任务正在进行"}

        cat_dir = os.path.join(MODELS_DIR, category)
        os.makedirs(cat_dir, exist_ok=True)

        model_name_clean = model_name.replace('/', '_').replace('\\', '_')
        save_dir = os.path.join(cat_dir, model_name_clean)

        status = {
            "status": "downloading", 
            "progress": 0, 
            "message": "准备下载...", 
            "model_name": model_name, 
            "category": category,
            "path": save_dir,
            "source": source
        }
        update_download_status(status)

        # 以独立子进程执行下载，取消时可直接终止进程，立即中断 snapshot_download
        script_path = os.path.join(PROJECT_ROOT, "backend", "utils", "download_model.py")
        cmd = [sys.executable, script_path, model_name, save_dir, DOWNLOAD_STATUS_FILE, source]
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW
        try:
            _download_process = subprocess.Popen(cmd, creationflags=creationflags)
        except Exception as e:
            _model_logger.error("[下载管理] 启动下载子进程失败: %s", e)
            update_download_status({
                "status": "error",
                "message": f"启动下载失败: {e}",
                "error": str(e),
            })
            return {"success": False, "error": f"启动下载失败: {e}"}

        watcher = threading.Thread(
            target=_download_watcher,
            args=(_download_process, model_name, save_dir, category),
            daemon=True
        )
        watcher.start()

        return {"success": True, "message": "下载任务已启动"}

def get_download_status() -> Dict:
    return _load_download_status()

def import_model(source_path: str, category: str, name: str = "", description: str = "") -> Dict:
    if not os.path.exists(source_path):
        return {"success": False, "error": "源路径不存在"}
    
    cat_dir = os.path.join(MODELS_DIR, category)
    os.makedirs(cat_dir, exist_ok=True)
    
    if os.path.isdir(source_path):
        target_name = name if name else os.path.basename(source_path)
        target_path = os.path.join(cat_dir, target_name)
        
        if os.path.exists(target_path):
            return {"success": False, "error": f"目标路径已存在: {target_path}"}
        
        shutil.copytree(source_path, target_path)
        _add_to_index(target_name, target_path, category, description)
        
        return {"success": True, "message": "模型导入成功", "path": target_path}
    else:
        target_name = name if name else os.path.basename(source_path)
        target_path = os.path.join(cat_dir, target_name)
        
        if os.path.exists(target_path):
            return {"success": False, "error": f"目标文件已存在: {target_path}"}
        
        shutil.copy2(source_path, target_path)
        _add_to_index(target_name, target_path, category, description)
        
        return {"success": True, "message": "模型文件导入成功", "path": target_path}

def get_recommended_models(category: str = None) -> List[Dict]:
    if category and category in RECOMMENDED_MODELS:
        return RECOMMENDED_MODELS[category]
    return [model for models in RECOMMENDED_MODELS.values() for model in models]

def cancel_download() -> Dict:
    global _download_process

    with _download_lock:
        proc = _download_process
        if proc and proc.poll() is None:
            # 直接终止下载子进程，立即中断下载，不阻塞当前请求
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception as e:
                    _model_logger.error("[下载管理] 终止下载子进程失败: %s", e)
        _download_process = None

        download_status = get_download_status()
        save_dir = download_status.get("path", "")

        saved_bytes = 0
        if save_dir and os.path.exists(save_dir):
            saved_bytes = get_directory_size(save_dir)

        status = {
            "status": "canceled",
            "progress": download_status.get("progress", 0),
            "message": "下载已取消",
        }
        update_download_status(status)

        return {"success": True, "message": "下载已取消", "saved_bytes": saved_bytes}

def delete_model(model_path: str) -> Dict:
    if not os.path.exists(model_path):
        return {"success": False, "error": "模型路径不存在"}
    
    if not model_path.startswith(MODELS_DIR):
        return {"success": False, "error": "无权删除此路径"}
    
    download_status = _load_download_status()
    if download_status.get("status") == "downloading" and download_status.get("path") == model_path:
        return {"success": False, "error": "该模型正在下载中，请先取消下载"}
    
    try:
        if os.path.isdir(model_path):
            shutil.rmtree(model_path)
        else:
            os.remove(model_path)
        
        index = _load_index()
        index["models"] = [m for m in index.get("models", []) if m.get("path") != model_path]
        _save_index(index)
        
        return {"success": True, "message": "模型删除成功"}
    except Exception as e:
        return {"success": False, "error": f"删除失败: {str(e)}"}


_model_logger = log_manager.get_logger("model")


def add_log(message: str, level: str = "INFO"):
    try:
        if level == "INFO":
            _model_logger.info(message)
        elif level == "WARNING":
            _model_logger.warning(message)
        elif level == "ERROR":
            _model_logger.error(message)
        else:
            _model_logger.info(message)
    except:
        pass
    print(f"[LOG][{level}] {message}")


def find_cosyvoice_model() -> str:
    try:
        from core.config_manager import get_cosyvoice_config
        config = get_cosyvoice_config()
        if config.get("model_path") and os.path.exists(config["model_path"]):
            return config["model_path"]
    except:
        pass

    default_path = os.path.join(MODELS_DIR, "CosyVoice", "CosyVoice2-0.5B")
    if os.path.exists(default_path):
        return default_path

    return None


def find_qwen_model() -> str:
    try:
        from core.config_manager import get_qwen_config
        config = get_qwen_config()
        if config.get("model_path") and os.path.exists(config["model_path"]):
            return config["model_path"]
    except:
        pass

    default_path = os.path.join(MODELS_DIR, "Qwen", "Qwen3-0___6B")
    if os.path.exists(default_path):
        return default_path

    return None


def find_dreamlite_model():
    from core.config_manager import get_dreamlite_model_config
    dreamlite_config = get_dreamlite_model_config()
    model_path = dreamlite_config.get("model_path", "")
    if model_path and os.path.exists(model_path):
        return model_path

    for model in get_models("dreamlite"):
        path = model.get("path")
        if path and os.path.exists(path):
            return path

    return None


def load_cosyvoice_model(model_path, force=False):
    from core.global_manager import global_manager

    cosyvoice_model = global_manager.cosyvoice_model
    cosyvoice_model_lock = global_manager.cosyvoice_model_lock
    model_loading_status = global_manager.model_loading_status
    system_status = global_manager.system_status

    with cosyvoice_model_lock:
        cosyvoice_model = global_manager.cosyvoice_model
        if not force and cosyvoice_model is not None and cosyvoice_model.is_loaded():
            add_log(f"CosyVoice模型已加载，跳过加载（force={force}）")
            return

        add_log(f"正在加载CosyVoice模型: {model_path}")
        system_status["current_operation"] = "加载CosyVoice模型"

        from models.cosyvoice_model import CosyVoiceModel
        cosyvoice_model = CosyVoiceModel(model_path)
        global_manager.cosyvoice_model = cosyvoice_model

        add_log("正在初始化CosyVoice前端和模型...")
        system_status["current_operation"] = "初始化CosyVoice前端..."

        if cosyvoice_model.initialize():
            global_manager.set_cosyvoice_loaded(True)
            system_status["cosyvoice_loaded"] = True
            global_manager.set_cosyvoice_loaded(True)
            add_log("CosyVoice模型加载成功")
        else:
            add_log("CosyVoice前端初始化失败", "ERROR")
            model_loading_status["cosyvoice"]["status"] = "error"
            model_loading_status["cosyvoice"]["message"] = "CosyVoice前端初始化失败"

        system_status["current_operation"] = "空闲"


def load_qwen_model(model_path, force=False):
    from core.global_manager import global_manager

    qwen_model = global_manager.qwen_model
    qwen_model_lock = global_manager.qwen_model_lock
    model_loading_status = global_manager.model_loading_status
    system_status = global_manager.system_status

    with qwen_model_lock:
        qwen_model = global_manager.qwen_model
        if not force and qwen_model is not None and qwen_model.is_loaded():
            add_log(f"Qwen模型已加载，跳过加载（force={force}）")
            return

        add_log(f"正在加载Qwen模型: {model_path}")
        system_status["current_operation"] = "加载Qwen模型"

        from models.qwen_model import QwenModel
        qwen_model = QwenModel(model_path)
        global_manager.qwen_model = qwen_model

        if qwen_model.is_loaded():
            global_manager.set_qwen_loaded(True)
            system_status["qwen_loaded"] = True
            global_manager.set_qwen_loaded(True)
            add_log("Qwen模型加载成功")
        else:
            add_log("Qwen模型加载失败", "ERROR")
            model_loading_status["qwen"]["status"] = "error"
            model_loading_status["qwen"]["message"] = "Qwen模型加载失败"

        system_status["current_operation"] = "空闲"


def load_dreamlite_model(model_path, force=False):
    from core.global_manager import global_manager

    dreamlite_model = global_manager.dreamlite_model
    dreamlite_model_lock = global_manager.dreamlite_model_lock
    model_loading_status = global_manager.model_loading_status
    system_status = global_manager.system_status

    with dreamlite_model_lock:
        dreamlite_model = global_manager.dreamlite_model
        if not force and dreamlite_model is not None and dreamlite_model.is_loaded():
            add_log(f"DreamLite模型已加载，跳过加载（force={force}）")
            return

        add_log(f"正在加载DreamLite模型: {model_path}")
        system_status["current_operation"] = "加载DreamLite模型"

        try:
            from models.dreamlite_model import DreamLiteModel
            dreamlite_model = DreamLiteModel(model_path)
            global_manager.dreamlite_model = dreamlite_model

            if dreamlite_model.is_loaded():
                system_status["dreamlite_loaded"] = True
                global_manager.set_dreamlite_loaded(True)
                add_log("DreamLite模型加载成功")
            else:
                add_log("DreamLite模型加载失败", "ERROR")
                model_loading_status["dreamlite"]["status"] = "error"
                model_loading_status["dreamlite"]["message"] = "DreamLite模型加载失败"
        except Exception as e:
            add_log(f"DreamLite模型加载异常: {e}", "ERROR")
            model_loading_status["dreamlite"]["status"] = "error"
            model_loading_status["dreamlite"]["message"] = f"DreamLite模型加载异常: {e}"
            import traceback
            traceback.print_exc()

        system_status["current_operation"] = "空闲"


def ensure_cosyvoice_loaded() -> bool:
    """确保 CosyVoice 模型已加载。

    注意: 不能在此处获取 cosyvoice_model_lock,因为 load_cosyvoice_model 内部
    会再次获取同一把锁,而 threading.Lock 不是可重入锁,会导致死锁。
    load_*_model 内部已有锁保护和双重检查,此处无需加锁。
    """
    from core.global_manager import global_manager

    if global_manager.cosyvoice_model is not None and global_manager.cosyvoice_model.is_loaded():
        return True

    model_path = find_cosyvoice_model()
    if model_path is None:
        add_log("未找到可用的CosyVoice模型", "ERROR")
        return False

    load_cosyvoice_model(model_path)
    return global_manager.cosyvoice_model is not None and global_manager.cosyvoice_model.is_loaded()


def ensure_qwen_loaded() -> bool:
    """确保 Qwen 模型已加载。

    注意: 不能在此处获取 qwen_model_lock,因为 load_qwen_model 内部
    会再次获取同一把锁,而 threading.Lock 不是可重入锁,会导致死锁。
    load_*_model 内部已有锁保护和双重检查,此处无需加锁。
    """
    from core.global_manager import global_manager

    if global_manager.qwen_model is not None and global_manager.qwen_model.is_loaded():
        return True

    model_path = find_qwen_model()
    if model_path is None:
        add_log("未找到可用的Qwen模型", "ERROR")
        return False

    load_qwen_model(model_path)
    return global_manager.qwen_model is not None and global_manager.qwen_model.is_loaded()


def ensure_dreamlite_loaded() -> bool:
    """确保 DreamLite 模型已加载。

    注意: 不能在此处获取 dreamlite_model_lock,因为 load_dreamlite_model 内部
    会再次获取同一把锁,而 threading.Lock 不是可重入锁,会导致死锁。
    load_*_model 内部已有锁保护和双重检查,此处无需加锁。
    """
    from core.global_manager import global_manager

    if global_manager.dreamlite_model is not None and global_manager.dreamlite_model.is_loaded():
        return True

    model_path = find_dreamlite_model()
    if model_path is None:
        add_log("未找到可用的DreamLite模型", "ERROR")
        return False

    load_dreamlite_model(model_path)
    return global_manager.dreamlite_model is not None and global_manager.dreamlite_model.is_loaded()


async def async_load_cosyvoice_model(model_path, force=False):
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: load_cosyvoice_model(model_path, force))


async def async_load_qwen_model(model_path, force=False):
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: load_qwen_model(model_path, force))


async def async_load_dreamlite_model(model_path, force=False):
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: load_dreamlite_model(model_path, force))


def load_qwen_embedding_model(model_path, force=False):
    from core.global_manager import global_manager

    qwen_embedding_model = global_manager.qwen_embedding_model
    qwen_embedding_model_lock = global_manager.qwen_embedding_model_lock
    model_loading_status = global_manager.model_loading_status
    system_status = global_manager.system_status

    with qwen_embedding_model_lock:
        qwen_embedding_model = global_manager.qwen_embedding_model
        if not force and qwen_embedding_model is not None and qwen_embedding_model.is_loaded():
            add_log(f"Qwen3-Embedding模型已加载，跳过加载（force={force}）")
            return

        add_log(f"正在加载Qwen3-Embedding模型: {model_path}")
        system_status["current_operation"] = "加载Qwen3-Embedding模型"

        from models.qwen_embedding_model import QwenEmbeddingModel
        qwen_embedding_model = QwenEmbeddingModel(model_path)
        global_manager.qwen_embedding_model = qwen_embedding_model

        if qwen_embedding_model.is_loaded():
            global_manager.set_qwen_embedding_loaded(True)
            system_status["qwen_embedding_loaded"] = True
            add_log("Qwen3-Embedding模型加载成功")
        else:
            add_log("Qwen3-Embedding模型加载失败", "ERROR")
            model_loading_status["qwen_embedding"]["status"] = "error"
            model_loading_status["qwen_embedding"]["message"] = "Qwen3-Embedding模型加载失败"

        system_status["current_operation"] = "空闲"


def find_qwen_embedding_model():
    from core.config_manager import get_config
    config = get_config()
    model_path = config.get("models", {}).get("qwen_embedding", {}).get("model_path", "")
    if model_path and os.path.exists(model_path):
        return model_path
    return None


def ensure_qwen_embedding_loaded() -> bool:
    from core.global_manager import global_manager

    if global_manager.qwen_embedding_model is not None and global_manager.qwen_embedding_model.is_loaded():
        return True

    model_path = find_qwen_embedding_model()
    if model_path is None:
        add_log("未找到可用的Qwen3-Embedding模型", "ERROR")
        return False

    load_qwen_embedding_model(model_path)
    return global_manager.qwen_embedding_model is not None and global_manager.qwen_embedding_model.is_loaded()


async def async_load_qwen_embedding_model(model_path, force=False):
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: load_qwen_embedding_model(model_path, force))


def load_qwen_reranker_model(model_path, force=False):
    from core.global_manager import global_manager

    qwen_reranker_model = global_manager.qwen_reranker_model
    qwen_reranker_model_lock = global_manager.qwen_reranker_model_lock
    model_loading_status = global_manager.model_loading_status
    system_status = global_manager.system_status

    with qwen_reranker_model_lock:
        qwen_reranker_model = global_manager.qwen_reranker_model
        if not force and qwen_reranker_model is not None and qwen_reranker_model.is_loaded():
            add_log(f"Qwen3-Reranker模型已加载，跳过加载（force={force}）")
            return

        add_log(f"正在加载Qwen3-Reranker模型: {model_path}")
        system_status["current_operation"] = "加载Qwen3-Reranker模型"

        from models.qwen_reranker_model import QwenRerankerModel
        qwen_reranker_model = QwenRerankerModel(model_path)
        global_manager.qwen_reranker_model = qwen_reranker_model

        if qwen_reranker_model.is_loaded():
            global_manager.set_qwen_reranker_loaded(True)
            system_status["qwen_reranker_loaded"] = True
            add_log("Qwen3-Reranker模型加载成功")
        else:
            add_log("Qwen3-Reranker模型加载失败", "ERROR")
            model_loading_status["qwen_reranker"]["status"] = "error"
            model_loading_status["qwen_reranker"]["message"] = "Qwen3-Reranker模型加载失败"

        system_status["current_operation"] = "空闲"


def find_qwen_reranker_model():
    from core.config_manager import get_config
    config = get_config()
    model_path = config.get("models", {}).get("qwen_reranker", {}).get("model_path", "")
    if model_path and os.path.exists(model_path):
        return model_path
    return None


def ensure_qwen_reranker_loaded() -> bool:
    from core.global_manager import global_manager

    if global_manager.qwen_reranker_model is not None and global_manager.qwen_reranker_model.is_loaded():
        return True

    model_path = find_qwen_reranker_model()
    if model_path is None:
        add_log("未找到可用的Qwen3-Reranker模型", "ERROR")
        return False

    load_qwen_reranker_model(model_path)
    return global_manager.qwen_reranker_model is not None and global_manager.qwen_reranker_model.is_loaded()


async def async_load_qwen_reranker_model(model_path, force=False):
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: load_qwen_reranker_model(model_path, force))


def reset_all_models():
    from core.global_manager import global_manager

    global_manager.cosyvoice_model = None
    global_manager.qwen_model = None
    global_manager.dreamlite_model = None
    global_manager.qwen_embedding_model = None
    global_manager.qwen_reranker_model = None

    global_manager.set_cosyvoice_loaded(False)
    global_manager.set_qwen_loaded(False)
    global_manager.set_dreamlite_loaded(False)
    global_manager.set_qwen_embedding_loaded(False)
    global_manager.set_qwen_reranker_loaded(False)

    system_status = global_manager.system_status

    system_status["current_operation"] = "空闲"

    try:
        import sys
        main_module = sys.modules.get("__main__")
        if main_module is None:
            main_module = sys.modules.get("main")
        if main_module is None:
            for mod_name in ["main", "backend.main"]:
                if mod_name in sys.modules:
                    main_module = sys.modules[mod_name]
                    break
        if main_module is not None:
            for attr in ["cosyvoice_model", "qwen_model", "dreamlite_model"]:
                if hasattr(main_module, attr):
                    setattr(main_module, attr, None)
    except Exception:
        pass

    try:
        import sys
        if "routers.agents" in sys.modules:
            agents_module = sys.modules["routers.agents"]
            if hasattr(agents_module, "cosyvoice_model"):
                agents_module.cosyvoice_model = None
    except Exception:
        pass

    try:
        import sys
        if "services.audio" in sys.modules:
            audio_module = sys.modules["services.audio"]
            if hasattr(audio_module, "cosyvoice_model"):
                audio_module.cosyvoice_model = None
    except Exception:
        pass

    try:
        import gc
        gc.collect()
    except Exception:
        pass

    add_log("所有模型引用已重置")