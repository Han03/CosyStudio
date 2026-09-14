"""角色状态仓库：webnovel_character_state（每章末角色状态快照）。"""

from typing import Dict, List, Optional
from repositories.base_repository import _get_conn, _lock, safe_int
from utils.logger import log_manager

_logger = log_manager.get_logger("character_state_repository")


def upsert_character_state(
    project_id: int,
    character_id: int,
    character_name: str,
    chapter_number: int,
    location: str = "",
    state_summary: str = "",
    emotion: str = "",
    knowledge: str = "",
    notes: str = "",
) -> Dict:
    """写入/覆盖某角色某章末状态。返回该行 dict。"""
    import time
    now = time.time()
    with _lock:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO webnovel_character_state
               (project_id, character_id, character_name, chapter_number,
                location, state_summary, emotion, knowledge, notes,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(character_id, chapter_number) DO UPDATE SET
                 project_id=excluded.project_id,
                 character_name=excluded.character_name,
                 location=excluded.location,
                 state_summary=excluded.state_summary,
                 emotion=excluded.emotion,
                 knowledge=excluded.knowledge,
                 notes=excluded.notes,
                 updated_at=excluded.updated_at""",
            (safe_int(project_id), safe_int(character_id), character_name or "",
             safe_int(chapter_number), location or "", state_summary or "",
             emotion or "", knowledge or "", notes or "",
             now, now),
        )
        conn.commit()
        cursor = conn.execute(
            "SELECT * FROM webnovel_character_state WHERE character_id = ? AND chapter_number = ?",
            (safe_int(character_id), safe_int(chapter_number)),
        )
        row = cursor.fetchone()
        return dict(row) if row else {}


def get_character_states_by_chapter(project_id: int, chapter_number: int) -> List[Dict]:
    """获取指定章末全部角色状态。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """SELECT * FROM webnovel_character_state
               WHERE project_id = ? AND chapter_number = ?
               ORDER BY id""",
            (safe_int(project_id), safe_int(chapter_number)),
        )
        return [dict(r) for r in cursor.fetchall()]


def get_character_states_before_chapter(project_id: int, chapter_number: int) -> List[Dict]:
    """获取上一章末角色状态；若上一章无记录，回退到最近的已有记录章。"""
    target = max(0, safe_int(chapter_number) - 1)
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """SELECT * FROM webnovel_character_state
               WHERE project_id = ? AND chapter_number <= ?
               ORDER BY chapter_number DESC, id LIMIT 30""",
            (safe_int(project_id), target),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        if not rows:
            return []
        latest_ch = rows[0]["chapter_number"]
        return [r for r in rows if r["chapter_number"] == latest_ch]


def delete_character_states_by_chapter(project_id: int, chapter_number: int) -> int:
    """删除指定章节的角色状态快照。返回删除数。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "DELETE FROM webnovel_character_state WHERE project_id = ? AND chapter_number = ?",
            (safe_int(project_id), safe_int(chapter_number))
        )
        conn.commit()
        return cursor.rowcount
