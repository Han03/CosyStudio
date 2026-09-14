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
    get_character_items_by_project,
    get_worldview_by_project, get_worldview_factions,
    get_power_system_by_project,
    get_golden_finger_by_project,
    get_character_group_by_project, get_character_group_members,
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
        raise ContextAnalysisError("上章末角色状态资源加载失败：last_character_states 为空")
    return states


def _load_previous_hook(ref, env):
    hook = env["structural_data"].get("previous_hook") or {}
    if not hook.get("hook_content"):
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
        raw_type = card.get("character_type", "")
        characters.append({
            "role": _CHAR_TYPE_LABELS.get(raw_type, raw_type),
            "character_name": card.get("name", ""),
            "alias": card.get("alias", ""),
            "identity": card.get("identity", ""),
            "protagonist_relation": card.get("protagonist_relation", ""),
            "personality": card.get("core_personality", ""),
            "flaw": card.get("personality_flaw", ""),
            "goals": card.get("true_desire", "") or card.get("long_term_goal", ""),
            "abilities": card.get("ability_limit", ""),
            "items": [
                {"name": it.get("item_name", ""),
                 "quantity": it.get("quantity", 1) or 1,
                 "desc": it.get("source", "") or it.get("change_note", "")}
                for it in items_by_char.get(cid, [])
                if it.get("item_name")
            ],
        })
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
    from webnovel.repositories import get_character_cards_by_project
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
        raise ContextAnalysisError("伏笔资源加载失败：未选择伏笔 id")
    loops = [f for f in env["inventory"].get("foreshadows", []) if str(f.get("id")) in ids]
    if not loops:
        raise ContextAnalysisError(f"伏笔资源加载失败：ids={sorted(ids)} 在活跃伏笔中不存在")
    return loops


def _load_previous_chapter(ref, env):
    chapter_index = ref.get("chapter_index")
    if chapter_index is None:
        raise ContextAnalysisError("前文资源加载失败：未指定 chapter_index")
    depth = ref.get("depth", "full")
    if depth == "summary":
        for ch in env["inventory"].get("previous_chapters", []):
            if ch.get("index") == chapter_index:
                summary = ch.get("summary", "")
                if not summary:
                    raise ContextAnalysisError(f"第{chapter_index}章摘要为空")
                return {"chapter_index": chapter_index, "content": summary, "is_summary": True}
        raise ContextAnalysisError(f"第{chapter_index}章不在前文清单中")
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
        return "（无角色状态记录）"
    return "\n".join(lines)


def _fmt_previous_hook(hook, depth="full"):
    return (
        f"- 结尾状态: {hook.get('hook_content', '')}\n"
        f"- 状态类型: {hook.get('hook_type', '')}\n"
        f"- 结尾情绪: {hook.get('ending_emotion', '')}"
    )


def _fmt_character_full(characters, depth="full"):
    """角色详情（审查/剧情生成用），含持有物品。"""
    if not characters:
        return "（无角色信息）"
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
        items = c.get("items", []) or []
        item_names = [it.get("name", "") for it in items if isinstance(it, dict) and it.get("name")]
        if item_names:
            line += f" | 持有物品: {'、'.join(item_names[:6])}"
        lines.append(line)
    return "\n".join(lines) if lines else "（无角色信息）"


def _fmt_character_summary(characters, depth="summary"):
    """角色速写（草稿生成用），含物品清单 + 物品一致性约束。"""
    if not characters:
        return "（无角色）"
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


def _fmt_character_group(char_group, depth="full"):
    if not char_group or not isinstance(char_group, dict):
        return "（无主角团）"
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
    return "\n".join(parts) if parts else "（无主角团成员）"


def _fmt_worldview(world_settings, depth="full"):
    if not world_settings:
        return "（无世界观设定）"
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
    return "\n".join(parts) if parts else "（无世界观设定）"


def _fmt_power_system(ps, depth="full"):
    if not ps or not isinstance(ps, dict):
        return "（未设定力量体系）"
    lines = []
    if ps.get("system_type"):
        lines.append(f"- 体系类型: {ps['system_type']}")
    if ps.get("core_creed"):
        lines.append(f"- 核心理念: {str(ps['core_creed'])[:200]}")
    if ps.get("cost_rules"):
        lines.append(f"- 代价规则: {str(ps['cost_rules'])[:200]}")
    if lines:
        lines.append("- 描写要求：涉及修炼/战斗/能力使用时，须体现过程与代价，不得超出设定边界")
    return "\n".join(lines) if lines else "（未设定力量体系）"


