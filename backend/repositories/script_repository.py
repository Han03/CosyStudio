from typing import Any, Dict, List, Optional

from .base_repository import _get_conn, _lock


def add_script(book_id: int, name: str, description: str = "",
               chapter_count: int = 0, task_id: str = "",
               status: str = "pending") -> Optional[int]:
    import time
    conn = _get_conn()
    now = time.time()
    with _lock:
        cur = conn.execute(
            """INSERT INTO scripts
               (book_id, name, chapter_count, status, description, task_id, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (book_id, name, chapter_count, status, description, task_id, now, now),
        )
        conn.commit()
        return cur.lastrowid


def get_script(script_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT * FROM scripts WHERE id=?", (script_id,)
        ).fetchone()
    return dict(row) if row else None


def get_scripts_by_book(book_id: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            "SELECT * FROM scripts WHERE book_id=? ORDER BY created_at DESC",
            (book_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_scripts_by_task_id(task_id: str) -> List[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            "SELECT * FROM scripts WHERE task_id=? ORDER BY created_at DESC",
            (task_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_script(script_id: int, **fields):
    if not fields:
        return
    import time
    conn = _get_conn()
    now = time.time()
    fields["updated_at"] = now
    set_clause = ", ".join([f"{k}=?" for k in fields])
    params = list(fields.values()) + [script_id]
    with _lock:
        conn.execute(
            f"UPDATE scripts SET {set_clause} WHERE id=?", params
        )
        conn.commit()


def delete_script(script_id: int) -> bool:
    """删除剧本及其台词/章节关联数据。

    ⚠️ 【严禁删除 llm_call_logs 表】—— LLM 调用日志是问题分析依据，必须永久保留。
       即便删除了剧本，历史上针对该 script_id 的 LLM 调用记录、初始化过程记录
       都必须保留在 llm_call_logs 中，便于追溯和复现问题。
       本函数只允许操作：scripts / script_lines / script_chapters 三张白名单表。
    """
    conn = _get_conn()
    with _lock:
        # 白名单 + 前缀二次校验，防止误删 llm_call_logs 等其他表
        allowed_script_tables = [
            ("script_lines", True),       # 允许（script_ 前缀）
            ("script_chapters", True),    # 允许（script_ 前缀）
        ]
        from utils.logger import logger as _l
        for tbl, require_prefix in allowed_script_tables:
            if require_prefix and not tbl.startswith("script_"):
                _l.warning(f"[script_repository] 拒绝删除非 script_ 表: {tbl}（已跳过）")
                continue
            try:
                conn.execute(f"DELETE FROM {tbl} WHERE script_id=?", (script_id,))
            except Exception as e:
                _l.warning(f"[script_repository] 清理 {tbl} 时忽略错误: {e}")
        # 删除主表（单独处理，白名单明确允许）
        cur = conn.execute("DELETE FROM scripts WHERE id=?", (script_id,))
        conn.commit()
    return (cur.rowcount or 0) > 0