from typing import Any, Dict, List

from .base_repository import _get_conn, _lock


def add_chapter_sentences(book_id: int, chapter_index: int, sentences: List[str]) -> int:
    if not sentences:
        return 0
    import time
    conn = _get_conn()
    now = time.time()
    rows = [
        (book_id, chapter_index, idx, s, len(s), now)
        for idx, s in enumerate(sentences)
    ]
    with _lock:
        conn.execute(
            "DELETE FROM ebook_chapter_sentences WHERE book_id=? AND chapter_index=?",
            (book_id, chapter_index),
        )
        conn.executemany(
            """INSERT INTO ebook_chapter_sentences
               (book_id, chapter_index, sentence_index, content, char_count, created_at)
               VALUES (?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()
    return len(rows)


def get_chapter_sentences(book_id: int, chapter_index: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            """SELECT * FROM ebook_chapter_sentences
               WHERE book_id=? AND chapter_index=? ORDER BY sentence_index ASC""",
            (book_id, chapter_index),
        ).fetchall()
    return [dict(r) for r in rows]


def get_chapter_sentence_count(book_id: int, chapter_index: int) -> int:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT COUNT(*) FROM ebook_chapter_sentences WHERE book_id=? AND chapter_index=?",
            (book_id, chapter_index),
        ).fetchone()
    return row[0] if row else 0