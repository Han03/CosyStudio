"""写作任务数据访问层。"""

import time
import json
from typing import Optional, List, Dict, Any
from repositories.base_repository import _get_conn, _lock, _loads


def add_writing_task(script_id: int, chapter_index: int, task_type: str,
                     prompt: str = "", context: str = "") -> dict:
    """添加写作任务。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO script_writing_tasks (script_id, chapter_index, task_type, prompt, context,
                                               status, progress, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (script_id, chapter_index, task_type, prompt, context, "pending", 0, now, now)
        )
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "script_id": script_id,
            "chapter_index": chapter_index,
            "task_type": task_type,
            "prompt": prompt,
            "context": context,
            "status": "pending",
            "progress": 0,
            "created_at": now,
            "updated_at": now,
        }


def get_writing_tasks(script_id: int, chapter_index: int = None, status: str = "") -> List[dict]:
    """获取写作任务列表。"""
    with _lock:
        conn = _get_conn()
        query = "SELECT * FROM script_writing_tasks WHERE script_id = ?"
        params = [script_id]
        
        if chapter_index is not None:
            query += " AND chapter_index = ?"
            params.append(chapter_index)
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY created_at DESC"
        
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_writing_task(script_id: int, task_id: int) -> Optional[dict]:
    """获取单个写作任务。"""
    with _lock:
        conn = _get_conn()
        if script_id is None or script_id <= 0:
            cursor = conn.execute(
                "SELECT * FROM script_writing_tasks WHERE id = ?",
                (task_id,)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM script_writing_tasks WHERE script_id = ? AND id = ?",
                (script_id, task_id)
            )
        row = cursor.fetchone()
        return dict(row) if row else None


def update_writing_task(task_id: int, **kwargs) -> bool:
    """更新写作任务。"""
    with _lock:
        conn = _get_conn()
        kwargs["updated_at"] = time.time()
        keys = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(task_id)
        conn.execute(
            f"UPDATE script_writing_tasks SET {keys} WHERE id = ?",
            values
        )
        conn.commit()
        return True


def delete_writing_task(task_id: int) -> bool:
    """删除写作任务。"""
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM script_writing_tasks WHERE id = ?", (task_id,))
        conn.commit()
        return True


def get_running_tasks() -> List[dict]:
    """获取所有运行中的写作任务。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM script_writing_tasks WHERE status = ? ORDER BY created_at DESC",
            ("running",)
        )
        return [dict(row) for row in cursor.fetchall()]


def get_active_writing_tasks() -> List[dict]:
    """获取所有进行中的写作任务（pending 或 running）。

    pending 仅在任务创建后、工作流启动前的极短窗口存在；
    全局互斥检查需同时统计两种状态，否则跨剧本并发请求可从 pending 窗口穿过。
    """
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM script_writing_tasks WHERE status IN ('pending', 'running') ORDER BY created_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]
