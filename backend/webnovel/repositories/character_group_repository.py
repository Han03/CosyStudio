"""webnovel_character_group数据访问层。"""

import time
from typing import Optional, List, Dict, Any
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_character_group(project_id: int, **kwargs) -> dict:
    """添加主角组。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_character_group (project_id, common_goal, stage_goal, decision_maker,
                                                   executor, information_hub, emotional_pivot, pov_ratio,
                                                   rotation_rules, anti_overpower_constraints, value_conflicts,
                                                   resource_conflicts, trust_cracks, anti_trope_influence,
                                                   hard_constraint_cooperation, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (safe_int(project_id),
             safe_str(kwargs.get("common_goal", "")), safe_str(kwargs.get("stage_goal", "")),
             safe_str(kwargs.get("decision_maker", "")),
             safe_str(kwargs.get("executor", "")), safe_str(kwargs.get("information_hub", "")),
             safe_str(kwargs.get("emotional_pivot", "")),
             safe_str(kwargs.get("pov_ratio", "")), safe_str(kwargs.get("rotation_rules", "")),
             safe_str(kwargs.get("anti_overpower_constraints", "")), safe_str(kwargs.get("value_conflicts", "")),
             safe_str(kwargs.get("resource_conflicts", "")), safe_str(kwargs.get("trust_cracks", "")),
             safe_str(kwargs.get("anti_trope_influence", "")), safe_str(kwargs.get("hard_constraint_cooperation", "")),
             now, now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id, **kwargs, "created_at": now, "updated_at": now}


def get_character_group(project_id: int, group_id: int) -> Optional[dict]:
    """获取单个主角组。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_character_group WHERE project_id = ? AND id = ?",
            (project_id, group_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_character_group_by_project(project_id: int) -> Optional[dict]:
    """获取项目的主角组。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_character_group WHERE project_id = ?",
            (project_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def add_character_group_member(group_id: int, character_id=None, role: str = "", main_line_contribution: str = "", key_flaw: str = "", key_ability: str = "") -> dict:
    """添加团队成员。"""
    with _lock:
        conn = _get_conn()
        # character_id 允许为 None（LLM 生成的引用可能无效）
        cid = safe_int(character_id) if character_id is not None else None
        cursor = conn.execute(
            "INSERT INTO webnovel_character_group_member (group_id, character_id, role, main_line_contribution, key_flaw, key_ability) VALUES (?, ?, ?, ?, ?, ?)",
            (safe_int(group_id), cid,
             safe_str(role), safe_str(main_line_contribution), safe_str(key_flaw), safe_str(key_ability))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "group_id": group_id, "character_id": cid, "role": role, "main_line_contribution": main_line_contribution, "key_flaw": key_flaw, "key_ability": key_ability}


def get_character_group_members(group_id: int) -> List[dict]:
    """获取团队成员列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_character_group_member WHERE group_id = ?",
            (group_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def add_character_group_arc(group_id: int, stage: str, description: str = "") -> dict:
    """添加团队成长弧线。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO webnovel_character_group_arc (group_id, stage, description) VALUES (?, ?, ?)",
            (safe_int(group_id), safe_str(stage), safe_str(description))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "group_id": group_id, "stage": stage, "description": description}


def get_character_group_arcs(group_id: int) -> List[dict]:
    """获取团队成长弧线列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_character_group_arc WHERE group_id = ?",
            (group_id,)
        )
        return [dict(row) for row in cursor.fetchall()]