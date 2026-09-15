"""资源注册表：智能创作流程所有可注入 prompt 区块的统一资源定义。

每类可注入内容对应一个"资源"：定义加载器（从业务库/上游产物加载数据）
与格式化器（渲染为 prompt 区块文本）。ContextAnalyzer 依据 LLM 的
structured_refs 选择，通过本注册表加载并渲染区块，统一组装 assembled_context。

资源分三类：
1. 结构化可查询资源：业务库数据（角色卡/世界观/伏笔/前文/状态表等），由 LLM 选择
2. RAG 可查询资源：向量库检索（rag_queries 生成），由 LLM 选择查询
3. 创作约束：静态约束（审查维度/写作规范）+ 动态约束（consistency_notes）+
   数据型约束（不可提前揭示伏笔），装配器生成，不经 LLM 选择

失败即报错：任何资源加载/渲染失败抛 ContextAnalysisError，由上游中断流程。
"""

import json
from typing import Any, Dict, List, Optional

from utils.logger import log_manager

from webnovel.repositories import (
    get_character_card,
    get_character_cards_by_project,
    get_character_items_by_project,
    get_character_relationships,
    get_open_loops_by_project,
    get_worldview_by_project, get_worldview_factions,
    get_power_system_by_project,
    get_golden_finger_by_project,
    get_character_group_by_project, get_character_group_members,
    get_timelines_by_project, get_timeline_chapters,
)
from repositories.base_repository import safe_int
from webnovel.repositories.character_state_repository import (
    get_character_states_before_chapter,
    get_character_states_by_chapter,
)

_logger = log_manager.get_logger("resource_registry")


class ContextAnalysisError(Exception):
    """上下文分析/装配失败，直接报错中断流程，不做任何降级。"""


# character_type 英文 → 中文标签
_CHAR_TYPE_LABELS = {
    'protagonist': '主角', 'co_protagonist': '主角团核心',
    'heroine': '女主', 'villain': '反派',
    'supporting': '配角', 'minor': '龙套',
}

# 审查维度常量（原 executor 常量，收敛到注册表统一管理）
REVIEW_DIMENSIONS = {
    "chapter_plot_reviewer": [
        {"key": "completeness", "name": "规划覆盖", "description": "是否覆盖了章节规划中的所有关键事件和必须覆盖节点"},
        {"key": "logic", "name": "因果逻辑", "description": "剧情节点之间的因果关系是否合理，有无逻辑断裂或跳跃"},
        {"key": "conflict", "name": "冲突张力", "description": "剧情结构中的冲突设计是否充分，是否有足够的转折和悬念"},
        {"key": "setting_match", "name": "设定匹配", "description": "剧情点行为是否符合角色能力、金手指与世界观规则，有无超出设定边界的行为"},
    ],
    "draft_reviewer": [
        {"key": "excitement", "name": "爽点呈现", "description": "爽点是否在正文中得到充分展现，是否有足够的感染力"},
        {"key": "consistency", "name": "设定一致", "description": "人物性格、能力、世界观设定在正文中是否保持一致，角色行为是否符合性格；同时核对：角色状态连续（受伤/恢复/情绪）、物品持有与使用是否遵循清单（禁止凭空出现）、有无说出超出自身知识边界的信息"},
        {"key": "rhythm", "name": "节奏控制", "description": "文字节奏是否合理，场景详略是否得当"},
        {"key": "coherence", "name": "叙事连贯", "description": "叙事是否连贯流畅，有无突兀跳跃或断裂；时间线是否自洽（事件先后、日夜/季节）"},
        {"key": "retention", "name": "结尾自然度", "description": "章节是否收尾于自然节拍，让读者无感知地滑入下一章；设问收束、旁白预告、总结预言、公式化追加悬念应扣分；不要因缺少显式钩子扣分"},
    ],
}

# ── 加载器：统一签名 loader(ref, env) -> data ──────────────────
# env = {"inventory", "structural_data", "task_inputs", "project_id", "script_id", "chapter_index"}


def _load_chapter_plan(ref, env):
    plan = env["structural_data"].get("current_chapter_plan")
    if not plan:
        raise ContextAnalysisError("章节规划资源加载失败：current_chapter_plan 为空")
    return plan


def _load_volume_outline(ref, env):
    vol = env["structural_data"].get("current_volume")
    if not vol:
        raise ContextAnalysisError("卷纲资源加载失败：current_volume 为空")
    return vol


def _load_project(ref, env):
    proj = env["structural_data"].get("project")
    if not proj:
        raise ContextAnalysisError("项目信息资源加载失败：project 为空")
    return proj


def _load_character_states(ref, env):
    states = env["structural_data"].get("last_character_states") or []
    if not states:
        # 首章（chapter_index<=1）无上章末状态属正常空态，返回空列表由装配层跳过空区块；
        # 非首章缺上章状态视为数据链断裂（上章应用结果缺失），保持失败即报错
        chapter_index = env.get("chapter_index") or 0
        if chapter_index <= 1:
            return []
        raise ContextAnalysisError("上章末角色状态资源加载失败：last_character_states 为空")
    return states


def _load_previous_hook(ref, env):
    hook = env["structural_data"].get("previous_hook") or {}
    if not hook.get("hook_content"):
        # 首章无上一章结尾属正常空态，返回空 dict 由装配层跳过空区块；
        # 非首章为空视为数据链断裂（上章 chapter_meta 缺失），保持失败即报错
        chapter_index = env.get("chapter_index") or 0
        if chapter_index <= 1:
            return {}
        raise ContextAnalysisError("上一章结尾状态资源加载失败：previous_hook 为空")
    return hook


