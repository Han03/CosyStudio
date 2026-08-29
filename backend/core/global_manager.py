import threading
import asyncio


class GlobalManager:
    """
    全局变量管理器 - 统一管理应用中的全局状态

    包含：
    - 模型实例（cosyvoice_model, qwen_model, dreamlite_model, qwen_embedding_model, qwen_reranker_model）
    - 智能体管理器（agent_manager）
    - 系统状态（system_status, model_loading_status, system_resources）
    - 并发控制锁（cosyvoice_model_lock, qwen_model_lock等）
    - 各模型的配置参数（qwen_generate_params, cosyvoice_config, dreamlite_config, qwen_embedding_config, qwen_reranker_config）

    所有模型实例、加载状态、锁、参数属性均从 MODEL_CATEGORIES 字典派生。
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        """初始化全局变量"""
        from core.model_manager import get_loadable_categories
        from utils.logger import logger

        self._loadable_categories = get_loadable_categories()

        # 模型实例（动态生成属性）
        for meta in self._loadable_categories.values():
            setattr(self, f"_{meta['model_attr']}", None)

        # 智能体管理器
        self.agent_manager = None

        # 系统状态
        self.system_status = {
            meta["loaded_flag"]: False for meta in self._loadable_categories.values()
        }
        self.system_status.update({
            "agents_count": 0,
            "current_operation": "",
            "status": "running",
            "start_time": "",
            "version": self._read_version(),
            "logs": [],
            "is_model_running": False,
            "running_model_type": "",
        })

        # 模型运行状态锁
        self._model_running_lock = threading.Lock()

        # 模型加载状态
        self.model_loading_status = {
            meta["loading_status_key"]: {
                "status": "not_loaded",
                "progress": 0,
                "message": "未加载",
                "error": None
            }
            for meta in self._loadable_categories.values()
        }

        # 系统资源
        self.system_resources = {
            "cpu": {"percent": 0},
            "memory": {"percent": 0, "used": "0 B", "total": "0 B"},
            "disk": {"percent": 0, "free": "0 B"},
            "gpu": {"available": False, "memory_percent": 0, "name": "", "memory_used": "0 B", "memory_total": "0 B"}
        }

        # 并发控制锁（动态生成）
        for meta in self._loadable_categories.values():
            config_key = meta["config_key"]
            setattr(self, f"{config_key}_model_lock", threading.Lock())
            setattr(self, f"{config_key}_async_lock", asyncio.Lock())

        # 各模型的配置参数（从配置文件加载，动态生成属性）
        from .config_manager import (
            get_qwen_generate_params,
            get_cosyvoice_config_params,
            get_dreamlite_config_params,
            get_qwen_embedding_config_params,
            get_qwen_reranker_config_params
        )
        self.qwen_generate_params = get_qwen_generate_params()
        self.cosyvoice_config = get_cosyvoice_config_params()
        self.dreamlite_config = get_dreamlite_config_params()
        self.qwen_embedding_config = get_qwen_embedding_config_params()
        self.qwen_reranker_config = get_qwen_reranker_config_params()

    def _read_version(self):
        """从 version.json 读取版本号"""
        import os
        import json
        try:
            version_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "version.json"
            )
            if os.path.exists(version_file):
                with open(version_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("version", "1.0.0")
        except Exception:
            pass
        return "1.0.0"

    def reset_models(self):
        """重置所有模型"""
        for meta in self._loadable_categories.values():
            setattr(self, f"_{meta['model_attr']}", None)
            self.system_status[meta["loaded_flag"]] = False
            self.model_loading_status[meta["loading_status_key"]] = {
                "status": "not_loaded",
                "progress": 0,
                "message": "未加载",
                "error": None
            }
        self.system_status["current_operation"] = "空闲"

    def reset_cosyvoice(self):
        """重置CosyVoice模型"""
        self._cosyvoice_model = None
        self.system_status["cosyvoice_loaded"] = False
        self.model_loading_status["cosyvoice"] = {
            "status": "not_loaded",
            "progress": 0,
            "message": "未加载",
            "error": None
        }

    def reset_qwen(self):
        """重置Qwen模型"""
        self._qwen_model = None
        self.system_status["qwen_loaded"] = False
        self.model_loading_status["qwen"] = {
            "status": "not_loaded",
            "progress": 0,
            "message": "未加载",
            "error": None
        }

    def reset_dreamlite(self):
        """重置DreamLite模型"""
        self._dreamlite_model = None
        self.system_status["dreamlite_loaded"] = False
        self.model_loading_status["dreamlite"] = {
            "status": "not_loaded",
            "progress": 0,
            "message": "未加载",
            "error": None
        }

    def reset_qwen_embedding(self):
        """重置Qwen3-Embedding模型"""
        self._qwen_embedding_model = None
        self.system_status["qwen_embedding_loaded"] = False
        self.model_loading_status["qwen_embedding"] = {
            "status": "not_loaded",
            "progress": 0,
            "message": "未加载",
            "error": None
        }

    def reset_qwen_reranker(self):
        """重置Qwen3-Reranker模型"""
        self._qwen_reranker_model = None
        self.system_status["qwen_reranker_loaded"] = False
        self.model_loading_status["qwen_reranker"] = {
            "status": "not_loaded",
            "progress": 0,
            "message": "未加载",
            "error": None
        }

    def _set_model_loaded(self, model:str, loaded: bool):
        """设置模型加载状态"""
        self.system_status[model] = loaded
        if loaded:
            self.model_loading_status[model]["status"] = "loaded"
            self.model_loading_status[model]["progress"] = 100
            self.model_loading_status[model]["message"] = f"{model}模型加载成功"
        else:
            self.model_loading_status[model]["status"] = "not_loaded"
            self.model_loading_status[model]["progress"] = 0
            self.model_loading_status[model]["message"] = "未加载"
            self.model_loading_status[model]["error"] = None

    def set_cosyvoice_loaded(self, loaded: bool):
        """设置CosyVoice加载状态"""
        self._set_model_loaded("cosyvoice", loaded)

    def set_qwen_loaded(self, loaded: bool):
        """设置Qwen加载状态"""
        self._set_model_loaded("qwen", loaded)

    def set_dreamlite_loaded(self, loaded: bool):
        """设置DreamLite加载状态"""
        self._set_model_loaded("dreamlite", loaded)

    def set_qwen_embedding_loaded(self, loaded: bool):
        """设置Qwen3-Embedding加载状态"""
        self._set_model_loaded("qwen_embedding", loaded)

    def set_qwen_reranker_loaded(self, loaded: bool):
        """设置Qwen3-Reranker加载状态"""
        self._set_model_loaded("qwen_reranker", loaded)

    def update_qwen_generate_params(self, params):
        """更新Qwen生成参数"""
        from .config_manager import update_qwen_generate_params as save_params
        save_params(params)
        self.qwen_generate_params = params.copy()

    def update_cosyvoice_config(self, params):
        """更新CosyVoice配置参数"""
        from .config_manager import update_cosyvoice_config_params as save_params
        save_params(params)
        self.cosyvoice_config = params.copy()

    def update_dreamlite_config(self, num_inference_steps=None, width=None, height=None):
        """更新DreamLite配置参数"""
        from .config_manager import update_dreamlite_config_params as save_config
        save_config(num_inference_steps=num_inference_steps, width=width, height=height)
        from .config_manager import get_dreamlite_config_params
        self.dreamlite_config = get_dreamlite_config_params()

    def update_qwen_embedding_config(self, batch_size=None, max_length=None):
        """更新Qwen3-Embedding配置参数"""
        from .config_manager import update_qwen_embedding_config_params as save_config
        save_config(batch_size=batch_size, max_length=max_length)
        from .config_manager import get_qwen_embedding_config_params
        self.qwen_embedding_config = get_qwen_embedding_config_params()

    def update_qwen_reranker_config(self, max_length=None):
        """更新Qwen3-Reranker配置参数"""
        from .config_manager import update_qwen_reranker_config_params as save_config
        save_config(max_length=max_length)
        from .config_manager import get_qwen_reranker_config_params
        self.qwen_reranker_config = get_qwen_reranker_config_params()

    @property
    def cosyvoice_model(self):
        """获取CosyVoice模型"""
        return self._cosyvoice_model

    @cosyvoice_model.setter
    def cosyvoice_model(self, value):
        """设置CosyVoice模型"""
        self._cosyvoice_model = value

    @property
    def qwen_model(self):
        """获取Qwen模型"""
        return self._qwen_model

    @qwen_model.setter
    def qwen_model(self, value):
        """设置Qwen模型"""
        self._qwen_model = value

    @property
    def dreamlite_model(self):
        """获取DreamLite模型"""
        return self._dreamlite_model

    @dreamlite_model.setter
    def dreamlite_model(self, value):
        """设置DreamLite模型"""
        self._dreamlite_model = value

    @property
    def qwen_embedding_model(self):
        """获取Qwen3-Embedding模型"""
        return self._qwen_embedding_model

    @qwen_embedding_model.setter
    def qwen_embedding_model(self, value):
        """设置Qwen3-Embedding模型"""
        self._qwen_embedding_model = value

    @property
    def qwen_reranker_model(self):
        """获取Qwen3-Reranker模型"""
        return self._qwen_reranker_model

    @qwen_reranker_model.setter
    def qwen_reranker_model(self, value):
        """设置Qwen3-Reranker模型"""
        self._qwen_reranker_model = value

    def try_acquire_model(self, model_type: str) -> bool:
        """尝试获取模型运行权限。
        
        Args:
            model_type: 模型类型，如 "qwen", "cosyvoice", "dreamlite"
        
        Returns:
            True if acquired, False if another model is running
        """
        with self._model_running_lock:
            if self.system_status["is_model_running"]:
                return False
            self.system_status["is_model_running"] = True
            self.system_status["running_model_type"] = model_type
            return True

    def release_model(self):
        """释放模型运行权限"""
        with self._model_running_lock:
            self.system_status["is_model_running"] = False
            self.system_status["running_model_type"] = ""

    def is_model_busy(self) -> bool:
        """检查是否有模型正在运行"""
        return self.system_status["is_model_running"]


# 创建全局单例实例
global_manager = GlobalManager()
