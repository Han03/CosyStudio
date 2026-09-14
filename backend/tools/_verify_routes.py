# -*- coding: utf-8 -*-
"""验证：路由清单 + 编译"""
import re, py_compile

p = r"C:\MyProjects\CosyStudio\backend\webnovel\api\routes.py"
t = open(p, encoding="utf-8").read()
for m in re.finditer(r'@router\.(get|post|put|delete)\("([^"]+)"\)', t):
    path = m.group(2)
    if "loop" in path or "cool" in path or "foreshadow" in path.lower():
        print(m.group(1).upper(), path)
py_compile.compile(p, doraise=True)
print("[OK] 编译通过")
