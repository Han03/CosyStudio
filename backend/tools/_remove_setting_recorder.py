# -*- coding: utf-8 -*-
"""删除 setting_recorder 节点：orchestrator / executors 注册 / e2e / model_capability / prompt_diag / 文件。"""
import os

BACKEND = r"C:\MyProjects\CosyStudio\backend"

def patch(path, old, new, must=True):
    p = os.path.join(BACKEND, path)
    with open(p, encoding="utf-8") as f:
        text = f.read()
    if old not in text:
        if must:
            raise SystemExit(f"[FAIL] 未找到: {path}\n---\n{old[:200]}")
        return False
    text = text.replace(old, new, 1)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"[OK] {path}")
    return True

# 1. orchestrator: DEFAULT_STEPS（循环列表，setting_recorder 后接 context_builder）+ write 流程
patch("webnovel/pipeline/orchestrator.py",
      '        "setting_recorder",\n'
      '        "context_builder",\n'
      '        "chapter_plot_generator",',
      '        "context_builder",\n'
      '        "chapter_plot_generator",')
patch("webnovel/pipeline/orchestrator.py",
      '            "draft_polisher",\n'
      '            "setting_recorder",\n'
      '        ],',
      '            "draft_polisher",\n'
      '        ],')

# 2. executors/__init__.py
patch("webnovel/pipeline/executors/__init__.py",
      "from .setting_recorder_executor import SettingRecorderExecutor\n",
      "")
patch("webnovel/pipeline/executors/__init__.py",
      "    SettingRecorderExecutor,\n",
      "")

# 3. e2e 脚本
patch("tools/_e2e_run.py",
      '        "setting_recorder",\n',
      "", must=False)
patch("tools/_e2e_run.py",
      "→ draft_reviewer → draft_polisher → setting_recorder",
      "→ draft_reviewer → draft_polisher", must=False)

# 4. model_capability 能力描述
patch("api/model_capability.py",
      '            "setting_recorder": {"name": "设定记录", "description": "世界观设定提取与记录"},\n',
      "", must=False)

# 5. prompt_diag runner
patch("tools/prompt_diag/runner.py",
      '        ("webnovel.pipeline.executors.setting_recorder_executor", "add_worldview", {}),\n',
      "", must=False)

# 6. 删除文件
for f in ["webnovel/pipeline/executors/setting_recorder_executor.py",
          "webnovel/prompts/knowledge_explain_prompt.md"]:
    fp = os.path.join(BACKEND, f)
    if os.path.exists(fp):
        os.remove(fp)
        print(f"[DEL] {f}")

print("\nsetting_recorder 节点移除完成")
