# -*- coding: utf-8 -*-
"""max_tokens 余量调整：生成类 ×2.4，剧情类 plot_count×600。"""
p = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\orchestrator.py"
with open(p, encoding="utf-8") as f:
    t = f.read()

old = '''            "polish_max_tokens": max(1500, polish_max * 2),
            "draft_max_tokens": max(800, draft_max * 2),
            "revise_draft_max_tokens": max(800, draft_max * 2),
            "plot_max_tokens": max(1200, plot_count * 400),
            "plot_revise_max_tokens": max(1200, plot_count * 400),'''
new = '''            "polish_max_tokens": max(1500, round(polish_max * 2.4)),
            "draft_max_tokens": max(800, round(draft_max * 2.4)),
            "revise_draft_max_tokens": max(800, round(draft_max * 2.4)),
            "plot_max_tokens": max(1500, plot_count * 600),
            "plot_revise_max_tokens": max(1500, plot_count * 600),'''
if old not in t:
    raise SystemExit("未找到目标文本")
t = t.replace(old, new, 1)
with open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(t)
print("[OK] max_tokens 余量已调整")

# 验证推导
raw = 1000
polish_min, polish_max = round(raw * 0.8), round(raw * 1.2)
draft_min, draft_max = round(polish_min * 0.5), round(polish_max * 0.5)
plot_count = max(4, min(10, round(raw / 250)))
print(f"\n1000字档: polish_max_tokens={max(1500, round(polish_max*2.4))} "
      f"draft_max_tokens={max(800, round(draft_max*2.4))} "
      f"plot_max_tokens={max(1500, plot_count*600)}")
raw = 4000
polish_min, polish_max = round(raw * 0.8), round(raw * 1.2)
draft_min, draft_max = round(polish_min * 0.5), round(polish_max * 0.5)
plot_count = max(4, min(10, round(raw / 250)))
print(f"4000字档: polish_max_tokens={max(1500, round(polish_max*2.4))} "
      f"draft_max_tokens={max(800, round(draft_max*2.4))} "
      f"plot_max_tokens={max(1500, plot_count*600)}")
