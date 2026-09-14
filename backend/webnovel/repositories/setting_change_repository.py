"""webnovel_setting_change 数据访问层（基础设定变更日志表）。

记录角色卡等基础设定的每次变更（创建/能力更新/身份揭露/删除），
携带变更前后快照（JSON），供"取消应用结果"时按章节回退。
entity_type / change_type 为通用字段，后续可扩展记录其他基础设定。
"""

import time
from typing import Optional, List, Dict
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_setting_change(project_id: int, chapter_number: int,
                       entity_type: str, entity_id: int,
                       change_type: str,
                       before_data: str = "", after_data: str = "") -> Optional[dict]:
    """记录一条基础设定变更。before/after 为 JSON 快照字符串。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """INSERT INTO webnovel_setting_change
               (project_id, chapter_number, entity_type, entity_id, change_type,
                before_data, after_data, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (safe_int(project_id), safe_int(chapter_number),
             safe_str(entity_type), safe_int(entity_id), safe_str(change_type),
             safe_str(before_data), safe_str(after_data), now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id,
                "chapter_number": chapter_number, "entity_type": entity_type,
                "entity_id": entity_id, "change_type": change_type,
                "before_data": before_data, "after_data": after_data}


def get_setting_changes_by_chapter(project_id: int, chapter_number: int) -> List[dict]:
    """获取指定章节的基础设定变更记录（按创建时间排序，回退时逆序处理）。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """SELECT * FROM webnovel_setting_change
               WHERE project_id = ? AND chapter_number = ? ORDER BY id""",
            (safe_int(project_id), safe_int(chapter_number))
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_setting_changes_by_chapter(project_id: int, chapter_number: int) -> int:
    """删除指定章节的基础设定变更记录（回退完成后清理），返回删除数。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "DELETE FROM webnovel_setting_change WHERE project_id = ? AND chapter_number = ?",
            (safe_int(project_id), safe_int(chapter_number))
        )
        conn.commit()
        return cursor.rowcount
