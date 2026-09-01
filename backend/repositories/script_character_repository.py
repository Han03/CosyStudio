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
    tts_capability_id: str = '',
    cloud_extra_params: str = '{}',
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
                   SET agent_id=?, speed=?, seed=?, tts_capability_id=?, cloud_extra_params=?, updated_at=?
                   WHERE script_id=? AND role=?""",
                (agent_id, speed, seed, tts_capability_id, cloud_extra_params, now, script_id, role),
            )
        else:
            conn.execute(
                """INSERT INTO script_character_configs
                   (script_id, role, agent_id, speed, seed, tts_capability_id, cloud_extra_params, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (script_id, role, agent_id, speed, seed, tts_capability_id, cloud_extra_params, now, now),
            )
        conn.commit()
    return True


def add_script_characters(script_id: int, roles: List[str],
                         profiles: Optional[Dict[str, Dict[str, str]]] = None) -> List[Dict[str, Any]]:
    """新增角色记录。

    Args:
        script_id: 剧本 ID
        roles: 角色名列表
        profiles: 可选的角色属性映射 {role: {gender, age, description}}
    """
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
                profile = (profiles or {}).get(role, {})
                conn.execute(
                    """INSERT INTO script_characters
                       (script_id, role, line_count, gender, age, description, created_at)
                       VALUES (?, ?, 0, ?, ?, ?, ?)""",
                    (script_id, role,
                     profile.get("gender", ""),
                     profile.get("age", ""),
                     profile.get("description", ""),
                     now),
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


def update_character_profile(script_id: int, role: str,
                             gender: str = '', age: str = '',
                             description: str = '') -> bool:
    """更新角色的性别/年龄/描述属性。"""
    conn = _get_conn()
    with _lock:
        conn.execute(
            """UPDATE script_characters
               SET gender=?, age=?, description=?
               WHERE script_id=? AND role=?""",
            (gender, age, description, script_id, role),
        )
        conn.commit()
    return True


def batch_update_character_profiles(script_id: int,
                                    profiles: List[Dict[str, Any]]) -> int:
    """批量更新角色属性。

    Args:
        script_id: 剧本 ID
        profiles: [{role, gender, age, description}, ...]

    Returns:
        成功更新的记录数
    """
    if not profiles:
        return 0
    conn = _get_conn()
    updated = 0
    with _lock:
        for p in profiles:
            role = p.get("role", "").strip()
            if not role:
                continue
            conn.execute(
                """UPDATE script_characters
                   SET gender=?, age=?, description=?
                   WHERE script_id=? AND role=?""",
                (p.get("gender", ""), p.get("age", ""),
                 p.get("description", ""), script_id, role),
            )
            updated += 1
        conn.commit()
    return updated