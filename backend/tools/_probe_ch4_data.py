# -*- coding: utf-8 -*-
"""探查第4章相关数据分布与章节文件路径"""
import sqlite3, os, sys

sys.path.insert(0, r"C:\MyProjects\CosyStudio\backend")
DB = r"C:\MyProjects\CosyStudio\data\cache\app.db"
db = sqlite3.connect(DB)
cur = db.cursor()

def cols(t):
    return [c[1] for c in cur.execute(f"PRAGMA table_info({t})").fetchall()]

# 1. chapter_plan
print("=== chapter_plan 表结构 ===")
c = cols("webnovel_chapter_plan")
print(c)
key = "chapter_index" if "chapter_index" in c else "chapter_number"
sk = "script_id" if "script_id" in c else ("project_id" if "project_id" in c else None)
if sk:
    rows = cur.execute(f"SELECT * FROM webnovel_chapter_plan WHERE {sk}=999913 AND {key}=4").fetchall()
    print(f"ch4 规划（{sk}={key}）:", len(rows), "行")
    if rows:
        print("  样例:", rows[0][:5])
else:
    rows = cur.execute(f"SELECT * FROM webnovel_chapter_plan WHERE {key}=4").fetchall()
    print(f"ch4 规划: {len(rows)} 行")

# 2. script_chapters
print("\n=== script_chapters ch4 ===")
rows = cur.execute(
    "SELECT id, script_id, chapter_index, title, file_path, word_count FROM script_chapters "
    "WHERE script_id=999913 AND chapter_index=4").fetchall()
for r in rows:
    print(" ", r)

# 3. pipeline_logs
print("\n=== script_writing_pipeline_logs ===")
c = cols("script_writing_pipeline_logs")
print("结构:", c)
n = cur.execute("SELECT COUNT(*) FROM script_writing_pipeline_logs").fetchone()[0]
print("总行数:", n)
if n:
    row = cur.execute("SELECT * FROM script_writing_pipeline_logs LIMIT 1").fetchone()
    print("样例:", str(row)[:200])

# 4. 事实表 ch4 分布
print("\n=== 事实表 ch4 分布 ===")
for t, col in [
    ("webnovel_character_state", "chapter_number"),
    ("webnovel_cool_points", "chapter_number"),
    ("webnovel_review_record", "chapter_number"),
    ("webnovel_chapter_meta", "chapter_number"),
    ("webnovel_open_loops", "planted_chapter"),
    ("webnovel_foreshadow", "buried_chapter"),
    ("webnovel_character_item", "chapter_number"),
    ("webnovel_character_growth", "chapter_number"),
]:
    try:
        c = cols(t)
        if col in c:
            n = cur.execute(f"SELECT COUNT(*) FROM {t} WHERE {col}=4").fetchone()[0]
            tot = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}.{col}=4: {n} 行（表总 {tot}）")
        else:
            print(f"  {t}: 无 {col} 列（{c[:6]}...）")
    except Exception as e:
        print(f"  {t}: {e}")

db.close()

# 5. 章节文件路径
print("\n=== 章节文件路径 ===")
from services.script_service import ScriptService
try:
    svc = ScriptService()
    d = svc._get_chapter_dir(999913)
    print("get_chapter_dir:", d, "存在:", os.path.exists(d))
    p = os.path.join(d, "4.txt")
    print("4.txt 存在:", os.path.exists(p))
except Exception as e:
    print("get_chapter_dir 失败:", e)
