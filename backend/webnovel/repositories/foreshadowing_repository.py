"""伏笔（open_loops）和爽点（cool_points）仓库。"""

import time
from typing import Optional, Dict, List
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_open_loop(
    project_id: int,
    content: str,
    tier: str = "",
    planted_chapter: int = 0,
    target_chapter: int = 0,
    evidence: str = ""
) -> Dict:
    """添加伏笔（open_loop）。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_open_loops 
            (project_id, content, status, tier, planted_chapter, target_chapter, 
             urgency, evidence, created_at, updated_at)
            VALUES (?, ?, 'active', ?, ?, ?, 0.0, ?, ?, ?)
            """,
            (safe_int(project_id), safe_str(content), safe_str(tier),
             safe_int(planted_chapter), safe_int(target_chapter),
             safe_str(evidence), now, now)
        )
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "project_id": project_id,
            "content": content,
            "status": "active",
            "tier": tier,
            "planted_chapter": planted_chapter,
            "target_chapter": target_chapter,
            "resolved_chapter": 0,
            "urgency": 0.0,
            "evidence": evidence,
            "created_at": now,
            "updated_at": now
        }


def update_open_loop_resolved(loop_id: int, resolved_chapter: int) -> bool:
    """标记伏笔为已回收。"""
    conn = _get_conn()
    cursor = conn.execute(
        """
        UPDATE webnovel_open_loops 
        SET status = 'resolved', resolved_chapter = ?, updated_at = ?
        WHERE id = ? AND status != 'resolved'
        """,
        (resolved_chapter, time.time(), loop_id)
    )
    conn.commit()
    return cursor.rowcount > 0


def get_open_loops_by_project(project_id: int, status: str = None) -> List[Dict]:
    """获取项目的所有伏笔。"""
    conn = _get_conn()
    if status:
        cursor = conn.execute(
            "SELECT * FROM webnovel_open_loops WHERE project_id = ? AND status = ? ORDER BY planted_chapter",
            (project_id, status)
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM webnovel_open_loops WHERE project_id = ? ORDER BY planted_chapter",
            (project_id,)
        )
    return [dict(row) for row in cursor.fetchall()]


def get_active_open_loops(project_id: int) -> List[Dict]:
    """获取项目的活跃伏笔。"""
    return get_open_loops_by_project(project_id, "active")


def update_open_loop_urgency(project_id: int, current_chapter: int) -> int:
    """更新伏笔紧急度。"""
    conn = _get_conn()
    cursor = conn.execute(
        """
        SELECT id, tier, planted_chapter, target_chapter 
        FROM webnovel_open_loops 
        WHERE project_id = ? AND status = 'active' AND target_chapter > 0
        """,
        (project_id,)
    )
    loops = cursor.fetchall()
    
    updated_count = 0
    for loop in loops:
        tier_weight = {
            "核心": 3.0,
            "支线": 2.0,
            "装饰": 1.0
        }.get(loop["tier"], 1.0)
        if loop["target_chapter"] > 0:
            urgency = (current_chapter / loop["target_chapter"]) * tier_weight
            conn.execute(
                "UPDATE webnovel_open_loops SET urgency = ?, updated_at = ? WHERE id = ?",
                (min(urgency, 3.0), time.time(), loop["id"])
            )
            updated_count += 1
    conn.commit()
    return updated_count


def add_cool_point(
    project_id: int,
    chapter_number: int,
    content: str,
    cool_point_type: str = "",
    execution_mode: str = "",
    structure_stage: str = "",
    pressure_level: int = 0,
    release_level: int = 0,
    reader_emotion: str = "",
    impact_score: int = 0,
    evidence: str = ""
) -> Dict:
    """添加爽点。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_cool_points 
            (project_id, chapter_number, content, cool_point_type, execution_mode, 
             structure_stage, pressure_level, release_level, timing_position, 
             reader_emotion, impact_score, evidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?)
            """,
            (safe_int(project_id), safe_int(chapter_number), safe_str(content),
             safe_str(cool_point_type), safe_str(execution_mode),
             safe_str(structure_stage), safe_int(pressure_level),
             safe_int(release_level), safe_str(reader_emotion),
             safe_int(impact_score), safe_str(evidence), now, now)
        )
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "project_id": project_id,
            "chapter_number": chapter_number,
            "content": content,
            "cool_point_type": cool_point_type,
            "execution_mode": execution_mode,
            "structure_stage": structure_stage,
            "pressure_level": pressure_level,
            "release_level": release_level,
            "timing_position": "",
            "reader_emotion": reader_emotion,
            "impact_score": impact_score,
            "evidence": evidence,
            "created_at": now,
            "updated_at": now
        }


def get_cool_points_by_project(project_id: int) -> List[Dict]:
    """获取项目的所有爽点。"""
    conn = _get_conn()
    cursor = conn.execute(
        "SELECT * FROM webnovel_cool_points WHERE project_id = ? ORDER BY chapter_number",
        (project_id,)
    )
    return [dict(row) for row in cursor.fetchall()]


def get_cool_points_by_chapter(project_id: int, chapter_number: int) -> List[Dict]:
    """获取指定章节的爽点。"""
    conn = _get_conn()
    cursor = conn.execute(
        "SELECT * FROM webnovel_cool_points WHERE project_id = ? AND chapter_number = ?",
        (project_id, chapter_number)
    )
    return [dict(row) for row in cursor.fetchall()]


def get_cool_points_count_by_type(project_id: int) -> Dict[str, int]:
    """按类型统计爽点数量。"""
    conn = _get_conn()
    cursor = conn.execute(
        "SELECT cool_point_type, COUNT(*) as count FROM webnovel_cool_points WHERE project_id = ? GROUP BY cool_point_type",
        (project_id,)
    )
    return {row["cool_point_type"] or "未分类": row["count"] for row in cursor.fetchall()}


# ── webnovel_foreshadow 铺垫碎片 ─────────────────────────────────────────────

def add_foreshadow(
    project_id: int,
    volume_outline_id: int,
    content: str,
    buried_chapter: int = 0,
    payoff_chapter: int = 0,
    level: str = ""
) -> Dict:
    """添加铺垫碎片。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_foreshadow
            (project_id, volume_outline_id, content, buried_chapter, payoff_chapter, level, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (safe_int(project_id), safe_int(volume_outline_id), safe_str(content),
             safe_int(buried_chapter), safe_int(payoff_chapter), safe_str(level), now, now)
        )
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "project_id": project_id,
            "volume_outline_id": volume_outline_id,
            "content": content,
            "buried_chapter": buried_chapter,
            "payoff_chapter": payoff_chapter,
            "level": level,
            "created_at": now,
            "updated_at": now
        }


def get_foreshadows_by_volume(volume_outline_id: int) -> List[Dict]:
    """获取指定卷纲的铺垫碎片列表。"""
    conn = _get_conn()
    cursor = conn.execute(
        "SELECT * FROM webnovel_foreshadow WHERE volume_outline_id = ? ORDER BY buried_chapter",
        (volume_outline_id,)
    )
    return [dict(row) for row in cursor.fetchall()]


def get_foreshadows_by_project(project_id: int) -> List[Dict]:
    """获取项目的所有铺垫碎片。"""
    conn = _get_conn()
    cursor = conn.execute(
        "SELECT * FROM webnovel_foreshadow WHERE project_id = ? ORDER BY buried_chapter",
        (project_id,)
    )
    return [dict(row) for row in cursor.fetchall()]
