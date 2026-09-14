# -*- coding: utf-8 -*-
"""T1 补充：context_analyzer schema 引导（修正字符串拼接匹配）。"""
p = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\context_analyzer.py"
with open(p, encoding="utf-8") as f:
    t = f.read()

# 1) 示例 depth：previous_chapter 推荐 tail
old1 = '''            arg_hints = {
            "character_card": '"ids": [角色id]',
            "foreshadow": '"ids": [伏笔id]',
            "previous_chapter": '"chapter_index": 章节号',
        }'''
# 上面 old1 可能缩进不同，直接用实际代码
old1a = '''        arg_hints = {
            "character_card": '"ids": [角色id]',
            "foreshadow": '"ids": [伏笔id]',
            "previous_chapter": '"chapter_index": 章节号',
        }'''
new1a = '''        arg_hints = {
            "character_card": '"ids": [角色id]',
            "foreshadow": '"ids": [伏笔id]',
            "previous_chapter": '"chapter_index": 章节号',
        }
        # 前文按承接需求引导 depth：剧情承接用 tail，文风参照用 style
        _PREV_CH_DEPTH_RECOMMEND = {"previous_chapter": "tail"}'''
if old1a not in t:
    raise SystemExit("T1-2a 未找到")
t = t.replace(old1a, new1a, 1)

# 2) 示例 depth 使用推荐值
old2 = '''            depths = list(res.get("formatters", {}).keys())
            depth_hint = " | ".join(depths) if depths else "full"
            arg = arg_hints.get(r, "")
            if arg:
                ref_lines.append(
                    f'    {{"resource": "{r}", {arg}, "depth": "{depth_hint.split()[0]}"}}')
            else:
                ref_lines.append(f'    {{"resource": "{r}", "depth": "{depth_hint.split()[0]}"}}')'''
new2 = '''            depths = list(res.get("formatters", {}).keys())
            depth_hint = " | ".join(depths) if depths else "full"
            recommend = _PREV_CH_DEPTH_RECOMMEND.get(r) or (depths[0] if depths else "full")
            arg = arg_hints.get(r, "")
            if arg:
                ref_lines.append(
                    f'    {{"resource": "{r}", {arg}, "depth": "{recommend}"}}')
            else:
                ref_lines.append(f'    {{"resource": "{r}", "depth": "{recommend}"}}')'''
if old2 not in t:
    raise SystemExit("T1-2b 未找到")
t = t.replace(old2, new2, 1)

# 3) 字段说明补充前文 depth 建议
old3 = '''            "- structured_refs：本节点可选资源清单（见【资源目录】），resource 只能取上述值；"
            "ids 从清单中选；depth 决定加载深度（full=完整/summary=摘要/tail=结尾片段/style=文风片段）。\\n"'''
new3 = '''            "- structured_refs：本节点可选资源清单（见【资源目录】），resource 只能取上述值；"
            "ids 从清单中选；depth 决定加载深度（full=完整/summary=摘要/tail=结尾片段/style=文风片段）。"
            "previous_chapter 建议 depth=tail（承接上一章结尾，约500字）或 style（润色文风参照，约320字），full 将截断至1500字。\\n"'''
if old3 not in t:
    raise SystemExit("T1-3 未找到")
t = t.replace(old3, new3, 1)

with open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(t)
print("[OK] context_analyzer: schema 引导完成")

import py_compile
py_compile.compile(p, doraise=True)
print("[OK] 编译通过")
