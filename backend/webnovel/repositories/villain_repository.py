"""webnovel_villain数据访问层。"""

import time
from typing import Optional, List, Dict, Any
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_villain(project_id: int, **kwargs) -> dict:
    """添加反派设定。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_villain (project_id, name, identity_faction, appearance_timing,
                                          core_desire, core_fear, action_principle, shared_desire_flaw,
                                          villain_path, value_conflict_points, power_level, key_abilities,
                                          organization_resources, restricted_rules, cost_mechanism,
                                          counter_points, can_be_redeemed, has_higher_villain,
                                          upgrade_rhythm, power_ladder, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id,
             safe_str(kwargs.get("name", "")), safe_str(kwargs.get("identity_faction", "")),
             safe_str(kwargs.get("appearance_timing", "")),
             safe_str(kwargs.get("core_desire", "")), safe_str(kwargs.get("core_fear", "")),
             safe_str(kwargs.get("action_principle", "")), safe_str(kwargs.get("shared_desire_flaw", "")),
             safe_str(kwargs.get("villain_path", "")),
             safe_str(kwargs.get("value_conflict_points", "")), safe_str(kwargs.get("power_level", "")),
             safe_str(kwargs.get("key_abilities", "")), safe_str(kwargs.get("organization_resources", "")),
             safe_str(kwargs.get("restricted_rules", "")), safe_str(kwargs.get("cost_mechanism", "")),
             safe_str(kwargs.get("counter_points", "")), safe_int(kwargs.get("can_be_redeemed", 0)),
             safe_int(kwargs.get("has_higher_villain", 0)), safe_str(kwargs.get("upgrade_rhythm", "")),
             safe_str(kwargs.get("power_ladder", "")), now, now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id, **kwargs, "created_at": now, "updated_at": now}


def get_villain(project_id: int, villain_id: int) -> Optional[dict]:
    """获取单个反派设定。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_villain WHERE project_id = ? AND id = ?",
            (project_id, villain_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_villains_by_project(project_id: int) -> List[dict]:
    """获取项目的反派列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_villain WHERE project_id = ?",
            (project_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def get_villain_by_project(project_id: int) -> Optional[dict]:
    """获取项目的主要反派设定（返回第一个）。"""
    villains = get_villains_by_project(project_id)
    return villains[0] if villains else None


def update_villain(villain_id: int, **kwargs) -> None:
    """更新反派设定。"""
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
        params.append(villain_id)
        
        conn.execute(
            f"UPDATE webnovel_villain SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()


def add_villain_hierarchy(villain_id: int, tier: str, villain_name: str = "", stage: str = "", goal: str = "", protagonist_relation: str = "") -> dict:
    """添加反派分层。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO webnovel_villain_hierarchy (villain_id, tier, villain_name, stage, goal, protagonist_relation) VALUES (?, ?, ?, ?, ?, ?)",
            (villain_id, tier, villain_name, stage, goal, protagonist_relation)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "villain_id": villain_id, "tier": tier, "villain_name": villain_name, "stage": stage, "goal": goal, "protagonist_relation": protagonist_relation}


def get_villain_hierarchy(villain_id: int) -> List[dict]:
    """获取反派分层列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_villain_hierarchy WHERE villain_id = ?",
            (villain_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def add_villain_plot_node(villain_id: int, node_type: str, chapter: int = 0, description: str = "") -> dict:
    """添加反派剧情节点。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO webnovel_villain_plot_node (villain_id, node_type, chapter, description) VALUES (?, ?, ?, ?)",
            (villain_id, node_type, chapter, description)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "villain_id": villain_id, "node_type": node_type, "chapter": chapter, "description": description}


def get_villain_plot_nodes(villain_id: int) -> List[dict]:
    """获取反派剧情节点列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_villain_plot_node WHERE villain_id = ?",
            (villain_id,)
        )
        return [dict(row) for row in cursor.fetchall()]