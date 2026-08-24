"""webnovel_volume_outline数据访问层。"""

import time
from typing import Optional, List, Dict, Any
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_volume_outline(project_id: int, volume_number: int, **kwargs) -> dict:
    """添加卷纲。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_volume_outline (project_id, volume_number, volume_name, chapter_start,
                                                  chapter_end, core_conflict, volume_climax,
                                                  promise_description, promise_types, catalyst_event,
                                                  irreversible_change, protagonist_goal, mid_reversal,
                                                  reversal_insight, lowest_point_event, lowest_point_cost,
                                                  protagonist_choice, payoff_items, new_hook,
                                                  unresolved_issues, core_conflict_anchor, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (safe_int(project_id), safe_int(volume_number),
             safe_str(kwargs.get("volume_name", "")), safe_int(kwargs.get("chapter_start", 0)),
             safe_int(kwargs.get("chapter_end", 0)),
             safe_str(kwargs.get("core_conflict", "")), safe_str(kwargs.get("volume_climax", "")),
             safe_str(kwargs.get("promise_description", "")), safe_str(kwargs.get("promise_types", "")),
             safe_str(kwargs.get("catalyst_event", "")), safe_str(kwargs.get("irreversible_change", "")),
             safe_str(kwargs.get("protagonist_goal", "")), safe_str(kwargs.get("mid_reversal", "")),
             safe_str(kwargs.get("reversal_insight", "")), safe_str(kwargs.get("lowest_point_event", "")),
             safe_str(kwargs.get("lowest_point_cost", "")), safe_str(kwargs.get("protagonist_choice", "")),
             safe_str(kwargs.get("payoff_items", "")), safe_str(kwargs.get("new_hook", "")),
             safe_str(kwargs.get("unresolved_issues", "")),
             safe_str(kwargs.get("core_conflict_anchor", "")), now, now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id, "volume_number": volume_number, **kwargs, "created_at": now, "updated_at": now}


def get_volume_outline(project_id: int, vo_id: int) -> Optional[dict]:
    """获取单个卷纲。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_volume_outline WHERE project_id = ? AND id = ?",
            (project_id, vo_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_volume_outlines_by_project(project_id: int) -> List[dict]:
    """获取项目的卷纲列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_volume_outline WHERE project_id = ? ORDER BY volume_number",
            (project_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def add_volume_crisis(volume_outline_id: int, crisis_order: int, crisis_event: str = "", cost_risk_upgrade: str = "", result_change: str = "") -> dict:
    """添加升级危机链。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO webnovel_volume_crisis (volume_outline_id, crisis_order, crisis_event, cost_risk_upgrade, result_change) VALUES (?, ?, ?, ?, ?)",
            (safe_int(volume_outline_id), safe_int(crisis_order),
             safe_str(crisis_event), safe_str(cost_risk_upgrade), safe_str(result_change))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "volume_outline_id": volume_outline_id, "crisis_order": crisis_order, "crisis_event": crisis_event, "cost_risk_upgrade": cost_risk_upgrade, "result_change": result_change}


def get_volume_crises(volume_outline_id: int) -> List[dict]:
    """获取升级危机链列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_volume_crisis WHERE volume_outline_id = ? ORDER BY crisis_order",
            (volume_outline_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def update_volume_outline(vo_id: int, **kwargs) -> bool:
    """更新卷纲。"""
    with _lock:
        conn = _get_conn()
        kwargs["updated_at"] = time.time()
        keys = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(vo_id)
        conn.execute(f"UPDATE webnovel_volume_outline SET {keys} WHERE id = ?", values)
        conn.commit()
        return True


def delete_volume_outline(vo_id: int) -> bool:
    """删除卷纲。"""
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM webnovel_volume_outline WHERE id = ?", (vo_id,))
        conn.commit()
        return True