# -*- coding: utf-8 -*-
"""验证时间轴改造：编译 + 注册 + 幂等逻辑 + 残留"""
import sys, os, py_compile
sys.path.insert(0, r"C:\MyProjects\CosyStudio\backend")
os.chdir(r"C:\MyProjects\CosyStudio\backend")

files = [
    r"webnovel\pipeline\executors\volume_timeline_generator_executor.py",
    r"webnovel\pipeline\executors\plan_executor.py",
    r"webnovel\pipeline\executors\__init__.py",
    r"webnovel\pipeline\orchestrator.py",
    r"webnovel\services\webnovel_service.py",
    r"webnovel\api\routes.py",
    r"api\model_capability.py",
]
for f in files:
    py_compile.compile(f, doraise=True)
    print("[OK] 编译:", f)

# 注册链
from webnovel.pipeline.orchestrator import PipelineOrchestrator
assert "volume_timeline_generator" in PipelineOrchestrator.DEFAULT_STEPS
assert "timeline_fixer" not in PipelineOrchestrator.DEFAULT_STEPS
print("[OK] DEFAULT_STEPS:", PipelineOrchestrator.DEFAULT_STEPS[:3])

from webnovel.pipeline.executors import EXECUTORS
names = [e.step_name for e in EXECUTORS]
assert "volume_timeline_generator" in names, names
assert "timeline_fixer" not in names, names
print("[OK] EXECUTORS 注册:", "volume_timeline_generator" in names)

from webnovel.pipeline.executors.volume_timeline_generator_executor import VolumeTimelineGeneratorExecutor
print("[OK] executor 类可导入")

# 死文件检查
assert not os.path.exists(r"webnovel\pipeline\executors\timeline_fixer_executor.py")
assert not os.path.exists(r"webnovel\prompts\plan_timeline_prompt.md")
assert os.path.exists(r"webnovel\prompts\volume_timeline_prompt.md")
print("[OK] 文件增删符合预期")

# prompt 可加载
e = VolumeTimelineGeneratorExecutor(999913, 1, 0)
pd = e._load_prompt("volume_timeline")
assert pd["user_prompt"] and "time_base" in pd["user_prompt"]
print("[OK] prompt 加载成功")
