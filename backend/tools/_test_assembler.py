# -*- coding: utf-8 -*-
"""上下文分析器改造验证：静态完整性 + Gather 装配（mock Analyze）。

适配 selectable 单源控制（selectable + auto_sections，无 sections 过滤）。
用法：python _test_assembler.py
不调用 LLM / 不查业务库（只测不查库资源路径）。
"""
import asyncio
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from webnovel.pipeline.resource_registry import (
    RESOURCE_REGISTRY, STEP_ASSEMBLY, ContextAnalysisError,
)
from webnovel.pipeline.context_analyzer import ContextAnalyzer

FAILURES = []

# 查库 loader 的 mock 覆盖（测试不依赖真实业务库数据；字段匹配对应 formatter）
_DB_LOADER_OVERRIDES = {
    "worldview": lambda ref, env: [{
        "id": 3, "world_summary": "明末乱世，饥荒连年", "social_common_sense": "尊卑有序",
        "factions_list": [{"faction_name": "明军"}, {"faction_name": "流民"}]}],
    "power_system": lambda ref, env: {
        "system_type": "内功", "core_creed": "内力源于丹田", "cost_rules": "突破消耗气血"},
    "golden_finger": lambda ref, env: {
        "main_role": "系统", "type": "兑换", "core_function": "兑换物资", "irreversible_cost": "消耗寿命"},
    "character_group": lambda ref, env: {
        "name": "主角团", "goal": "回现代", "members_summary": "苏瑶",
        "enriched_members": []},
    "character_card": lambda ref, env: [
        {"role": "主角", "character_name": "李承言", "identity": "长工",
         "personality": "忠厚", "flaw": "固执", "goals": "活下去", "items": []}],
    "timeline": lambda ref, env: {
        "timeline": {"id": 1, "volume_number": 1, "time_base": "崇祯九年", "time_span": "3日"},
        "chapters": [{"chapter_number": 1, "time_anchor": "六月初一"}]},
}


def check(cond, msg):
    if not cond:
        FAILURES.append(msg)
        print(f"  [FAIL] {msg}")
    else:
        print(f"  [OK] {msg}")


def parse_selectable(assembly):
    """解析 selectable 元素（str 或 (name, depth)）→ [(name, depth_or_None)] + name 集合。"""
    items = []
    for item in assembly.get("selectable", []):
        if isinstance(item, (list, tuple)):
            items.append((item[0], item[1] if len(item) > 1 else None))
        else:
            items.append((item, None))
    return items, {name for name, _ in items}


def test_static_integrity():
    print("== 静态完整性 ==")
    for step_name, assembly in STEP_ASSEMBLY.items():
        sel_items, sel_names = parse_selectable(assembly)
        auto_items = assembly.get("auto_sections", [])
        # selectable：资源已注册 + 结构化 + 深度可用
        for name, depth in sel_items:
            check(name in RESOURCE_REGISTRY,
                  f"{step_name}.selectable 资源 {name} 已注册")
            if name in RESOURCE_REGISTRY:
                res = RESOURCE_REGISTRY[name]
                check(res["category"] == "structured",
                      f"{step_name}.selectable {name} 为结构化资源")
                if depth and depth not in res["formatters"]:
                    check(False, f"{step_name}.selectable {name} 节点默认深度 {depth} 无 formatter")
        # auto_sections：资源已注册 + 深度可用（task_input 可为 list/json）
        for name, depth in auto_items:
            check(name in RESOURCE_REGISTRY,
                  f"{step_name}.auto_sections 资源 {name} 已注册")
            if name in RESOURCE_REGISTRY:
                res = RESOURCE_REGISTRY[name]
                if depth and depth not in res["formatters"]:
                    check(False, f"{step_name}.auto_sections {name} 深度 {depth} 无 formatter")
        # selectable 与 auto_sections 不重叠（LLM 可选 ≠ 自动挂载）
        auto_names = {name for name, _ in auto_items}
        overlap = sel_names & auto_names
        check(not overlap,
              f"{step_name} selectable 与 auto_sections 无重叠" if not overlap
              else f"{step_name} 重叠资源: {sorted(overlap)}")
    # 每个资源至少一个 formatter，default_depth 可用
    for res_name, res in RESOURCE_REGISTRY.items():
        check(bool(res.get("formatters")), f"资源 {res_name} 有 formatter")
        check(res["default_depth"] in res["formatters"],
              f"资源 {res_name} default_depth={res['default_depth']} 可用")
    print()


