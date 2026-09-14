# -*- coding: utf-8 -*-
"""空区块优化：
1. formatter 的"（无…）"占位改为返回空串（有指令语义的 plot_list 占位保留）
2. _assemble_context 组装层跳过空区块（标题也不输出）
"""
import py_compile

# ── 1. resource_registry.py formatter 空值占位 → "" ──
p1 = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\resource_registry.py"
with open(p1, encoding="utf-8") as f:
    t = f.read()

repl = [
    # (old, new)
    ('        return "（无角色状态记录）"', '        return ""'),
    ('        return "（无角色信息）"', '        return ""'),
    ('        return "（无角色）"', '        return ""'),
    ('        return "（无主角团）"', '        return ""'),
    ('    return "\\n".join(parts) if parts else "（无主角团成员）"',
     '    return "\\n".join(parts) if parts else ""'),
    ('        return "（无世界观设定）"', '        return ""'),
    ('    return "\\n".join(parts) if parts else "（无世界观设定）"',
     '    return "\\n".join(parts) if parts else ""'),
    ('        return "（未设定力量体系）"', '        return ""'),
    ('    return "\\n".join(lines) if lines else "（未设定力量体系）"',
     '    return "\\n".join(lines) if lines else ""'),
    ('        return "（未设定金手指）"', '        return ""'),
    ('        return "（无活跃伏笔）"', '        return ""'),
    ('        return "（无检索结果）"', '        return ""'),
    ('        return "（无）"', '        return ""'),
    ('        return "（无审查维度）"', '        return ""'),
]
for old, new in repl:
    cnt = t.count(old)
    assert cnt >= 1, f"未找到: {old}"
    t = t.replace(old, new)

# _fmt_golden_finger：存在但字段全空时也返回 ""
old_gf = '''def _fmt_golden_finger(gf, depth="full"):
    if not gf or not isinstance(gf, dict):
        return ""
    return (
        f"- 名称: {gf.get('main_role', '')}\\n"
        f"- 类型: {gf.get('type', '')}\\n"
        f"- 核心能力: {str(gf.get('core_function', ''))[:200]}\\n"
        f"- 不可逆代价: {str(gf.get('irreversible_cost', ''))[:200]}"
    )'''
new_gf = '''def _fmt_golden_finger(gf, depth="full"):
    if not gf or not isinstance(gf, dict):
        return ""
    parts = []
    if gf.get("main_role"):
        parts.append(f"- 名称: {gf['main_role']}")
    if gf.get("type"):
        parts.append(f"- 类型: {gf['type']}")
    if gf.get("core_function"):
        parts.append(f"- 核心能力: {str(gf['core_function'])[:200]}")
    if gf.get("irreversible_cost"):
        parts.append(f"- 不可逆代价: {str(gf['irreversible_cost'])[:200]}")
    return "\\n".join(parts)'''
assert old_gf in t, "_fmt_golden_finger 未找到"
t = t.replace(old_gf, new_gf, 1)

# _fmt_previous_hook：全空返回 ""
old_hook = '''def _fmt_previous_hook(hook, depth="full"):
    return (
        f"- 结尾状态: {hook.get('hook_content', '')}\\n"
        f"- 状态类型: {hook.get('hook_type', '')}\\n"
        f"- 结尾情绪: {hook.get('ending_emotion', '')}"
    )'''
new_hook = '''def _fmt_previous_hook(hook, depth="full"):
    parts = []
    if hook.get("hook_content"):
        parts.append(f"- 结尾状态: {hook['hook_content']}")
    if hook.get("hook_type"):
        parts.append(f"- 状态类型: {hook['hook_type']}")
    if hook.get("ending_emotion"):
        parts.append(f"- 结尾情绪: {hook['ending_emotion']}")
    return "\\n".join(parts)'''
assert old_hook in t, "_fmt_previous_hook 未找到"
t = t.replace(old_hook, new_hook, 1)

with open(p1, "w", encoding="utf-8", newline="\n") as f:
    f.write(t)
py_compile.compile(p1, doraise=True)
print("[OK] resource_registry.py formatter 空占位已改为空串")

# ── 2. context_analyzer.py 组装层跳过空区块 ──
p2 = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\context_analyzer.py"
with open(p2, encoding="utf-8") as f:
    t2 = f.read()

old_asm = '''                if sec_name not in _JSON_SECTIONS:
                    body = normalize_text_block(body, mode="preserve_md_list")
                ordered.append(f"{header}\\n{body}")'''
new_asm = '''                if sec_name not in _JSON_SECTIONS:
                    body = normalize_text_block(body, mode="preserve_md_list")
                if not body or not body.strip():
                    # 空区块整体跳过，不保留空标题
                    continue
                ordered.append(f"{header}\\n{body}")'''
assert old_asm in t2, "组装逻辑未找到"
t2 = t2.replace(old_asm, new_asm, 1)

with open(p2, "w", encoding="utf-8", newline="\n") as f:
    f.write(t2)
py_compile.compile(p2, doraise=True)
print("[OK] context_analyzer.py 组装层已跳过空区块")
