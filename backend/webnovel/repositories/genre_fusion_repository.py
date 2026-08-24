"""webnovel_genre_fusion数据访问层。"""

import time
from typing import Optional, List, Dict, Any
from repositories.base_repository import _get_conn, _lock, safe_str


def add_genre_fusion(project_id: int, **kwargs) -> dict:
    """添加复合题材融合设定。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_genre_fusion (project_id, main_genre, sub_genre, proportion,
                                                shared_core_conflict, shared_payoff_goal, reader_promise,
                                                rule_compatibility, conflict_points, sub_genre_trigger_condition,
                                                non_mixable_rules, main_genre_responsibilities,
                                                sub_genre_responsibilities, rhythm_arrangement,
                                                style_split_points, setting_conflict_points,
                                                reader_expectation_deviation, avoidance_methods,
                                                anti_trope_rules, hard_constraints,
                                                protagonist_flaw_amplification, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id,
             safe_str(kwargs.get("main_genre", "")), safe_str(kwargs.get("sub_genre", "")),
             safe_str(kwargs.get("proportion", "")),
             safe_str(kwargs.get("shared_core_conflict", "")), safe_str(kwargs.get("shared_payoff_goal", "")),
             safe_str(kwargs.get("reader_promise", "")), safe_str(kwargs.get("rule_compatibility", "")),
             safe_str(kwargs.get("conflict_points", "")), safe_str(kwargs.get("sub_genre_trigger_condition", "")),
             safe_str(kwargs.get("non_mixable_rules", "")), safe_str(kwargs.get("main_genre_responsibilities", "")),
             safe_str(kwargs.get("sub_genre_responsibilities", "")), safe_str(kwargs.get("rhythm_arrangement", "")),
             safe_str(kwargs.get("style_split_points", "")), safe_str(kwargs.get("setting_conflict_points", "")),
             safe_str(kwargs.get("reader_expectation_deviation", "")), safe_str(kwargs.get("avoidance_methods", "")),
             safe_str(kwargs.get("anti_trope_rules", "")), safe_str(kwargs.get("hard_constraints", "")),
             safe_str(kwargs.get("protagonist_flaw_amplification", "")), now, now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id, **kwargs, "created_at": now, "updated_at": now}


def get_genre_fusion(project_id: int, gf_id: int) -> Optional[dict]:
    """获取单个复合题材融合设定。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_genre_fusion WHERE project_id = ? AND id = ?",
            (project_id, gf_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_genre_fusion_by_project(project_id: int) -> Optional[dict]:
    """获取项目的复合题材融合设定。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_genre_fusion WHERE project_id = ?",
            (project_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None