def _make_env():
    structural = {
        "project": {"title": "测试书", "genre": "历史穿越", "one_liner": "现代人穿明末"},
        "current_chapter_plan": {
            "chapter_title": "初到明末", "summary": "主角穿越明末",
            "key_events": "遇到李承言；得知饥荒", "rhythm": "平缓-紧张",
            "cpns": "入城", "cen": "夜宿", "must_cover_nodes": ["入城"],
        },
        "current_volume": {
            "volume_name": "第一卷·乱世", "core_conflict": "生存与立场",
            "protagonist_goal": "活下去",
        },
        "last_character_states": [
            {"character_name": "苏瑶", "location": "客栈", "state": "受伤未愈"},
        ],
        "previous_hook": {"hook_content": "门外传来脚步声", "hook_type": "悬念", "ending_emotion": "紧张"},
        "undisclosed_foreshadows": [
            {"content": "玉佩来历", "planted_chapter": 1, "tier": "A"},
        ],
    }
    inventory = {
        "characters": [{"id": 1, "name": "李承言", "type": "配角", "summary": "身份:长工"}],
        "foreshadows": [{"id": 7, "content": "玉佩来历", "tier": "A", "planted_chapter": 1, "urgency": "高"}],
        "world_settings": [{"id": 3, "name": "明末", "summary": "饥荒连年"}],
        "power_system": {"name": "内功", "summary": "体系类型:内功"},
        "golden_finger": {"name": "系统", "summary": "类型:兑换"},
        "character_group": {"name": "主角团", "goal": "回现代", "members_summary": "苏瑶"},
        "previous_chapters": [{"index": 1, "summary": "第1章 穿越", "has_full": True}],
        "rag_candidates": [{"doc_id": "r1", "type": "chapter_summary", "chapter": 1, "preview": "穿越过程"}],
    }
    return structural, inventory


async def test_gather_step(step_name, refs, notes, task_inputs=None):
    print(f"== Gather 装配: {step_name} ==")
    structural, inventory = _make_env()
    analyzer = ContextAnalyzer(script_id=1, chapter_index=2)
    env = {
        "inventory": inventory, "structural_data": structural,
        "task_inputs": task_inputs or {}, "project_id": 1,
        "script_id": 1, "chapter_index": 2,
    }
    selection = {"structured_refs": refs, "rag_queries": [], "custom_notes": notes}
    overrides = {}
    for name, loader in _DB_LOADER_OVERRIDES.items():
        res = RESOURCE_REGISTRY[name]
        overrides[name] = {**res, "loader": loader}
    with mock.patch.dict(RESOURCE_REGISTRY, overrides):
        step_ctx = await analyzer._assemble_context(step_name, selection, env)
    assembled = step_ctx.get("assembled_context", "")
    check(bool(assembled), "assembled_context 非空")
    assembly = STEP_ASSEMBLY[step_name]
    # 选中资源区块全部出现在 assembled 中（LLM 选中即注入）
    for ref in refs:
        header = RESOURCE_REGISTRY[ref["resource"]]["header"].strip("【】")
        check(header in assembled, f"选中区块【{header}】已注入")
    # auto_sections 区块按配置注入（consistency_notes 仅在 notes 非空时渲染）
    auto_names = {name for name, _ in assembly.get("auto_sections", [])}
    if "consistency_notes" in auto_names and notes:
        check("一致性约束" in assembled, "【一致性约束】区块已组装")
    if "undisclosed_foreshadows" in auto_names:
        check("不可提前揭示的伏笔" in assembled, "【不可提前揭示的伏笔】区块已组装")
    if "dimensions" in auto_names:
        check("审查维度" in assembled, "【审查维度】区块已组装")
    # 组装顺序：selectable 命中项按 selectable 顺序（仅检查实际选中的资源；
    # 避免其他区块正文中出现的同名文本误命中 find）
    sel_items, _ = parse_selectable(assembly)
    sel_order = [name for name, _ in sel_items]
    selected_names = [ref["resource"] for ref in refs]
    sel_idx = [assembled.find(RESOURCE_REGISTRY[n]["header"].strip("【】"))
               for n in sel_order if n in selected_names]
    check(all(i >= 0 for i in sel_idx) and sel_idx == sorted(sel_idx),
          f"{step_name} 注入顺序按 selectable 顺序")
    print("--- assembled 预览 ---")
    print(assembled[:600].replace("\n", " ⏎ "))
    print()


