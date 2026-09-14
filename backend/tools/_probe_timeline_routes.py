# -*- coding: utf-8 -*-
"""查 timeline 相关接口与数据源"""
import re

p = r"C:\MyProjects\CosyStudio\backend\webnovel\api\routes.py"
t = open(p, encoding="utf-8").read()
lines = t.split("\n")

# 1. 找所有 timeline 相关路由
for m in re.finditer(r'@router\.(get|post|put|delete)\("([^"]*timeline[^"]*)"\)', t, re.I):
    line_no = t[: m.start()].count("\n") + 1
    print("=== ", m.group(1).upper(), m.group(2), " @", line_no)
    for j in range(line_no - 1, min(line_no + 45, len(lines))):
        print(j + 1, "|", lines[j][:108])
    print()

# 2. 找所有 timeline 相关导入
print("### timeline 相关 import")
for i, ln in enumerate(lines):
    if "timeline" in ln.lower() and ("import" in ln or "from" in ln):
        print(i + 1, "|", ln[:120])

# 3. 找 router 路径前缀
for i, ln in enumerate(lines):
    if "router = APIRouter" in ln or "prefix" in ln and "APIRouter" in ln:
        print("router def:", i + 1, "|", ln[:120])
