# -*- coding: utf-8 -*-
"""修复 draft_generate / draft_polish 输出格式块（按行定位替换，规避转义）。"""
import os

BACKEND = r"C:\MyProjects\CosyStudio\backend"

def replace_block(path, start_marker, end_marker, new_block, must=True):
    p = os.path.join(BACKEND, path)
    with open(p, encoding="utf-8") as f:
        lines = f.readlines()
    start = end = None
    for i, ln in enumerate(lines):
        if start is None and start_marker in ln:
            start = i
        elif start is not None and end_marker in ln:
            end = i
            break
    if start is None or end is None:
        if must:
            raise SystemExit(f"[FAIL] 块定位失败: {path} [{start_marker} → {end_marker}]")
        return False
    # 保留 end_marker 所在行，替换 start..end-1
    new_lines = lines[:start] + [new_block] + lines[end:]
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(new_lines)
    print(f"[OK] {path} 输出格式块已替换")
    return True

# F. draft_generate：输出格式节 → 纯文本
new_f = "  【输出格式】\n" \
        "  请直接输出小说草稿纯文本正文，不要包含任何JSON、代码块标记、元信息、注释或说明文字。\n" \
        "  - 正文即草稿本身，从第一句正文开始，达到字数要求后自然停止\n" \
        "  - 段落之间用空行分隔\n\n"
replace_block("webnovel/prompts/draft_generate_prompt.md",
              "  【输出格式】", "  请输出章节草稿：", new_f)

# H. draft_polish：输出格式节 → 纯文本
new_h = "  【输出格式】\n" \
        "  请直接输出润色后的完整小说章节正文纯文本，不要包含任何JSON、代码块标记、元信息、注释或说明文字。\n" \
        "  - 正文即成品，从第一句正文开始，结尾自然收住\n" \
        "  - 段落之间用空行分隔（一个空行）\n\n"
replace_block("webnovel/prompts/draft_polish_prompt.md",
              "  【输出格式】", "  【润色红线（必须遵守）】", new_h)

# 顺带：draft_polish 第19行 双换行说明（真实文本），改为空行
p = os.path.join(BACKEND, "webnovel/prompts/draft_polish_prompt.md")
with open(p, encoding="utf-8") as f:
    t = f.read()
old = "  - 段落之间必须用两个连续换行（即 JSON 字符串中的 \\n\\n）分隔，严禁只用单个 \\n"
if old in t:
    t = t.replace(old, "  - 段落之间必须用空行分隔（一个空行），严禁不用空行", 1)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(t)
    print("[OK] draft_polish 分段说明已更新")
else:
    print("[WARN] draft_polish 分段说明未匹配，跳过")

print("\n完成")