def _load_character_cards(ref, env):
    ids = ref.get("ids") or []
    if not ids:
        raise ContextAnalysisError("角色卡资源加载失败：未选择角色 id")
    project_id = env["project_id"]
    try:
        items_by_char = get_character_items_by_project(project_id)
    except Exception:
        items_by_char = {}
    characters = []
    for cid in ids:
        card = get_character_card(project_id, cid)
        if not card:
            continue
        characters.append(_build_card_enriched(card, project_id, items_by_char))
    if not characters:
        raise ContextAnalysisError(f"角色卡资源加载失败：ids={ids} 均无有效数据")
    # 主角排最前
    characters.sort(key=lambda c: (c.get("role") != "主角", c.get("role") != "主角团核心"))
    return characters


def _load_character_group(ref, env):
    project_id = env["project_id"]
    char_group = get_character_group_by_project(project_id)
    if not char_group:
        raise ContextAnalysisError("主角团资源加载失败：未设定角色组")
    group_members = get_character_group_members(char_group["id"])
    all_chars = {c.get("id"): c for c in get_character_cards_by_project(project_id)}
    enriched = []
    for m in group_members:
        info = {**m}
        card = all_chars.get(m.get("character_id"))
        if card:
            info["character_name"] = card.get("name", "")
            info["personality"] = card.get("core_personality", "")
            info["identity"] = card.get("identity", "")
        enriched.append(info)
    return {**char_group, "enriched_members": enriched}


def _load_worldview(ref, env):
    project_id = env["project_id"]
    worldview = get_worldview_by_project(project_id)
    if not worldview:
        raise ContextAnalysisError("世界观资源加载失败：未设定世界观")
    worldview["factions_list"] = get_worldview_factions(worldview["id"])
    return [worldview]


def _load_power_system(ref, env):
    project_id = env["project_id"]
    ps = get_power_system_by_project(project_id)
    if not ps:
        raise ContextAnalysisError("力量体系资源加载失败：未设定力量体系")
    return ps


def _load_golden_finger(ref, env):
    project_id = env["project_id"]
    gf = get_golden_finger_by_project(project_id)
    if not gf:
        raise ContextAnalysisError("金手指资源加载失败：未设定金手指")
    return gf


def _load_foreshadows(ref, env):
    ids = {str(i) for i in (ref.get("ids") or [])}
    if not ids:
        # 当前无活跃伏笔属正常空态（LLM 传空 ids 表示无需注入），
        # 返回空列表由装配层跳过空区块
        return []
    loops = [f for f in env["inventory"].get("foreshadows", []) if str(f.get("id")) in ids]
    if not loops:
        raise ContextAnalysisError(f"伏笔资源加载失败：ids={sorted(ids)} 在活跃伏笔中不存在")
    return loops


def _load_timeline(ref, env):
    """章节时间轴：按卷匹配时间线主记录 + 章节锚点列表。

    项目暂无时间轴数据时返回 None（渲染为空区块，自动跳过），不视为失败——
    时间轴是辅助参考资源，未生成时间线的项目/卷不应阻断创作。
    """
    project_id = env["project_id"]
    timelines = get_timelines_by_project(project_id)
    if not timelines:
        return None
    vol = env["structural_data"].get("current_volume") or {}
    volume_number = ref.get("volume_number") or vol.get("volume_number")
    tl = None
    if volume_number is not None:
        for t in timelines:
            if t.get("volume_number") == volume_number:
                tl = t
                break
    if tl is None:
        tl = timelines[0]
    chapters = get_timeline_chapters(tl["id"]) or []
    return {"timeline": tl, "chapters": chapters}


def _load_previous_chapter(ref, env):
    chapter_index = ref.get("chapter_index")
    if chapter_index is None:
        raise ContextAnalysisError("前文资源加载失败：未指定 chapter_index")
    if chapter_index <= 0:
        # 首章无前文属正常空态（LLM 可能以 chapter_index=0 表达"无前文"），
        # 返回空 dict 由装配层跳过空区块
        return {}
    depth = ref.get("depth", "full")
    if depth == "summary":
        for ch in env["inventory"].get("previous_chapters", []):
            if ch.get("index") == chapter_index:
                summary = ch.get("summary", "")
                if not summary:
                    raise ContextAnalysisError(f"第{chapter_index}章摘要为空")
                return {"chapter_index": chapter_index, "content": summary, "is_summary": True}
        # env 仅保留窗口（最近 5 章）；更早章节按章从 RAG 查摘要，不依赖 env
        summary = _fetch_chapter_summary(env.get("project_id"), chapter_index)
        if not summary:
            raise ContextAnalysisError(
                f"第{chapter_index}章不在前文清单中（env 无摘要且 RAG 未命中）")
        return {"chapter_index": chapter_index, "content": summary, "is_summary": True}
    # full / tail：加载全文
    content = _read_chapter_content(env["script_id"], chapter_index)
    if not content:
        raise ContextAnalysisError(f"第{chapter_index}章全文读取失败")
    return {"chapter_index": chapter_index, "content": content, "is_latest": True}


def _read_chapter_content(script_id: int, chapter_index: int) -> Optional[str]:
    """读取章节全文。"""
    try:
        from services.script_service import ScriptService
        svc = ScriptService()
        content = svc._read_script_chapter_content(script_id, chapter_index)
        if content:
            return content
    except Exception:
        pass
    from repositories import get_script_lines
    lines = get_script_lines(script_id, chapter_index)
    if lines:
        return "\n".join(line["content"] for line in lines)
    return None


