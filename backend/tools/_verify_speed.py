# -*- coding: utf-8 -*-
"""验证：编译 + word_config 推导 + prompt 占位符 + 残留检查。"""
import os
import py_compile
import re

BACKEND = r"C:\MyProjects\CosyStudio\backend"

# 1. 编译
files = [
    "webnovel/pipeline/orchestrator.py",
    "webnovel/pipeline/context_analyzer.py",
    "webnovel/pipeline/executors/chapter_plot_generator_executor.py",
    "webnovel/pipeline/executors/chapter_plot_reviewer_executor.py",
    "webnovel/pipeline/executors/draft_generator_executor.py",
    "webnovel/pipeline/executors/draft_polisher_executor.py",
    "webnovel/pipeline/executors/draft_reviewer_executor.py",
]
for f in files:
    py_compile.compile(os.path.join(BACKEND, f), doraise=True)
print("[OK] 编译通过:", len(files), "个文件")

# 2. word_config 推导（复用 orchestrator 逻辑）
def calc(raw):
    raw = max(raw, 1)
    polish_min, polish_max = round(raw * 0.8), round(raw * 1.2)
    draft_min, draft_max = round(polish_min * 0.5), round(polish_max * 0.5)
    plot_count = max(4, min(10, round(raw / 250)))
    plot_desc_max = 60
    draft_point_max = max(60, draft_max // max(plot_count, 1))
    return {
        "polish": (polish_min, polish_max),
        "draft": (draft_min, draft_max),
        "plot_count": plot_count,
        "draft_point_max": draft_point_max,
        "polish_max_tokens": max(1500, polish_max * 2),
        "draft_max_tokens": max(800, draft_max * 2),
        "plot_max_tokens": max(1200, plot_count * 400),
        "review_max_tokens": 800,
    }

for w in (1000, 2000, 4000):
    c = calc(w)
    print(f"\nchapter_words={w}: polish={c['polish']} draft={c['draft']} "
          f"plot={c['plot_count']}点/每点草稿{c['draft_point_max']}字 "
          f"tok: polish={c['polish_max_tokens']} draft={c['draft_max_tokens']} plot={c['plot_max_tokens']}")

# 3. prompt 占位符完整性（format 参数匹配）
import sys
sys.path.insert(0, BACKEND)
from webnovel.pipeline.orchestrator import PipelineOrchestrator

prompts = {
    "chapter_plot_generate": ["chapter_index", "continue_prev", "assembled_context", "plot_count", "plot_desc_max"],
    "draft_generate": ["continue_prev", "user_prompt_section", "assembled_context", "draft_word_min", "draft_word_max", "draft_point_max"],
    "draft_polish": ["assembled_context", "draft_content", "polish_word_min", "polish_word_max"],
    "revise_draft": ["issues_text", "suggestions_text", "draft", "assembled_context", "draft_word_min", "draft_word_max"],
}
orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)  # 不初始化，仅用 _load_prompt 需要的属性
import inspect
# _load_prompt 是实例方法，直接调用需要 self 属性；手动加载模板
for name, params in prompts.items():
    path = os.path.join(BACKEND, "webnovel", "prompts", f"{name}_prompt.md")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    user_prompt = content.split("user_prompt: |", 1)[1].split("---", 1)[0] if "user_prompt: |" in content else ""
    placeholders = set(re.findall(r"\{(\w+)\}", user_prompt))
    missing = [p for p in params if p not in placeholders]
    extra = [p for p in placeholders if p not in params]
    # 排除 {{ }} 转义（双花括号不算占位符，已由正则过滤）
    print(f"[{'OK' if not missing else 'MISSING'}] {name}: 占位符={sorted(placeholders)}"
          + (f" 缺={missing}" if missing else "") + (f" 多={extra}" if extra else ""))

# 4. 残留检查
print("\n== 残留检查 ==")
for root, _, fs in os.walk(os.path.join(BACKEND, "webnovel")):
    for fn in fs:
        if fn.endswith((".py", ".md")):
            p = os.path.join(root, fn)
            with open(p, encoding="utf-8", errors="ignore") as f:
                t = f.read()
            if "反斜杠n反斜杠n" in t or "max(3500" in t or "max(8000" in t or "请严格按照JSON格式输出" in t:
                print(f"  [残留] {os.path.relpath(p, BACKEND)}")
print("[OK] 残留检查完成")
