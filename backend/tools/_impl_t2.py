# -*- coding: utf-8 -*-
"""T2 ctx 分析输入瘦身：
1) 资源目录候选截断减半（角色20字/伏笔30字/前文40字等）
2) RAG 候选 15条→10条、preview 60字→30字
3) 输出 schema 字段说明精简
"""
p = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\context_analyzer.py"
with open(p, encoding="utf-8") as f:
    t = f.read()

# ---- 1. 资源目录候选截断 ----
pairs = [
    # (old, new)
    ("f\"    [{c.get('id')}] {c.get('name')}({c.get('type')}): {c.get('summary', '')[:60]}\"",
     "f\"    [{c.get('id')}] {c.get('name')}({c.get('type')}): {c.get('summary', '')[:20]}\""),
    ("f\"    [{f.get('id')}] [{f.get('tier', '')}] {f.get('content', '')[:60]} \"",
     "f\"    [{f.get('id')}] [{f.get('tier', '')}] {f.get('content', '')[:30]} \""),
    ("f\"    [{w.get('id')}] {w.get('name', '')}: {w.get('summary', '')[:80]}\"",
     "f\"    [{w.get('id')}] {w.get('name', '')}: {w.get('summary', '')[:40]}\""),
    ("f\"    {ps.get('name', '')}: {ps.get('summary', '')[:100]}\"",
     "f\"    {ps.get('name', '')}: {ps.get('summary', '')[:50]}\""),
    ("f\"    {gf.get('name', '')}: {gf.get('summary', '')[:100]}\"",
     "f\"    {gf.get('name', '')}: {gf.get('summary', '')[:50]}\""),
    ("f\"    {cg.get('name', '')}: 共同目标 {cg.get('goal', '')[:60]} | 成员: {cg.get('members_summary', '')[:60]}\"",
     "f\"    {cg.get('name', '')}: 共同目标 {cg.get('goal', '')[:30]} | 成员: {cg.get('members_summary', '')[:30]}\""),
    ("f\"    第{ch.get('index')}章: {ch.get('summary', '')[:80]}\"",
     "f\"    第{ch.get('index')}章: {ch.get('summary', '')[:40]}\""),
    ("summary = plan.get(\"summary\", \"\")[:100] if plan else \"\"",
     "summary = plan.get(\"summary\", \"\")[:50] if plan else \"\""),
    ("f\"    卷: {vol.get('volume_name', '')} | 核心冲突: {str(vol.get('core_conflict', ''))[:60]}\"",
     "f\"    卷: {vol.get('volume_name', '')} | 核心冲突: {str(vol.get('core_conflict', ''))[:30]}\""),
    ("f\"    {st.get('character_name') or st.get('name', '?')}: 位置 {st.get('location', '')} | 状态 {st.get('state', '')}\"",
     "f\"    {st.get('character_name') or st.get('name', '?')}: 位置 {str(st.get('location', ''))[:20]} | 状态 {str(st.get('state', ''))[:40]}\""),
    ("f\"    {hook.get('hook_content', '')[:80]}\"",
     "f\"    {hook.get('hook_content', '')[:40]}\""),
]
for old, new in pairs:
    if old in t:
        t = t.replace(old, new, 1)
        print(f"  [OK] {old[:40]}...")
    else:
        print(f"  [SKIP] 未找到: {old[:50]}")

# ---- 2. RAG 候选 15→10、preview 60→30 ----
old2 = '''        for i, c in enumerate(candidates[:15]):
            doc_id = c.get("doc_id", f"rag_{i}")
            ctype = c.get("type", "")
            chapter = c.get("chapter", 0)
            preview = c.get("preview", "")[:60]
            lines.append(f"  [{doc_id}] {ctype}/第{chapter}章: {preview}")'''
new2 = '''        for i, c in enumerate(candidates[:10]):
            doc_id = c.get("doc_id", f"rag_{i}")
            ctype = c.get("type", "")
            chapter = c.get("chapter", 0)
            preview = c.get("preview", "")[:30]
            lines.append(f"  [{doc_id}] {ctype}/第{chapter}章: {preview}")'''
if old2 in t:
    t = t.replace(old2, new2, 1)
    print("  [OK] RAG 候选 15→10 条、preview 60→30 字")
else:
    print("  [SKIP] RAG 候选未找到")

# ---- 3. 输出 schema 字段说明精简 ----
old3 = '''            "字段说明：\\n"
            "- structured_refs：本节点可选资源清单（见【资源目录】），resource 只能取上述值；"
            "ids 从清单中选；depth 决定加载深度（full=完整/summary=摘要/tail=结尾片段/style=文风片段）。"
            "previous_chapter 建议 depth=tail（承接上一章结尾，约500字）或 style（润色文风参照，约320字），full 将截断至1500字。\\n"
            "- 引用参数（必填）：character_card/foreshadow 必须填 ids（从【资源目录】清单选）；"
            "previous_chapter 必须填 chapter_index（从【资源目录】前文清单选章节号，例如 2 表示第2章），不得省略。\\n"
            "- rag_queries：RAG 语义检索查询，每条含实体与限定、禁止复制原文；"
            "types 可选值：chapter/chapter_summary/chapter_paragraph/foreshadow/character/worldview/power_system/golden_finger/villain/volume_outline。\\n"
            "- custom_notes：一致性要点，按【本节点一致性维度】检查，"
            "每条格式「[维度名] 主体: 规则」，如「[角色状态] 苏瑶: 保持受伤未愈状态」，不超过50字。\\n"'''
new3 = '''            "字段说明：\\n"
            "- structured_refs 从【资源目录】选；character_card/foreshadow 必填 ids，previous_chapter 必填 chapter_index；"
            "previous_chapter 建议 depth=tail(500字)或style(320字)。\\n"
            "- rag_queries：RAG 语义检索查询（含实体限定，禁止复制原文）；types：chapter/chapter_summary/foreshadow/character/worldview/power_system/golden_finger/villain/volume_outline。\\n"
            "- custom_notes：一致性要点，格式「[维度名] 主体: 规则」，如「[角色状态] 苏瑶: 保持受伤未愈状态」，≤50字。\\n"'''
if old3 in t:
    t = t.replace(old3, new3, 1)
    print("  [OK] schema 字段说明精简")
else:
    print("  [SKIP] schema 字段说明未找到")

with open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(t)
import py_compile
py_compile.compile(p, doraise=True)
print("[OK] 编译通过")
