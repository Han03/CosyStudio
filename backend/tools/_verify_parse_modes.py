# -*- coding: utf-8 -*-
"""验证 parse_llm_json 纯文本/JSON 双模式。"""
from utils.llm_json_parser import parse_llm_json

# 纯文本模式
r = parse_llm_json(
    "第一段正文。\n\n第二段正文。",
    executor_name="test", prompt_name="draft_chapter_test",
    enable_logging=False, expect_json=False,
)
print("expect_json=False ->", r)
assert r == {"content": "第一段正文。\n\n第二段正文。"}, "纯文本模式返回错误"

# JSON 模式不受影响
r2 = parse_llm_json(
    '{"plots": [1, 2]}',
    executor_name="test", prompt_name="plot_test",
    enable_logging=False, expect_json=True,
)
print("expect_json=True ->", r2)
assert r2 == {"plots": [1, 2]}, "JSON 模式回归"

# JSON 模式对纯文本仍走策略（保持原行为）
r3 = parse_llm_json(
    "纯文本没有JSON",
    executor_name="test", prompt_name="x",
    enable_logging=False, expect_json=True,
)
print("expect_json=True + 纯文本 ->", r3)
assert r3 is None, "JSON 模式对纯文本应返回 None"

print("[OK] 纯文本/JSON 双模式验证通过")