def _fetch_chapter_summary(project_id: Optional[int], chapter_index: int) -> Optional[str]:
    """按章号从 RAG 取章节摘要（chapter_summary 类型，全量可查）。"""
    if not project_id:
        return None
    try:
        from services.vector_store import get_rag_service
        for doc in get_rag_service().get_chunks(project_id, "chapter_summary"):
            if doc.get("chapter_number") == chapter_index:
                content = doc.get("content", "")
                return content if content else None
    except Exception:
        pass
    return None


def _load_plot_list(ref, env):
    plot_list = env["task_inputs"].get("plot_list")
    if plot_list is None:
        raise ContextAnalysisError("剧情列表任务输入缺失")
    return plot_list


def _load_review_result(ref, env):
    review_result = env["task_inputs"].get("review_result")
    if review_result is None:
        raise ContextAnalysisError("审查结果任务输入缺失")
    return review_result


# ── 结构化查询处理器：统一签名 query_loader(ref, env) -> list ──
# ref = {"resource", "filters": {...}, "text", "limit"}
# 全量拉取 + 内存过滤（数据量小，毫秒级），结果复用现有 formatter 渲染。

def _build_card_enriched(card: dict, project_id: int, items_by_char: dict) -> dict:
    """单张角色卡 → 富化结构（含物品/关系），与 _load_character_cards 一致。"""
    raw_type = card.get("character_type", "")
    rels = []
    try:
        rels = [
            {"target": r.get("target_name", ""), "type": r.get("relation_type", ""),
             "desc": (r.get("description") or "")[:40]}
            for r in get_character_relationships(card.get("id"))
            if r.get("target_name") and r.get("relation_type")
        ]
    except Exception:
        rels = []
    return {
        "role": _CHAR_TYPE_LABELS.get(raw_type, raw_type),
        "character_name": card.get("name", ""),
        "alias": card.get("alias", ""),
        "identity": card.get("identity", ""),
        "protagonist_relation": card.get("protagonist_relation", ""),
        "personality": card.get("core_personality", ""),
        "flaw": card.get("personality_flaw", ""),
        "goals": card.get("true_desire", "") or card.get("long_term_goal", ""),
        "abilities": card.get("ability_limit", ""),
        "relationships": rels,
        "items": [
            {"name": it.get("item_name", ""),
             "quantity": it.get("quantity", 1) or 1,
             "desc": it.get("source", "") or it.get("change_note", "")}
            for it in items_by_char.get(card.get("id"), [])
            if it.get("item_name")
        ],
    }


def _query_character_cards(ref, env):
    """按 filters 检索角色卡：type（中文/英文）/keyword（name/identity/personality）/ids。"""
    filters = ref.get("filters") or {}
    limit = ref.get("limit", 5)
    project_id = env["project_id"]
    cards = get_character_cards_by_project(project_id) or []
    type_f = filters.get("type")
    if type_f:
        label_to_raw = {v: k for k, v in _CHAR_TYPE_LABELS.items()}
        raw = label_to_raw.get(type_f, type_f)
        cards = [c for c in cards if c.get("character_type") == raw]
    ids = filters.get("ids")
    if ids:
        id_set = {str(i) for i in ids}
        cards = [c for c in cards if str(c.get("id")) in id_set]
    keyword = filters.get("keyword")
    if keyword:
        kw = str(keyword)
        cards = [c for c in cards if kw in str(c.get("name", ""))
                 or kw in str(c.get("identity", ""))
                 or kw in str(c.get("core_personality", ""))]
    if not cards:
        return []
    try:
        items_by_char = get_character_items_by_project(project_id)
    except Exception:
        items_by_char = {}
    enriched = [_build_card_enriched(c, project_id, items_by_char) for c in cards]
    # 主角排最前
    enriched.sort(key=lambda c: (c.get("role") != "主角", c.get("role") != "主角团核心"))
    return enriched[:limit]


def _query_character_states(ref, env):
    """按 filters 检索角色状态：chapter（指定章）/name/keyword。"""
    filters = ref.get("filters") or {}
    limit = ref.get("limit", 5)
    project_id = env["project_id"]
    chapter = filters.get("chapter")
    if chapter is not None:
        states = get_character_states_by_chapter(project_id, safe_int(chapter)) or []
    else:
        # 未指定章 → 最近一章状态（与写作侧"上章末状态"一致）
        states = get_character_states_before_chapter(project_id, 10 ** 9) or []
    name = filters.get("name")
    if name:
        states = [s for s in states if str(name) in str(s.get("character_name", ""))]
    cid = filters.get("character_id")
    if cid is not None:
        states = [s for s in states if str(s.get("character_id")) == str(cid)]
    keyword = filters.get("keyword")
    if keyword:
        states = [s for s in states if str(keyword) in str(s.get("state_summary", ""))]
    return states[:limit]


def _query_foreshadows(ref, env):
    """按 filters 检索伏笔：status（active/resolved）/tier/chapter（planted<=）/keyword。"""
    filters = ref.get("filters") or {}
    limit = ref.get("limit", 8)
    project_id = env["project_id"]
    loops = get_open_loops_by_project(project_id) or []
    status = filters.get("status")
    if status in ("active", "open"):
        loops = [l for l in loops if l.get("status") == "active"]
    elif status == "resolved":
        loops = [l for l in loops if l.get("status") == "resolved"]
    tier = filters.get("tier")
    if tier:
        loops = [l for l in loops if str(tier) in str(l.get("tier", ""))]
    chapter = filters.get("chapter")
    if chapter is not None:
        loops = [l for l in loops if (l.get("planted_chapter") or 0) <= safe_int(chapter)]
    keyword = filters.get("keyword")
    if keyword:
        loops = [l for l in loops if str(keyword) in str(l.get("content", ""))]
    return loops[:limit]


