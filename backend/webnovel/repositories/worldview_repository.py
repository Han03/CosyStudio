"""webnovel_worldview数据访问层。"""

import time
from typing import Optional, List, Dict, Any
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_worldview(project_id: int, **kwargs) -> dict:
    """添加世界观设定。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_worldview (project_id, world_summary, main_genre, sub_genre, fusion_mechanism,
                                             continent_count, core_regions, edge_regions, social_hierarchy,
                                             resource_distribution, belief_ideology, resource_scarcity,
                                             political_rules, social_common_sense, hard_constraints,
                                             energy_cycle, technology_basis, fairness_cost_rules,
                                             currency_system, exchange_rules, main_currency_form,
                                             trading_scenes, important_locations, key_resource_points,
                                             daily_currency, transportation_communication, education_career,
                                             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id,
             safe_str(kwargs.get("world_summary", "")), safe_str(kwargs.get("main_genre", "")),
             safe_str(kwargs.get("sub_genre", "")),
             safe_str(kwargs.get("fusion_mechanism", "")), safe_int(kwargs.get("continent_count", 0)),
             safe_str(kwargs.get("core_regions", "")),
             safe_str(kwargs.get("edge_regions", "")), safe_str(kwargs.get("social_hierarchy", "")),
             safe_str(kwargs.get("resource_distribution", "")), safe_str(kwargs.get("belief_ideology", "")),
             safe_str(kwargs.get("resource_scarcity", "")), safe_str(kwargs.get("political_rules", "")),
             safe_str(kwargs.get("social_common_sense", "")), safe_str(kwargs.get("hard_constraints", "")),
             safe_str(kwargs.get("energy_cycle", "")), safe_str(kwargs.get("technology_basis", "")),
             safe_str(kwargs.get("fairness_cost_rules", "")), safe_str(kwargs.get("currency_system", "")),
             safe_str(kwargs.get("exchange_rules", "")), safe_str(kwargs.get("main_currency_form", "")),
             safe_str(kwargs.get("trading_scenes", "")), safe_str(kwargs.get("important_locations", "")),
             safe_str(kwargs.get("key_resource_points", "")), safe_str(kwargs.get("daily_currency", "")),
             safe_str(kwargs.get("transportation_communication", "")), safe_str(kwargs.get("education_career", "")), now, now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id, **kwargs, "created_at": now, "updated_at": now}


def get_worldview(project_id: int, worldview_id: int) -> Optional[dict]:
    """获取单个世界观设定。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_worldview WHERE project_id = ? AND id = ?",
            (project_id, worldview_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_worldview_by_project(project_id: int) -> Optional[dict]:
    """获取项目的世界观设定。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_worldview WHERE project_id = ?",
            (project_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def add_worldview_faction(worldview_id: int, faction_name: str = "", tier: str = "", relation: str = "", hierarchy: str = "") -> dict:
    """添加势力格局。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO webnovel_worldview_faction (worldview_id, faction_name, tier, relation, hierarchy) VALUES (?, ?, ?, ?, ?)",
            (safe_int(worldview_id), safe_str(faction_name), safe_str(tier), safe_str(relation), safe_str(hierarchy))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "worldview_id": worldview_id, "faction_name": faction_name, "tier": tier, "relation": relation, "hierarchy": hierarchy}


def get_worldview_factions(worldview_id: int) -> List[dict]:
    """获取势力格局列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_worldview_faction WHERE worldview_id = ?",
            (worldview_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def add_worldview_history(worldview_id: int, era: str = "", event: str = "") -> dict:
    """添加历史年表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO webnovel_worldview_history (worldview_id, era, event) VALUES (?, ?, ?)",
            (safe_int(worldview_id), safe_str(era), safe_str(event))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "worldview_id": worldview_id, "era": era, "event": event}


def get_worldview_history(worldview_id: int) -> List[dict]:
    """获取历史年表列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_worldview_history WHERE worldview_id = ?",
            (worldview_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def update_worldview(worldview_id: int, **kwargs) -> None:
    """更新世界观设定。"""
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
        params.append(worldview_id)
        
        conn.execute(
            f"UPDATE webnovel_worldview SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()