def _fmt_golden_finger(gf, depth="full"):
    if not gf or not isinstance(gf, dict):
        return "（未设定金手指）"
    return (
        f"- 名称: {gf.get('main_role', '')}\n"
        f"- 类型: {gf.get('type', '')}\n"
        f"- 核心能力: {str(gf.get('core_function', ''))[:200]}\n"
        f"- 不可逆代价: {str(gf.get('irreversible_cost', ''))[:200]}"
    )


def _fmt_foreshadows(loops, depth="full"):
    if not loops:
        return "（无活跃伏笔）"
    lines = []
    for loop in loops[:8]:
        lines.append(
            f"- [{loop.get('tier', '')}] {loop.get('content', '')} "
            f"(第{loop.get('planted_chapter') or loop.get('planted_ch') or 0}章埋下)"
        )
    return "\n".join(lines)


def _fmt_previous_chapter(data, depth="full"):
    ch_idx = data.get("chapter_index", "?")
    content = data.get("content", "")
    if data.get("is_summary"):
        return f"第{ch_idx}章摘要: {content}"
    if depth == "tail":
        tail = content[-500:] if len(content) > 500 else content
        return f"第{ch_idx}章结尾: {tail}"
    if len(content) > 4000:
        content = content[:2000] + "\n……（中间内容省略）……\n" + content[-2000:]
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
        line = f"{i}. 【{scene}】"
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


def _fmt_rag_results(rag_results, depth="full", limit=5):
    if not rag_results:
        return "（无检索结果）"
    parts = []
    for r in rag_results[:limit]:
        if isinstance(r, str):
            parts.append(r[:200])
        elif isinstance(r, dict):
            content = r.get("content", "")[:200]
            chunk_type = r.get("chunk_type", "")
            ch_num = r.get("chapter_number", 0)
            if chunk_type and ch_num:
                parts.append(f"[第{ch_num}章/{chunk_type}] {content}")
            else:
                parts.append(content)
    return "\n".join(parts)


def _fmt_consistency_notes(notes, depth="full"):
    if not notes:
        return "（无）"
    return "\n".join(f"- {note}" for note in notes)


def _fmt_undisclosed(undisclosed, depth="full"):
    if not undisclosed:
        return "（无）"
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
        return "（无审查维度）"
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
        "loader": None, "formatters": {"full": _fmt_rag_results},
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
    "chapter_plot_generator": {
        "sections": [
            ("chapter_plan", "full"),
            ("volume_outline", "full"),
            ("previous_chapter", "full"),
            ("previous_hook", "full"),
            ("character_state", "full"),
            ("undisclosed_foreshadows", None),
            ("character_card", "full"),
            ("character_group", "full"),
            ("golden_finger", "full"),
            ("power_system", "full"),
            ("worldview", "full"),
            ("foreshadow", "full"),
            ("rag_results", "full"),
            ("consistency_notes", None),
        ],
        "selectable": [
            "chapter_plan", "volume_outline", "project", "character_state",
            "previous_hook", "character_card", "character_group",
            "golden_finger", "power_system", "worldview", "foreshadow",
            "previous_chapter",
        ],
    },
    "chapter_plot_reviewer": {
        "sections": [
            ("chapter_plan", "full"),
            ("volume_outline", "full"),
            ("character_card", "full"),
            ("golden_finger", "full"),
            ("worldview", "full"),
            ("foreshadow", "full"),
            ("undisclosed_foreshadows", None),
            ("dimensions", None),
        ],
        "selectable": [
            "chapter_plan", "volume_outline", "character_card",
            "golden_finger", "worldview", "foreshadow",
        ],
    },
    "draft_generator": {
        "sections": [
            ("character_card", "summary"),
            ("previous_chapter", "full"),
            ("character_state", "full"),
            ("undisclosed_foreshadows", None),
            ("plot_list", "list"),
            ("rag_results", "full"),
            ("consistency_notes", None),
        ],
        "selectable": [
            "character_card", "previous_chapter", "character_state",
            "character_group", "worldview", "power_system", "golden_finger",
            "foreshadow",
        ],
    },
    "draft_reviewer": {
        "sections": [
            ("chapter_plan", "full"),
            ("previous_chapter", "tail"),
            ("character_state", "full"),
            ("worldview", "full"),
            ("character_card", "full"),
            ("dimensions", None),
            ("consistency_notes", None),
        ],
        "selectable": [
            "chapter_plan", "character_state", "worldview",
            "character_card", "previous_chapter",
        ],
    },
    "draft_polisher": {
        "sections": [
            ("review_result", "full"),
            ("previous_chapter", "style"),
            ("worldview", "full"),
            ("power_system", "full"),
            ("consistency_notes", None),
        ],
        "selectable": [
            "worldview", "power_system", "previous_chapter",
        ],
    },
}

# 结构化资源目录（分析 prompt 展示候选清单用）：resource -> 候选提取函数(data) -> [{id, name, summary}]
