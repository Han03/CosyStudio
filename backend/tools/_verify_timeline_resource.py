# -*- coding: utf-8 -*-
"""验证 timeline 资源注册：loader / formatter / 候选展示"""
import sys, os
sys.path.insert(0, r"C:\MyProjects\CosyStudio\backend")
os.chdir(r"C:\MyProjects\CosyStudio\backend")

import py_compile
py_compile.compile(r"webnovel\pipeline\resource_registry.py", doraise=True)
py_compile.compile(r"webnovel\pipeline\context_analyzer.py", doraise=True)
print("[OK] 编译通过")

from webnovel.pipeline.resource_registry import (
    RESOURCE_REGISTRY, STEP_ASSEMBLY, _load_timeline, _fmt_timeline,
)

# 1. 注册项存在且字段正确
res = RESOURCE_REGISTRY.get("timeline")
assert res, "timeline 未注册"
print("[OK] 注册项:", res["label"], "|", res["header"], "|", res["category"])

# 2. 各节点白名单
for step, asc in STEP_ASSEMBLY.items():
    has = "timeline" in asc["selectable"]
    print(f"    {step}: selectable 含 timeline = {has}")

# 3. loader 真实数据（project 93）
env = {
    "project_id": 93,
    "structural_data": {"current_volume": {"volume_number": 1}},
    "inventory": {},
}
data = _load_timeline({"resource": "timeline"}, env)
assert data and data["timeline"], "loader 返回空"
tl = data["timeline"]
print(f"[OK] loader: volume={tl.get('volume_number')} time_base={tl.get('time_base')} chapters={len(data['chapters'])}")

# 4. formatter 输出
text = _fmt_timeline(data, "full")
print("---- formatter 输出 ----")
print(text)

# 5. 候选展示（模拟 context_analyzer._format_resource_candidates）
from webnovel.pipeline.context_analyzer import ContextAnalyzer
ca = ContextAnalyzer(93, 4)
cand = ca._format_resource_candidates("timeline", env)
print("---- 候选展示 ----")
print(cand)
