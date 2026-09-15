"""约束包数据仓库。

提供 webnovel_csv_pack 表的 CRUD 操作，用于存储和检索分类约束包。
"""

import json
import re
import time
from typing import Dict, List, Optional

from repositories.base_repository import _get_conn, _lock, safe_str, safe_int

# 约束包题材归一化：genres_json 题材模板名 ↔ webnovel_csv_pack 题材标签 的映射。
# csv_pack 题材列（applicable_genre）用"题材模板体系"命名（玄幻/修真/高武、都市日常、
# 宫斗宅斗…），与项目 genre（如「修仙」）存在命名错位，先归一化再匹配避免 0 命中。
_PACK_GENRE_ALIASES = {
    "修仙": "修真", "凡人流": "修真", "仙侠": "修真", "修真": "修真",
    "电竞": "游戏体育", "直播文": "游戏体育",
}


def _normalize_pack_genre(genre: str) -> str:
    """约束包题材归一化：去空格 + 别名映射。"""
    if not genre:
        return ""
    g = (genre or "").strip()
    return _PACK_GENRE_ALIASES.get(g, g)


def _match_pack_genre_row(applicable_genre: str, norm_genre: str) -> bool:
    """判断约束包行是否匹配归一化题材。

    匹配规则（按优先级）：
    1. 题材列为空 → 兜底命中（通用约束包）
    2. 题材列为「通用」 → 兜底命中
    3. 题材列按 /、、, 拆分 token，任一 token 与归一化题材相等 → 命中
    4. 归一化题材是 token 的子串（如"种田"⊂"历史穿越-种田流"）→ 命中，保留合理子题材归并

    注意：不做反向子串匹配（token 是题材子串），避免"历史古代"误命中"古代 / 古言脑洞"
    这类跨题材误注入。
    """
    raw = (applicable_genre or "").strip()
    if not raw or raw == "通用":
        return True
    tokens = [t.strip() for t in re.split(r"[/、,，]", raw) if t.strip()]
    for t in tokens:
        if t == norm_genre:
            return True
        if norm_genre and norm_genre in t:
            return True
    return False


def filter_packs_by_template(packs: List[Dict], template_creative_constraints) -> List[Dict]:
    """按题材模板点名的通用叠加包过滤（策略 a：模板精选通用包）。

    题材类（M/F）全部保留（以运行时题材匹配为准）；通用类（U）只保留题材模板
    creative_constraints 中点名的那个包。模板未点名任何 U 包时保持原样（兜底，
    不因过滤导致约束包为空）。
    """
    if not packs:
        return packs
    cc = template_creative_constraints
    if isinstance(cc, (list, dict)):
        cc = json.dumps(cc, ensure_ascii=False)
    elif not isinstance(cc, str):
        cc = str(cc or "")
    named_u = set(re.findall(r"Pack\s*(U\d{2})", cc))
    if not named_u:
        return packs
    return [
        p for p in packs
        if not (p.get("pack_code") or "").startswith("U") or p.get("pack_code") in named_u
    ]


def get_csv_packs_by_genre(genre: str) -> List[Dict]:
    """根据题材获取相关的约束包（归一化 + token 匹配，含空题材/通用兜底）。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """
            SELECT * FROM webnovel_csv_pack
            ORDER BY category_group, sort_order, pack_code
            """
        )
        rows = [dict(r) for r in cursor.fetchall()]
    if not genre:
        return rows
    norm_genre = _normalize_pack_genre(genre)
    return [r for r in rows if _match_pack_genre_row(r.get("applicable_genre", ""), norm_genre)]


def add_csv_pack(
    pack_code: str,
    pack_name: str,
    category: str = "",
    category_group: str = "",
    rules: str = "",
    character_conflict: str = "",
    hooks: str = "",
    cool_points: str = "",
    applicable_genre: str = "",
    sort_order: int = 0,
) -> Dict:
    """添加一个约束包。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_csv_pack
            (pack_code, pack_name, category, category_group, rules,
             character_conflict, hooks, cool_points, applicable_genre, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (safe_str(pack_code), safe_str(pack_name), safe_str(category), safe_str(category_group),
             safe_str(rules), safe_str(character_conflict), safe_str(hooks), safe_str(cool_points),
             safe_str(applicable_genre), safe_int(sort_order))
        )
        conn.commit()
        return {"id": cursor.lastrowid, "pack_code": pack_code, "pack_name": pack_name}


