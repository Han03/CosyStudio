"""章节版本数据访问层。"""

import time
from typing import List, Dict, Optional
from repositories.base_repository import _get_conn, _lock


def add_chapter_version(script_id: int, chapter_index: int, content: str) -> dict:
    """添加章节版本记录。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        word_count = len(content)
        cursor = conn.execute(
            """
            INSERT INTO script_chapter_versions 
            (script_id, chapter_index, content, word_count, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (script_id, chapter_index, content, word_count, now)
        )
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "script_id": script_id,
            "chapter_index": chapter_index,
            "content": content,
            "word_count": word_count,
            "created_at": now,
        }


def get_chapter_versions(script_id: int, chapter_index: int) -> List[dict]:
    """获取章节的所有版本记录（按时间倒序）。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """
            SELECT * FROM script_chapter_versions 
            WHERE script_id = ? AND chapter_index = ?
            ORDER BY created_at DESC
            """,
            (script_id, chapter_index)
        )
        return [dict(row) for row in cursor.fetchall()]


def get_chapter_version_detail(script_id: int, version_id: int) -> Optional[dict]:
    """获取单个版本详情。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """
            SELECT * FROM script_chapter_versions 
            WHERE script_id = ? AND id = ?
            """,
            (script_id, version_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def delete_chapter_versions(script_id: int, chapter_index: int) -> bool:
    """删除章节的所有版本记录。"""
    with _lock:
        conn = _get_conn()
        conn.execute(
            """
            DELETE FROM script_chapter_versions 
            WHERE script_id = ? AND chapter_index = ?
            """,
            (script_id, chapter_index)
        )
        conn.commit()
        return True


def delete_chapter_version(script_id: int, version_id: int) -> bool:
    """删除单个版本记录。"""
    with _lock:
        conn = _get_conn()
        conn.execute(
            """
            DELETE FROM script_chapter_versions 
            WHERE script_id = ? AND id = ?
            """,
            (script_id, version_id)
        )
        conn.commit()
        return True


def get_chapter_version_count(script_id: int, chapter_index: int) -> int:
    """获取章节的版本数量。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM script_chapter_versions 
            WHERE script_id = ? AND chapter_index = ?
            """,
            (script_id, chapter_index)
        )
        row = cursor.fetchone()
        return row[0] if row else 0
