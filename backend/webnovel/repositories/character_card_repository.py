"""webnovel_character_card数据访问层。"""

import time
from typing import Optional, List, Dict, Any, Set
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_character_card(project_id: int, character_type: str, **kwargs) -> dict:
    """添加角色卡。

    如果同一 project_id 下已存在相同 name 的角色（非空），
    则返回已有记录而非重复创建。
    """
    name = safe_str(kwargs.get("name", ""))
    with _lock:
        conn = _get_conn()
        # 唯一约束冲突检查：同名角色不重复创建
        if name:
            cursor = conn.execute(
                "SELECT id, project_id, character_type, name FROM webnovel_character_card WHERE project_id = ? AND name = ?",
                (safe_int(project_id), name)
            )
            existing = cursor.fetchone()
            if existing:
                return dict(existing)
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_character_card (project_id, character_type, name, age, identity,
                                                 starting_state, core_tags, first_impression,
                                                 core_personality, behavior_bottom_line, emotion_triggers,
                                                 easy_to_anger, easy_to_soften, short_term_goal,
                                                 medium_term_goal, long_term_goal, true_desire,
                                                 personality_flaw, ability_limit, psychological_shadow,
                                                 cost_tolerance, behavior_pattern, failure_reaction,
                                                 breakthrough_strength, ooc_warnings, need_foreshadowing,
                                                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (safe_int(project_id), safe_str(character_type),
             safe_str(kwargs.get("name", "")), safe_int(kwargs.get("age", 0)), safe_str(kwargs.get("identity", "")),
             safe_str(kwargs.get("starting_state", "")), safe_str(kwargs.get("core_tags", "")),
             safe_str(kwargs.get("first_impression", "")),
             safe_str(kwargs.get("core_personality", "")), safe_str(kwargs.get("behavior_bottom_line", "")),
             safe_str(kwargs.get("emotion_triggers", "")), safe_str(kwargs.get("easy_to_anger", "")),
             safe_str(kwargs.get("easy_to_soften", "")),
             safe_str(kwargs.get("short_term_goal", "")), safe_str(kwargs.get("medium_term_goal", "")),
             safe_str(kwargs.get("long_term_goal", "")),
             safe_str(kwargs.get("true_desire", "")), safe_str(kwargs.get("personality_flaw", "")),
             safe_str(kwargs.get("ability_limit", "")),
             safe_str(kwargs.get("psychological_shadow", "")), safe_str(kwargs.get("cost_tolerance", "")),
             safe_str(kwargs.get("behavior_pattern", "")), safe_str(kwargs.get("failure_reaction", "")),
             safe_str(kwargs.get("breakthrough_strength", "")), safe_str(kwargs.get("ooc_warnings", "")),
             safe_str(kwargs.get("need_foreshadowing", "")), now, now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id, "character_type": character_type, **kwargs, "created_at": now, "updated_at": now}


def get_character_card(project_id: int, char_id: int) -> Optional[dict]:
    """获取单个角色卡。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_character_card WHERE project_id = ? AND id = ?",
            (project_id, char_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_character_cards_by_project(project_id: int, character_type: str = "") -> List[dict]:
    """获取项目的角色卡列表。"""
    with _lock:
        conn = _get_conn()
        if character_type:
            cursor = conn.execute(
                "SELECT * FROM webnovel_character_card WHERE project_id = ? AND character_type = ?",
                (project_id, character_type)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM webnovel_character_card WHERE project_id = ?",
                (project_id,)
            )
        return [dict(row) for row in cursor.fetchall()]


def update_character_card(char_id: int, **kwargs) -> bool:
    """更新角色卡。"""
    with _lock:
        conn = _get_conn()
        kwargs["updated_at"] = time.time()
        keys = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(char_id)
        conn.execute(
            f"UPDATE webnovel_character_card SET {keys} WHERE id = ?",
            values
        )
        conn.commit()
        return True


def add_character_relationship(character_id: int, relation_type: str, target_character_id: int = None, target_name: str = "", description: str = "") -> dict:
    """添加角色关系。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO webnovel_character_relationship (character_id, relation_type, target_character_id, target_name, description) VALUES (?, ?, ?, ?, ?)",
            (safe_int(character_id), safe_str(relation_type),
             safe_int(target_character_id) if target_character_id is not None else None,
             safe_str(target_name), safe_str(description))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "character_id": character_id, "relation_type": relation_type, "target_character_id": target_character_id, "target_name": target_name, "description": description}


def get_character_relationships(character_id: int) -> List[dict]:
    """获取角色关系列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_character_relationship WHERE character_id = ?",
            (character_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def add_character_growth(character_id: int, stage: str, description: str = "") -> dict:
    """添加角色成长弧线。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO webnovel_character_growth (character_id, stage, description) VALUES (?, ?, ?)",
            (safe_int(character_id), safe_str(stage), safe_str(description))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "character_id": character_id, "stage": stage, "description": description}


def get_character_growths(character_id: int) -> List[dict]:
    """获取角色成长弧线列表。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_character_growth WHERE character_id = ?",
            (character_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def add_character_power(character_id: int, **kwargs) -> dict:
    """添加角色能力。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_character_power (character_id, realm, layer, bottleneck, signature_skills, resources_equipment)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (safe_int(character_id),
             safe_str(kwargs.get("realm", "")), safe_int(kwargs.get("layer", 0)),
             safe_str(kwargs.get("bottleneck", "")),
             safe_str(kwargs.get("signature_skills", "")),
             safe_str(kwargs.get("resources_equipment", "")))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "character_id": character_id, **kwargs}


def get_character_power(character_id: int) -> Optional[dict]:
    """获取角色能力。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_character_power WHERE character_id = ?",
            (character_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_active_character_ids(project_id: int, chapter_index: int, recent_window: int = 3) -> Set[int]:
    """获取活跃角色ID集合：核心角色 + 最近N章剧情中出场的角色。

    核心角色（protagonist/heroine/villain）始终活跃。
    近期出场角色从 webnovel_chapter_plot 的 characters 列提取（逗号分隔）。
    """
    ids = set()

    # 核心角色始终活跃
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT id FROM webnovel_character_card WHERE project_id = ? AND character_type IN ('protagonist','heroine','villain')",
            (project_id,)
        )
        for row in cursor.fetchall():
            ids.add(row["id"])

    # 最近N章剧情中出场的角色（从行级存储的 characters 列提取）
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """SELECT DISTINCT chapter_index FROM webnovel_chapter_plot
               WHERE project_id = ? AND chapter_index < ?
               ORDER BY chapter_index DESC LIMIT ?""",
            (project_id, chapter_index, recent_window)
        )
        recent_chapters = [row["chapter_index"] for row in cursor.fetchall()]

        char_names = set()
        if recent_chapters:
            placeholders = ",".join("?" * len(recent_chapters))
            cursor = conn.execute(
                f"""SELECT characters FROM webnovel_chapter_plot
                    WHERE project_id = ? AND chapter_index IN ({placeholders})""",
                (project_id, *recent_chapters)
            )
            for row in cursor.fetchall():
                chars_raw = row["characters"] or ""
                if chars_raw:
                    for c in chars_raw.split(","):
                        name = c.strip()
                        if name:
                            char_names.add(name)

    # 名称→ID 查找
    if char_names:
        with _lock:
            conn = _get_conn()
            placeholders = ",".join("?" * len(char_names))
            cursor = conn.execute(
                f"SELECT id FROM webnovel_character_card WHERE project_id = ? AND name IN ({placeholders})",
                (project_id, *char_names)
            )
            for row in cursor.fetchall():
                ids.add(row["id"])

    return ids