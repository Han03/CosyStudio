from typing import Any, Dict, List, Optional

from .base_repository import _get_conn, _lock


def add_script_chapters(script_id: int, chapters: List[Dict[str, Any]]) -> int:
    if not chapters:
        return 0
    import time
    conn = _get_conn()
    now = time.time()
    rows = [
        (script_id, c.get("chapter_index", 0), c.get("title", ""),
         c.get("file_path", ""), c.get("word_count", 0), now)
        for c in chapters
    ]
    with _lock:
        conn.executemany(
            """INSERT INTO script_chapters
               (script_id, chapter_index, title, file_path, word_count, created_at)
               VALUES (?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()
    return len(rows)


def get_script_chapters_all(script_id: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            """SELECT * FROM script_chapters
               WHERE script_id=? ORDER BY chapter_index ASC""",
            (script_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_script_chapter(script_id: int, chapter_index: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            """SELECT * FROM script_chapters
               WHERE script_id=? AND chapter_index=?""",
            (script_id, chapter_index),
        ).fetchone()
    return dict(row) if row else None


def get_script_chapter_count(script_id: int) -> int:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT COUNT(*) FROM script_chapters WHERE script_id=?", (script_id,)
        ).fetchone()
    return row[0] if row else 0


def update_script_chapter(script_id: int, chapter_index: int, **fields) -> bool:
    allowed = {"title", "file_path", "word_count"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    conn = _get_conn()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    params = list(updates.values()) + [script_id, chapter_index]
    with _lock:
        cur = conn.execute(
            f"UPDATE script_chapters SET {set_clause} WHERE script_id=? AND chapter_index=?",
            params,
        )
        conn.commit()
    return cur.rowcount > 0


def delete_script_chapter(script_id: int, chapter_index: int) -> bool:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "DELETE FROM script_chapters WHERE script_id=? AND chapter_index=?",
            (script_id, chapter_index),
        )
        conn.commit()
    return cur.rowcount > 0


def get_max_chapter_index(script_id: int) -> int:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT MAX(chapter_index) FROM script_chapters WHERE script_id=?",
            (script_id,),
        ).fetchone()
    return row[0] if row and row[0] is not None else 0