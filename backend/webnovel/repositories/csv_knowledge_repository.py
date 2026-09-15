"""CSV 知识通用仓库。

提供 webnovel_csv_* 系列表（除 csv_pack 已有独立仓库外）的统一查询与格式化接口。
用于深度初始化阶段的直接注入（路径 A）和 RAG 索引构建（路径 B）。

支持表：
  csv_genre_tone, csv_golden_finger, csv_verdict_rules,
  csv_pacing, csv_plot, csv_scene, csv_naming, csv_writing, csv_character
"""

from typing import Dict, List, Optional

from repositories.base_repository import _get_conn, _lock, safe_str


# ──────────────────────────────────────────────────────────
# 通用查询
# ──────────────────────────────────────────────────────────
# 题材别名归一化：genres_json 题材模板体系 ↔ CSV 知识表题材标签体系 的映射。
# CSV 表题材标签全集：仙侠/玄幻/都市/悬疑/奇幻/科幻/历史/古言/现言/幻言/种田/
# 快穿/年代/游戏/衍生/全部（applicable_genre 或 genre 列，| 分隔多题材）。
# 项目 genre 来自题材模板（如「修仙」），先归一化再匹配，避免命名错位导致 0 命中。
_GENRE_ALIASES = {
    # 修仙/修真 体系 → 仙侠
    "修仙": "仙侠", "修真": "仙侠", "凡人流": "仙侠", "修仙门派": "仙侠",
    "玄幻修仙": "玄幻", "都市修真": "都市", "高武": "都市",
    # 悬疑 体系
    "悬疑灵异": "悬疑", "灵异": "悬疑", "恐怖": "悬疑", "规则怪谈": "悬疑",
    "女频悬疑": "悬疑", "悬疑脑洞": "悬疑",
    # 言情 体系
    "古代言情": "古言", "宫斗宅斗": "古言", "民国言情": "古言",
    "现代言情": "现言", "职场婚恋": "现言", "豪门总裁": "现言",
    "青春甜宠": "现言", "狗血言情": "现言", "替身文": "现言",
    "幻想言情": "幻言", "多子多福": "幻言",
    # 奇幻/科幻/历史 体系
    "西方玄幻": "西幻", "西幻": "西幻", "奇幻": "奇幻",
    "科幻末世": "科幻", "末世": "科幻", "无限流": "科幻",
    "历史脑洞": "历史", "抗战谍战": "历史", "年代": "年代",
    "快穿": "快穿", "游戏体育": "游戏", "电竞": "游戏", "直播文": "游戏",
    "种田": "种田", "衍生": "衍生", "现实题材": "都市",
    "都市异能": "都市", "都市日常": "都市", "都市脑洞": "都市",
    "系统流": "玄幻", "克苏鲁": "悬疑", "黑暗题材": "悬疑", "知乎短篇": "现言",
}



def normalize_genre(genre: str) -> str:
    """题材归一化：去空格 + 别名映射，返回可匹配的题材词。"""
    if not genre:
        return ""
    g = (genre or "").strip()
    return _GENRE_ALIASES.get(g, g)


