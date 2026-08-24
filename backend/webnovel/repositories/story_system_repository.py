"""webnovel_master_setting / webnovel_anti_pattern 数据访问层。"""

import json
import time
from typing import Dict, List, Optional
from repositories.base_repository import _get_conn, _lock, safe_int


def save_master_setting(project_id: int, content: Dict) -> Dict:
    """保存或更新项目的 MASTER_SETTING 内容（upsert）。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        content_json = json.dumps(content, ensure_ascii=False)

        cursor = conn.execute(
            "SELECT id FROM webnovel_master_setting WHERE project_id = ?",
            (safe_int(project_id),)
        )
        existing = cursor.fetchone()

        if existing:
            conn.execute(
                "UPDATE webnovel_master_setting SET content_json = ?, updated_at = ? WHERE project_id = ?",
                (content_json, now, safe_int(project_id))
            )
            conn.commit()
            return {"id": existing["id"], "project_id": project_id}
        else:
            cursor = conn.execute(
                """
                INSERT INTO webnovel_master_setting (project_id, content_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (safe_int(project_id), content_json, now, now)
            )
            conn.commit()
            return {"id": cursor.lastrowid, "project_id": project_id}


def get_master_setting(project_id: int) -> Optional[Dict]:
    """获取项目的 MASTER_SETTING 内容。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_master_setting WHERE project_id = ?",
            (safe_int(project_id),)
        )
        row = cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        try:
            result["content"] = json.loads(result["content_json"]) if result["content_json"] else {}
        except json.JSONDecodeError:
            result["content"] = {}
        return result


def save_anti_patterns(project_id: int, anti_patterns: List[Dict]) -> int:
    """保存项目的反套路模式列表（先删后插）。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        pid = safe_int(project_id)

        conn.execute("DELETE FROM webnovel_anti_pattern WHERE project_id = ?", (pid,))

        count = 0
        for ap in anti_patterns:
            conn.execute(
                """
                INSERT INTO webnovel_anti_pattern (project_id, pattern, severity, category, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    ap.get("pattern", ""),
                    ap.get("severity", "medium"),
                    ap.get("category", ""),
                    ap.get("description", ""),
                    now
                )
            )
            count += 1
        conn.commit()
        return count


def get_anti_patterns(project_id: int) -> List[Dict]:
    """获取项目的反套路模式列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_anti_pattern WHERE project_id = ? ORDER BY id",
            (safe_int(project_id),)
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_master_setting(project_id: int) -> None:
    """删除项目的 MASTER_SETTING。"""
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM webnovel_master_setting WHERE project_id = ?", (safe_int(project_id),))
        conn.commit()


def delete_anti_patterns(project_id: int) -> None:
    """删除项目的所有反套路模式。"""
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM webnovel_anti_pattern WHERE project_id = ?", (safe_int(project_id),))
        conn.commit()
