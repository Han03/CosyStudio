"""LLM调用日志数据访问层。

重要设计约束（问题分析日志不可丢失）：
  - 无论深度初始化/LLM调用/任何业务流程是否报错，LLM调用日志都必须**成功落盘并永久保留**，
    用于事后排查失败原因、分析LLM输出质量、复现问题。
  - 🔴 日志使用**独立的 SQLite 数据库文件**（llm_call_logs.db），与主业务数据库（app.db）
    物理隔离。同一 db 文件的多连接在 SQLite 中只允许一个写者，当主业务连接持有写事务时，
    日志连接的 commit 会因 database is locked 而失败。
    独立文件彻底消除了锁竞争，保证日志写入不受任何业务事务影响。
"""

import os
import time
import json
import threading
import sqlite3
from typing import Any, Dict, List, Optional

from .base_repository import _DB_PATH


# ==============================================================================
# 日志专用：独立数据库文件 + 独立连接（与主业务完全物理隔离）
# ==============================================================================

# 🔴 关键：日志使用独立的 db 文件，避免与主业务连接竞争写锁
# app.db → llm_call_logs.db
_LOG_DB_PATH = os.path.splitext(_DB_PATH)[0] + "_llm_logs.db"

_log_conn: Optional[sqlite3.Connection] = None
_log_conn_lock = threading.RLock()


