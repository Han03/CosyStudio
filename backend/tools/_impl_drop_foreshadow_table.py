# -*- coding: utf-8 -*-
"""删除 webnovel_foreshadow（整体废弃，方案A）：
- schema.py 建表+索引
- foreshadowing_repository.py 3 个函数
- plan_executor.py 写回路径+import
- webnovel_service.py RAG 源+chunk 函数+import
- project_repository.py 表清单
- repositories/__init__.py 导出
"""
import py_compile

# ── 1. schema.py ──
p = r"C:\MyProjects\CosyStudio\backend\repositories\schema.py"
t = open(p, encoding="utf-8").read()
old = '''        CREATE TABLE IF NOT EXISTS webnovel_foreshadow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            volume_outline_id INTEGER NOT NULL,
            content TEXT DEFAULT '',
            buried_chapter INTEGER DEFAULT 0,
            payoff_chapter INTEGER DEFAULT 0,
            level TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (project_id) REFERENCES webnovel_project(id) ON DELETE CASCADE,
            FOREIGN KEY (volume_outline_id) REFERENCES webnovel_volume_outline(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_webnovel_foreshadow_project ON webnovel_foreshadow(project_id);
        CREATE INDEX IF NOT EXISTS idx_webnovel_foreshadow_volume ON webnovel_foreshadow(volume_outline_id);

'''
assert old in t, "schema 建表未找到"
t = t.replace(old, "", 1)
open(p, "w", encoding="utf-8", newline="\n").write(t)
py_compile.compile(p, doraise=True)
print("[OK] schema.py")

# ── 2. foreshadowing_repository.py ──
p = r"C:\MyProjects\CosyStudio\backend\webnovel\repositories\foreshadowing_repository.py"
t = open(p, encoding="utf-8").read()
old = '''

# ── webnovel_foreshadow 铺垫碎片 ─────────────────────────────────────────────

def add_foreshadow(
    project_id: int,
    volume_outline_id: int,
    content: str,
    buried_chapter: int = 0,
    payoff_chapter: int = 0,
    level: str = ""
) -> Dict:
    """添加铺垫碎片。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO webnovel_foreshadow
            (project_id, volume_outline_id, content, buried_chapter, payoff_chapter, level, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (safe_int(project_id), safe_int(volume_outline_id), safe_str(content),
             safe_int(buried_chapter), safe_int(payoff_chapter), safe_str(level), now, now)
        )
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "project_id": project_id,
            "volume_outline_id": volume_outline_id,
            "content": content,
            "buried_chapter": buried_chapter,
            "payoff_chapter": payoff_chapter,
            "level": level,
            "created_at": now,
            "updated_at": now
        }


def get_foreshadows_by_volume(volume_outline_id: int) -> List[Dict]:
    """获取指定卷纲的铺垫碎片列表。"""
    conn = _get_conn()
    cursor = conn.execute(
        "SELECT * FROM webnovel_foreshadow WHERE volume_outline_id = ? ORDER BY buried_chapter",
        (volume_outline_id,)
    )
    return [dict(row) for row in cursor.fetchall()]


def get_foreshadows_by_project(project_id: int) -> List[Dict]:
    """获取项目的所有铺垫碎片。"""
    conn = _get_conn()
    cursor = conn.execute(
        "SELECT * FROM webnovel_foreshadow WHERE project_id = ? ORDER BY buried_chapter",
        (project_id,)
    )
    return [dict(row) for row in cursor.fetchall()]'''
assert old in t, "repository 函数未找到"
t = t.replace(old, "", 1)
open(p, "w", encoding="utf-8", newline="\n").write(t)
py_compile.compile(p, doraise=True)
print("[OK] foreshadowing_repository.py")

