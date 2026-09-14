# -*- coding: utf-8 -*-
"""ctx 分析 prompt 步骤名中文化：
1. STEP_GOALS 每项加 name（中文名）
2. _build_analysis_prompt 渲染 step_name=goal["name"]（模板 {step_name} 传中文）
3. _format_prev_selections 复用 STEP_GOALS name，删除重复 step_labels
"""
import py_compile

p = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\context_analyzer.py"
with open(p, encoding="utf-8") as f:
    t = f.read()

# ── 1. STEP_GOALS 加 name ──
old_goals = '''STEP_GOALS = {
    "chapter_plot_generator": {
        "description": (
            "为第{chapter_index}章生成场景级剧情列表。"
            "需要理解章节规划目标、角色当前状态、活跃伏笔布局、前文衔接点。"
        ),
        "focus": "剧情规划覆盖、伏笔布局时机、角色弧线推进、前文自然衔接",
    },
    "draft_generator": {
        "description": (
            "根据剧情列表创作白描草稿。"
            "需要精确的角色行为参考、物品约束、前文衔接。"
        ),
        "focus": "角色行为与性格一致、物品清单约束、前文结尾自然承接、剧情完整覆盖",
    },
    "draft_reviewer": {
        "description": (
            "审查草稿质量。需要对照设定检查一致性、对照前文检查连贯性。"
        ),
        "focus": "设定一致性、角色行为合理性、剧情逻辑、前文连贯",
    },
    "draft_polisher": {
        "description": (
            "将白描草稿润色为完整小说。需要世界观氛围参考、力量体系描写参考。"
        ),
        "focus": "世界观细节准确、力量体系描写规范、文风统一",
    },
    "chapter_plot_reviewer": {
        "description": (
            "审查剧情列表质量。需要对照角色能力设定、世界观规则与伏笔布局检查合理性。"
        ),
        "focus": "设定匹配、伏笔布局合理性、剧情因果、信息揭示时机",
    },
}'''
new_goals = '''STEP_GOALS = {
    "chapter_plot_generator": {
        "name": "剧情生成",
        "description": (
            "为第{chapter_index}章生成场景级剧情列表。"
            "需要理解章节规划目标、角色当前状态、活跃伏笔布局、前文衔接点。"
        ),
        "focus": "剧情规划覆盖、伏笔布局时机、角色弧线推进、前文自然衔接",
    },
    "draft_generator": {
        "name": "草稿生成",
        "description": (
            "根据剧情列表创作白描草稿。"
            "需要精确的角色行为参考、物品约束、前文衔接。"
        ),
        "focus": "角色行为与性格一致、物品清单约束、前文结尾自然承接、剧情完整覆盖",
    },
    "draft_reviewer": {
        "name": "草稿审查",
        "description": (
            "审查草稿质量。需要对照设定检查一致性、对照前文检查连贯性。"
        ),
        "focus": "设定一致性、角色行为合理性、剧情逻辑、前文连贯",
    },
    "draft_polisher": {
        "name": "草稿润色",
        "description": (
            "将白描草稿润色为完整小说。需要世界观氛围参考、力量体系描写参考。"
        ),
        "focus": "世界观细节准确、力量体系描写规范、文风统一",
    },
    "chapter_plot_reviewer": {
        "name": "剧情审查",
        "description": (
            "审查剧情列表质量。需要对照角色能力设定、世界观规则与伏笔布局检查合理性。"
        ),
        "focus": "设定匹配、伏笔布局合理性、剧情因果、信息揭示时机",
    },
}'''
assert old_goals in t, "STEP_GOALS 未找到"
t = t.replace(old_goals, new_goals, 1)

# ── 2. 渲染 step_name=goal["name"] ──
old_render = '''            return normalize_text_block(user_prompt.format(
                chapter_index=chapter_index,
                step_name=step_name,'''
new_render = '''            return normalize_text_block(user_prompt.format(
                chapter_index=chapter_index,
                step_name=goal["name"],'''
assert old_render in t, "渲染点未找到"
t = t.replace(old_render, new_render, 1)

# ── 3. _format_prev_selections 复用 STEP_GOALS name ──
old_labels = '''        step_labels = {
            "chapter_plot_generator": "剧情生成",
            "draft_generator": "草稿生成",
            "draft_reviewer": "草稿审查",
        }
        parts = ["【前序步骤已选择的上下文】"]
        for step_name, sel in prev_selections.items():
            if not isinstance(sel, dict):
                continue
            label = step_labels.get(step_name, step_name)'''
new_labels = '''        parts = ["【前序步骤已选择的上下文】"]
        for step_name, sel in prev_selections.items():
            if not isinstance(sel, dict):
                continue
            goal = STEP_GOALS.get(step_name)
            label = goal["name"] if goal else step_name'''
assert old_labels in t, "step_labels 未找到"
t = t.replace(old_labels, new_labels, 1)

with open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(t)
py_compile.compile(p, doraise=True)
print("[OK] context_analyzer.py 已更新")

# ── 4. 验证：渲染一条 prompt 确认中文步骤名 ──
import sys
sys.path.insert(0, r"C:\MyProjects\CosyStudio\backend")
from webnovel.pipeline.context_analyzer import STEP_GOALS
for k, v in STEP_GOALS.items():
    print(f"  {k} -> {v['name']}")