def _get_log_conn() -> sqlite3.Connection:
    """获取日志专用的独立 SQLite 连接。

    使用独立的数据库文件（llm_call_logs.db），与主业务数据库（app.db）
    物理隔离，彻底消除 SQLite 单文件多连接的写锁竞争问题。
    """
    global _log_conn
    if _log_conn is None:
        with _log_conn_lock:
            if _log_conn is None:
                os.makedirs(os.path.dirname(_LOG_DB_PATH), exist_ok=True)
                _log_conn = sqlite3.connect(_LOG_DB_PATH, check_same_thread=False, timeout=30.0)
                _log_conn.row_factory = sqlite3.Row
                _log_conn.text_factory = str
                _log_conn.execute("PRAGMA journal_mode=WAL")
                _log_conn.execute("PRAGMA encoding='UTF-8'")
                # 日志连接故意关闭外键约束，避免任何级联影响日志表
                _log_conn.execute("PRAGMA foreign_keys=OFF")
                # 立即同步，确保崩溃/断电日志也不丢
                _log_conn.execute("PRAGMA synchronous=FULL")
                # 日志文件自建表，不依赖主业务连接的 _init_schema
                _log_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS llm_call_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        request_id TEXT DEFAULT '',
                        script_id INTEGER DEFAULT 0,
                        project_id INTEGER DEFAULT 0,
                        executor_name TEXT DEFAULT '',
                        prompt_name TEXT DEFAULT '',
                        model_name TEXT DEFAULT '',
                        system_prompt TEXT DEFAULT '',
                        user_prompt TEXT DEFAULT '',
                        raw_output TEXT DEFAULT '',
                        parsed_output TEXT DEFAULT '',
                        parse_success INTEGER DEFAULT 0,
                        success_strategy TEXT DEFAULT '',
                        strategies_tried INTEGER DEFAULT 0,
                        error_message TEXT DEFAULT '',
                        input_tokens INTEGER DEFAULT 0,
                        output_tokens INTEGER DEFAULT 0,
                        latency_ms INTEGER DEFAULT 0,
                        created_at REAL
                    )
                    """
                )
                _log_conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_llm_call_logs_parse_success ON llm_call_logs(parse_success)"
                )
                _log_conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_llm_call_logs_executor ON llm_call_logs(executor_name, prompt_name)"
                )
                _log_conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_llm_call_logs_created ON llm_call_logs(created_at DESC)"
                )
    return _log_conn


def _reset_log_conn() -> None:
    """关闭并重置日志连接（commit 失败、连接损坏时调用）。

    将 _log_conn 置为 None，下次 _get_log_conn() 会创建全新连接。
    必须在 _log_conn_lock 持有期间调用。
    """
    global _log_conn
    if _log_conn is not None:
        try:
            _log_conn.close()
        except Exception:
            pass
        _log_conn = None


# ==============================================================================
# 裁剪（只按容量裁剪，与业务删除完全无关）
# ==============================================================================

_trim_lock = threading.Lock()
_MAX_LOG_ROWS = 50000
_TRIM_TO_ROWS = 30000


def _try_trim_logs(conn: sqlite3.Connection) -> None:
    """尝试裁剪日志表，避免无限膨胀（仅按行数保留最新 3w 条）。"""
    if not _trim_lock.acquire(blocking=False):
        return
    try:
        count = conn.execute("SELECT COUNT(*) FROM llm_call_logs").fetchone()[0]
        if count > _MAX_LOG_ROWS:
            boundary = conn.execute(
                "SELECT id FROM llm_call_logs ORDER BY id DESC LIMIT 1 OFFSET ?",
                (_TRIM_TO_ROWS - 1,),
            ).fetchone()
            if boundary:
                conn.execute("DELETE FROM llm_call_logs WHERE id < ?", (boundary[0],))
                conn.commit()
    except Exception:
        pass
    finally:
        _trim_lock.release()


# ==============================================================================
# 写入（最关键：独立连接 + 立即 commit + 同步）
# ==============================================================================

def add_llm_call_log(
    request_id: str = "",
    script_id: int = 0,
    project_id: int = 0,
    executor_name: str = "",
    prompt_name: str = "",
    model_name: str = "",
    system_prompt: str = "",
    user_prompt: str = "",
    raw_output: str = "",
    parsed_output: Any = None,
    parse_success: bool = False,
    success_strategy: str = "",
    strategies_tried: int = 0,
    error_message: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
) -> int:
    """添加一条LLM调用日志。

    保证：
      1. 使用独立 sqlite3 连接（_get_log_conn）写日志，与主业务事务完全隔离；
      2. INSERT 后立即 commit，并由 PRAGMA synchronous=FULL 保证落盘；
      3. 即使后续流程抛出任何异常、触发项目级联删除，本日志已永久保留。
    """
    now = time.time()
    parsed_text = ""
    if parsed_output is not None:
        try:
            parsed_text = json.dumps(parsed_output, ensure_ascii=False)
        except Exception:
            parsed_text = str(parsed_output)

    def _truncate(text: Any, limit: int) -> str:
        if text is None:
            return ""
        s = text if isinstance(text, str) else str(text)
        return s if len(s) <= limit else s[:limit]

    log_id = 0
    # 用 log_conn 专属锁，避免与主业务 _lock 互相竞争，也保证日志写的顺序
    with _log_conn_lock:
        conn = _get_log_conn()
        try:
            cursor = conn.execute(
                """
                INSERT INTO llm_call_logs (
                    request_id, script_id, project_id, executor_name, prompt_name, model_name,
                    system_prompt, user_prompt, raw_output, parsed_output,
                    parse_success, success_strategy, strategies_tried, error_message,
                    input_tokens, output_tokens, latency_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _truncate(request_id, 128),
                    int(script_id or 0),
                    int(project_id or 0),
                    _truncate(executor_name, 128),
                    _truncate(prompt_name, 128),
                    _truncate(model_name, 128),
                    _truncate(system_prompt, 32768),
                    _truncate(user_prompt, 131072),
                    _truncate(raw_output, 131072),
                    _truncate(parsed_text, 131072),
                    1 if parse_success else 0,
                    _truncate(success_strategy, 64),
                    int(strategies_tried or 0),
                    _truncate(error_message, 1024),
                    int(input_tokens or 0),
                    int(output_tokens or 0),
                    int(latency_ms or 0),
                    now,
                ),
            )
            conn.commit()  # ← 关键：独立连接立即提交，不受主事务影响
            log_id = cursor.lastrowid or 0
        except Exception as write_ex:
            # 🔴 必须 rollback：commit 失败后连接会残留未提交事务，
            # 如果不回滚，后续所有 INSERT + commit 都会因脏事务状态而持续失败，
            # 导致日志永久丢失（autoincrement 计数器推进但表为空）。
            try:
                conn.rollback()
            except Exception:
                # rollback 也失败说明连接本身已损坏，必须重建
                _reset_log_conn()
                conn = _get_log_conn()
            # 用项目日志系统记录错误（不仅仅输出到 stderr）
            try:
                from utils.logger import log_manager
                log_manager.get_logger("llm_call_log").error(
                    f"[LLM_LOG_WRITE_FAILED] {type(write_ex).__name__}: {write_ex}"
                )
            except Exception:
                import sys as _sys
                print(f"[LLM_LOG_WRITE_FAILED] {write_ex}", file=_sys.stderr)
            return 0

    # 裁剪后台异步一点，不影响返回
    try:
        _try_trim_logs(_get_log_conn())
    except Exception:
        pass

    return log_id