def _query_timeline(ref, env):
    """按 filters 检索时间轴：volume（卷号）/chapter（章号）。"""
    filters = ref.get("filters") or {}
    project_id = env["project_id"]
    timelines = get_timelines_by_project(project_id) or []
    if not timelines:
        return []
    volume = filters.get("volume")
    tl = None
    if volume is not None:
        for t in timelines:
            if t.get("volume_number") == safe_int(volume):
                tl = t
                break
    if tl is None:
        tl = timelines[0]
    chapters = get_timeline_chapters(tl["id"]) or []
    ch = filters.get("chapter")
    if ch is not None:
        chapters = [c for c in chapters if c.get("chapter_number") == safe_int(ch)]
    return [{"timeline": tl, "chapters": chapters}]


def _query_items(ref, env):
    """按 filters 检索角色物品：character（角色名/id）/keyword（物品名/变更说明）。"""
    filters = ref.get("filters") or {}
    limit = ref.get("limit", 10)
    project_id = env["project_id"]
    items_by_char = get_character_items_by_project(project_id) or {}
    name_by_id = {c.get("id"): c.get("name", "?") for c in (get_character_cards_by_project(project_id) or [])}
    rows = []
    for cid, items in items_by_char.items():
        for it in items:
            row = dict(it)
            row["character_id"] = cid
            row["character_name"] = name_by_id.get(cid, f"角色#{cid}")
            rows.append(row)
    char = filters.get("character")
    if char:
        rows = [r for r in rows if str(char) == str(r.get("character_id"))
                or str(char) in str(r.get("character_name", ""))]
    keyword = filters.get("keyword")
    if keyword:
        rows = [r for r in rows if str(keyword) in str(r.get("item_name", ""))
                or str(keyword) in str(r.get("change_note", ""))]
    only_held = filters.get("only_held", True)
    if only_held:
        rows = [r for r in rows if r.get("status") != "lost"]
    return rows[:limit]


# ── 格式化器：统一签名 formatter(data, depth) -> str（不含区块标题）──

def _fmt_chapter_plan(plan, depth="full"):
    parts = []
    title = plan.get("chapter_title", "")
    if title:
        parts.append(f"标题: {title}")
    if plan.get("summary"):
        parts.append(f"概要: {plan['summary']}")
    if plan.get("key_events"):
        ke = plan["key_events"]
        parts.append(f"关键事件: {ke[:400] if isinstance(ke, str) else json.dumps(ke, ensure_ascii=False)[:400]}")
    if plan.get("rhythm"):
        parts.append(f"节奏: {plan['rhythm']}")
    if plan.get("cpns"):
        parts.append(f"剧情节点: {plan['cpns']}")
    if plan.get("cen"):
        parts.append(f"结束节点: {plan['cen']}")
    if plan.get("must_cover_nodes"):
        nodes = plan["must_cover_nodes"]
        parts.append(f"必须覆盖节点: {json.dumps(nodes, ensure_ascii=False) if isinstance(nodes, list) else nodes}")
    if plan.get("forbidden_zones"):
        parts.append(f"禁忌区域: {plan['forbidden_zones']}")
    return "\n".join(parts) if parts else "（无章节规划内容）"


def _fmt_volume_outline(vol, depth="full"):
    parts = []
    if vol.get("volume_name"):
        parts.append(f"卷名: {vol['volume_name']}")
    if vol.get("core_conflict"):
        parts.append(f"核心冲突: {str(vol['core_conflict'])[:200]}")
    if vol.get("protagonist_goal"):
        parts.append(f"主角目标: {str(vol['protagonist_goal'])[:200]}")
    return "\n".join(parts) if parts else "（无卷纲内容）"


def _fmt_project(proj, depth="full"):
    parts = []
    if proj.get("title"):
        parts.append(f"书名: {proj['title']}")
    if proj.get("genre"):
        parts.append(f"题材: {proj['genre']}")
    if proj.get("one_liner"):
        parts.append(f"一句话简介: {proj['one_liner']}")
    return "\n".join(parts) if parts else "（无项目信息）"


def _fmt_character_states(states, depth="full"):
    lines = []
    for st in states:
        if not isinstance(st, dict):
            continue
        name = st.get("character_name") or st.get("name") or ""
        line_parts = [name] if name else []
        for key, label in (("location", "位置"), ("state", "状态"),
                           ("emotion", "情绪"), ("health", "健康"),
                           ("items", "持有"), ("knowledge", "已知")):
            val = st.get(key)
            # 🔴 数据库字段为 state_summary（含状态描述），兼容旧字段名 state
            if not val and key == "state":
                val = st.get("state_summary")
            if val:
                line_parts.append(f"{label}:{str(val)[:80]}")
        if line_parts:
            lines.append("- " + " | ".join(line_parts))
    if not lines:
        return ""
    return "\n".join(lines)


def _fmt_previous_hook(hook, depth="full"):
    parts = []
    if hook.get("hook_content"):
        parts.append(f"- 结尾状态: {hook['hook_content']}")
    if hook.get("hook_type"):
        parts.append(f"- 状态类型: {hook['hook_type']}")
    if hook.get("ending_emotion"):
        parts.append(f"- 结尾情绪: {hook['ending_emotion']}")
    return "\n".join(parts)


