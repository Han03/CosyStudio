"""应用生命周期管理 — 启动钩子、资源监控、日志辅助。"""
import os
import json
import asyncio
import threading
from datetime import datetime

from fastapi import FastAPI

from utils.logger import log_manager
from core.global_manager import global_manager

_main_logger = log_manager.get_logger("system")


# ============================================================
# 日志辅助
# ============================================================

def add_log(message: str, level: str = "INFO"):
    """写入日志并同时推送到内存状态和标准输出。"""
    system_status = global_manager.system_status
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = {"time": timestamp, "message": message, "level": level}
        system_status["logs"].append(log_entry)
        if len(system_status["logs"]) > 100:
            system_status["logs"] = system_status["logs"][-100:]
    except Exception as e:
        print(f"[add_log 错误] {e}")

    try:
        if level == "INFO":
            _main_logger.info(message)
        elif level == "WARNING":
            _main_logger.warning(message)
        elif level == "ERROR":
            _main_logger.error(message)
        else:
            _main_logger.info(message)
    except Exception as e:
        print(f"[logger 错误] {e}")

    print(f"[LOG][{level}] {message}")


# ============================================================
# 版本读取
# ============================================================

def get_version() -> str:
    """从 version.json 读取版本号。"""
    version_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "version.json")
    if os.path.exists(version_path):
        try:
            with open(version_path, "r", encoding="utf-8") as f:
                return json.load(f).get("version", "1.0.0")
        except:
            pass
    return "1.0.0"


# ============================================================
# 智能体加载
# ============================================================

def load_agent_manager():
    """加载智能体管理器。"""
    from agents.agent_manager import AgentManager
    from core.paths import AGENTS_DATA_DIR
    add_log("正在加载智能体管理器...")
    agent_manager = AgentManager(AGENTS_DATA_DIR)
    global_manager.agent_manager = agent_manager
    add_log("智能体管理器加载完成")


# ============================================================
# 资源监控
# ============================================================

def _periodic_resource_update_thread():
    """后台线程：每 2 秒刷新系统资源占用。"""
    import time
    import importlib.util

    _resource_monitor_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'utils', 'resource_monitor.py')
    _resource_monitor_spec = importlib.util.spec_from_file_location('utils.resource_monitor', _resource_monitor_path)
    _resource_monitor_module = importlib.util.module_from_spec(_resource_monitor_spec)
    _resource_monitor_spec.loader.exec_module(_resource_monitor_module)
    resource_monitor = _resource_monitor_module.resource_monitor

    system_resources = global_manager.system_resources
    while True:
        try:
            resources = resource_monitor.get_system_resources()
            system_resources["cpu"] = {"percent": resources["cpu"]["percent"]}
            system_resources["memory"] = {
                "percent": resources["memory"]["percent"],
                "used": resources["memory"]["used"],
                "total": resources["memory"]["total"]
            }
            system_resources["disk"] = {
                "percent": resources["disk"]["percent"],
                "free": resources["disk"]["free"]
            }
            system_resources["gpu"] = {
                "available": resources["gpu"]["available"],
                "memory_percent": resources["gpu"]["memory_percent"] if resources["gpu"]["available"] else 0,
                "name": resources["gpu"].get("name", "") if resources["gpu"]["available"] else "",
                "memory_used": resources["gpu"].get("memory_used", "0 B") if resources["gpu"]["available"] else "0 B",
                "memory_total": resources["gpu"].get("memory_total", "0 B") if resources["gpu"]["available"] else "0 B"
            }
        except Exception as e:
            print(f"[WARN] 资源更新异常: {e}")
        time.sleep(2)


async def _periodic_resource_recording():
    """异步任务：每 30 秒记录资源快照。"""
    import importlib.util
    _resource_monitor_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'utils', 'resource_monitor.py')
    _resource_monitor_spec = importlib.util.spec_from_file_location('utils.resource_monitor', _resource_monitor_path)
    _resource_monitor_module = importlib.util.module_from_spec(_resource_monitor_spec)
    _resource_monitor_spec.loader.exec_module(_resource_monitor_module)
    resource_monitor = _resource_monitor_module.resource_monitor

    while True:
        await asyncio.sleep(30)
        resource_monitor.record_resources()


# ============================================================
# 启动钩子注册
# ============================================================

def register_startup_hooks(app: FastAPI):
    """注册 FastAPI startup 事件。"""
    import importlib.util

    # 加载 resource_monitor 模块
    _resource_monitor_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'utils', 'resource_monitor.py')
    _resource_monitor_spec = importlib.util.spec_from_file_location('utils.resource_monitor', _resource_monitor_path)
    _resource_monitor_module = importlib.util.module_from_spec(_resource_monitor_spec)
    _resource_monitor_spec.loader.exec_module(_resource_monitor_module)
    resource_monitor = _resource_monitor_module.resource_monitor

    @app.on_event("startup")
    async def startup_event():
        add_log("========================================")
        add_log(f"CosyChat 服务启动 v{get_version()}")
        add_log("========================================")

        add_log("正在检查系统资源占用...")
        health_check = resource_monitor.check_resource_health()

        if not health_check['healthy']:
            add_log("⚠️ 资源占用异常警告:", "WARNING")
            for issue in health_check['issues']:
                add_log(f"  - {issue}", "WARNING")
            add_log("服务将继续启动，但建议释放资源后重新启动", "WARNING")
        else:
            add_log("✓ 系统资源占用正常")

        add_log(f"CPU: {health_check['resources']['cpu']['percent']}%")
        add_log(f"内存: {health_check['resources']['memory']['percent']}% (已用: {health_check['resources']['memory']['used']})")
        add_log(f"磁盘: {health_check['resources']['disk']['percent']}% (剩余: {health_check['resources']['disk']['free']})")

        if health_check['resources']['gpu']['available']:
            gpu = health_check['resources']['gpu']
            add_log(f"GPU: {gpu['name']}")
            add_log(f"GPU显存: {gpu['memory_percent']:.2f}% (已用: {gpu['memory_used']})")

        resource_monitor.record_resources()

        resource_thread = threading.Thread(target=_periodic_resource_update_thread, daemon=True)
        resource_thread.start()
        asyncio.create_task(_periodic_resource_recording())
        add_log("资源监控任务已启动（每2秒更新状态）")

        from repositories import init_db
        init_db()
        add_log("SQLite 数据库已初始化")

        load_agent_manager()

        add_log("服务启动完成，模型和代理按需加载")
