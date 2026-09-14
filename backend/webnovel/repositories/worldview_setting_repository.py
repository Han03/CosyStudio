"""webnovel_worldview_setting 数据访问层（世界观设定条目表）。

用于记录 fact_recorder 每章新交代的世界观设定（原追加进 webnovel_worldview.world_summary 字符串），
按章节独立存储，支持按章查询/删除（取消应用结果时回退）。
"""

import time
from typing import Optional, List, Dict
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_worldview_setting(project_id: int, chapter_number: int,
                          name: str, content: str, category: str = "") -> Optional[dict]:
    """新增世界观设定条目。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """INSERT INTO webnovel_worldview_setting
               (project_id, chapter_number, name, content, category, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (safe_int(project_id), safe_int(chapter_number),
             safe_str(name), safe_str(content), safe_str(category), now, now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id,
                "chapter_number": chapter_number, "name": name,
                "content": content, "category": category}


def get_worldview_settings_by_project(project_id: int) -> List[dict]:
    """获取项目全部世界观设定条目（按章排序）。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """SELECT * FROM webnovel_worldview_setting
               WHERE project_id = ? ORDER BY chapter_number, id""",
            (safe_int(project_id),)
        )
        return [dict(row) for row in cursor.fetchall()]


def get_worldview_settings_by_chapter(project_id: int, chapter_number: int) -> List[dict]:
    """获取指定章节的世界观设定条目。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """SELECT * FROM webnovel_worldview_setting
               WHERE project_id = ? AND chapter_number = ? ORDER BY id""",
            (safe_int(project_id), safe_int(chapter_number))
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_worldview_settings_by_chapter(project_id: int, chapter_number: int) -> int:
    """删除指定章节的世界观设定条目，返回删除数。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "DELETE FROM webnovel_worldview_setting WHERE project_id = ? AND chapter_number = ?",
            (safe_int(project_id), safe_int(chapter_number))
        )
        conn.commit()
        return cursor.rowcount
