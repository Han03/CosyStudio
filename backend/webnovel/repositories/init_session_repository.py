import time
import json
from typing import Dict, Optional

from repositories.base_repository import _get_conn, _lock


def create_init_session(script_id: int) -> Dict:
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_init_session 
            (script_id, current_step, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (script_id, 2, "active", now, now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "script_id": script_id, "current_step": 2, "status": "active"}


def get_init_session(script_id: int) -> Optional[Dict]:
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_init_session WHERE script_id = ? AND status = 'active'",
            (script_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def update_init_session(session_id: int, **kwargs):
    with _lock:
        conn = _get_conn()
        kwargs["updated_at"] = time.time()
        keys = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(session_id)
        conn.execute(
            f"UPDATE webnovel_init_session SET {keys} WHERE id = ?",
            values
        )
        conn.commit()


def advance_init_session(session_id: int, next_step: int):
    with _lock:
        conn = _get_conn()
        conn.execute(
            "UPDATE webnovel_init_session SET current_step = ?, updated_at = ? WHERE id = ?",
            (next_step, time.time(), session_id)
        )
        conn.commit()


def complete_init_session(session_id: int):
    with _lock:
        conn = _get_conn()
        conn.execute(
            "UPDATE webnovel_init_session SET status = 'completed', updated_at = ? WHERE id = ?",
            (time.time(), session_id)
        )
        conn.commit()


def get_completed_init_session(script_id: int) -> Optional[Dict]:
    """获取已完成的初始化会话（用于重复初始化时恢复历史数据）。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_init_session WHERE script_id = ? AND status = 'completed' ORDER BY id DESC LIMIT 1",
            (script_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

def delete_init_session(session_id: int):
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM webnovel_init_session WHERE id = ?", (session_id,))
        conn.commit()


def save_step_data(session_id: int, step: int, data: Dict):
    with _lock:
        conn = _get_conn()
        now = time.time()
        
        step_map = {
            2: "project_data",
            3: "protagonist_data",
            4: "golden_finger_data",
            5: "world_data",
            6: "constraints_data"
        }
        
        field = step_map.get(step)
        if field:
            conn.execute(
                f"UPDATE webnovel_init_session SET {field} = ?, updated_at = ? WHERE id = ?",
                (json.dumps(data, ensure_ascii=False), now, session_id)
            )
            conn.commit()


def save_relationship_data(session_id: int, data: Dict):
    with _lock:
        conn = _get_conn()
        conn.execute(
            "UPDATE webnovel_init_session SET relationship_data = ?, updated_at = ? WHERE id = ?",
            (json.dumps(data, ensure_ascii=False), time.time(), session_id)
        )
        conn.commit()


def save_ai_generated_data(session_id: int, data: Dict):
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT ai_generated_data FROM webnovel_init_session WHERE id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        existing = {}
        if row and row[0]:
            try:
                existing = json.loads(row[0])
            except json.JSONDecodeError:
                existing = {}
        existing.update(data)
        conn.execute(
            "UPDATE webnovel_init_session SET ai_generated_data = ?, updated_at = ? WHERE id = ?",
            (json.dumps(existing, ensure_ascii=False), time.time(), session_id)
        )
        conn.commit()


def get_all_init_data(session_id: int) -> Dict:
    with _lock:
        conn = _get_conn()
        cursor = conn.execute("SELECT * FROM webnovel_init_session WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        if not row:
            return {}
        
        result = dict(row)
        for key in ["project_data", "protagonist_data", "relationship_data", 
                   "golden_finger_data", "world_data", "constraints_data", "ai_generated_data"]:
            if result[key]:
                try:
                    result[key] = json.loads(result[key])
                except json.JSONDecodeError:
                    result[key] = {}
        return result