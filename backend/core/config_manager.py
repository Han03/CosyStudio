import os
import json
import threading

from core.paths import CONFIG_DIR
CONFIG_FILE = os.path.join(CONFIG_DIR, "system_config.json")


def _build_default_models():
    """从 MODEL_CATEGORIES 派生默认 models 配置"""
    from core.model_manager import get_loadable_categories
    return {
        meta["config_key"]: {"model_path": "", "model_name": ""}
        for meta in get_loadable_categories().values()
    }


CAPABILITY_TYPES = {
    "text_predict": "文本预测",
    "text_to_speech": "语音合成",
    "text_to_image": "文生图",
    "text_to_vector": "文本转向量",
    "text_rerank": "片段重排序"
}

PLATFORM_CODES = {
    "local": {
        "name": "本地模型",
        "description": "本地部署的开源模型"
    },
    "aliyun": {
        "name": "阿里云百炼",
        "description": "阿里云大模型服务平台"
    },
    "volcengine": {
        "name": "火山引擎",
        "description": "火山引擎方舟大模型平台"
    },
    
    "deepseek": {
        "name": "DeepSeek",
        "description": "深度求索大模型服务"
    },
    "zhipu": {
        "name": "智谱AI",
        "description": "智谱AI大模型服务"
    },
    "baidu": {
        "name": "百度千帆",
        "description": "百度智能云千帆大模型平台"
    },
    "moonshot": {
        "name": "月之暗面",
        "description": "月之暗面大模型服务"
    },
    "google": {
        "name": "Google AI",
        "description": "Google AI Studio"
    },
    "groq": {
        "name": "Groq",
        "description": "Groq大模型推理服务"
    },
    "openrouter": {
        "name": "OpenRouter",
        "description": "多模型路由服务"
    }
}

