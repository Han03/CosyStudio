# -*- coding: utf-8 -*-
"""上下文分析器改造验证：静态完整性 + Gather 装配（mock Analyze）。

用法：python _test_assembler.py
不调用 LLM / 不查业务库（只测不查库资源路径）。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from webnovel.pipeline.resource_registry import (
    RESOURCE_REGISTRY, STEP_ASSEMBLY, ContextAnalysisError,
)
from webnovel.pipeline.context_analyzer import ContextAnalyzer

FAILURES = []


def check(cond, msg):
    if not cond:
        FAILURES.append(msg)
        print(f"  [FAIL] {msg}")
    else:
        print(f"  [OK] {msg}")


def test_static_integrity():
    print("== 静态完整性 ==")
    for step_name, assembly in STEP_ASSEMBLY.items():
        for res_name, depth in assembly["sections"]:
            check(res_name in RESOURCE_REGISTRY,
                  f"{step_name}.sections 资源 {res_name} 已注册")
            if res_name in RESOURCE_REGISTRY:
                res = RESOURCE_REGISTRY[res_name]
                if depth and depth not in res["formatters"]:
                    check(False, f"{step_name}.sections {res_name} 缺少 formatter 深度 {depth}")
        for res_name in assembly["selectable"]:
            check(res_name in RESOURCE_REGISTRY,
                  f"{step_name}.selectable 资源 {res_name} 已注册")
            if res_name in RESOURCE_REGISTRY:
                check(RESOURCE_REGISTRY[res_name]["category"] == "structured",
                      f"{step_name}.selectable {res_name} 为结构化资源")
    # 每个资源至少一个 formatter
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
    step_ctx = await analyzer._assemble_context(step_name, selection, env)
    assembled = step_ctx.get("assembled_context", "")
    check(bool(assembled), "assembled_context 非空")
    assembly = STEP_ASSEMBLY[step_name]
    # 任务输入/约束区块应存在
    for res_name, _ in assembly["sections"]:
        if res_name in ("undisclosed_foreshadows", "dimensions", "consistency_notes") or res_name == "plot_list" or res_name == "review_result":
            pass
    # 检查选中资源区块出现在 assembled 中
    for ref in refs:
        header = RESOURCE_REGISTRY[ref["resource"]]["header"].strip("【】")
        check(header in assembled, f"区块【{header}】已组装")
    assembly = STEP_ASSEMBLY[step_name]
    if any(s[0] == "consistency_notes" for s in assembly["sections"]):
        check("一致性约束" in assembled, "【一致性约束】区块已组装")
    if any(s[0] == "undisclosed_foreshadows" for s in assembly["sections"]):
        check("不可提前揭示的伏笔" in assembled, "【不可提前揭示的伏笔】区块已组装")
    if any(s[0] == "dimensions" for s in assembly["sections"]):
        check("审查维度" in assembled, "【审查维度】区块已组装")
    print("--- assembled 预览 ---")
    print(assembled[:600].replace("\n", " ⏎ "))
    print()


async def main():
    test_static_integrity()

    # 剧情生成：选 章节规划/卷纲/前文(摘要)/钩子/角色状态 + notes
    await test_gather_step(
        "chapter_plot_generator",
        [
            {"resource": "chapter_plan", "depth": "full"},
            {"resource": "volume_outline", "depth": "full"},
            {"resource": "previous_chapter", "chapter_index": 1, "depth": "summary"},
            {"resource": "previous_hook", "depth": "full"},
            {"resource": "character_state", "depth": "full"},
        ],
        ["[剧情因果] 第2章承接第1章穿越"],
    )

    # 剧情审查：维度区块 + 章节规划
    await test_gather_step(
        "chapter_plot_reviewer",
        [
            {"resource": "chapter_plan", "depth": "full"},
            {"resource": "volume_outline", "depth": "full"},
        ],
        [],
    )

    # 草稿生成：任务输入 plot_list（前文用 summary，避免依赖真实章节数据）
    await test_gather_step(
        "draft_generator",
        [
            {"resource": "character_state", "depth": "full"},
            {"resource": "previous_chapter", "chapter_index": 1, "depth": "summary"},
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
        [],
        [],
        task_inputs={"review_result": [{"name": "爽点呈现", "issues": [{"severity": "high", "location": "第2段", "description": "冲突弱"}], "suggestions": "加强反差"}]},
    )

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

    # 失败即报错：character_state 为空（structural 无状态）
    env2 = dict(env, structural_data={**structural, "last_character_states": []})
    try:
        await analyzer._assemble_context(
            "draft_generator",
            {"structured_refs": [{"resource": "character_state", "depth": "full"}], "rag_queries": [], "custom_notes": []},
            env2)
        check(False, "空角色状态应抛错")
    except ContextAnalysisError as e:
        check(True, f"空角色状态抛错: {e}")

    print()
    if FAILURES:
        print(f"共 {len(FAILURES)} 个失败:")
        for f in FAILURES:
            print(" -", f)
        sys.exit(1)
    print("全部验证通过")


if __name__ == "__main__":
    asyncio.run(main())