def _fmt_character_full(characters, depth="full"):
    """角色详情（审查/剧情生成用），含持有物品。"""
    if not characters:
        return ""
    lines = []
    for c in characters:
        name = c.get("character_name", "")
        if not name:
            continue
        line = f"- {name}"
        if c.get("protagonist_relation"):
            line += f" | 与主角关系: {c['protagonist_relation'][:40]}"
        if c.get("identity"):
            line += f" | 身份: {c['identity'][:60]}"
        if c.get("personality"):
            line += f" | 性格: {c['personality'][:80]}"
        if c.get("flaw"):
            line += f" | 缺陷: {c['flaw'][:60]}"
        if c.get("abilities"):
            line += f" | 能力: {str(c['abilities'])[:100]}"
        if c.get("goals"):
            line += f" | 目标: {str(c['goals'])[:60]}"
        rels = c.get("relationships", []) or []
        if rels:
            rel_str = "；".join(
                f"与{r.get('target', '')}（{r.get('type', '')}）" for r in rels[:4]
            )
            line += f" | 关系: {rel_str}"
        items = c.get("items", []) or []
        item_names = [it.get("name", "") for it in items if isinstance(it, dict) and it.get("name")]
        if item_names:
            line += f" | 持有物品: {'、'.join(item_names[:6])}"
        lines.append(line)
    return "\n".join(lines) if lines else "（无角色信息）"


def _fmt_character_summary(characters, depth="summary"):
    """角色速写（草稿生成用），含物品清单 + 物品一致性约束。"""
    if not characters:
        return ""
    lines = []
    for char in characters:
        name = char.get("character_name", "")
        if not name:
            continue
        parts = [name]
        if char.get("identity"):
            parts.append(f"身份:{char['identity']}")
        if char.get("personality"):
            parts.append(f"性格:{char['personality']}")
        if char.get("flaw"):
            parts.append(f"缺陷:{char['flaw']}")
        if char.get("goals"):
            parts.append(f"目标:{char['goals']}")
        items = char.get("items", []) or []
        item_strs = []
        for it in items:
            if not isinstance(it, dict) or not it.get("name"):
                continue
            qty = it.get("quantity", 1) or 1
            item_strs.append(f"{it['name']}x{qty}" if qty > 1 else it["name"])
        parts.append(f"持有物品:{'、'.join(item_strs)}" if item_strs else "持有物品:无")
        lines.append(" | ".join(parts))
    lines.append(
        "物品一致性约束：角色使用、掏出、挥动任何物品前，必须已在其持有物品清单中；"
        "禁止凭空出现清单外的物品；若剧情需要新物品，必须先写获得它的过程。"
    )
    return "\n".join(lines)


def _fmt_character_items(items, depth="full"):
    """角色物品（结构化查询结果渲染）。"""
    if not items:
        return ""
    lines = []
    for it in items[:10]:
        name = it.get("character_name", "") or f"角色#{it.get('character_id', '')}"
        item = it.get("item_name", "")
        if not item:
            continue
        qty = it.get("quantity", 1) or 1
        item_str = f"{item}x{qty}" if qty > 1 else item
        line = f"- {name}持有 {item_str}"
        note = (it.get("change_note", "") or it.get("source", "") or "")[:30]
        if note:
            line += f"（{note}）"
        lines.append(line)
    return "\n".join(lines)


def _fmt_character_group(char_group, depth="full"):
    if not char_group or not isinstance(char_group, dict):
        return ""
    parts = []
    cg_goal = char_group.get("common_goal", "") or char_group.get("goal", "")
    if cg_goal:
        parts.append(f"- 共同目标: {cg_goal[:200]}")
    stage_goal = char_group.get("stage_goal", "")
    if stage_goal:
        parts.append(f"- 阶段目标: {stage_goal[:200]}")
    enriched_members = char_group.get("enriched_members", [])
    if enriched_members:
        for m in enriched_members[:6]:
            name = m.get("character_name") or m.get("role", f"成员{m.get('id', '')}")
            role = m.get("role", "")
            ability = (m.get("key_ability", "") or "")[:50]
            flaw = (m.get("key_flaw", "") or "")[:50]
            line_parts = [f"- {name}: {role}"] if role else [f"- {name}"]
            if ability:
                line_parts.append(f"能力: {ability}")
            if flaw:
                line_parts.append(f"缺陷: {flaw}")
            parts.append(" | ".join(line_parts))
    return "\n".join(parts) if parts else ""


def _fmt_worldview(world_settings, depth="full"):
    if not world_settings:
        return ""
    parts = []
    for s in world_settings:
        if isinstance(s, dict):
            summary = s.get("world_summary", "") or s.get("content", "")
            if summary:
                parts.append(f"- 世界简介: {str(summary)[:200]}")
            social = s.get("social_common_sense", "")
            if social:
                parts.append(f"- 社会常识: {str(social)[:200]}")
            factions = s.get("factions_list", [])
            if factions:
                names = "、".join(f.get("faction_name", "") for f in factions[:5])
                parts.append(f"- 主要势力: {names}")
    return "\n".join(parts) if parts else ""


def _fmt_power_system(ps, depth="full"):
    if not ps or not isinstance(ps, dict):
        return ""
    lines = []
    if ps.get("system_type"):
        lines.append(f"- 体系类型: {ps['system_type']}")
    if ps.get("core_creed"):
        lines.append(f"- 核心理念: {str(ps['core_creed'])[:200]}")
    if ps.get("cost_rules"):
        lines.append(f"- 代价规则: {str(ps['cost_rules'])[:200]}")
    if lines:
        lines.append("- 描写要求：涉及修炼/战斗/能力使用时，须体现过程与代价，不得超出设定边界")
    return "\n".join(lines) if lines else ""