def batch_add_csv_packs(packs: List[Dict]) -> int:
    """批量添加约束包。"""
    with _lock:
        conn = _get_conn()
        count = 0
        for pack in packs:
            try:
                conn.execute(
                    """
                    INSERT INTO webnovel_csv_pack
                    (pack_code, pack_name, category, category_group, rules,
                     character_conflict, hooks, cool_points, applicable_genre, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        safe_str(pack.get("pack_code", "")),
                        safe_str(pack.get("pack_name", "")),
                        safe_str(pack.get("category", "")),
                        safe_str(pack.get("category_group", "")),
                        safe_str(pack.get("rules", "")),
                        safe_str(pack.get("character_conflict", "")),
                        safe_str(pack.get("hooks", "")),
                        safe_str(pack.get("cool_points", "")),
                        safe_str(pack.get("applicable_genre", "")),
                        safe_int(pack.get("sort_order", 0)),
                    )
                )
                count += 1
            except Exception:
                pass
        conn.commit()
        return count


def get_csv_pack(pack_id: int) -> Optional[Dict]:
    """根据 ID 获取约束包。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_csv_pack WHERE id = ?",
            (pack_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def get_csv_pack_by_code(pack_code: str) -> Optional[Dict]:
    """根据代码获取约束包。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM webnovel_csv_pack WHERE pack_code = ?",
            (pack_code,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def get_all_csv_packs(
    category_group: str = "",
    category: str = "",
    applicable_genre: str = ""
) -> List[Dict]:
    """获取所有约束包，支持按分类分组、分类、适用题材过滤。"""
    with _lock:
        conn = _get_conn()
        query = "SELECT * FROM webnovel_csv_pack WHERE 1=1"
        params = []
        
        if category_group:
            query += " AND category_group = ?"
            params.append(category_group)
        
        if category:
            query += " AND category = ?"
            params.append(category)
        
        if applicable_genre:
            query += " AND (applicable_genre = ? OR applicable_genre LIKE ?)"
            params.extend([applicable_genre, f"%{applicable_genre}%"])
        
        query += " ORDER BY category_group, sort_order, pack_code"
        
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_csv_packs_by_category_group(category_group: str) -> List[Dict]:
    """按分类分组获取约束包。"""
    return get_all_csv_packs(category_group=category_group)


def update_csv_pack(pack_id: int, **kwargs) -> bool:
    """更新约束包。"""
    with _lock:
        conn = _get_conn()
        if not kwargs:
            return False
        
        keys = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(pack_id)
        
        conn.execute(
            f"UPDATE webnovel_csv_pack SET {keys} WHERE id = ?",
            values
        )
        conn.commit()
        return True


def delete_csv_pack(pack_id: int) -> bool:
    """删除约束包。"""
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM webnovel_csv_pack WHERE id = ?", (pack_id,))
        conn.commit()
        return True


def clear_all_csv_packs() -> int:
    """清空所有约束包。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute("DELETE FROM webnovel_csv_pack")
        conn.commit()
        return cursor.rowcount


def get_csv_pack_count() -> int:
    """获取约束包总数。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM webnovel_csv_pack")
        row = cursor.fetchone()
        return row["cnt"] if row else 0


def get_unique_categories() -> List[str]:
    """获取所有唯一的分类。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute("SELECT DISTINCT category FROM webnovel_csv_pack ORDER BY category")
        rows = cursor.fetchall()
        return [row["category"] for row in rows if row["category"]]


def get_unique_category_groups() -> List[str]:
    """获取所有唯一的分类分组。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute("SELECT DISTINCT category_group FROM webnovel_csv_pack ORDER BY category_group")
        rows = cursor.fetchall()
        return [row["category_group"] for row in rows if row["category_group"]]


def format_pack_for_prompt(packs: List[Dict]) -> str:
    """将约束包格式化为可供 AI 使用的提示文本。"""
    if not packs:
        return ""
    
    lines = ["【分类约束包参考】"]
    
    for pack in packs:
        lines.append(f"\n**Pack {pack.get('pack_code', '')} {pack.get('pack_name', '')}**")
        if pack.get("rules"):
            lines.append(f"- 规则限制：{pack['rules']}")
        if pack.get("character_conflict"):
            lines.append(f"- 角色矛盾：{pack['character_conflict']}")
        if pack.get("hooks"):
            lines.append(f"- 钩子：{pack['hooks']}")
        if pack.get("cool_points"):
            lines.append(f"- 爽点：{pack['cool_points']}")
    
    return "\n".join(lines)
