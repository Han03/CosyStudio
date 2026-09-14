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
    """获取指定章节的最新一条元数据（多版本按 id 取最新）。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """SELECT * FROM webnovel_chapter_meta
               WHERE project_id = ? AND chapter_number = ?
               ORDER BY id DESC LIMIT 1""",
            (project_id, chapter_number)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_chapter_meta_list(project_id: int) -> List[dict]:
    """获取项目各章节的最新一条元数据（每章一条，取各章 id 最大版本）。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """SELECT m.* FROM webnovel_chapter_meta m
               JOIN (SELECT chapter_number, MAX(id) AS max_id
                     FROM webnovel_chapter_meta WHERE project_id = ?
                     GROUP BY chapter_number) latest
                 ON m.id = latest.max_id
               ORDER BY m.chapter_number""",
            (project_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_chapter_meta(project_id: int, chapter_number: int) -> int:
    """删除指定章节的所有元数据版本。返回删除数。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "DELETE FROM webnovel_chapter_meta WHERE project_id = ? AND chapter_number = ?",
            (safe_int(project_id), safe_int(chapter_number))
        )
        conn.commit()
        return cursor.rowcount