def _fmt_golden_finger(gf, depth="full"):
    if not gf or not isinstance(gf, dict):
        return ""
    parts = []
    if gf.get("main_role"):
        parts.append(f"- 名称: {gf['main_role']}")
    if gf.get("type"):
        parts.append(f"- 类型: {gf['type']}")
    if gf.get("core_function"):
        parts.append(f"- 核心能力: {str(gf['core_function'])[:200]}")
    if gf.get("irreversible_cost"):
        parts.append(f"- 不可逆代价: {str(gf['irreversible_cost'])[:200]}")
    return "\n".join(parts)


def _fmt_foreshadows(loops, depth="full"):
    if not loops:
        return ""
    lines = []
    for loop in loops[:8]:
        lines.append(
            f"- [{loop.get('tier', '')}] {loop.get('content', '')} "
            f"(第{loop.get('planted_chapter') or loop.get('planted_ch') or 0}章埋下)"
        )
    return "\n".join(lines)


def _fmt_timeline(data, depth="full"):
    """章节时间轴：卷基准时间 + 最近章节的时间锚点/间隔/跨度/倒计时。"""
    if not data or not isinstance(data, dict):
        return ""
    tl = data.get("timeline") or {}
    chapters = data.get("chapters") or []
    parts = []
    meta = []
    if tl.get("time_base"):
        meta.append(f"基准时间: {tl['time_base']}")
    if tl.get("time_span"):
        meta.append(f"时间跨度: {tl['time_span']}")
    if meta:
        parts.append(" | ".join(meta))
    if not chapters:
        return "\n".join(parts) if parts else ""
    # 最近 6 章（含当前章），保持时间推进顺序
    recent = chapters[-6:]
    for ch in recent:
        cnum = ch.get("chapter_number", "?")
        bits = []
        if ch.get("time_anchor"):
            bits.append(f"时间锚点: {ch['time_anchor']}")
        if ch.get("chapter_duration"):
            bits.append(f"章内跨度: {ch['chapter_duration']}")
        if ch.get("interval_from_prev"):
            bits.append(f"距上章: {ch['interval_from_prev']}")
        if ch.get("countdown_status") and ch.get("countdown_status") != "无":
            bits.append(f"倒计时: {ch['countdown_status']}")
        line = f"- 第{cnum}章"
        if bits:
            line += " | " + " | ".join(bits)
        parts.append(line)
    parts.append("时间一致性要求：本章时间须与上章时间锚点衔接（间隔/跳跃须有原文依据），禁止时间倒挂")
    return "\n".join(parts)


def _fmt_previous_chapter(data, depth="full"):
    if not data or not data.get("content"):
        # 空态（首章无前文）不渲染，由装配层跳过空区块
        return ""
    ch_idx = data.get("chapter_index", "?")
    content = data.get("content", "")
    if data.get("is_summary"):
        return f"第{ch_idx}章摘要: {content}"
    if depth == "tail":
        tail = content[-500:] if len(content) > 500 else content
        return f"第{ch_idx}章结尾: {tail}"
    # full 深度硬截断：前文仅作承接/设定参考，超 1500 字取首尾
    if len(content) > 1500:
        content = content[:750] + "\n……（中间内容省略）……\n" + content[-750:]
    return f"第{ch_idx}章（请仔细承接）:\n{content}"


def _fmt_style_anchor(data, depth="style"):
    """文风锚点：前文代表性片段（润色用）。"""
    content = data.get("content", "")
    idx = data.get("chapter_index", "?")
    return f"--- 第{idx}章片段（风格参照，仅模仿其语言节奏，不得照抄情节） ---\n{content[:320]}"


def _fmt_plot_list(plot_list, depth="list"):
    if not plot_list:
        return "（暂无详细剧情，请根据章节规划自由发挥）"
    if depth == "json":
        return json.dumps(plot_list, ensure_ascii=False, indent=2)
    lines = []
    for i, plot in enumerate(plot_list, 1):
        if not isinstance(plot, dict):
            continue
        scene = plot.get("scene", "")
        description = plot.get("description", "")
        characters = plot.get("characters", [])
        emotion = plot.get("emotion", "")
        conflict = plot.get("conflict", "")
        line = f"{i}. 场景「{scene}」"
        if description:
            line += f"\n   {description}"
        if characters:
            char_str = "、".join(characters) if isinstance(characters, list) else str(characters)
            line += f"\n   角色: {char_str}"
        if emotion:
            line += f"\n   情绪: {emotion}"
        if conflict:
            line += f"\n   冲突: {conflict}"
        lines.append(line)
    return "\n\n".join(lines)


def _fmt_review_result(review_result, depth="full"):
    issues = []
    suggestions = []
    for review in review_result:
        for issue in review.get("issues", []):
            if isinstance(issue, dict) and 'severity' in issue and 'description' in issue:
                severity = issue.get('severity', '')
                description = issue.get('description', '')
                location = issue.get('location', '')
                if severity in ["critical", "high", "medium"]:
                    issues.append(f"- [{severity}] {location}: {description}")
        if review.get("suggestions"):
            suggestions.append(f"- [{review['name']}] {review['suggestions']}")
    parts = []
    if issues:
        parts.append("【审查问题】\n" + "\n".join(issues))
    if suggestions:
        parts.append("【修改建议】\n" + "\n".join(suggestions))
    return "\n".join(parts) if parts else "（无审查问题与建议）"


def _fmt_rag_results(rag_results, depth="full", limit=3):
    if not rag_results:
        return ""
    parts = []
    for r in rag_results[:limit]:
        if isinstance(r, str):
            parts.append(r[:150])
        elif isinstance(r, dict):
            content = r.get("content", "")[:150]
            chunk_type = r.get("chunk_type", "")
            ch_num = r.get("chapter_number", 0)
            if chunk_type and ch_num:
                parts.append(f"[第{ch_num}章/{chunk_type}] {content}")
            else:
                parts.append(content)
    return "\n".join(parts)


