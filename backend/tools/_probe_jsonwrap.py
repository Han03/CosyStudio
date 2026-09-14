# -*- coding: utf-8 -*-
"""查 JSON 包装来源：prompt 输出格式要求 + executor 解析逻辑。"""
import re

def grep(path, patterns):
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            for p in patterns:
                if p in line:
                    print(f"  {path.split(chr(92))[-1]}:{i}: {line.rstrip()[:100]}")
                    break

print("== prompt 输出格式要求 ==")
grep(r"C:\MyProjects\CosyStudio\backend\webnovel\prompts\draft_generate_prompt.md", ["JSON", "json", "content", "输出"])
grep(r"C:\MyProjects\CosyStudio\backend\webnovel\prompts\draft_polish_prompt.md", ["JSON", "json", "content", "输出"])
grep(r"C:\MyProjects\CosyStudio\backend\webnovel\prompts\chapter_plot_revise_prompt.md", ["JSON", "json", "content", "输出"])
grep(r"C:\MyProjects\CosyStudio\backend\webnovel\prompts\revise_draft_prompt.md", ["JSON", "json", "content", "输出"])

print("\n== executor 解析逻辑 ==")
for path in [r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\draft_generator_executor.py",
             r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\draft_polisher_executor.py",
             r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\chapter_plot_reviewer_executor.py",
             r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\draft_reviewer_executor.py"]:
    grep(path, ["parse_llm_json", "json.loads", '"content"', ".get('content'", "content\""])
