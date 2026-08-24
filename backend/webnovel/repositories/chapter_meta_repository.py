"""webnovel_chapter_meta数据访问层。"""

import time
from typing import Optional, List, Dict, Any
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_chapter_meta(project_id: int, chapter_number: int, **kwargs) -> dict:
    """添加章节元数据。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_chapter_meta (project_id, chapter_number, hook_type, hook_content, hook_strength,
                                                opening_pattern, hook_pattern, emotion_rhythm, info_density,
                                                ending_time, ending_location, ending_emotion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (safe_int(project_id), safe_int(chapter_number),
             safe_str(kwargs.get("hook_type", "")), safe_str(kwargs.get("hook_content", "")),
             safe_str(kwargs.get("hook_strength", "")),
             safe_str(kwargs.get("opening_pattern", "")), safe_str(kwargs.get("hook_pattern", "")),
             safe_str(kwargs.get("emotion_rhythm", "")),
             safe_str(kwargs.get("info_density", "")), safe_str(kwargs.get("ending_time", "")),
             safe_str(kwargs.get("ending_location", "")), safe_str(kwargs.get("ending_emotion", "")))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id, "chapter_number": chapter_number, **kwargs}


def get_chapter_meta(project_id: int, chapter_number: int) -> Optional[dict]:
    """获取章节元数据。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_chapter_meta WHERE project_id = ? AND chapter_number = ?",
            (project_id, chapter_number)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_chapter_meta_list(project_id: int) -> List[dict]:
    """获取项目的章节元数据列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_chapter_meta WHERE project_id = ? ORDER BY chapter_number",
            (project_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def update_chapter_meta(meta_id: int, **kwargs) -> bool:
    """更新章节元数据。"""
    with _lock:
        conn = _get_conn()
        keys = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(meta_id)
        conn.execute(
            f"UPDATE webnovel_chapter_meta SET {keys} WHERE id = ?",
            values
        )
        conn.commit()
        return True