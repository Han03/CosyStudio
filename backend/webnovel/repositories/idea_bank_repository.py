import time
import json
from typing import Dict, Optional
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_idea_bank(project_id: int, selected_idea: Dict = None, constraints_inherited: Dict = None) -> Dict:
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_idea_bank (project_id, selected_idea, constraints_inherited, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                safe_int(project_id),
                safe_str(selected_idea or {}),
                safe_str(constraints_inherited or {}),
                now,
                now
            )
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id}


def get_idea_bank(project_id: int) -> Optional[Dict]:
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_idea_bank WHERE project_id = ?",
            (project_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        try:
            result["selected_idea"] = json.loads(result["selected_idea"]) if result["selected_idea"] else {}
            result["constraints_inherited"] = json.loads(result["constraints_inherited"]) if result["constraints_inherited"] else {}
        except json.JSONDecodeError:
            result["selected_idea"] = {}
            result["constraints_inherited"] = {}
        return result


def update_idea_bank(project_id: int, selected_idea: Dict = None, constraints_inherited: Dict = None) -> None:
    with _lock:
        conn = _get_conn()
        now = time.time()
        updates = []
        params = []
        
        if selected_idea is not None:
            updates.append("selected_idea = ?")
            params.append(json.dumps(selected_idea, ensure_ascii=False))
        
        if constraints_inherited is not None:
            updates.append("constraints_inherited = ?")
            params.append(json.dumps(constraints_inherited, ensure_ascii=False))
        
        updates.append("updated_at = ?")
        params.append(now)
        params.append(project_id)
        
        conn.execute(
            f"UPDATE webnovel_idea_bank SET {', '.join(updates)} WHERE project_id = ?",
            params
        )
        conn.commit()


def delete_idea_bank(project_id: int) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM webnovel_idea_bank WHERE project_id = ?", (project_id,))
        conn.commit()


def get_idea_bank_by_project(project_id: int) -> Optional[Dict]:
    """获取项目的创意库（别名函数）。"""
    return get_idea_bank(project_id)