def _fmt_rag_results_qa(rag_results, depth="qa"):
    """RAG 结果（问答模式）：全文注入 + 来源标注，供回答 LLM 作为证据。"""
    if not rag_results:
        return ""
    parts = []
    for i, r in enumerate(rag_results[:10], 1):
        if isinstance(r, str):
            parts.append(f"[片段{i}] {r}")
            continue
        content = (r.get("content", "") or "").strip()
        if not content:
            continue
        chunk_type = r.get("chunk_type", "")
        ch_num = r.get("chapter_number", 0)
        src = f"类型={chunk_type} 章节={ch_num}" if ch_num else f"类型={chunk_type}"
        parts.append(f"[片段{i}][{src}]\n{content}")
    return "\n\n".join(parts)


def _fmt_consistency_notes(notes, depth="full"):
    if not notes:
        return ""
    return "\n".join(f"- {note}" for note in notes)


def _fmt_undisclosed(undisclosed, depth="full"):
    if not undisclosed:
        return ""
    lines = []
    for f in undisclosed:
        lines.append(
            f"- [{f.get('tier', '')}] {f.get('content', '')[:120]} "
            f"(第{f.get('planted_chapter', 0)}章埋下)"
        )
    return "\n".join(lines)


def _fmt_dimensions(step_name, depth="full"):
    dims = REVIEW_DIMENSIONS.get(step_name, [])
    if not dims:
        return ""
    lines = []
    for d in dims:
        lines.append(f"- {d['name']}({d['key']})：{d['description']}")
    return "\n".join(lines)


# ── 资源注册表 ────────────────────────────────────────────────

RESOURCE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "chapter_plan": {
        "label": "章节规划", "header": "【章节规划】", "category": "structured",
        "loader": _load_chapter_plan, "formatters": {"full": _fmt_chapter_plan},
        "default_depth": "full", "task_input": False,
    },
    "volume_outline": {
        "label": "当前卷纲", "header": "【当前卷纲】", "category": "structured",
        "loader": _load_volume_outline, "formatters": {"full": _fmt_volume_outline},
        "default_depth": "full", "task_input": False,
    },
    "project": {
        "label": "项目信息", "header": "【项目信息】", "category": "structured",
        "loader": _load_project, "formatters": {"full": _fmt_project},
        "default_depth": "full", "task_input": False,
    },
    "character_state": {
        "label": "上章末角色状态", "header": "【上章末角色状态】", "category": "structured",
        "loader": _load_character_states, "formatters": {"full": _fmt_character_states},
        "default_depth": "full", "task_input": False,
        "queryable": True, "query_loader": _query_character_states,
        "query_filters": ["chapter", "name", "character_id", "keyword"],
    },
    "previous_hook": {
        "label": "上一章结尾状态", "header": "【上一章结尾】", "category": "structured",
        "loader": _load_previous_hook, "formatters": {"full": _fmt_previous_hook},
        "default_depth": "full", "task_input": False,
    },
    "character_card": {
        "label": "角色卡", "header": "【角色设定】", "category": "structured",
        "loader": _load_character_cards,
        "formatters": {"full": _fmt_character_full, "summary": _fmt_character_summary},
        "default_depth": "full", "task_input": False,
        "queryable": True, "query_loader": _query_character_cards,
        "query_filters": ["type", "keyword", "ids"],
    },
    "character_item": {
        "label": "角色物品", "header": "【角色物品】", "category": "structured",
        "loader": None, "formatters": {"full": _fmt_character_items},
        "default_depth": "full", "task_input": False,
        "queryable": True, "query_loader": _query_items,
        "query_filters": ["character", "keyword", "only_held"],
    },
    "character_group": {
        "label": "主角团", "header": "【主角团】", "category": "structured",
        "loader": _load_character_group, "formatters": {"full": _fmt_character_group},
        "default_depth": "full", "task_input": False,
    },
    "worldview": {
        "label": "世界观", "header": "【世界观】", "category": "structured",
        "loader": _load_worldview, "formatters": {"full": _fmt_worldview},
        "default_depth": "full", "task_input": False,
    },
    "power_system": {
        "label": "力量体系", "header": "【力量体系】", "category": "structured",
        "loader": _load_power_system, "formatters": {"full": _fmt_power_system},
        "default_depth": "full", "task_input": False,
    },
    "golden_finger": {
        "label": "金手指", "header": "【金手指】", "category": "structured",
        "loader": _load_golden_finger, "formatters": {"full": _fmt_golden_finger},
        "default_depth": "full", "task_input": False,
    },
    "foreshadow": {
        "label": "活跃伏笔", "header": "【活跃伏笔】", "category": "structured",
        "loader": _load_foreshadows, "formatters": {"full": _fmt_foreshadows},
        "default_depth": "full", "task_input": False,
        "queryable": True, "query_loader": _query_foreshadows,
        "query_filters": ["status", "tier", "chapter", "keyword"],
    },
    "timeline": {
        "label": "章节时间轴", "header": "【章节时间轴】", "category": "structured",
        "loader": _load_timeline, "formatters": {"full": _fmt_timeline},
        "default_depth": "full", "task_input": False,
        "queryable": True, "query_loader": _query_timeline,
        "query_filters": ["volume", "chapter"],
    },
    "previous_chapter": {
        "label": "前文章节", "header": "【前文回顾】", "category": "structured",
        "loader": _load_previous_chapter,
        "formatters": {"full": _fmt_previous_chapter, "summary": _fmt_previous_chapter,
                       "tail": _fmt_previous_chapter, "style": _fmt_style_anchor},
        "default_depth": "full", "task_input": False,
    },
    "plot_list": {
        "label": "剧情列表", "header": "【剧情列表】", "category": "task_input",
        "loader": _load_plot_list, "formatters": {"list": _fmt_plot_list, "json": _fmt_plot_list},
        "default_depth": "list", "task_input": True,
    },
    "review_result": {
        "label": "审查反馈", "header": "【审查反馈】", "category": "task_input",
        "loader": _load_review_result, "formatters": {"full": _fmt_review_result},
        "default_depth": "full", "task_input": True,
    },
    "rag_results": {
        "label": "历史参考 RAG", "header": "【历史参考 RAG】", "category": "rag",
        "loader": None,
        "formatters": {"full": _fmt_rag_results, "qa": _fmt_rag_results_qa},
        "default_depth": "full", "task_input": False,
    },
    "consistency_notes": {
        "label": "一致性约束", "header": "【一致性约束】", "category": "constraint",
        "loader": None, "formatters": {"full": _fmt_consistency_notes},
        "default_depth": "full", "task_input": False,
    },
    "undisclosed_foreshadows": {
        "label": "不可提前揭示的伏笔", "header": "【不可提前揭示的伏笔】", "category": "constraint",
        "loader": None, "formatters": {"full": _fmt_undisclosed},
        "default_depth": "full", "task_input": False,
    },
    "dimensions": {
        "label": "审查维度", "header": "【审查维度】", "category": "constraint",
        "loader": None, "formatters": {"full": _fmt_dimensions},
        "default_depth": "full", "task_input": False,
    },
}

