from typing import Any, Dict, List, Optional

from .base_repository import _get_conn, _lock


def get_character_configs(script_id: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            "SELECT * FROM script_character_configs WHERE script_id=?",
            (script_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_character_config(script_id: int, role: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT * FROM script_character_configs WHERE script_id=? AND role=?",
            (script_id, role),
        ).fetchone()
    return dict(row) if row else None


def upsert_character_config(
    script_id: int,
    role: str,
    agent_id: str = '',
    speed: float = 1.0,
    seed: int = 0,
) -> bool:
    import time
    conn = _get_conn()
    now = time.time()
    with _lock:
        existing = conn.execute(
            "SELECT id FROM script_character_configs WHERE script_id=? AND role=?",
            (script_id, role),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE script_character_configs
                   SET agent_id=?, speed=?, seed=?, updated_at=?
                   WHERE script_id=? AND role=?""",
                (agent_id, speed, seed, now, script_id, role),
            )
        else:
            conn.execute(
                """INSERT INTO script_character_configs
                   (script_id, role, agent_id, speed, seed, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (script_id, role, agent_id, speed, seed, now, now),
            )
        conn.commit()
    return True


def add_script_characters(script_id: int, roles: List[str]) -> List[Dict[str, Any]]:
    if not roles:
        return []
    import time
    conn = _get_conn()
    now = time.time()
    inserted = []
    with _lock:
        for role in roles:
            role = role.strip()
            if not role:
                continue
            existing = conn.execute(
                "SELECT id FROM script_characters WHERE script_id=? AND role=?",
                (script_id, role),
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO script_characters (script_id, role, line_count, created_at)
                       VALUES (?, ?, 0, ?)""",
                    (script_id, role, now),
                )
                inserted.append({"script_id": script_id, "role": role})
        conn.commit()
    return inserted


def get_script_characters(script_id: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            "SELECT * FROM script_characters WHERE script_id=? ORDER BY line_count DESC, role",
            (script_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def increment_character_line_count(script_id: int, roles: List[str]) -> None:
    if not roles:
        return
    conn = _get_conn()
    with _lock:
        for role in roles:
            role = role.strip()
            if not role:
                continue
            conn.execute(
                "UPDATE script_characters SET line_count = line_count + 1 WHERE script_id=? AND role=?",
                (script_id, role),
            )
        conn.commit()


def delete_script_characters(script_id: int) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute("DELETE FROM script_characters WHERE script_id=?", (script_id,))
        conn.commit()