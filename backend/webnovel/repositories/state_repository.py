"""webnovel_state数据访问层。"""

import time
from typing import Optional, List, Dict, Any
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_webnovel_state(project_id: int, **kwargs) -> dict:
    """添加webnovel状态。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_state (project_id, current_chapter, total_words, volumes_completed, current_volume, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (safe_int(project_id),
             safe_int(kwargs.get("current_chapter", 0)), safe_int(kwargs.get("total_words", 0)),
             safe_str(kwargs.get("volumes_completed", "")),
             safe_int(kwargs.get("current_volume", 1)), now, now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id, **kwargs, "created_at": now, "updated_at": now}


def get_webnovel_state(project_id: int, state_id: int) -> Optional[dict]:
    """获取单个webnovel状态。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_state WHERE project_id = ? AND id = ?",
            (project_id, state_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_webnovel_state_by_project(project_id: int) -> Optional[dict]:
    """获取项目的webnovel状态。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_state WHERE project_id = ?",
            (project_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def update_webnovel_state(state_id: int, **kwargs) -> bool:
    """更新webnovel状态。"""
    with _lock:
        conn = _get_conn()
        kwargs["updated_at"] = time.time()
        keys = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(state_id)
        conn.execute(
            f"UPDATE webnovel_state SET {keys} WHERE id = ?",
            values
        )
        conn.commit()
        return True


def add_plot_thread(project_id: int, thread_type: str = "", content: str = "", status: str = "", chapter: int = 0) -> dict:
    """添加剧情线程。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO webnovel_plot_thread (project_id, thread_type, content, status, chapter) VALUES (?, ?, ?, ?, ?)",
            (project_id, thread_type, content, status, chapter)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id, "thread_type": thread_type, "content": content, "status": status, "chapter": chapter}


def get_plot_threads(project_id: int, thread_type: str = "") -> List[dict]:
    """获取剧情线程列表。"""
    with _lock:
        conn = _get_conn()
        if thread_type:
            cursor = conn.execute(
                "SELECT * FROM webnovel_plot_thread WHERE project_id = ? AND thread_type = ?",
                (project_id, thread_type)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM webnovel_plot_thread WHERE project_id = ?",
                (project_id,)
            )
        return [dict(row) for row in cursor.fetchall()]