DEFAULT_CONFIG = {
    "models": {},
    "qwen_generate": {
        "temperature": 0.1,
        "top_p": 0.5,
        "top_k": 10,
        "do_sample": False,
        "repetition_penalty": 1.0,
        "length_penalty": 1.0,
        "num_beams": 1,
        "early_stopping": True,
        "max_new_tokens": 2048,
    },
    "cosyvoice_config": {
        "speed": 1.0
    },
    "dreamlite_config": {
        "num_inference_steps": 4,
        "width": 1024,
        "height": 1024
    },
    "qwen_embedding_config": {
        "batch_size": 32,
        "max_length": 512
    },
    "qwen_reranker_config": {
        "max_length": 1024
    },
    "platform_keys": {
        "local": {
            "enabled": True,
            "code": "local",
            "name": "本地模型",
            "description": "本地部署的开源模型"
        },
        "aliyun": {
            "enabled": False,
            "code": "aliyun",
            "name": "阿里云百炼",
            "description": "阿里云大模型服务平台",
            "api_key": "",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "default_model": "qwen-plus"
        },
        "zhipu": {
            "enabled": False,
            "code": "zhipu",
            "name": "智谱AI",
            "description": "智谱AI大模型服务",
            "api_key": "",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "default_model": "glm-4-plus"
        },
        "baidu": {
            "enabled": False,
            "code": "baidu",
            "name": "百度千帆",
            "description": "百度智能云千帆大模型平台",
            "api_key": "",
            "secret_key": "",
            "base_url": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions",
            "default_model": "ernie-4.0-turbo"
        },
        "moonshot": {
            "enabled": False,
            "code": "moonshot",
            "name": "月之暗面",
            "description": "月之暗面大模型服务",
            "api_key": "",
            "base_url": "https://api.moonshot.cn/v1",
            "default_model": "moonshot-v1-8k"
        },
        "volcengine": {
            "enabled": False,
            "code": "volcengine",
            "name": "火山引擎",
            "description": "火山引擎方舟大模型平台",
            "api_key": "",
            "secret_key": "",
            "auth_type": "api_key",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "default_model": "doubao-pro-4k"
        },
        "deepseek": {
            "enabled": False,
            "code": "deepseek",
            "name": "DeepSeek",
            "description": "深度求索大模型服务",
            "api_key": "",
            "base_url": "https://api.deepseek.com/v1",
            "default_model": "deepseek-chat"
        },
        "google": {
            "enabled": False,
            "code": "google",
            "name": "Google AI",
            "description": "Google AI Studio",
            "api_key": "",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "default_model": "gemini-pro"
        },
        "groq": {
            "enabled": False,
            "code": "groq",
            "name": "Groq",
            "description": "Groq大模型推理服务",
            "api_key": "",
            "base_url": "https://api.groq.com/openai/v1",
            "default_model": "mixtral-8x7b-32768"
        },
        "openrouter": {
            "enabled": False,
            "code": "openrouter",
            "name": "OpenRouter",
            "description": "多模型路由服务",
            "api_key": "",
            "base_url": "https://openrouter.ai/api/v1",
            "default_model": "meta-llama/llama-3-8b-chat"
        }
    },
    "model_capabilities": {
        "text_predict": [
            {
                "id": "text_predict_local_qwen",
                "platform_code": "local",
                "model_code": "qwen",
                "priority": 10,
                "enabled": True,
                "description": "本地Qwen模型文本预测"
            },
            {
                "id": "text_predict_aliyun",
                "platform_code": "aliyun",
                "model_code": "qwen-plus",
                "priority": 5,
                "enabled": False,
                "description": "阿里云Qwen-Plus文本预测"
            },
            {
                "id": "text_predict_zhipu",
                "platform_code": "zhipu",
                "model_code": "glm-4-plus",
                "priority": 5,
                "enabled": False,
                "description": "智谱GLM-4-Plus文本预测"
            }
        ],
        "text_to_speech": [
            {
                "id": "tts_local_cosyvoice",
                "platform_code": "local",
                "model_code": "cosyvoice",
                "priority": 10,
                "enabled": True,
                "description": "本地CosyVoice语音合成"
            },
            {
                "id": "tts_aliyun",
                "platform_code": "aliyun",
                "model_code": "cosyvoice-v3",
                "priority": 5,
                "enabled": False,
                "description": "阿里云语音合成"
            }
        ],
        "text_to_image": [
            {
                "id": "t2i_local_dreamlite",
                "platform_code": "local",
                "model_code": "dreamlite",
                "priority": 10,
                "enabled": True,
                "description": "本地DreamLite文生图"
            },
            {
                "id": "t2i_aliyun",
                "platform_code": "aliyun",
                "model_code": "stable-diffusion-xl",
                "priority": 5,
                "enabled": False,
                "description": "阿里云文生图"
            }
        ],
        "text_to_vector": [
            {
                "id": "t2v_local_qwen_embedding",
                "platform_code": "local",
                "model_code": "qwen_embedding",
                "priority": 10,
                "enabled": True,
                "description": "本地Qwen-Embedding文本转向量"
            }
        ],
        "text_rerank": [
            {
                "id": "rerank_local_qwen_reranker",
                "platform_code": "local",
                "model_code": "qwen_reranker",
                "priority": 10,
                "enabled": True,
                "description": "本地Qwen3-Reranker片段重排序"
            }
        ]
    },
    "call_point_models": {},
    "system": {
        "app_name": "CosyWritter",
        "max_workers": 4,
        "log_level": "INFO",
        "port": 8000
    }
}

_config_lock = threading.Lock()
_current_config = None

def _ensure_config_dir():
    config_dir = os.path.dirname(CONFIG_FILE)
    os.makedirs(config_dir, exist_ok=True)

def _load_config():
    global _current_config
    _ensure_config_dir()

    # 确保 DEFAULT_CONFIG["models"] 从字典派生
    DEFAULT_CONFIG["models"] = _build_default_models()

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                _current_config = json.load(f)
                _migrate_legacy_keys(_current_config)
                _merge_defaults(_current_config)
        except:
            _current_config = DEFAULT_CONFIG.copy()
    else:
        _current_config = DEFAULT_CONFIG.copy()

def _migrate_legacy_keys(config):
    """迁移旧版配置键名（幂等）"""
    need_save = False
    return need_save

def _merge_defaults(config):
    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = value if not isinstance(value, dict) or key != "models" else value.copy()
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if sub_key not in config[key]:
                    config[key][sub_key] = sub_value

def _save_config():
    _ensure_config_dir()
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(_current_config, f, indent=2, ensure_ascii=False)

def get_config():
    global _current_config
    if _current_config is None:
        _load_config()
    return _current_config.copy()

def get_model_config(model_type):
    config = get_config()
    return config.get("models", {}).get(model_type, {})

def get_cosyvoice_config():
    return get_model_config("cosyvoice")

def get_qwen_config():
    return get_model_config("qwen")

def get_dreamlite_model_config():
    return get_model_config("dreamlite")

