from typing import Any, Dict, List, Optional

from .base_repository import _get_conn, _lock


def add_chapters(book_id: int, chapters: List[Dict[str, Any]]) -> int:
    if not chapters:
        return 0
    import time
    conn = _get_conn()
    now = time.time()
    rows = [
        (book_id, c.get("chapter_index", 0), c.get("title", ""),
         c.get("start_pos", 0), c.get("end_pos", 0),
         c.get("content", ""), c.get("word_count", 0), now)
        for c in chapters
    ]
    with _lock:
        conn.executemany(
            """INSERT INTO ebook_chapters
               (book_id, chapter_index, title, start_pos, end_pos, content, word_count, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()
    return len(rows)


def get_chapters(book_id: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            """SELECT * FROM ebook_chapters
               WHERE book_id=? ORDER BY chapter_index ASC""",
            (book_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_chapter(book_id: int, chapter_index: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            """SELECT * FROM ebook_chapters
               WHERE book_id=? AND chapter_index=?""",
            (book_id, chapter_index),
        ).fetchone()
    return dict(row) if row else None


def get_chapter_count(book_id: int) -> int:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT COUNT(*) FROM ebook_chapters WHERE book_id=?", (book_id,)
        ).fetchone()
    return row[0] if row else 0