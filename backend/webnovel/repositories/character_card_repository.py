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
            INSERT INTO webnovel_character_card (project_id, character_type, name, alias, age, identity,
                                                 starting_state, core_tags, first_impression,
                                                 core_personality, behavior_bottom_line, emotion_triggers,
                                                 easy_to_anger, easy_to_soften, short_term_goal,
                                                 medium_term_goal, long_term_goal, true_desire,
                                                 personality_flaw, ability_limit, psychological_shadow,
                                                 cost_tolerance, behavior_pattern, failure_reaction,
                                                 breakthrough_strength, ooc_warnings, need_foreshadowing,
                                                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (safe_int(project_id), safe_str(character_type),
             safe_str(kwargs.get("name", "")), safe_str(kwargs.get("alias", "")), safe_int(kwargs.get("age", 0)), safe_str(kwargs.get("identity", "")),
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


def delete_character_card(char_id: int) -> bool:
    """删除角色卡（关系/成长/能力等关联数据经外键级联删除）。"""
    with _lock:
        conn = _get_conn()
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("DELETE FROM webnovel_character_card WHERE id = ?", (safe_int(char_id),))
        conn.commit()
        return True


def reassign_character_data(old_char_id: int, new_char_id: int) -> None:
    """将旧角色卡的关系/成长/能力/物品数据迁移到新卡（身份揭露合并时调用）。"""
    with _lock:
        conn = _get_conn()
        old_id, new_id = safe_int(old_char_id), safe_int(new_char_id)
        conn.execute(
            "UPDATE webnovel_character_relationship SET character_id = ? WHERE character_id = ?",
            (new_id, old_id)
        )
        conn.execute(
            "UPDATE webnovel_character_relationship SET target_character_id = ? WHERE target_character_id = ?",
            (new_id, old_id)
        )
        conn.execute(
            "UPDATE webnovel_character_growth SET character_id = ? WHERE character_id = ?",
            (new_id, old_id)
        )
        conn.execute(
            "UPDATE webnovel_character_power SET character_id = ? WHERE character_id = ?",
            (new_id, old_id)
        )
        # 物品随角色卡合并迁移：同名冲突时保留新卡的记录，删除旧卡的重复项，
        # 避免触发 (character_id, item_name) 唯一索引冲突
        conn.execute(
            """DELETE FROM webnovel_character_item
               WHERE character_id = ? AND item_name IN (
                   SELECT item_name FROM webnovel_character_item WHERE character_id = ?
               )""",
            (old_id, new_id)
        )
        conn.execute(
            "UPDATE webnovel_character_item SET character_id = ? WHERE character_id = ?",
            (new_id, old_id)
        )
        conn.commit()


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


# ==============================================================================
# 角色物品（动态持有清单，事实记录阶段增减，防止写文出现未持有物品）
# ==============================================================================

def upsert_character_item(
    character_id: int, item_name: str, item_desc: str = "",
    source: str = "", chapter: int = 0, note: str = ""
) -> dict:
    """获得物品：同名记录存在则复用（状态复位 held 并刷新信息），否则新增。"""
    item_name = safe_str(item_name)
    if not item_name:
        return {}
    now = time.time()
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT id FROM webnovel_character_item WHERE character_id = ? AND item_name = ?",
            (safe_int(character_id), item_name)
        )
        existing = cursor.fetchone()
        if existing:
            conn.execute(
                """UPDATE webnovel_character_item
                   SET item_desc = ?, source = ?, acquired_chapter = ?, status = 'held',
                       lost_chapter = 0, change_note = ?, updated_at = ?
                   WHERE id = ?""",
                (safe_str(item_desc), safe_str(source), safe_int(chapter),
                 safe_str(note), now, existing["id"])
            )
            conn.commit()
            return {"id": existing["id"], "character_id": character_id, "item_name": item_name,
                    "status": "held", "acquired_chapter": safe_int(chapter)}
        cursor = conn.execute(
            """INSERT INTO webnovel_character_item
               (character_id, item_name, item_desc, source, acquired_chapter,
                status, lost_chapter, change_note, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'held', 0, ?, ?, ?)""",
            (safe_int(character_id), item_name, safe_str(item_desc), safe_str(source),
             safe_int(chapter), safe_str(note), now, now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "character_id": character_id, "item_name": item_name,
                "status": "held", "acquired_chapter": safe_int(chapter)}


def mark_character_item_lost(
    character_id: int, item_name: str, status: str = "lost",
    chapter: int = 0, note: str = ""
) -> bool:
    """失去物品：精确匹配优先，子串匹配兜底（对齐身份揭露的匹配策略）。

    未命中返回 False（角色没有该物品却"失去"，属于不一致信号，由调用方记日志，
    不凭空建记录）。
    """
    item_name = safe_str(item_name)
    if not item_name:
        return False
    if status not in ("lost", "destroyed", "gifted"):
        return False
    now = time.time()
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT id, item_name FROM webnovel_character_item WHERE character_id = ?",
            (safe_int(character_id),)
        )
        rows = cursor.fetchall()
        target_id = None
        for row in rows:
            if row["item_name"] == item_name:
                target_id = row["id"]
                break
        if target_id is None:
            for row in rows:
                if item_name in row["item_name"] or row["item_name"] in item_name:
                    target_id = row["id"]
                    break
        if target_id is None:
            return False
        conn.execute(
            """UPDATE webnovel_character_item
               SET status = ?, lost_chapter = ?, change_note = ?, updated_at = ?
               WHERE id = ?""",
            (status, safe_int(chapter), safe_str(note), now, target_id)
        )
        conn.commit()
        return True


def get_character_items(character_id: int, only_held: bool = True) -> List[dict]:
    """获取角色的物品列表（默认仅持有中）。"""
    with _lock:
        conn = _get_conn()
        sql = "SELECT * FROM webnovel_character_item WHERE character_id = ?"
        if only_held:
            sql += " AND status = 'held'"
        cursor = conn.execute(sql, (safe_int(character_id),))
        return [dict(row) for row in cursor.fetchall()]


def get_character_items_by_project(project_id: int, only_held: bool = True) -> Dict[int, List[dict]]:
    """批量获取项目下所有角色的持有物品，按 character_id 分组。

    供上下文构建器一次性加载，避免逐角色查询。
    """
    with _lock:
        conn = _get_conn()
        sql = """SELECT i.* FROM webnovel_character_item i
                 JOIN webnovel_character_card c ON i.character_id = c.id
                 WHERE c.project_id = ?"""
        if only_held:
            sql += " AND i.status = 'held'"
        cursor = conn.execute(sql, (safe_int(project_id),))
        grouped: Dict[int, List[dict]] = {}
        for row in cursor.fetchall():
            grouped.setdefault(row["character_id"], []).append(dict(row))
        return grouped


def get_active_character_ids(project_id: int, chapter_index: int, recent_window: int = 3) -> Set[int]:
    """获取活跃角色ID集合：核心角色 + 最近N章剧情中出场的角色。

    核心角色（protagonist/co_protagonist/heroine/villain）始终活跃。
    近期出场角色从 webnovel_chapter_plot 的 characters 列提取（逗号分隔）。
    """
    ids = set()

    # 核心角色始终活跃
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT id FROM webnovel_character_card WHERE project_id = ? AND character_type IN ('protagonist','co_protagonist','heroine','villain')",
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