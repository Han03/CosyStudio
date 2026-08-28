import os
import sys
import time
import logging
import asyncio
import threading
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from typing import Dict, List, Optional, Callable

from core.paths import LOG_DIR


def cleanup_old_logs(log_dir: str, max_days: int = 7):
    try:
        cutoff_date = datetime.now() - timedelta(days=max_days)
        for filename in os.listdir(log_dir):
            if filename.endswith('.log'):
                filepath = os.path.join(log_dir, filename)
                try:
                    file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if file_time < cutoff_date:
                        os.remove(filepath)
                        print(f"[日志清理] 已删除过期日志: {filename}")
                except Exception as e:
                    print(f"[日志清理] 删除文件失败 {filename}: {e}")
    except Exception as e:
        print(f"[日志清理] 清理失败: {e}")


cleanup_old_logs(LOG_DIR, 7)

_log_format = '%(asctime)s [%(levelname)s] %(message)s'
_file_handler = TimedRotatingFileHandler(
    filename=os.path.join(LOG_DIR, 'app.log'),
    when='midnight',
    interval=1,
    backupCount=7,
    encoding='utf-8'
)
_file_handler.setFormatter(logging.Formatter(_log_format))
_file_handler.suffix = '%Y-%m-%d'

logging.basicConfig(
    level=logging.INFO,
    format=_log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        _file_handler
    ]
)


class LogManager:
    """日志管理器 - 统一管理系统日志，支持业务分类和WebSocket实时推送

    使用方式:
        from utils.logger import log_manager

        # 获取指定业务分类的日志工具
        log = log_manager.get_logger("system")
        log.info("系统启动成功")
        log.error("发生错误", exc_info=True)

        # 注册WebSocket回调，用于实时推送日志
        log_manager.add_ws_callback(callback)
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
        self._loggers: Dict[str, logging.Logger] = {}
        self._ws_callbacks: List[Callable] = []
        self._ws_callbacks_lock = threading.Lock()
        self._max_logs = 1000
        self._log_buffer: List[dict] = []
        self._buffer_lock = threading.Lock()

    def get_logger(self, category: str = "system") -> "CategoryLogger":
        """获取指定业务分类的日志工具

        Args:
            category: 业务分类名称，如 system, websocket, task, model 等

        Returns:
            CategoryLogger 实例，支持 info/warning/error/debug 等方法
        """
        if category not in self._loggers:
            logger = logging.getLogger(f"app.{category}")
            logger.setLevel(logging.INFO)
            self._loggers[category] = logger

        return CategoryLogger(category, self._loggers[category], self)

    def add_ws_callback(self, callback: Callable):
        """注册WebSocket日志回调

        Args:
            callback: 回调函数，接收一个字典参数: {timestamp, level, category, message}
        """
        with self._ws_callbacks_lock:
            if callback not in self._ws_callbacks:
                self._ws_callbacks.append(callback)

    def remove_ws_callback(self, callback: Callable):
        """移除WebSocket日志回调"""
        with self._ws_callbacks_lock:
            if callback in self._ws_callbacks:
                self._ws_callbacks.remove(callback)

    def _broadcast_log(self, level: str, category: str, message: str):
        """广播日志到所有WebSocket连接

        Args:
            level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
            category: 业务分类
            message: 日志消息
        """
        log_entry = {
            "timestamp": time.time(),
            "level": level,
            "category": category,
            "message": message
        }

        with self._buffer_lock:
            self._log_buffer.append(log_entry)
            if len(self._log_buffer) > self._max_logs:
                self._log_buffer = self._log_buffer[-self._max_logs:]

        with self._ws_callbacks_lock:
            callbacks = list(self._ws_callbacks)

        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(callback(log_entry))
                    except RuntimeError:
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                loop.call_soon_threadsafe(
                                    lambda: loop.create_task(callback(log_entry))
                                )
                            else:
                                asyncio.run(callback(log_entry))
                        except RuntimeError:
                            pass
                else:
                    callback(log_entry)
            except Exception:
                pass

    def get_recent_logs(self, limit: int = 100, category: Optional[str] = None) -> List[dict]:
        """获取最近的日志

        Args:
            limit: 返回日志数量限制
            category: 可选，按业务分类过滤

        Returns:
            日志条目列表
        """
        with self._buffer_lock:
            logs = list(self._log_buffer)

        if category:
            logs = [log for log in logs if log.get("category") == category]

        return logs[-limit:]

    def clear_logs(self):
        """清空日志缓冲区"""
        with self._buffer_lock:
            self._log_buffer.clear()


class CategoryLogger:
    """业务分类日志工具 - 包装标准logger，添加分类和WebSocket广播"""

    def __init__(self, category: str, logger: logging.Logger, manager: LogManager):
        self._category = category
        self._logger = logger
        self._manager = manager

    def debug(self, message: str, *args, **kwargs):
        self._logger.debug(message, *args, **kwargs)
        self._manager._broadcast_log("DEBUG", self._category, message)

    def info(self, message: str, *args, **kwargs):
        self._logger.info(message, *args, **kwargs)
        self._manager._broadcast_log("INFO", self._category, message)

    def warning(self, message: str, *args, **kwargs):
        self._logger.warning(message, *args, **kwargs)
        self._manager._broadcast_log("WARNING", self._category, message)

    def warn(self, message: str, *args, **kwargs):
        self.warning(message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs):
        self._logger.error(message, *args, **kwargs)
        self._manager._broadcast_log("ERROR", self._category, message)

    def exception(self, message: str, *args, **kwargs):
        self._logger.exception(message, *args, **kwargs)
        self._manager._broadcast_log("ERROR", self._category, message)

    def critical(self, message: str, *args, **kwargs):
        self._logger.critical(message, *args, **kwargs)
        self._manager._broadcast_log("CRITICAL", self._category, message)

    def log(self, level: int, message: str, *args, **kwargs):
        self._logger.log(level, message, *args, **kwargs)
        level_name = logging.getLevelName(level)
        self._manager._broadcast_log(level_name, self._category, message)


log_manager = LogManager()

logger = log_manager.get_logger("system")


def get_logger(category: str = "system") -> CategoryLogger:
    """获取指定业务分类的日志工具（便捷函数）

    Args:
        category: 业务分类名称

    Returns:
        CategoryLogger 实例
    """
    return log_manager.get_logger(category)


def add_log(message: str, level: str = "INFO"):
    """便捷日志函数 - 兼容旧代码

    Args:
        message: 日志消息
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
    """
    logger_instance = get_logger("system")
    level = level.upper()
    if level == "DEBUG":
        logger_instance.debug(message)
    elif level == "WARNING":
        logger_instance.warning(message)
    elif level == "ERROR":
        logger_instance.error(message)
    else:
        logger_instance.info(message)
