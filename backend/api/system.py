import os
import json
import torch
import asyncio
from fastapi import APIRouter, HTTPException, Request

from utils.logger import log_manager
from core.global_manager import global_manager
from core.config_manager import get_app_name as _get_app_name

router = APIRouter()

resource_monitor = None
_system_logger = log_manager.get_logger("system")
try:
    import importlib.util
    _resource_monitor_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'utils', 'resource_monitor.py')
    _resource_monitor_spec = importlib.util.spec_from_file_location('utils.resource_monitor', _resource_monitor_path)
    _resource_monitor_module = importlib.util.module_from_spec(_resource_monitor_spec)
    _resource_monitor_spec.loader.exec_module(_resource_monitor_module)
    resource_monitor = _resource_monitor_module.resource_monitor
except Exception as e:
    _system_logger.warning(f"资源监控模块加载失败: {e}")

system_status = global_manager.system_status
system_resources = global_manager.system_resources
model_loading_status = global_manager.model_loading_status


def add_log(message: str, level: str = "INFO"):
    try:
        if level == "INFO":
            _system_logger.info(message)
        elif level == "WARNING":
            _system_logger.warning(message)
        elif level == "ERROR":
            _system_logger.error(message)
        else:
            _system_logger.info(message)
    except:
        pass
    print(f"[LOG][{level}] {message}")


def get_version():
    version_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "version.json")
    try:
        with open(version_path, "r", encoding="utf-8") as f:
            return json.load(f).get("version", "1.0.0")
    except:
        return "1.0.0"


def check_gpu_available():
    if torch.cuda.is_available():
        return {"available": True, "device": torch.cuda.get_device_name(0)}
    return {"available": False, "device": "CPU"}


@router.get("/api/status")
async def get_status():
    from core.model_manager import get_loadable_categories

    # 动态生成加载状态字段（如 dreamlite_loaded）
    status = {
        meta["loaded_flag"]: system_status.get(meta["loaded_flag"], False)
        for meta in get_loadable_categories().values()
    }

    # 若后台线程还未完成首次资源更新（2s循环），则直接从 resource_monitor 拉一次真实值
    res = system_resources
    if resource_monitor and (
        (res.get("memory") or {}).get("used") == "0 B"
        or (res.get("cpu") or {}).get("percent") == 0
    ):
        try:
            res = resource_monitor.get_system_resources()
        except Exception:
            pass

    status.update({
        "app_name": _get_app_name(),
        "current_operation": system_status["current_operation"],
        "logs": system_status["logs"][-20:],
        "version": get_version(),
        "resources": res,
        "model_loading_status": model_loading_status
    })
    return status


@router.get("/api/models/loading-status")
async def get_model_loading_status():
    return model_loading_status


@router.get("/api/resources")
async def get_resources():
    if resource_monitor:
        return resource_monitor.get_system_resources()
    return {"error": "资源监控模块未加载"}


@router.get("/api/resources/health")
async def check_health():
    if resource_monitor:
        return resource_monitor.check_resource_health()
    return {"error": "资源监控模块未加载"}


@router.get("/api/resources/history")
async def get_resource_history():
    if resource_monitor:
        return {"history": resource_monitor.get_history()}
    return {"error": "资源监控模块未加载"}


@router.post("/api/resources/check")
async def check_resources_before_action():
    if resource_monitor:
        health_check = resource_monitor.check_resource_health()
        resource_monitor.record_resources()

        if not health_check['healthy']:
            return {
                "can_proceed": False,
                "message": "资源占用过高，建议释放资源后再操作",
                "issues": health_check['issues'],
                "resources": health_check['resources']
            }

        return {
            "can_proceed": True,
            "message": "资源状态正常，可以继续操作",
            "resources": health_check['resources']
        }
    return {"error": "资源监控模块未加载"}


@router.get("/api/settings")
async def get_settings():
    from core.config_manager import get_config

    config = get_config()

    return {
        "config": config,
        "models": config.get("models", {}),
        "gpu_available": check_gpu_available()
    }


@router.get("/api/server-info")
async def get_server_info():
    from core.config_manager import get_server_port
    import socket
    
    try:
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
    except:
        hostname = "localhost"
        ip_address = "127.0.0.1"
    
    return {
        "port": get_server_port(),
        "hostname": hostname,
        "ip_address": ip_address,
        "base_url": f"http://{ip_address}:{get_server_port()}"
    }


class SettingsRequest:
    models: dict = None
    qwen_generate: dict = None
    cosyvoice_config: dict = None
    dreamlite_config: dict = None
    qwen_embedding_config: dict = None
    platform_keys: dict = None
    model_capabilities: dict = None
    call_point_models: dict = None


