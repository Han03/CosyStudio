# -*- coding: utf-8 -*-
"""精确替换 _allowed_update_keys（Edit 工具遇特殊字符失败，改用脚本）。"""
p = r"C:\MyProjects\CosyStudio\backend\utils\llm_json_parser.py"
with open(p, encoding="utf-8") as f:
    content = f.read()

old = (
    '                _allowed_update_keys = (\n'
    '                    "raw_output", "parsed_output", "parse_success", "success_strategy",\n'
    '                    "strategies_tried", "error_message", "input_tokens", "output_tokens", "latency_ms",\n'
    '                )'
)
new = (
    '                # token/latency 由 execute_text_chat 统一测量并 INSERT，parse 阶段绝不回写：\n'
    '                # update_llm_call_log 无条件覆盖全部列（缺省参数=0），若把这三个键放进来，\n'
    '                # 会把 INSERT 时的真实 token/latency 覆盖成 0（历史 ctx_analysis 等全 0 的根因）。\n'
    '                _allowed_update_keys = (\n'
    '                    "raw_output", "parsed_output", "parse_success", "success_strategy",\n'
    '                    "strategies_tried", "error_message",\n'
    '                )'
)
assert old in content, "pattern not found"
content = content.replace(old, new, 1)
with open(p, "w", encoding="utf-8") as f:
    f.write(content)
print("OK")
