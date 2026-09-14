# -*- coding: utf-8 -*-
"""清理 prompt_diag 的 setting_recorder 残留。"""
import os

BACKEND = r"C:\MyProjects\CosyStudio\backend"

p = os.path.join(BACKEND, r"tools\prompt_diag\runner.py")
with open(p, encoding="utf-8") as f:
    t = f.read()
old = '    "setting_recorder": {"setting_recorder"},\n'
if old in t:
    t = t.replace(old, "")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(t)
    print("[OK] runner.py 节点映射已删")
else:
    print("[SKIP] runner.py 无残留")

p2 = os.path.join(BACKEND, r"tools\prompt_diag\README.md")
with open(p2, encoding="utf-8") as f:
    t2 = f.read()
if "setting_recorder" in t2:
    t2 = t2.replace("、`setting_recorder`", "").replace("`setting_recorder`、", "")
    with open(p2, "w", encoding="utf-8", newline="\n") as f:
        f.write(t2)
    print("[OK] README.md 节点清单已删")
else:
    print("[SKIP] README.md 无残留")