def get_qwen_embedding_model_config():
    return get_model_config("qwen_embedding")

def get_qwen_reranker_model_config():
    return get_model_config("qwen_reranker")

def set_config(new_config):
    global _current_config
    with _config_lock:
        _current_config = new_config
        _merge_defaults(_current_config)
        _save_config()
    return _current_config

def update_model_config(model_type, model_path, model_name):
    with _config_lock:
        if _current_config is None:
            _load_config()

        if "models" not in _current_config:
            _current_config["models"] = {}

        if model_type not in _current_config["models"]:
            _current_config["models"][model_type] = {}

        _current_config["models"][model_type]["model_path"] = model_path
        _current_config["models"][model_type]["model_name"] = model_name

        _save_config()

    return _current_config

def update_cosyvoice_config(model_path, model_name):
    return update_model_config("cosyvoice", model_path, model_name)

def update_qwen_config(model_path, model_name):
    return update_model_config("qwen", model_path, model_name)

def update_dreamlite_model_config(model_path, model_name):
    return update_model_config("dreamlite", model_path, model_name)

def update_qwen_embedding_model_config(model_path, model_name):
    return update_model_config("qwen_embedding", model_path, model_name)

def update_qwen_reranker_model_config(model_path, model_name):
    return update_model_config("qwen_reranker", model_path, model_name)

def get_qwen_generate_params():
    config = get_config()
    return config.get("qwen_generate", {})

def update_qwen_generate_params(params):
    with _config_lock:
        if _current_config is None:
            _load_config()

        if "qwen_generate" not in _current_config:
            _current_config["qwen_generate"] = {}

        int_params = ['top_k', 'num_beams', 'max_new_tokens']
        bool_params = ['do_sample', 'early_stopping']

        for key, value in params.items():
            if key in int_params:
                try:
                    _current_config["qwen_generate"][key] = int(float(value))
                except (ValueError, TypeError):
                    pass
            elif key in bool_params:
                if isinstance(value, str):
                    _current_config["qwen_generate"][key] = value.lower() == 'true'
                else:
                    _current_config["qwen_generate"][key] = bool(value)
            else:
                _current_config["qwen_generate"][key] = value

        _save_config()

    return _current_config

def get_cosyvoice_config_params():
    config = get_config()
    return config.get("cosyvoice_config", {"speed": 1.0})

def update_cosyvoice_config_params(params):
    with _config_lock:
        if _current_config is None:
            _load_config()

        if "cosyvoice_config" not in _current_config:
            _current_config["cosyvoice_config"] = {}

        float_params = ['speed']

        for key, value in params.items():
            if key in float_params:
                try:
                    _current_config["cosyvoice_config"][key] = float(value)
                except (ValueError, TypeError):
                    pass
            else:
                _current_config["cosyvoice_config"][key] = value

        _save_config()

    return _current_config

def get_dreamlite_config_params():
    config = get_config()
    return config.get("dreamlite_config", {"num_inference_steps": 4, "width": 1024, "height": 1024})

def update_dreamlite_config_params(num_inference_steps=None, width=None, height=None):
    with _config_lock:
        if _current_config is None:
            _load_config()

        if "dreamlite_config" not in _current_config:
            _current_config["dreamlite_config"] = {}

        int_params = {
            "num_inference_steps": num_inference_steps,
            "width": width,
            "height": height,
        }

        for key, value in int_params.items():
            if value is not None:
                try:
                    _current_config["dreamlite_config"][key] = int(float(value))
                except (ValueError, TypeError):
                    pass

        _save_config()

    return _current_config

def get_qwen_embedding_config_params():
    config = get_config()
    return config.get("qwen_embedding_config", {"batch_size": 32, "max_length": 512})

def update_qwen_embedding_config_params(batch_size=None, max_length=None):
    with _config_lock:
        if _current_config is None:
            _load_config()

        if "qwen_embedding_config" not in _current_config:
            _current_config["qwen_embedding_config"] = {}

        int_params = {
            "batch_size": batch_size,
            "max_length": max_length,
        }

        for key, value in int_params.items():
            if value is not None:
                try:
                    _current_config["qwen_embedding_config"][key] = int(float(value))
                except (ValueError, TypeError):
                    pass

        _save_config()

    return _current_config

def get_qwen_reranker_config_params():
    config = get_config()
    return config.get("qwen_reranker_config", {"max_length": 1024})

