"""webnovel_timeline数据访问层。"""

import time
from typing import Optional, List, Dict, Any
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_timeline(project_id: int, volume_number: int, **kwargs) -> dict:
    """添加时间线。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_timeline (project_id, volume_number, time_base, time_span, countdown_events, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (safe_int(project_id), safe_int(volume_number),
             safe_str(kwargs.get("time_base", "")), safe_str(kwargs.get("time_span", "")),
             safe_str(kwargs.get("countdown_events", "")), now, now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id, "volume_number": volume_number, **kwargs, "created_at": now, "updated_at": now}


def get_timeline(project_id: int, timeline_id: int) -> Optional[dict]:
    """获取单个时间线。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_timeline WHERE project_id = ? AND id = ?",
            (project_id, timeline_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_timelines_by_project(project_id: int) -> List[dict]:
    """获取项目的时间线列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_timeline WHERE project_id = ? ORDER BY volume_number",
            (project_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def get_timeline_by_project(project_id: int) -> Optional[dict]:
    """获取项目的时间线（返回第一个）。"""
    timelines = get_timelines_by_project(project_id)
    return timelines[0] if timelines else None


def add_timeline_chapter(timeline_id: int, chapter_number: int, time_anchor: str = "", chapter_duration: str = "", interval_from_prev: str = "", countdown_status: str = "", notes: str = "") -> dict:
    """添加章节时间轴。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO webnovel_timeline_chapter (timeline_id, chapter_number, time_anchor, chapter_duration, interval_from_prev, countdown_status, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (safe_int(timeline_id), safe_int(chapter_number),
             safe_str(time_anchor), safe_str(chapter_duration),
             safe_str(interval_from_prev), safe_str(countdown_status), safe_str(notes))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "timeline_id": timeline_id, "chapter_number": chapter_number, "time_anchor": time_anchor, "chapter_duration": chapter_duration, "interval_from_prev": interval_from_prev, "countdown_status": countdown_status, "notes": notes}


def upsert_timeline_chapter(timeline_id: int, chapter_number: int, time_anchor: str = "", chapter_duration: str = "", interval_from_prev: str = "", countdown_status: str = "", notes: str = "") -> dict:
    """更新或插入章节时间轴。按 (timeline_id, chapter_number) 去重，存在则更新，不存在则插入。"""
    with _lock:
        conn = _get_conn()
        # 先查询是否已存在
        cursor = conn.execute(
            "SELECT id FROM webnovel_timeline_chapter WHERE timeline_id = ? AND chapter_number = ?",
            (safe_int(timeline_id), safe_int(chapter_number))
        )
        existing = cursor.fetchone()
        if existing:
            conn.execute(
                """UPDATE webnovel_timeline_chapter
                   SET time_anchor = ?, chapter_duration = ?, interval_from_prev = ?,
                       countdown_status = ?, notes = ?
                   WHERE id = ?""",
                (safe_str(time_anchor), safe_str(chapter_duration),
                 safe_str(interval_from_prev), safe_str(countdown_status),
                 safe_str(notes), existing["id"])
            )
            conn.commit()
            return {"id": existing["id"], "timeline_id": timeline_id, "chapter_number": chapter_number,
                    "time_anchor": time_anchor, "chapter_duration": chapter_duration,
                    "interval_from_prev": interval_from_prev, "countdown_status": countdown_status, "notes": notes}
        else:
            return add_timeline_chapter(timeline_id, chapter_number, time_anchor, chapter_duration,
                                        interval_from_prev, countdown_status, notes)


def get_timeline_chapters(timeline_id: int) -> List[dict]:
    """获取章节时间轴列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_timeline_chapter WHERE timeline_id = ? ORDER BY chapter_number",
            (timeline_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def add_timeline_countdown(timeline_id: int, event_name: str = "", start_countdown: str = "", current_status: str = "", trigger_chapter: int = 0, result: str = "") -> dict:
    """添加倒计时事件。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO webnovel_timeline_countdown (timeline_id, event_name, start_countdown, current_status, trigger_chapter, result) VALUES (?, ?, ?, ?, ?, ?)",
            (safe_int(timeline_id), safe_str(event_name), safe_str(start_countdown),
             safe_str(current_status), safe_int(trigger_chapter), safe_str(result))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "timeline_id": timeline_id, "event_name": event_name, "start_countdown": start_countdown, "current_status": current_status, "trigger_chapter": trigger_chapter, "result": result}


def get_timeline_countdowns(timeline_id: int) -> List[dict]:
    """获取倒计时事件列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_timeline_countdown WHERE timeline_id = ?",
            (timeline_id,)
        )
        return [dict(row) for row in cursor.fetchall()]