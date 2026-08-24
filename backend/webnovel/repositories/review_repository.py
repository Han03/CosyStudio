"""webnovel_review数据访问层。"""

import time
from typing import Optional, List, Dict, Any
from repositories.base_repository import _get_conn, _lock


def add_review_record(project_id: int, chapter_number: int, review_type: str = "",
                      score: int = 0, feedback: str = "", suggestions: str = "") -> dict:
    """添加审查记录。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_review_record (project_id, chapter_number, review_type,
                                                  score, feedback, suggestions, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, chapter_number, review_type, score, feedback, suggestions, now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id, "chapter_number": chapter_number,
                "review_type": review_type, "score": score, "feedback": feedback,
                "suggestions": suggestions, "created_at": now}


def get_review_records(project_id: int, chapter_number: int = None) -> List[dict]:
    """获取审查记录列表。"""
    with _lock:
        conn = _get_conn()
        if chapter_number is not None:
            cursor = conn.execute(
                "SELECT * FROM webnovel_review_record WHERE project_id = ? AND chapter_number = ?",
                (project_id, chapter_number)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM webnovel_review_record WHERE project_id = ?",
                (project_id,)
            )
        return [dict(row) for row in cursor.fetchall()]


def get_chapter_review_summary(project_id: int, chapter_number: int) -> Dict[str, Any]:
    """获取章节审查汇总。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """
            SELECT review_type, AVG(score) as avg_score, COUNT(*) as count
            FROM webnovel_review_record
            WHERE project_id = ? AND chapter_number = ?
            GROUP BY review_type
            """,
            (project_id, chapter_number)
        )
        rows = cursor.fetchall()
        summary = {}
        for row in rows:
            summary[row[0]] = {"avg_score": row[1], "count": row[2]}
        return summary


def delete_review_record(record_id: int) -> bool:
    """删除审查记录。"""
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM webnovel_review_record WHERE id = ?", (record_id,))
        conn.commit()
        return True


def delete_chapter_review_records(project_id: int, chapter_number: int) -> bool:
    """删除章节的所有审查记录。"""
    with _lock:
        conn = _get_conn()
        conn.execute(
            "DELETE FROM webnovel_review_record WHERE project_id = ? AND chapter_number = ?",
            (project_id, chapter_number)
        )
        conn.commit()
        return True