def update_qwen_reranker_config_params(max_length=None):
    with _config_lock:
        if _current_config is None:
            _load_config()

        if "qwen_reranker_config" not in _current_config:
            _current_config["qwen_reranker_config"] = {}

        int_params = {
            "max_length": max_length,
        }

        for key, value in int_params.items():
            if value is not None:
                try:
                    _current_config["qwen_reranker_config"][key] = int(float(value))
                except (ValueError, TypeError):
                    pass

        _save_config()

    return _current_config

def get_app_name() -> str:
    config = get_config()
    return config.get("system", {}).get("app_name", "CosyWritter")

def get_server_port():
    config = get_config()
    return config.get("system", {}).get("port", 8000)

def reset_config():
    global _current_config
    with _config_lock:
        DEFAULT_CONFIG["models"] = _build_default_models()
        _current_config = DEFAULT_CONFIG.copy()
        _save_config()
    return _current_config

def get_model_capabilities():
    config = get_config()
    return config.get("model_capabilities", {})

def get_capability_by_type(capability_type: str):
    capabilities = get_model_capabilities()
    return capabilities.get(capability_type, [])

def get_enabled_capabilities(capability_type: str):
    capabilities = get_capability_by_type(capability_type)
    enabled = [c for c in capabilities if c.get("enabled", False)]
    enabled.sort(key=lambda x: x.get("priority", 0), reverse=True)
    return enabled

def update_model_capabilities(capabilities: dict):
    with _config_lock:
        if _current_config is None:
            _load_config()
        _current_config["model_capabilities"] = capabilities
        _save_config()
    return _current_config

def update_capability(capability_type: str, capability_id: str, updates: dict):
    with _config_lock:
        if _current_config is None:
            _load_config()
        capabilities = _current_config.get("model_capabilities", {})
        if capability_type not in capabilities:
            capabilities[capability_type] = []
        for cap in capabilities[capability_type]:
            if cap.get("id") == capability_id:
                cap.update(updates)
                break
        _current_config["model_capabilities"] = capabilities
        _save_config()
    return _current_config

def add_capability(capability_type: str, capability: dict):
    with _config_lock:
        if _current_config is None:
            _load_config()
        capabilities = _current_config.get("model_capabilities", {})
        if capability_type not in capabilities:
            capabilities[capability_type] = []
        capabilities[capability_type].append(capability)
        _current_config["model_capabilities"] = capabilities
        _save_config()
    return _current_config

def delete_capability(capability_type: str, capability_id: str):
    with _config_lock:
        if _current_config is None:
            _load_config()
        capabilities = _current_config.get("model_capabilities", {})
        if capability_type in capabilities:
            capabilities[capability_type] = [
                cap for cap in capabilities[capability_type]
                if cap.get("id") != capability_id
            ]
            _current_config["model_capabilities"] = capabilities
            _save_config()
    return _current_config


def get_call_point_models() -> dict:
    """获取所有调用点模型覆盖配置，返回 {executor_name: {capability_id: ...}}"""
    config = get_config()
    return config.get("call_point_models", {})


def get_call_point_model(executor_name: str):
    """获取指定调用点的模型覆盖配置。

    通过 capability_id 查找对应的 platform_code 和 model_code，
    未配置或能力不存在时返回 None。
    """
    configs = get_call_point_models()
    override = configs.get(executor_name)
    if not override or not override.get("capability_id"):
        return None

    capability_id = override["capability_id"]
    # 从 model_capabilities.text_predict 中查找对应能力
    all_capabilities = get_model_capabilities()
    text_predict_caps = all_capabilities.get("text_predict", [])
    for cap in text_predict_caps:
        if cap.get("id") == capability_id and cap.get("enabled", False):
            return {
                "platform_code": cap["platform_code"],
                "model_code": cap["model_code"],
            }
    return None


def update_call_point_models(configs: dict):
    """批量更新调用点模型覆盖配置。

    configs 格式: {executor_name: {capability_id: "..."}}
    capability_id 为空的视为删除。
    """
    with _config_lock:
        if _current_config is None:
            _load_config()
        if "call_point_models" not in _current_config:
            _current_config["call_point_models"] = {}
        _current_config["call_point_models"].update(configs)
        # 清理空值（capability_id 为空的视为删除）
        to_remove = [
            k for k, v in _current_config["call_point_models"].items()
            if not v.get("capability_id")
        ]
        for k in to_remove:
            del _current_config["call_point_models"][k]
        _save_config()
    return _current_config


_load_config()
