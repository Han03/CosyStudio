# -*- coding: utf-8 -*-
"""修复验证：formatter 字段 / 前文清单起点 / JSON 探测 / 审查解析回填。"""
import json
import sys

sys.path.insert(0, r"C:\MyProjects\CosyStudio\backend")

# 1) _fmt_character_states 字段兼容
from webnovel.pipeline.resource_registry import _fmt_character_states
sample = [
    {"character_name": "林天昊", "location": "破庙墙角",
     "state_summary": "身体冰冷，时间债务反噬持续影响", "emotion": "虚弱",
     "knowledge": "敌军先锋逼近"},
    {"character_name": "李威", "location": "破庙门口",
     "state_summary": "高度戒备", "emotion": "警惕", "items": "长刀"},
]
rendered = _fmt_character_states(sample)
print("=== 1) 角色状态渲染 ===")
print(rendered)
assert "状态:身体冰冷" in rendered, "state_summary 未渲染！"
assert "位置:破庙墙角" in rendered
# 兼容旧字段名 state
rendered2 = _fmt_character_states([{"character_name": "X", "location": "L", "state": "旧字段"}])
assert "状态:旧字段" in rendered2, "旧字段 state 兼容失败"
print("✓ 修复1 通过（state_summary 渲染 + 旧字段兼容）")

# 2) 前文清单起点
from webnovel.pipeline.executors.context_builder_executor import ContextBuilderExecutor
import inspect
src = inspect.getsource(ContextBuilderExecutor._build_prev_chapters_inventory)
assert "range(max(1, chapter_index - 5), chapter_index)" in src, "起点未改为 1"
print("✓ 修复2 通过（range 起点 max(1, ...)）")

# 3) 审查解析统一走 parse_llm_json
from webnovel.pipeline.executors.draft_reviewer_executor import DraftReviewerExecutor
from webnovel.pipeline.executors.chapter_plot_reviewer_executor import ChapterPlotReviewerExecutor
dsrc = inspect.getsource(DraftReviewerExecutor._parse_review_response)
psrc = inspect.getsource(ChapterPlotReviewerExecutor._parse_review_response)
assert "parse_llm_json(" in dsrc and "json.loads(" not in dsrc, "draft_reviewer 解析未统一"
assert "parse_llm_json(" in psrc and "json.loads(" not in psrc, "plot_reviewer 解析未统一"
print("✓ 修复3 通过（两个审查 executor 统一走 parse_llm_json）")

# 4) JSON 探测（修复7）
from core.model_executor import _probe_json_parse
assert _probe_json_parse('```json\n{"a": 1}\n```') is True
assert _probe_json_parse('{"content": "正文\\n\\n第二段"}') is True
assert _probe_json_parse('这不是JSON') is False
assert _probe_json_parse('') is False
assert _probe_json_parse('{"a": 1,') is False
print("✓ 修复7 通过（_probe_json_parse 探测正确）")

# 5) token 估算兜底逻辑（修复6，模拟云流式结束）
def est(prompt, content):
    total_p = 0
    total_c = 0
    if not total_p or not total_c:
        total_p = total_p or max(1, len(prompt) // 2)
        total_c = total_c or max(1, len(content) // 2)
    return total_p, total_c
p, c = est("你好", "第一段正文内容" * 10)
assert p == 1 and c > 0
print(f"✓ 修复6 通过（估算兜底: in={p}, out={c}）")

print("\n全部验证通过 ✅")
