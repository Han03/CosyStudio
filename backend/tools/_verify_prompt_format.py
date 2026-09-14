# -*- coding: utf-8 -*-
"""静态验证：
1. normalize_text_block 单测（多换行/全角空格/零宽/行尾空白/JSON保留）
2. 7 个 prompt frontmatter 可解析、system/user 非空
3. 全部模板用假数据渲染不抛 KeyError（占位符完整）
4. 改后 prompt 关键结构存在（处理步骤/长度约束/优先级等）
"""
import os, re, sys

sys.path.insert(0, r"C:\MyProjects\CosyStudio\backend")
from utils.prompt_normalizer import normalize_text_block

ok = True
def check(name, cond, detail=""):
    global ok
    if not cond:
        ok = False
    print(("[OK] " if cond else "[FAIL] ") + name + (f" | {detail}" if detail and not cond else ""))

# ── 1. 归一化单测 ──
dirty = "\u200b\u3000  你好　世界  \n\n\n第二行\t内容   \n\n\n\n第三行\x00\x08"
n = normalize_text_block(dirty)
check("归一化: 零宽/全角/行尾/空行/控制字符", "你好世界\n\n第二行 内容\n\n第三行" == n, repr(n))

js = "{\n  \"a\": \"x y\"\n}\n\n\n  "
nj = normalize_text_block(js, mode="preserve_json")
check("归一化: JSON 保留缩进", '{\n  "a": "x y"\n}' == nj, repr(nj))

md = "1. 第一项\n    续行内容  \n2. 第二项\n\n\n\n3. 第三项"
nm = normalize_text_block(md, mode="preserve_md_list")
check("归一化: md 列表保留缩进+压空行", "1. 第一项\n    续行内容\n2. 第二项\n\n3. 第三项" == nm, repr(nm))
check("归一化: 空输入", "" == normalize_text_block(""))

# ── 2/3. frontmatter 解析 + 占位符渲染 ──
PROMPTS = r"C:\MyProjects\CosyStudio\backend\webnovel\prompts"
names = ["chapter_plot_generate", "chapter_plot_review", "chapter_plot_revise",
         "draft_generate", "review_draft", "revise_draft", "draft_polish",
         "context_analysis"]

def parse(p):
    with open(p, encoding="utf-8") as f:
        c = f.read().strip()
    c = c[3:].strip() if c.startswith("---") else c
    c = c[:-3].strip() if c.endswith("---") else c
    lines = c.split("\n")
    sp, up = "", ""
    in_up = False
    for ln in lines:
        if in_up:
            up += ln + "\n"
            continue
        if ln.startswith("system_prompt:"):
            sp = ln.split(":", 1)[1].strip()
        elif ln.startswith("user_prompt:"):
            in_up = True
            up = ln.split(":", 1)[1].lstrip().strip()
            if up and not up.endswith("\n"):
                up += "\n"
    return sp, up.strip()

FILL = {"chapter_index": "1", "step_name": "剧情生成", "step_description": "生成剧情", "focus": "主线",
        "resource_catalog": "资源", "rag_candidates_text": "候选", "prev_step_selections_text": "前选",
        "dimension_checklist_text": "维度", "output_schema": "{}", "assembled_context": "上下文",
        "plot_text": "[]", "plot_count": "4", "plot_desc_max": "60", "original_plot_text": "[]",
        "issues_text": "无", "user_prompt_section": "写作要求", "draft_word_min": "400", "draft_word_max": "600",
        "draft_point_max": "150", "continue_prev": "", "draft": "草稿", "polish_word_min": "800",
        "polish_word_max": "1200", "draft_content": "草稿内容", "suggestions_text": "无",
        "chapter_summary": "摘要", "step_info": "步骤", "word_cfg": "", "previous_chapter": "1",
        "character_ids": "", "foreshadow_ids": "", "review_result": "{}", "key_events": "事件",
        "character_info": "角色", "location_info": "地点", "item_info": "物品",
        "relationship_info": "关系", "state_info": "状态", "worldview_info": "设定"}

for n in names:
    p = os.path.join(PROMPTS, f"{n}_prompt.md")
    sp, up = parse(p)
    check(f"frontmatter: {n}", sp and up, f"sp={len(sp)} up={len(up)}")
    if not (sp and up):
        continue
    # 渲染：未替换的占位符会 KeyError
    try:
        up.format(**FILL)
        check(f"渲染: {n}", True)
    except KeyError as e:
        check(f"渲染: {n}", False, f"缺占位符 {e}")

# ── 4. 关键结构存在性 ──
with open(os.path.join(PROMPTS, "draft_generate_prompt.md"), encoding="utf-8") as f:
    dg = f.read()
check("草稿生成: 编号写作要求", re.search(r"【写作要求】\n.*1\. 语言", dg, re.S))
check("草稿生成: 白描正反例", "【写作示范】" in dg and "好：" in dg and "坏：" in dg)
with open(os.path.join(PROMPTS, "draft_polish_prompt.md"), encoding="utf-8") as f:
    dp = f.read()
check("润色: 优先级声明", "【优先级】润色红线 > 润色要点 > 网文分段规范" in dp)
check("润色: 红线去重(开头无重复续写句)", "禁止在草稿情节结束后再追加收尾段" not in dp.split("【润色要点】")[0])
with open(os.path.join(PROMPTS, "chapter_plot_generate_prompt.md"), encoding="utf-8") as f:
    cg = f.read()
check("剧情生成: 处理步骤", "【处理步骤】" in cg and "【长度约束】" in cg and "【元素格式对照】" in cg)
with open(os.path.join(PROMPTS, "chapter_plot_revise_prompt.md"), encoding="utf-8") as f:
    cr = f.read()
check("剧情修订: 修改原则+长度约束", "【修改原则】" in cr and "【长度约束】" in cr)
with open(os.path.join(PROMPTS, "revise_draft_prompt.md"), encoding="utf-8") as f:
    rd = f.read()
check("草稿修订: 输出前自查", "【输出前自查】" in rd)
with open(os.path.join(PROMPTS, "context_analysis_prompt.md"), encoding="utf-8") as f:
    ca = f.read()
check("ctx分析: 三层选择约束", "1. 必选：" in ca and "2. 建议：" in ca and "3. 可选：" in ca)

# ── 5. 归一化接入点确认 ──
for path, needle in [
    (r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\base_executor.py", "def _format_prompt"),
    (r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\context_analyzer.py", 'normalize_text_block(content)'),
    (r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\context_analyzer.py", 'mode="preserve_md_list"'),
]:
    with open(path, encoding="utf-8") as f:
        t = f.read()
    check(f"接入: {path.split(chr(92))[-1]} 含 {needle[:30]}", needle in t)

print("\n" + ("全部通过" if ok else "存在失败项"))
sys.exit(0 if ok else 1)