def _csv_genre_rows(table_name: str, order_by: str) -> List[Dict]:
    """读取 CSV 表全量行（含题材列与空题材行）。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(f"SELECT * FROM {table_name} ORDER BY {order_by}")
        return [dict(row) for row in cursor.fetchall()]


def _match_genre_row(row: Dict, genre_column: str, norm_genre: str) -> bool:
    """判断一行是否匹配归一化题材。

    匹配规则（按优先级）：
    1. 题材列为空 → 兜底命中（全局知识行）
    2. 题材列按 | 拆分 token，任一 token 与归一化题材相等 → 命中
    3. 任一 token 包含归一化题材（或反向包含，如"玄幻修仙"含"修仙"）→ 命中
    """
    raw = (row.get(genre_column) or "").strip()
    if not raw:
        return True
    tokens = [t.strip() for t in raw.split("|") if t.strip()]
    for t in tokens:
        tn = normalize_genre(t)
        if not tn:
            continue
        if tn == norm_genre:
            return True
        if norm_genre and (norm_genre in tn or tn in norm_genre):
            return True
    return False


def query_csv_knowledge(
    table_name: str,
    genre: str = "",
    genre_column: str = "applicable_genre",
    order_by: str = "id",
) -> List[Dict]:
    """通用 CSV 知识表查询。

    Args:
        table_name: 表名（如 'webnovel_csv_golden_finger'），仅允许 csv_* 表
        genre: 按题材过滤（归一化 + token 匹配）；空字符串不过滤（返回全量）
        genre_column: 题材列名，多数表为 applicable_genre，verdict_rules 为 genre
        order_by: 排序列

    Returns:
        匹配的行列表（dict）
    """
    allowed = {
        "webnovel_csv_genre_tone", "webnovel_csv_golden_finger",
        "webnovel_csv_verdict_rules", "webnovel_csv_pacing",
        "webnovel_csv_plot", "webnovel_csv_scene",
        "webnovel_csv_naming", "webnovel_csv_writing",
        "webnovel_csv_character",
    }
    if table_name not in allowed:
        return []

    rows = _csv_genre_rows(table_name, order_by)
    if not genre:
        return rows

    norm_genre = normalize_genre(genre)
    return [r for r in rows if _match_genre_row(r, genre_column, norm_genre)]


# ──────────────────────────────────────────────────────────
# 直接注入格式化（路径 A — 小量知识塞进 prompt）
# ──────────────────────────────────────────────────────────

# 每张表的 (锚点标签, [(字段名, 显示标签)])
_TABLE_FIELD_SPECS = {
    "webnovel_csv_golden_finger": ("金手指设计", [
        ("setting_type", "设定类型"),
        ("value_control_boundary", "数值控制边界"),
        ("plot_interaction", "剧情互动方式"),
        ("pitfalls", "常见陷阱"),
    ]),
    "webnovel_csv_genre_tone": ("题材基调", [
        ("core_tone", "核心基调"),
        ("pacing_strategy", "节奏策略"),
        ("genre_flow", "题材流转"),
    ]),
    "webnovel_csv_naming": ("命名规则", [
        ("naming_object", "命名对象"),
        ("rules", "规则"),
        ("positive_example", "正例"),
        ("negative_example", "反例"),
    ]),
    "webnovel_csv_verdict_rules": ("裁决规则", [
        ("style_priority", "风格优先级"),
        ("payoff_priority", "爽点优先级"),
        ("conflict_verdict", "冲突裁决"),
        ("anti_pattern", "反套路"),
    ]),
    "webnovel_csv_pacing": ("节奏控制", [
        ("pacing_type", "节奏类型"),
        ("emotion_technique", "情绪技法"),
        ("pitfalls", "陷阱"),
    ]),
    "webnovel_csv_plot": ("剧情模板", [
        ("plot_name", "模板名称"),
        ("setup", "铺垫"),
        ("core_payoff", "核心爽点"),
        ("twist_design", "反转设计"),
        ("anti_cliche_variant", "反套路变体"),
    ]),
    "webnovel_csv_scene": ("场景模式", [
        ("scene_type", "场景类型"),
        ("mode_name", "模式名称"),
        ("description", "描述"),
        ("example", "示例"),
    ]),
    "webnovel_csv_writing": ("写作技巧", [
        ("technique_type", "技巧类型"),
        ("technique_name", "技巧名称"),
        ("applicable_scene", "适用场景"),
        ("pitfalls", "陷阱"),
    ]),
    "webnovel_csv_character": ("角色知识", [
        ("character_type", "角色类型"),
        ("core_motivation", "核心动机"),
        ("behavior_logic", "行为逻辑"),
        ("interaction_pattern", "互动模式"),
    ]),
}


def format_csv_knowledge_for_prompt(
    table_name: str,
    rows: List[Dict],
    header: str = "",
) -> str:
    """将 CSV 知识行格式化为紧凑文本，供直接注入 prompt。

    格式示例：
        【金手指设计知识】
        - 设定类型: 系统流。数值控制边界: 不能直接加属性。常见陷阱: 数值膨胀失控。
        - 设定类型: 老爷爷。数值控制边界: 每日使用次数有限。...

    Args:
        table_name: 表名，用于查找字段规格
        rows: 查询结果行
        header: 自定义标题（默认从 _TABLE_FIELD_SPECS 取）

    Returns:
        格式化文本；无数据时返回空字符串
    """
    if not rows:
        return ""

    spec = _TABLE_FIELD_SPECS.get(table_name)
    if not spec:
        return ""

    section_label, field_specs = spec
    if not header:
        header = f"【{section_label}知识】"

    lines = [header]
    for row in rows:
        parts = []
        for field_key, field_label in field_specs:
            val = str(row.get(field_key, "") or "").strip()
            if val:
                parts.append(f"{field_label}: {val}")
        if parts:
            lines.append(f"- {'。'.join(parts)}。")

    return "\n".join(lines) if len(lines) > 1 else ""


# ──────────────────────────────────────────────────────────
# RAG 索引格式化（路径 B — 自然语言锚点 + 标签化知识体）
# ──────────────────────────────────────────────────────────

# RAG chunk 使用的锚点标签
_RAG_ANCHOR_LABELS = {
    "webnovel_csv_golden_finger": "金手指设计",
    "webnovel_csv_genre_tone": "题材基调",
    "webnovel_csv_verdict_rules": "裁决规则",
    "webnovel_csv_pacing": "节奏技巧",
    "webnovel_csv_plot": "剧情技巧",
    "webnovel_csv_scene": "场景模式",
    "webnovel_csv_naming": "命名规则",
    "webnovel_csv_writing": "写作技巧",
    "webnovel_csv_character": "角色知识",
}

# RAG 索引时使用的字段（与直接注入相同，但不含 pitfalls 等负面知识）
_RAG_FIELD_SPECS = {
    "webnovel_csv_golden_finger": [
        ("setting_type", "设定类型"),
        ("value_control_boundary", "数值控制边界"),
        ("plot_interaction", "剧情互动方式"),
    ],
    "webnovel_csv_genre_tone": [
        ("core_tone", "核心基调"),
        ("pacing_strategy", "节奏策略"),
        ("genre_flow", "题材流转"),
    ],
    "webnovel_csv_naming": [
        ("naming_object", "命名对象"),
        ("rules", "规则"),
        ("positive_example", "正例"),
    ],
    "webnovel_csv_verdict_rules": [
        ("style_priority", "风格优先级"),
        ("payoff_priority", "爽点优先级"),
        ("conflict_verdict", "冲突裁决"),
        ("anti_pattern", "反套路"),
    ],
    "webnovel_csv_pacing": [
        ("pacing_type", "节奏类型"),
        ("emotion_technique", "情绪技法"),
    ],
    "webnovel_csv_plot": [
        ("plot_name", "模板名称"),
        ("setup", "铺垫"),
        ("core_payoff", "核心爽点"),
        ("twist_design", "反转设计"),
        ("anti_cliche_variant", "反套路变体"),
    ],
    "webnovel_csv_scene": [
        ("scene_type", "场景类型"),
        ("mode_name", "模式名称"),
        ("description", "描述"),
        ("example", "示例"),
    ],
    "webnovel_csv_writing": [
        ("technique_type", "技巧类型"),
        ("technique_name", "技巧名称"),
        ("applicable_scene", "适用场景"),
    ],
    "webnovel_csv_character": [
        ("character_type", "角色类型"),
        ("core_motivation", "核心动机"),
        ("behavior_logic", "行为逻辑"),
        ("interaction_pattern", "互动模式"),
    ],
}


def build_csv_knowledge_chunk_text(table_name: str, row: Dict) -> str:
    """将单行 CSV 知识格式化为 RAG 索引文本（自然语言锚点 + 标签化知识体）。

    格式示例：
        【剧情技巧】退婚打脸。
        铺垫：主角在宗门被未婚妻当众退婚，遭到众人嘲笑。
        核心爽点：主角暗中突破后在宗门大比上击败前未婚妻的未婚夫。
        反转设计：前未婚妻家族后悔想重新联姻被拒。

    Args:
        table_name: 表名
        row: 数据行

    Returns:
        格式化文本；无有效内容时返回空字符串
    """
    anchor_label = _RAG_ANCHOR_LABELS.get(table_name, "知识")
    field_specs = _RAG_FIELD_SPECS.get(table_name, [])
    if not field_specs:
        return ""

    # 确定锚点名称：优先使用表的特有名称字段
    anchor_name = ""
    name_field_map = {
        "webnovel_csv_plot": "plot_name",
        "webnovel_csv_scene": "mode_name",
        "webnovel_csv_writing": "technique_name",
        "webnovel_csv_naming": "naming_object",
        "webnovel_csv_character": "character_type",
        "webnovel_csv_pacing": "pacing_type",
        "webnovel_csv_golden_finger": "setting_type",
        "webnovel_csv_genre_tone": "category",
        "webnovel_csv_verdict_rules": "category",
    }
    name_key = name_field_map.get(table_name, "")
    if name_key:
        anchor_name = str(row.get(name_key, "") or "").strip()

    if anchor_name:
        opener = f"【{anchor_label}】{anchor_name}。"
    else:
        code = str(row.get("code", "") or "").strip()
        opener = f"【{anchor_label}】{code}。" if code else f"【{anchor_label}】。"

    # 构建标签化知识体
    body_parts = []
    for field_key, field_label in field_specs:
        val = str(row.get(field_key, "") or "").strip()
        if val:
            body_parts.append(f"{field_label}：{val}。")

    if not body_parts:
        return opener

    return opener + "\n".join(body_parts)
