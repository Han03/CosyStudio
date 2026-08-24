"""webnovel_golden_finger数据访问层。"""

import time
from typing import Optional, List, Dict, Any
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_golden_finger(project_id: int, **kwargs) -> dict:
    """添加金手指设定。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_golden_finger (project_id, genre_fit, main_role, visibility, type,
                                                core_function, visual_expression, trigger_condition,
                                                acquisition_event, cost_limitation, irreversible_cost,
                                                cooldown_limit, forbidden_items, failure_penalty,
                                                counter_method, anti_trope_alignment, hard_constraint_binding,
                                                protagonist_flaw_effect, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (safe_int(project_id),
             safe_str(kwargs.get("genre_fit", "")), safe_str(kwargs.get("main_role", "")),
             safe_str(kwargs.get("visibility", "")),
             safe_str(kwargs.get("type", "")), safe_str(kwargs.get("core_function", "")),
             safe_str(kwargs.get("visual_expression", "")),
             safe_str(kwargs.get("trigger_condition", "")), safe_str(kwargs.get("acquisition_event", "")),
             safe_str(kwargs.get("cost_limitation", "")), safe_str(kwargs.get("irreversible_cost", "")),
             safe_str(kwargs.get("cooldown_limit", "")), safe_str(kwargs.get("forbidden_items", "")),
             safe_str(kwargs.get("failure_penalty", "")), safe_str(kwargs.get("counter_method", "")),
             safe_str(kwargs.get("anti_trope_alignment", "")), safe_str(kwargs.get("hard_constraint_binding", "")),
             safe_str(kwargs.get("protagonist_flaw_effect", "")), now, now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id, **kwargs, "created_at": now, "updated_at": now}


def get_golden_finger(project_id: int, gf_id: int) -> Optional[dict]:
    """获取单个金手指设定。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_golden_finger WHERE project_id = ? AND id = ?",
            (project_id, gf_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_golden_finger_by_project(project_id: int) -> Optional[dict]:
    """获取项目的金手指设定。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_golden_finger WHERE project_id = ?",
            (project_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def update_golden_finger(gf_id: int, **kwargs) -> bool:
    """更新金手指设定。"""
    with _lock:
        conn = _get_conn()
        kwargs["updated_at"] = time.time()
        keys = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(gf_id)
        conn.execute(
            f"UPDATE webnovel_golden_finger SET {keys} WHERE id = ?",
            values
        )
        conn.commit()
        return True


def add_golden_finger_upgrade(golden_finger_id: int, stage: str, description: str = "") -> dict:
    """添加金手指升级路线。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO webnovel_golden_finger_upgrade (golden_finger_id, stage, description) VALUES (?, ?, ?)",
            (safe_int(golden_finger_id), safe_str(stage), safe_str(description))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "golden_finger_id": golden_finger_id, "stage": stage, "description": description}


def get_golden_finger_upgrades(golden_finger_id: int) -> List[dict]:
    """获取金手指升级路线列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_golden_finger_upgrade WHERE golden_finger_id = ?",
            (golden_finger_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def add_golden_finger_payoff(golden_finger_id: int, type: str, description: str = "") -> dict:
    """添加金手指爽点嵌入。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO webnovel_golden_finger_payoff (golden_finger_id, type, description) VALUES (?, ?, ?)",
            (safe_int(golden_finger_id), safe_str(type), safe_str(description))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "golden_finger_id": golden_finger_id, "type": type, "description": description}


def get_golden_finger_payoffs(golden_finger_id: int) -> List[dict]:
    """获取金手指爽点嵌入列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_golden_finger_payoff WHERE golden_finger_id = ?",
            (golden_finger_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def add_golden_finger_feedback(golden_finger_id: int, type: str, chapter_interval: int = 0, description: str = "") -> dict:
    """添加金手指反馈节奏。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO webnovel_golden_finger_feedback (golden_finger_id, type, chapter_interval, description) VALUES (?, ?, ?, ?)",
            (safe_int(golden_finger_id), safe_str(type), safe_int(chapter_interval), safe_str(description))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "golden_finger_id": golden_finger_id, "type": type, "chapter_interval": chapter_interval, "description": description}


def get_golden_finger_feedbacks(golden_finger_id: int) -> List[dict]:
    """获取金手指反馈节奏列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_golden_finger_feedback WHERE golden_finger_id = ?",
            (golden_finger_id,)
        )
        return [dict(row) for row in cursor.fetchall()]