def update_llm_call_log(
    log_id: int,
    raw_output: str = "",
    parsed_output: Any = None,
    parse_success: bool = False,
    success_strategy: str = "",
    strategies_tried: int = 0,
    error_message: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
) -> bool:
    """更新已有的LLM调用日志（用于 parse_llm_json 补充解析结果，避免重复插入）。

    典型场景：model_executor 的 finally 块先 INSERT 一条包含 raw_output 的日志并返回 log_id，
    随后 parse_llm_json 解析完成后通过本函数 UPDATE 同一条记录，补充 parsed_output / 解析策略等字段。

    Returns:
        True 表示更新成功，False 表示失败（log_id 不存在或写入异常）。
    """
    if not log_id or log_id <= 0:
        return False

    parsed_text = ""
    if parsed_output is not None:
        try:
            parsed_text = json.dumps(parsed_output, ensure_ascii=False)
        except Exception:
            parsed_text = str(parsed_output)

    def _truncate(text: Any, limit: int) -> str:
        if text is None:
            return ""
        s = text if isinstance(text, str) else str(text)
        return s if len(s) <= limit else s[:limit]

    with _log_conn_lock:
        conn = _get_log_conn()
        try:
            conn.execute(
                """
                UPDATE llm_call_logs SET
                    raw_output = ?,
                    parsed_output = ?,
                    parse_success = ?,
                    success_strategy = ?,
                    strategies_tried = ?,
                    error_message = ?,
                    input_tokens = ?,
                    output_tokens = ?,
                    latency_ms = ?
                WHERE id = ?
                """,
                (
                    _truncate(raw_output, 131072),
                    _truncate(parsed_text, 131072),
                    1 if parse_success else 0,
                    _truncate(success_strategy, 64),
                    int(strategies_tried or 0),
                    _truncate(error_message, 1024),
                    int(input_tokens or 0),
                    int(output_tokens or 0),
                    int(latency_ms or 0),
                    int(log_id),
                ),
            )
            conn.commit()
            return True
        except Exception as write_ex:
            try:
                conn.rollback()
            except Exception:
                _reset_log_conn()
            try:
                from utils.logger import log_manager
                log_manager.get_logger("llm_call_log").error(
                    f"[LLM_LOG_UPDATE_FAILED] {type(write_ex).__name__}: {write_ex}"
                )
            except Exception:
                import sys as _sys
                print(f"[LLM_LOG_UPDATE_FAILED] {write_ex}", file=_sys.stderr)
            return False


# ==============================================================================
# 查询（必须用日志连接，因为数据在独立的 db 文件中）
# ==============================================================================

def get_llm_call_log(log_id: int) -> Optional[Dict[str, Any]]:
    """获取单条LLM调用日志。"""
    conn = _get_log_conn()
    row = conn.execute(
        "SELECT * FROM llm_call_logs WHERE id=?", (log_id,)
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    try:
        result["parse_success"] = bool(result.get("parse_success", 0))
    except Exception:
        pass
    return result


def list_llm_call_logs(
    parse_success: Optional[bool] = None,
    executor_name: str = "",
    prompt_name: str = "",
    script_id: int = 0,
    project_id: int = 0,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """查询LLM调用日志列表。"""
    conn = _get_log_conn()
    clauses = []
    params: List[Any] = []
    if parse_success is not None:
        clauses.append("parse_success = ?")
        params.append(1 if parse_success else 0)
    if executor_name:
        clauses.append("executor_name = ?")
        params.append(executor_name)
    if prompt_name:
        clauses.append("prompt_name = ?")
        params.append(prompt_name)
    if script_id:
        clauses.append("script_id = ?")
        params.append(script_id)
    if project_id:
        clauses.append("project_id = ?")
        params.append(project_id)

    sql = "SELECT * FROM llm_call_logs"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([int(limit), int(offset)])

    rows = conn.execute(sql, params).fetchall()
    results = []
    for row in rows:
        d = dict(row)
        try:
            d["parse_success"] = bool(d.get("parse_success", 0))
        except Exception:
            pass
        results.append(d)
    return results


def get_failed_parse_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """获取解析失败的日志（用于分析）。"""
    return list_llm_call_logs(parse_success=False, limit=limit)


# ==============================================================================
# 仅按时间归档清理（与业务脚本/项目删除完全无关）
# ==============================================================================

def delete_old_llm_call_logs(older_than_days: int = 30) -> int:
    """删除N天前的旧日志，返回删除条数。

    注意：这里只按时间归档清理（默认保留 30 天），**绝不会因为任何项目/脚本删除而触发**。
    调用方请仅在后台归档任务中调用本函数。
    """
    import time as _time
    cutoff = _time.time() - float(max(1, older_than_days)) * 86400.0
    with _log_conn_lock:
        conn = _get_log_conn()
        cur = conn.execute("DELETE FROM llm_call_logs WHERE created_at < ?", (cutoff,))
        conn.commit()
        return cur.rowcount or 0
