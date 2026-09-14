# -*- coding: utf-8 -*-
"""T1 前文回顾瘦身：
1) _fmt_previous_chapter full 深度硬截断 1500 字（首尾各 750）
2) _build_output_schema previous_chapter 示例 depth 改 tail + 提示建议
"""
import re

# ---- 1. resource_registry.py ----
p1 = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\resource_registry.py"
with open(p1, encoding="utf-8") as f:
    t1 = f.read()

old1 = '''    if depth == "tail":
        tail = content[-500:] if len(content) > 500 else content
        return f"第{ch_idx}章结尾: {tail}"
    if len(content) > 4000:
        content = content[:2000] + "\\n……（中间内容省略）……\\n" + content[-2000:]
    return f"第{ch_idx}章（请仔细承接）:\\n{content}"'''
new1 = '''    if depth == "tail":
        tail = content[-500:] if len(content) > 500 else content
        return f"第{ch_idx}章结尾: {tail}"
    # full 深度硬截断：前文仅作承接/设定参考，超 1500 字取首尾
    if len(content) > 1500:
        content = content[:750] + "\\n……（中间内容省略）……\\n" + content[-750:]
    return f"第{ch_idx}章（请仔细承接）:\\n{content}"'''
if old1 not in t1:
    raise SystemExit("T1-1 未找到")
t1 = t1.replace(old1, new1, 1)
with open(p1, "w", encoding="utf-8", newline="\n") as f:
    f.write(t1)
print("[OK] resource_registry: full 深度硬截断 1500 字")

# ---- 2. context_analyzer.py schema 引导 ----
p2 = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\context_analyzer.py"
with open(p2, encoding="utf-8") as f:
    t2 = f.read()

old2 = '''        for r in selectable:
            label = res_labels.get(r, r)
            res = RESOURCE_REGISTRY.get(r, {})
            depths = list(res.get("formatters", {}).keys())
            depth_hint = " | ".join(depths) if depths else "full"
            arg = arg_hints.get(r, "")
            if arg:
                ref_lines.append(
                    f'    {{"resource": "{r}", {arg}, "depth": "{depth_hint.split()[0]}"}}')
            else:
                ref_lines.append(f'    {{"resource": "{r}", "depth": "{depth_hint.split()[0]}"}}')'''
new2 = '''        for r in selectable:
            label = res_labels.get(r, r)
            res = RESOURCE_REGISTRY.get(r, {})
            depths = list(res.get("formatters", {}).keys())
            depth_hint = " | ".join(depths) if depths else "full"
            # 前文按承接需求引导 depth：剧情承接用 tail，文风参照用 style
            recommend = "tail" if r == "previous_chapter" else (depths[0] if depths else "full")
            arg = arg_hints.get(r, "")
            if arg:
                ref_lines.append(
                    f'    {{"resource": "{r}", {arg}, "depth": "{recommend}"}}')
            else:
                ref_lines.append(f'    {{"resource": "{r}", "depth": "{recommend}"}}')'''
if old2 not in t2:
    raise SystemExit("T1-2 未找到")
t2 = t2.replace(old2, new2, 1)

old3 = '''- structured_refs：本节点可选资源清单（见【资源目录】），resource 只能取上述值；
            ids 从清单中选；depth 决定加载深度（full=完整/summary=摘要/tail=结尾片段/style=文风片段）。'''
new3 = '''- structured_refs：本节点可选资源清单（见【资源目录】），resource 只能取上述值；
            ids 从清单中选；depth 决定加载深度（full=完整/summary=摘要/tail=结尾片段/style=文风片段）。
            previous_chapter 建议 depth=tail（承接上一章结尾，500字）或 style（润色文风参照，320字），full 将截断至1500字。'''
if old3 not in t2:
    raise SystemExit("T1-3 未找到")
t2 = t2.replace(old3, new3, 1)
with open(p2, "w", encoding="utf-8", newline="\n") as f:
    f.write(t2)
print("[OK] context_analyzer: schema 引导 previous_chapter depth=tail/style")

# 编译检查
import py_compile
py_compile.compile(p1, doraise=True)
py_compile.compile(p2, doraise=True)
print("[OK] 编译通过")