# ── 3. plan_executor.py ──
p = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\plan_executor.py"
t = open(p, encoding="utf-8").read()
old = '''    add_open_loop, add_foreshadow,'''
new = '''    add_open_loop,'''
assert old in t, "plan import 未找到"
t = t.replace(old, new, 1)
old = '''        # 2. 铺垫碎片 → webnovel_foreshadow
        key_foreshadowing_raw = volume_outline.get("key_foreshadowing", "")
        if isinstance(key_foreshadowing_raw, str):
            key_foreshadowing = self._parse_json_field(key_foreshadowing_raw)
            if not key_foreshadowing and key_foreshadowing_raw:
                key_foreshadowing = [key_foreshadowing_raw]
        else:
            key_foreshadowing = key_foreshadowing_raw if isinstance(key_foreshadowing_raw, list) else []

        for item in key_foreshadowing[:5]:
            add_foreshadow(
                project_id=project_id,
                volume_outline_id=vo_id,
                content=item if isinstance(item, str) else str(item),
                buried_chapter=volume_outline.get("chapter_start", 0),
                payoff_chapter=0,
                level="卷级"
            )

        # 3. 开放线索 → webnovel_open_loops'''
new = '''        # 2. 开放线索 → webnovel_open_loops'''
assert old in t, "plan 写回段未找到"
t = t.replace(old, new, 1)
open(p, "w", encoding="utf-8", newline="\n").write(t)
py_compile.compile(p, doraise=True)
print("[OK] plan_executor.py")

# ── 4. webnovel_service.py ──
p = r"C:\MyProjects\CosyStudio\backend\webnovel\services\webnovel_service.py"
t = open(p, encoding="utf-8").read()
old = '''    get_power_system_by_project, get_foreshadows_by_project, get_villains_by_project,'''
new = '''    get_power_system_by_project, get_villains_by_project,'''
assert old in t, "service import 未找到"
t = t.replace(old, new, 1)

old = '''            # 6. 伏笔
            foreshadows = get_foreshadows_by_project(project_id)
            for fs in foreshadows:
                planted = fs.get('buried_chapter', 0) or 0
                _collect_one("foreshadow", _build_foreshadow_chunk_text(fs), chapter_number=planted,
                           metadata=json.dumps({"source": "foreshadow", "foreshadow_id": fs.get("id")}))

'''
assert old in t, "RAG 伏笔源未找到"
t = t.replace(old, "", 1)

old = '''def _build_foreshadow_chunk_text(fs: dict) -> str:
    """将伏笔格式化为自然描述的 RAG 索引文本。"""
    if not fs:
        return ""
    content = str(fs.get('content', '') or '').strip()
    if not content:
        return ""
    parts = [f"作品埋入了一条伏笔：{content}"]
    planted = fs.get('buried_chapter', 0)
    payoff = fs.get('payoff_chapter', 0)
    if planted:
        parts.append(f"该伏笔埋入第{planted}章")
    if payoff:
        parts.append(f"预计在第{payoff}章回收")
    level = str(fs.get('level', '') or '').strip()
    if level:
        parts.append(f"伏笔级别为{level}")
    return "，".join(parts) + "。"


'''
assert old in t, "chunk 函数未找到"
t = t.replace(old, "", 1)
open(p, "w", encoding="utf-8", newline="\n").write(t)
py_compile.compile(p, doraise=True)
print("[OK] webnovel_service.py")

# ── 5. project_repository.py ──
p = r"C:\MyProjects\CosyStudio\backend\webnovel\repositories\project_repository.py"
t = open(p, encoding="utf-8").read()
old = '''            "webnovel_timeline",
            "webnovel_foreshadow",
            "webnovel_volume_outline",'''
new = '''            "webnovel_timeline",
            "webnovel_volume_outline",'''
assert old in t, "表清单未找到"
t = t.replace(old, new, 1)
open(p, "w", encoding="utf-8", newline="\n").write(t)
py_compile.compile(p, doraise=True)
print("[OK] project_repository.py")

# ── 6. repositories/__init__.py ──
p = r"C:\MyProjects\CosyStudio\backend\webnovel\repositories\__init__.py"
t = open(p, encoding="utf-8").read()
old = '''    add_foreshadow, get_foreshadows_by_volume, get_foreshadows_by_project
)'''
new = ''')'''
assert old in t, "__init__ 导出未找到"
t = t.replace(old, new, 1)
open(p, "w", encoding="utf-8", newline="\n").write(t)
py_compile.compile(p, doraise=True)
print("[OK] repositories/__init__.py")
print("全部完成")