async def main():
    test_static_integrity()

    # 剧情生成：选 章节规划/卷纲/项目/前文(摘要)/钩子/角色状态/时间轴 + notes
    # 重点：project/timeline 曾"可选但永不注入"，现在必须注入
    await test_gather_step(
        "chapter_plot_generator",
        [
            {"resource": "chapter_plan", "depth": "full"},
            {"resource": "volume_outline", "depth": "full"},
            {"resource": "project", "depth": "full"},
            {"resource": "previous_chapter", "chapter_index": 1, "depth": "summary"},
            {"resource": "previous_hook", "depth": "full"},
            {"resource": "character_state", "depth": "full"},
            {"resource": "timeline", "depth": "full"},
        ],
        ["[剧情因果] 第2章承接第1章穿越"],
    )

    # 剧情审查：维度区块 + 章节规划 + 时间轴
    await test_gather_step(
        "chapter_plot_reviewer",
        [
            {"resource": "chapter_plan", "depth": "full"},
            {"resource": "volume_outline", "depth": "full"},
            {"resource": "timeline", "depth": "full"},
        ],
        [],
    )

    # 草稿生成：任务输入 plot_list + 设定类资源（世界/力量/金手指/主角团）均须注入；
    # character_card 以 ("character_card", "summary") tuple 形式配置，选中须合法注入
    await test_gather_step(
        "draft_generator",
        [
            {"resource": "character_state", "depth": "full"},
            {"resource": "previous_chapter", "chapter_index": 1, "depth": "summary"},
            {"resource": "worldview", "depth": "full"},
            {"resource": "power_system", "depth": "full"},
            {"resource": "golden_finger", "depth": "full"},
            {"resource": "character_group", "depth": "full"},
            {"resource": "character_card", "depth": "summary"},
        ],
        ["[物品] 铜钱: 已交给李承言保管"],
        task_inputs={"plot_list": [{"scene": "客栈", "description": "对话", "characters": ["李承言"], "emotion": "平静", "conflict": ""}]},
    )

    # 草稿审查：维度区块 + 章节规划
    await test_gather_step(
        "draft_reviewer",
        [
            {"resource": "chapter_plan", "depth": "full"},
            {"resource": "character_state", "depth": "full"},
        ],
        [],
    )

    # 润色：任务输入 review_result + 世界观/力量体系
    await test_gather_step(
        "draft_polisher",
        [{"resource": "worldview", "depth": "full"},
         {"resource": "power_system", "depth": "full"}],
        [],
        task_inputs={"review_result": [{"name": "爽点呈现", "issues": [{"severity": "high", "location": "第2段", "description": "冲突弱"}], "suggestions": "加强反差"}]},
    )

    # 目录=注入：空资源不列目录（首章空态资源从目录移除）
    print("== 资源目录空态过滤 ==")
    structural, inventory = _make_env()
    structural = dict(structural, last_character_states=[], previous_hook={})
    inventory = dict(inventory, foreshadows=[], previous_chapters=[])
    analyzer = ContextAnalyzer(script_id=1, chapter_index=1)
    env = {"inventory": inventory, "structural_data": structural,
           "task_inputs": {}, "project_id": 1, "script_id": 1, "chapter_index": 1}
    catalog = analyzer._build_resource_catalog("chapter_plot_generator", env)
    for res_name in ("character_state", "previous_hook", "foreshadow", "previous_chapter"):
        header = RESOURCE_REGISTRY[res_name]["header"].strip("【】")
        check(header not in catalog, f"空资源【{header}】不出现在目录")
    check("章节规划" in catalog, "有内容资源【章节规划】仍在目录")

    # 失败即报错：非法资源
    print("== 失败路径 ==")
    structural, inventory = _make_env()
    analyzer = ContextAnalyzer(script_id=1, chapter_index=2)
    env = {"inventory": inventory, "structural_data": structural,
           "task_inputs": {}, "project_id": 1, "script_id": 1, "chapter_index": 2}
    try:
        await analyzer._assemble_context(
            "draft_generator",
            {"structured_refs": [{"resource": "nonsense", "depth": "full"}], "rag_queries": [], "custom_notes": []},
            env)
        check(False, "非法资源应抛 ContextAnalysisError")
    except ContextAnalysisError as e:
        check(True, f"非法资源抛错: {e}")

    # 失败即报错：非首章 character_state 为空
    env2 = dict(env, structural_data={**structural, "last_character_states": []})
    try:
        await analyzer._assemble_context(
            "draft_generator",
            {"structured_refs": [{"resource": "character_state", "depth": "full"}], "rag_queries": [], "custom_notes": []},
            env2)
        check(False, "非首章空角色状态应抛错")
    except ContextAnalysisError as e:
        check(True, f"非首章空角色状态抛错: {e}")

    print()
    if FAILURES:
        print(f"共 {len(FAILURES)} 个失败:")
        for f in FAILURES:
            print(" -", f)
        sys.exit(1)
    print("全部验证通过")


if __name__ == "__main__":
    asyncio.run(main())
