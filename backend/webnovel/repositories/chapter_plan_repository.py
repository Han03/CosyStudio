import time
import json
from typing import Optional, List, Dict
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int
from webnovel.repositories.volume_outline_repository import get_volume_outlines_by_project


def add_chapter_plan(volume_outline_id: int, chapter_index: int, chapter_title: str = "",
                     summary: str = "", key_events: list = None, expected_cool_points: str = "",
                     foreshadowing: str = "", chapter_hook: str = "", chapter_goal: str = "",
                     resistance: str = "", cost: str = "", time_anchor: str = "",
                     chapter_duration: str = "", interval_from_prev: str = "",
                     countdown_status: str = "", strand: str = "", villain_tier: str = "",
                     perspective: str = "", key_entities: str = "", chapter_change: str = "",
                     unresolved_questions: str = "", cbn: str = "", cpns: list = None,
                     cen: str = "", must_cover_nodes: list = None, forbidden_zones: list = None) -> dict:
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_chapter_plan (
                volume_outline_id, chapter_index, chapter_title, summary, key_events,
                expected_cool_points, foreshadowing, chapter_hook, chapter_goal,
                resistance, cost, time_anchor, chapter_duration, interval_from_prev,
                countdown_status, strand, villain_tier, perspective, key_entities,
                chapter_change, unresolved_questions, cbn, cpns, cen,
                must_cover_nodes, forbidden_zones, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                safe_int(volume_outline_id), safe_int(chapter_index),
                safe_str(chapter_title), safe_str(summary),
                safe_str(key_events or []),
                safe_str(expected_cool_points), safe_str(foreshadowing),
                safe_str(chapter_hook), safe_str(chapter_goal),
                safe_str(resistance), safe_str(cost), safe_str(time_anchor),
                safe_str(chapter_duration), safe_str(interval_from_prev),
                safe_str(countdown_status), safe_str(strand),
                safe_str(villain_tier), safe_str(perspective),
                safe_str(key_entities), safe_str(chapter_change),
                safe_str(unresolved_questions), safe_str(cbn),
                safe_str(cpns or []), safe_str(cen),
                safe_str(must_cover_nodes or []),
                safe_str(forbidden_zones or []), now, now
            )
        )
        conn.commit()
        return {"id": cursor.lastrowid, "volume_outline_id": volume_outline_id, "chapter_index": chapter_index}


def get_chapter_plans_by_volume(volume_outline_id: int) -> List[dict]:
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_chapter_plan WHERE volume_outline_id = ? ORDER BY chapter_index",
            (volume_outline_id,)
        )
        rows = cursor.fetchall()
        result = []
        for row in rows:
            row_dict = dict(row)
            try:
                row_dict["key_events"] = json.loads(row_dict["key_events"]) if row_dict["key_events"] else []
                row_dict["cpns"] = json.loads(row_dict["cpns"]) if row_dict["cpns"] else []
                row_dict["must_cover_nodes"] = json.loads(row_dict["must_cover_nodes"]) if row_dict["must_cover_nodes"] else []
                row_dict["forbidden_zones"] = json.loads(row_dict["forbidden_zones"]) if row_dict["forbidden_zones"] else []
            except json.JSONDecodeError:
                row_dict["key_events"] = []
                row_dict["cpns"] = []
                row_dict["must_cover_nodes"] = []
                row_dict["forbidden_zones"] = []
            result.append(row_dict)
        return result


def delete_chapter_plan(plan_id: int) -> bool:
    """删除单个章节规划。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute("DELETE FROM webnovel_chapter_plan WHERE id = ?", (plan_id,))
        conn.commit()
        return cursor.rowcount > 0


def delete_chapter_plans_by_volume(volume_outline_id: int) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM webnovel_chapter_plan WHERE volume_outline_id = ?", (volume_outline_id,))
        conn.commit()


def delete_chapter_plans_in_range(volume_outline_id: int, start_chapter: int, end_chapter: int) -> None:
    """删除指定章节范围内的章节规划，用于合并式重新生成。"""
    with _lock:
        conn = _get_conn()
        conn.execute(
            "DELETE FROM webnovel_chapter_plan WHERE volume_outline_id = ? AND chapter_index >= ? AND chapter_index <= ?",
            (volume_outline_id, start_chapter, end_chapter)
        )
        conn.commit()


def get_chapter_plan(plan_id: int) -> Optional[dict]:
    with _lock:
        conn = _get_conn()
        cursor = conn.execute("SELECT * FROM webnovel_chapter_plan WHERE id = ?", (plan_id,))
        row = cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        try:
            result["key_events"] = json.loads(result["key_events"]) if result["key_events"] else []
            result["cpns"] = json.loads(result["cpns"]) if result["cpns"] else []
            result["must_cover_nodes"] = json.loads(result["must_cover_nodes"]) if result["must_cover_nodes"] else []
            result["forbidden_zones"] = json.loads(result["forbidden_zones"]) if result["forbidden_zones"] else []
        except json.JSONDecodeError:
            result["key_events"] = []
            result["cpns"] = []
            result["must_cover_nodes"] = []
            result["forbidden_zones"] = []
        return result


def get_all_chapter_plans_for_project(project_id: int) -> List[dict]:
    """获取项目下所有卷的章节规划（按卷分组返回）。"""
    volumes = get_volume_outlines_by_project(project_id)
    result = []
    for vol in volumes:
        plans = get_chapter_plans_by_volume(vol["id"])
        result.append({
            "volume_id": vol["id"],
            "volume_number": vol.get("volume_number", 1),
            "volume_name": vol.get("volume_name", ""),
            "chapter_start": vol.get("chapter_start", 0),
            "chapter_end": vol.get("chapter_end", 0),
            "chapter_plans": plans
        })
    return result


def update_chapter_plan(plan_id: int, **kwargs) -> bool:
    with _lock:
        conn = _get_conn()
        kwargs["updated_at"] = time.time()
        keys = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(plan_id)
        conn.execute(f"UPDATE webnovel_chapter_plan SET {keys} WHERE id = ?", values)
        conn.commit()
        return True
