# -*- coding: utf-8 -*-
"""验证空区块优化：无内容区块整体省略，有内容区块保留，plot_list 占位保留"""
import asyncio, sys
sys.path.insert(0, r"C:\MyProjects\CosyStudio\backend")

from webnovel.pipeline.context_analyzer import ContextAnalyzer
from webnovel.pipeline.resource_registry import (
    _fmt_character_states, _fmt_rag_results, _fmt_consistency_notes,
    _fmt_undisclosed, _fmt_plot_list, _fmt_previous_hook)

# 1. formatter 空值返回空串
for fn, empty_arg in ((_fmt_character_states, []), (_fmt_rag_results, []),
                      (_fmt_consistency_notes, []), (_fmt_undisclosed, []),
                      (_fmt_previous_hook, {})):
    out = fn(empty_arg)
    assert out == "", f"{fn.__name__} 空值未返回空串: {out!r}"
print("[OK] 无内容 formatter 均返回空串")

# 2. plot_list 占位保留（有指令语义）
out = _fmt_plot_list([])
assert "自由发挥" in out, "plot_list 占位丢失"
print("[OK] plot_list 空值占位保留:", out)

# 3. 组装层：模拟数据缺失场景
async def main():
    from webnovel.repositories.character_state_repository import get_character_states_before_chapter
    states = get_character_states_before_chapter(93, 4)
    ca = ContextAnalyzer(999913, 4)
    env = {
        "project_id": 93,
        "script_id": 999913,
        "task_inputs": {"plot_list": [
            {"scene": "破庙门口", "description": "李威示警", "characters": ["李威"], "emotion": "", "conflict": ""}]},
        "inventory": {"characters": [{"character_name": "林天昊", "identity": "主角", "items": []}],
                      "foreshadows": [], "world_settings": [],
                      "power_system": None, "golden_finger": None, "character_group": None,
                      "previous_chapters": [], "rag_candidates": []},
        "structural_data": {"last_character_states": states,
                            "current_chapter_plan": {"summary": "第4章 夜半铃响"},
                            "current_volume": None, "project": None,
                            "undisclosed_foreshadows": [], "previous_hook": {}},
    }
    sel = {"structured_refs": [
        {"resource": "character_state", "depth": "full"},
        {"resource": "chapter_plan", "depth": "full"},
    ], "rag_queries": [], "custom_notes": []}

    step_ctx = await ca._assemble_context("draft_generator", sel, env)
    ac = step_ctx["assembled_context"]
    # 应有：角色状态（有数据）、剧情列表（任务输入有数据）
    assert "上章末角色状态" in ac, "有数据的角色状态区块丢失"
    assert "剧情列表" in ac, "有数据的剧情列表区块丢失"
    # 不应有：空标题区块（一致性约束/不可提前揭示的伏笔/历史参考RAG/章节规划/卷纲/项目）
    for empty_hdr in ["【一致性约束】", "【不可提前揭示的伏笔】", "【历史参考 RAG】",
                      "【章节规划】", "【当前卷纲】", "【项目信息】", "【上一章结尾】"]:
        assert empty_hdr not in ac, f"空区块标题仍存在: {empty_hdr}"
    print("\n[OK] 组装上下文为空区块均被省略，有数据区块保留")
    print("---- assembled_context 区块顺序 ----")
    import re
    for h in re.findall(r"【[^】]+】", ac):
        print("  ", h)

asyncio.run(main())
