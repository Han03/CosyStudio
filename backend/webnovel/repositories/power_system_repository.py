"""webnovel_power_system数据访问层。"""

import time
from typing import Optional, List, Dict, Any
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_power_system(project_id: int, **kwargs) -> dict:
    """添加力量体系设定。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_power_system (project_id, core_creed, cost_rules, fairness_principle,
                                                system_type, typical_realm_chain, small_realm_divisions,
                                                energy_source, training_methods, social_control_mechanism,
                                                resource_types, resource_acquisition, scarcity_rules,
                                                alternative_paths, damage_defense_logic, battle_rhythm,
                                                counter_relations, escape_mechanism, forbidden_arts,
                                                high_level_limits, hard_limits, system_vulnerabilities,
                                                protagonist_exploitation, villain_counter,
                                                anti_trope_alignment, hard_constraint_binding,
                                                created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id,
             safe_str(kwargs.get("core_creed", "")), safe_str(kwargs.get("cost_rules", "")),
             safe_str(kwargs.get("fairness_principle", "")),
             safe_str(kwargs.get("system_type", "")), safe_str(kwargs.get("typical_realm_chain", "")),
             safe_str(kwargs.get("small_realm_divisions", "")), safe_str(kwargs.get("energy_source", "")),
             safe_str(kwargs.get("training_methods", "")), safe_str(kwargs.get("social_control_mechanism", "")),
             safe_str(kwargs.get("resource_types", "")), safe_str(kwargs.get("resource_acquisition", "")),
             safe_str(kwargs.get("scarcity_rules", "")), safe_str(kwargs.get("alternative_paths", "")),
             safe_str(kwargs.get("damage_defense_logic", "")), safe_str(kwargs.get("battle_rhythm", "")),
             safe_str(kwargs.get("counter_relations", "")), safe_str(kwargs.get("escape_mechanism", "")),
             safe_str(kwargs.get("forbidden_arts", "")), safe_str(kwargs.get("high_level_limits", "")),
             safe_str(kwargs.get("hard_limits", "")), safe_str(kwargs.get("system_vulnerabilities", "")),
             safe_str(kwargs.get("protagonist_exploitation", "")), safe_str(kwargs.get("villain_counter", "")),
             safe_str(kwargs.get("anti_trope_alignment", "")), safe_str(kwargs.get("hard_constraint_binding", "")), now, now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id, **kwargs, "created_at": now, "updated_at": now}


def get_power_system(project_id: int, ps_id: int) -> Optional[dict]:
    """获取单个力量体系设定。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_power_system WHERE project_id = ? AND id = ?",
            (project_id, ps_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_power_system_by_project(project_id: int) -> Optional[dict]:
    """获取项目的力量体系设定。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_power_system WHERE project_id = ?",
            (project_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def add_power_level(power_system_id: int, level_order: int, level_name: str = "", core_abilities: str = "", resource_requirements: str = "", breakthrough_method: str = "", failure_cost: str = "", overlevel_cost: str = "") -> dict:
    """添加等级体系。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_power_level (power_system_id, level_order, level_name, core_abilities, resource_requirements, breakthrough_method, failure_cost, overlevel_cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (safe_int(power_system_id), safe_int(level_order),
             safe_str(level_name), safe_str(core_abilities), safe_str(resource_requirements),
             safe_str(breakthrough_method), safe_str(failure_cost), safe_str(overlevel_cost))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "power_system_id": power_system_id, "level_order": level_order, "level_name": level_name, "core_abilities": core_abilities, "resource_requirements": resource_requirements, "breakthrough_method": breakthrough_method, "failure_cost": failure_cost, "overlevel_cost": overlevel_cost}


def get_power_levels(power_system_id: int) -> List[dict]:
    """获取等级体系列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_power_level WHERE power_system_id = ? ORDER BY level_order",
            (power_system_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def add_power_feedback(power_system_id: int, realm_change_chapter: int = 0, power_gap_display: str = "") -> dict:
    """添加力量体系反馈节奏。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO webnovel_power_feedback (power_system_id, realm_change_chapter, power_gap_display) VALUES (?, ?, ?)",
            (safe_int(power_system_id), safe_int(realm_change_chapter), safe_str(power_gap_display))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "power_system_id": power_system_id, "realm_change_chapter": realm_change_chapter, "power_gap_display": power_gap_display}


def get_power_feedbacks(power_system_id: int) -> List[dict]:
    """获取力量体系反馈节奏列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_power_feedback WHERE power_system_id = ?",
            (power_system_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def update_power_system(power_system_id: int, **kwargs) -> None:
    """更新力量体系设定。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        updates = []
        params = []
        
        for key, value in kwargs.items():
            updates.append(f"{key} = ?")
            params.append(value)
        
        updates.append("updated_at = ?")
        params.append(now)
        params.append(power_system_id)
        
        conn.execute(
            f"UPDATE webnovel_power_system SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()