@router.post("/api/settings")
async def update_settings(request: Request):
    from core.config_manager import set_config, get_config
    from core.model_manager import get_loadable_categories

    try:
        data = await request.json()
        current_config = get_config()

        settings = SettingsRequest()
        settings.models = data.get("models")
        settings.qwen_generate = data.get("qwen_generate")
        settings.cosyvoice_config = data.get("cosyvoice_config")
        settings.dreamlite_config = data.get("dreamlite_config")
        settings.qwen_embedding_config = data.get("qwen_embedding_config")
        settings.platform_keys = data.get("platform_keys")
        settings.model_capabilities = data.get("model_capabilities")
        settings.call_point_models = data.get("call_point_models")

        if settings.models:
            if "models" not in current_config:
                current_config["models"] = {}
            for cat_key in get_loadable_categories().keys():
                if cat_key in settings.models:
                    cat_settings = settings.models[cat_key]
                    if cat_key not in current_config["models"]:
                        current_config["models"][cat_key] = {}
                    if "model_path" in cat_settings:
                        current_config["models"][cat_key]["model_path"] = cat_settings["model_path"]
                    if "model_name" in cat_settings:
                        current_config["models"][cat_key]["model_name"] = cat_settings["model_name"]

        if settings.qwen_generate:
            if "qwen_generate" not in current_config:
                current_config["qwen_generate"] = {}
            current_config["qwen_generate"].update(settings.qwen_generate)

        if settings.cosyvoice_config:
            if "cosyvoice_config" not in current_config:
                current_config["cosyvoice_config"] = {}
            current_config["cosyvoice_config"].update(settings.cosyvoice_config)

        if settings.dreamlite_config:
            if "dreamlite_config" not in current_config:
                current_config["dreamlite_config"] = {}
            current_config["dreamlite_config"].update(settings.dreamlite_config)

        if settings.qwen_embedding_config:
            if "qwen_embedding_config" not in current_config:
                current_config["qwen_embedding_config"] = {}
            current_config["qwen_embedding_config"].update(settings.qwen_embedding_config)

        if settings.platform_keys:
            if "platform_keys" not in current_config:
                current_config["platform_keys"] = {}
            current_config["platform_keys"].update(settings.platform_keys)

        if settings.model_capabilities:
            if "model_capabilities" not in current_config:
                current_config["model_capabilities"] = {}
            current_config["model_capabilities"] = settings.model_capabilities

        if settings.call_point_models is not None:
            from core.config_manager import update_call_point_models
            update_call_point_models(settings.call_point_models)

        set_config(current_config)

        global_manager.update_qwen_generate_params(current_config.get("qwen_generate", {}))
        global_manager.update_cosyvoice_config(current_config.get("cosyvoice_config", {}))
        dreamlite_cfg = current_config.get("dreamlite_config", {})
        global_manager.update_dreamlite_config(
            num_inference_steps=dreamlite_cfg.get("num_inference_steps"),
            width=dreamlite_cfg.get("width"),
            height=dreamlite_cfg.get("height")
        )
        qwen_embedding_cfg = current_config.get("qwen_embedding_config", {})
        global_manager.update_qwen_embedding_config(
            batch_size=qwen_embedding_cfg.get("batch_size"),
            max_length=qwen_embedding_cfg.get("max_length")
        )

        return {"success": True, "message": "设置更新成功", "config": current_config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {e}")


@router.post("/api/models/params")
async def save_model_params(request: Request):
    from core.config_manager import set_config, get_config
    from core.model_manager import get_loadable_categories

    try:
        data = await request.json()
        category = data.get("category")
        params = data.get("params")

        if not category or not params:
            raise HTTPException(status_code=400, detail="缺少category或params参数")

        loadable_categories = get_loadable_categories()
        if category not in loadable_categories:
            raise HTTPException(status_code=400, detail=f"无效的模型分类: {category}")

        current_config = get_config()
        params_config_key = loadable_categories[category]["params_config_key"]

        if params_config_key not in current_config:
            current_config[params_config_key] = {}
        current_config[params_config_key].update(params)

        set_config(current_config)

        if category == "qwen":
            global_manager.update_qwen_generate_params(current_config.get("qwen_generate", {}))
        elif category == "cosyvoice":
            global_manager.update_cosyvoice_config(current_config.get("cosyvoice_config", {}))
        elif category == "dreamlite":
            cfg = current_config.get("dreamlite_config", {})
            global_manager.update_dreamlite_config(
                num_inference_steps=cfg.get("num_inference_steps"),
                width=cfg.get("width"),
                height=cfg.get("height")
            )
        elif category == "qwen_embedding":
            cfg = current_config.get("qwen_embedding_config", {})
            global_manager.update_qwen_embedding_config(
                batch_size=cfg.get("batch_size"),
                max_length=cfg.get("max_length")
            )

        return {"success": True, "message": f"{loadable_categories[category]['name']}参数保存成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存参数失败: {e}")


@router.post("/api/models/select")
async def select_model(request: Request):
    from core.config_manager import update_model_config

    try:
        data = await request.json()
        category = data.get("category")
        model_path = data.get("model_path")
        model_name = data.get("model_name")

        if not category or not model_path or not model_name:
            raise HTTPException(status_code=400, detail="缺少category、model_path或model_name参数")

        from core.model_manager import get_loadable_categories
        loadable_categories = get_loadable_categories()
        if category not in loadable_categories:
            raise HTTPException(status_code=400, detail=f"无效的模型分类: {category}")

        update_model_config(category, model_path, model_name)

        return {"success": True, "message": f"已选择{loadable_categories[category]['name']}模型: {model_name}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"选择模型失败: {e}")


@router.post("/api/shutdown")
async def shutdown_service():
    global cosyvoice_model, qwen_model

    add_log("正在关闭服务...")

    cosyvoice_model = global_manager.cosyvoice_model
    qwen_model = global_manager.qwen_model

    if cosyvoice_model is not None:
        try:
            cosyvoice_model.release()
            add_log("CosyVoice模型已释放")
        except Exception as e:
            add_log(f"释放CosyVoice模型时出错: {e}", "WARNING")
        cosyvoice_model = None

    if qwen_model is not None:
        try:
            qwen_model.release()
            add_log("Qwen模型已释放")
        except Exception as e:
            add_log(f"释放Qwen模型时出错: {e}", "WARNING")
        qwen_model = None

    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            add_log("GPU缓存已清理")
    except Exception as e:
        add_log(f"清理GPU缓存时出错: {e}", "WARNING")

    import gc
    gc.collect()
    add_log("垃圾回收完成")

    add_log("服务关闭完成，即将退出", "SUCCESS")

    asyncio.create_task(_delayed_exit())

    return {"success": True, "message": "服务正在关闭..."}


async def _delayed_exit():
    await asyncio.sleep(1)
    import os
    os._exit(0)


@router.post("/api/unload-models")
async def unload_models():
    import gc
    from core.model_manager import get_loadable_categories, reset_all_models

    unloaded_items = []

    for cat_key, meta in get_loadable_categories().items():
        model_attr = meta["model_attr"]
        display_name = meta["name"]

        model_instance = getattr(global_manager, model_attr, None)
        if model_instance is not None:
            try:
                model_instance.release()
            except Exception as e:
                add_log(f"卸载{display_name}模型时出错: {e}", "WARNING")
            unloaded_items.append(display_name)
            add_log(f"{display_name}模型已卸载", "INFO")

    reset_all_models()

    freed_memory = 0
    if torch.cuda.is_available():
        try:
            before_memory = torch.cuda.memory_allocated(0)
            for i in range(3):
                gc.collect()
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
                torch.cuda.synchronize()
            after_memory = torch.cuda.memory_allocated(0)
            freed_memory = before_memory - after_memory
            unloaded_items.append(f"GPU缓存({freed_memory/1024/1024:.1f}MB)")
            add_log(f"GPU缓存已清理，释放显存: {freed_memory/1024/1024:.1f} MB", "INFO")
        except Exception as e:
            add_log(f"清理GPU缓存时出错: {e}", "WARNING")

    gc.collect()

    message = f"已卸载: {', '.join(unloaded_items)}" if unloaded_items else "没有已加载的模型"
    add_log(message, "SUCCESS")

    return {"success": True, "message": message}


@router.post("/api/clear-memory")
async def clear_memory():
    return await unload_models()


@router.post("/api/clear-gpu-cache")
async def clear_gpu_cache():
    if torch.cuda.is_available():
        try:
            before_memory = torch.cuda.memory_allocated(0)
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            after_memory = torch.cuda.memory_allocated(0)

            freed_memory = before_memory - after_memory

            add_log(f"GPU缓存清理完成 - 释放显存: {freed_memory / 1024 / 1024:.2f} MB", "INFO")

            return {
                "success": True,
                "message": f"GPU缓存清理完成，释放显存: {freed_memory / 1024 / 1024:.2f} MB",
                "before": f"{before_memory / 1024 / 1024:.2f} MB",
                "after": f"{after_memory / 1024 / 1024:.2f} MB",
                "freed": f"{freed_memory / 1024 / 1024:.2f} MB"
            }
        except Exception as e:
            add_log(f"GPU缓存清理失败: {e}", "ERROR")
            return {"success": False, "error": str(e)}
    else:
        return {"success": False, "error": "CUDA不可用"}
