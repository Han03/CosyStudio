import os
import json
import time
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from utils.logger import logger

# ==============================================================================
# SQLite 参数绑定安全转换工具（统一维护，避免在各repository中重复定义）
# ==============================================================================

def safe_str(value: Any, default: str = "") -> str:
    """将任意值安全转换为 SQLite 支持的字符串类型。

    - None → default
    - str → 原样返回
    - int/float/bool → str() 转换
    - list/dict → json.dumps(ensure_ascii=False) 序列化
    - 其他类型 → str() 兜底
    """
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (list, dict)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def safe_int(value: Any, default: int = 0) -> int:
    """将任意值安全转换为整数（用于布尔标志、计数字段）。

    - None → default
    - bool → True=1 / False=0
    - int → 原样返回
    - str → 常见布尔字符串("true"/"1"/"yes"/"是")转1，其他尝试int()
    - 其他 → int() 兜底，失败返回 default
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "是"):
            return 1
        if lowered in ("false", "0", "no", "否", ""):
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    try:
        return int(value)
    except Exception:
        return default


# ==============================================================================
# 数据库连接与初始化
# ==============================================================================

from core.paths import CACHE_DIR as _DB_DIR, MEDIA_DIR as _MEDIA_DIR
_DB_PATH = os.path.join(_DB_DIR, "app.db")

_conn: Optional[sqlite3.Connection] = None
_lock = threading.RLock()


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                os.makedirs(_DB_DIR, exist_ok=True)
                _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
                _conn.row_factory = sqlite3.Row
                _conn.text_factory = str
                _conn.execute("PRAGMA journal_mode=WAL")
                _conn.execute("PRAGMA encoding='UTF-8'")
                _conn.execute("PRAGMA foreign_keys=ON")  # 启用外键约束，保证 ON DELETE CASCADE 生效
                _init_schema(_conn)
                logger.info(f"[Database] SQLite 已初始化: {_DB_PATH}")
    return _conn


from .schema import _init_schema




def init_db():
    _get_conn()


def _loads(s: Optional[str]) -> Any:
    if not s:
        return {}
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {}


def _content_hash(content: str) -> str:
    import hashlib
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def close():
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None