# ── 每节点装配配置：区块顺序 + 默认 depth + LLM 可选资源白名单 ──
# 每节点: {"sections": [(resource, depth), ...], "selectable": [resource, ...]}
# selectable 只含结构化资源（LLM 通过 structured_refs 选择）；
# 任务输入/约束/RAG 由装配器或 rag_queries 注入。

STEP_ASSEMBLY: Dict[str, Dict[str, Any]] = {
    # 每节点两清单，均按注入顺序排列：
    #   selectable   —— LLM 可选资源（分析阶段资源目录展示同一清单）。
    #                  元素为 "name" 或 ("name", 节点默认深度)。
    #                  LLM 显式 depth 优先 → 节点默认深度 → res.default_depth。
    #                  LLM 选中即注入，所见即所得，不再有"选中不注入"。
    #   auto_sections —— 非 LLM 选择区块（任务输入/约束/RAG），固定挂载，按序追加。
    "chapter_plot_generator": {
        "selectable": [
            "chapter_plan", "volume_outline", "project", "previous_chapter",
            "character_state", "previous_hook", "character_card",
            "character_group", "golden_finger", "power_system",
            "worldview", "foreshadow", "timeline",
        ],
        "queryable": [
            "character_card", "character_state", "foreshadow",
            "timeline", "character_item",
        ],
        "auto_sections": [
            ("undisclosed_foreshadows", None),
            ("rag_results", "full"),
            ("consistency_notes", None),
        ],
    },
    "chapter_plot_reviewer": {
        "selectable": [
            "chapter_plan", "volume_outline", "character_card",
            "golden_finger", "worldview", "foreshadow", "timeline",
        ],
        "queryable": [
            "character_card", "foreshadow", "timeline",
        ],
        "auto_sections": [
            ("undisclosed_foreshadows", None),
            ("dimensions", None),
        ],
    },
    "draft_generator": {
        "selectable": [
            ("character_card", "summary"), "previous_chapter", "character_state",
            "character_group", "worldview", "power_system", "golden_finger",
            "foreshadow", "timeline",
        ],
        "queryable": [
            "character_card", "character_state", "foreshadow",
            "timeline", "character_item",
        ],
        "auto_sections": [
            ("undisclosed_foreshadows", None),
            ("plot_list", "list"),
            ("rag_results", "full"),
            ("consistency_notes", None),
        ],
    },
    "draft_reviewer": {
        "selectable": [
            "chapter_plan", ("previous_chapter", "tail"), "character_state",
            "worldview", "character_card", "timeline",
        ],
        "queryable": [
            "character_card", "character_state", "timeline",
        ],
        "auto_sections": [
            ("dimensions", None),
            ("consistency_notes", None),
        ],
    },
    "draft_polisher": {
        "selectable": [
            "worldview", "power_system", ("previous_chapter", "style"),
        ],
        "queryable": [],
        "auto_sections": [
            ("review_result", "full"),
            ("consistency_notes", None),
        ],
    },
    # 知识问答（/query 状态查询）：与写作节点共用同一分析器引擎。
    # selectable = 全部结构化资源（比单节点宽），由 LLM 按用户问题选择；
    # auto_sections 只挂 RAG 检索（qa 深度：全文注入 + 来源标注）。
    # 不注入创作约束（undisclosed/consistency_notes/dimensions）。
    "qa_answer": {
        "selectable": [
            "character_state", "character_card", "character_group",
            "worldview", "power_system", "golden_finger", "foreshadow",
            "timeline", "previous_chapter", "previous_hook",
            "volume_outline", "project",
        ],
        "queryable": [
            "character_card", "character_state", "foreshadow",
            "timeline", "character_item",
        ],
        "auto_sections": [
            ("rag_results", "qa"),
        ],
    },
}

# 结构化资源目录（分析 prompt 展示候选清单用）：resource -> 候选提取函数(data) -> [{id, name, summary}]
