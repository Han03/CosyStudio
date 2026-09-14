# -*- coding: utf-8 -*-
"""删除 /foreshadowing 遗留接口（前端实际使用 /webnovel-open-loops）"""
import py_compile

p = r"C:\MyProjects\CosyStudio\backend\webnovel\api\routes.py"
t = open(p, encoding="utf-8").read()
old = '''@router.get("/foreshadowing")
def list_foreshadowing(script_id: int, status: str = Query("")):
    """获取伏笔列表。"""
    project = get_webnovel_project_by_script(script_id)
    if not project:
        return {"success": True, "foreshadowing": []}
    
    if status == "active":
        loops = get_active_open_loops(project["id"])
    else:
        loops = get_open_loops_by_project(project["id"], status)
    
    return {"success": True, "foreshadowing": loops}


'''
assert old in t, "未找到 /foreshadowing 接口"
t = t.replace(old, "", 1)
open(p, "w", encoding="utf-8", newline="\n").write(t)
py_compile.compile(p, doraise=True)
print("[OK] 已删除 /foreshadowing 遗留接口")
print("残留 'foreshadowing':", t.count("foreshadowing"))
