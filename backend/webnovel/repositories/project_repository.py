"""webnovel_project数据访问层。"""

import time
from typing import Optional, List, Dict, Any
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_webnovel_project(script_id: int, title: str = "", genre: str = "", genre_label: str = "",
                         target_words: int = 0, target_chapters: int = 0, one_liner: str = "",
                         story_summary: str = "", core_conflict: str = "", target_reader: str = "",
                         platform: str = "", anti_trope_rules: str = "", hard_constraints: str = "",
                         core_selling_points: str = "", opening_hook: str = "", protagonist_name: str = "",
                         protagonist_flaw: str = "", villain_mirror: str = "", protagonist_desire: str = "",
                         protagonist_archetype: str = "", protagonist_structure: str = "单主角",
                         heroine_config: str = "", heroine_names: str = "", heroine_role: str = "",
                         co_protagonists: str = "", co_protagonist_roles: str = "",
                         antagonist_tiers: str = "", antagonist_level: str = "",
                         golden_finger_name: str = "", golden_finger_type: str = "", golden_finger_style: str = "",
                         gf_visibility: str = "", gf_irreversible_cost: str = "",
                         world_scale: str = "", factions: str = "", power_system_type: str = "",
                         social_class: str = "", resource_distribution: str = "",
                         currency_system: str = "", currency_exchange: str = "",
                         sect_hierarchy: str = "", cultivation_chain: str = "", cultivation_subtiers: str = "") -> dict:
    """添加webnovel项目。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_project (script_id, title, genre, genre_label, target_words, target_chapters,
                                          one_liner, story_summary, core_conflict, target_reader, platform,
                                          anti_trope_rules, hard_constraints, core_selling_points, opening_hook,
                                          protagonist_name, protagonist_flaw, villain_mirror, protagonist_desire,
                                          protagonist_archetype, protagonist_structure, heroine_config, heroine_names,
                                          heroine_role, co_protagonists, co_protagonist_roles, antagonist_tiers,
                                          antagonist_level, golden_finger_name, golden_finger_type, golden_finger_style,
                                          gf_visibility, gf_irreversible_cost, world_scale, factions, power_system_type,
                                          social_class, resource_distribution, currency_system, currency_exchange,
                                          sect_hierarchy, cultivation_chain, cultivation_subtiers, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (safe_int(script_id), safe_str(title), safe_str(genre), safe_str(genre_label),
             safe_int(target_words), safe_int(target_chapters),
             safe_str(one_liner), safe_str(story_summary), safe_str(core_conflict),
             safe_str(target_reader), safe_str(platform),
             safe_str(anti_trope_rules), safe_str(hard_constraints),
             safe_str(core_selling_points), safe_str(opening_hook),
             safe_str(protagonist_name), safe_str(protagonist_flaw), safe_str(villain_mirror),
             safe_str(protagonist_desire),
             safe_str(protagonist_archetype), safe_str(protagonist_structure),
             safe_str(heroine_config), safe_str(heroine_names), safe_str(heroine_role),
             safe_str(co_protagonists), safe_str(co_protagonist_roles),
             safe_str(antagonist_tiers),
             safe_str(antagonist_level), safe_str(golden_finger_name),
             safe_str(golden_finger_type), safe_str(golden_finger_style),
             safe_str(gf_visibility), safe_str(gf_irreversible_cost),
             safe_str(world_scale), safe_str(factions), safe_str(power_system_type),
             safe_str(social_class), safe_str(resource_distribution),
             safe_str(currency_system), safe_str(currency_exchange),
             safe_str(sect_hierarchy), safe_str(cultivation_chain),
             safe_str(cultivation_subtiers), now, now)
        )
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "script_id": script_id,
            "title": title,
            "genre": genre,
            "genre_label": genre_label,
            "target_words": target_words,
            "target_chapters": target_chapters,
            "one_liner": one_liner,
            "story_summary": story_summary,
            "core_conflict": core_conflict,
            "target_reader": target_reader,
            "platform": platform,
            "anti_trope_rules": anti_trope_rules,
            "hard_constraints": hard_constraints,
            "core_selling_points": core_selling_points,
            "opening_hook": opening_hook,
            "protagonist_name": protagonist_name,
            "protagonist_flaw": protagonist_flaw,
            "villain_mirror": villain_mirror,
            "protagonist_desire": protagonist_desire,
            "protagonist_archetype": protagonist_archetype,
            "protagonist_structure": protagonist_structure,
            "heroine_config": heroine_config,
            "heroine_names": heroine_names,
            "heroine_role": heroine_role,
            "co_protagonists": co_protagonists,
            "co_protagonist_roles": co_protagonist_roles,
            "antagonist_tiers": antagonist_tiers,
            "antagonist_level": antagonist_level,
            "golden_finger_name": golden_finger_name,
            "golden_finger_type": golden_finger_type,
            "golden_finger_style": golden_finger_style,
            "gf_visibility": gf_visibility,
            "gf_irreversible_cost": gf_irreversible_cost,
            "world_scale": world_scale,
            "factions": factions,
            "power_system_type": power_system_type,
            "social_class": social_class,
            "resource_distribution": resource_distribution,
            "currency_system": currency_system,
            "currency_exchange": currency_exchange,
            "sect_hierarchy": sect_hierarchy,
            "cultivation_chain": cultivation_chain,
            "cultivation_subtiers": cultivation_subtiers,
            "created_at": now,
            "updated_at": now,
        }


def get_webnovel_project(project_id: int) -> Optional[dict]:
    """获取单个webnovel项目。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_project WHERE id = ?",
            (project_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_webnovel_project_by_script(script_id: int) -> Optional[dict]:
    """根据剧本ID获取webnovel项目。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_project WHERE script_id = ?",
            (script_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def update_webnovel_project(project_id: int, **kwargs) -> bool:
    """更新webnovel项目。"""
    with _lock:
        conn = _get_conn()
        kwargs["updated_at"] = time.time()
        keys = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(project_id)
        conn.execute(
            f"UPDATE webnovel_project SET {keys} WHERE id = ?",
            values
        )
        conn.commit()
        return True


def delete_webnovel_project(project_id: int) -> bool:
    """删除webnovel项目（手动级联清理所有webnovel_*关联子表 + 外键CASCADE双重保险）。

    ⚠️ 【严禁将 llm_call_logs、scripts 等非 webnovel_* 业务表加入清理范围】
       - llm_call_logs 是问题分析依据，必须永久保留；
       - scripts 表是剧本主数据，生命周期独立于 webnovel 初始化结果。
       下方同时做了两层机制保证：① 白名单仅包含显式列出的 webnovel_ 表；
       ② 执行前再加一次 startswith("webnovel_") 前缀过滤校验。
    """
    with _lock:
        conn = _get_conn()
        # 为稳妥起见，按依赖顺序手动清理所有直接通过 project_id 关联的 webnovel_* 子表
        # （外键 CASCADE 已开启，这里做双保险避免历史库未开启FK时留下孤儿数据）
        direct_project_tables = [
            "webnovel_idea_bank",
            "webnovel_review_record",
            "webnovel_chapter_meta",
            "webnovel_plot_thread",
            "webnovel_state",
            "webnovel_genre_fusion",
            "webnovel_timeline",
            "webnovel_foreshadow",
            "webnovel_volume_outline",
            "webnovel_worldview",
            "webnovel_power_system",
            "webnovel_villain",
            "webnovel_character_group",
            "webnovel_character_card",
            "webnovel_golden_finger",
            "webnovel_master_setting",
            "webnovel_anti_pattern",
        ]
        from utils.logger import logger as _l
        for tbl in direct_project_tables:
            # 防御：白名单前缀二次校验，绝不误删非 webnovel_* 表
            if not tbl.startswith("webnovel_"):
                _l.warning(f"[project_repository] 拒绝删除非 webnovel_ 表: {tbl}（已跳过）")
                continue
            try:
                conn.execute(f"DELETE FROM {tbl} WHERE project_id = ?", (project_id,))
            except Exception as e:
                # 个别表不存在不影响整体删除（兼容历史版本库）
                _l.warning(f"[project_repository] 清理 {tbl} 时忽略错误: {e}")
        conn.execute("DELETE FROM webnovel_project WHERE id = ?", (project_id,))
        conn.commit()
        return True


def delete_webnovel_project_by_script(script_id: int) -> bool:
    """根据 script_id 删除对应的 webnovel 项目（若存在）。用于初始化失败后清理脏数据。

    Returns:
        True 表示确实删除了项目；False 表示不存在可删除的项目。
    """
    proj = get_webnovel_project_by_script(script_id)
    if not proj:
        return False
    delete_webnovel_project(proj["id"])
    return True