from typing import Any, Dict, Optional

from .base_repository import _get_conn, _lock


def add_ebook(
    title: str,
    file_path: str,
    file_size: int,
    word_count: int,
    md5: str,
    fmt: str = "txt",
    encoding: str = "utf-8",
    author: str = "",
    description: str = "",
) -> Optional[int]:
    import time
    conn = _get_conn()
    now = time.time()
    with _lock:
        existing = conn.execute(
            "SELECT id FROM ebook_library WHERE md5=?", (md5,)
        ).fetchone()
        if existing is not None:
            return None
        cur = conn.execute(
            """INSERT INTO ebook_library
               (title, author, file_path, file_size, word_count, md5,
                format, encoding, description, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (title, author, file_path, file_size, word_count, md5,
             fmt, encoding, description, now, now),
        )
        conn.commit()
        return cur.lastrowid


def get_ebook(book_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT * FROM ebook_library WHERE id=?", (book_id,)
        ).fetchone()
    return dict(row) if row else None


def get_ebook_by_md5(md5: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT * FROM ebook_library WHERE md5=?", (md5,)
        ).fetchone()
    return dict(row) if row else None


def get_ebooks_paged(
    page: int = 1,
    page_size: int = 10,
    keyword: Optional[str] = None,
) -> Dict[str, Any]:
    conn = _get_conn()
    with _lock:
        if keyword:
            like = f"%{keyword}%"
            count_row = conn.execute(
                "SELECT COUNT(*) FROM ebook_library WHERE title LIKE ? OR author LIKE ?",
                (like, like),
            ).fetchone()
            rows = conn.execute(
                """SELECT * FROM ebook_library
                   WHERE title LIKE ? OR author LIKE ?
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (like, like, page_size, (page - 1) * page_size),
            ).fetchall()
        else:
            count_row = conn.execute(
                "SELECT COUNT(*) FROM ebook_library"
            ).fetchone()
            rows = conn.execute(
                """SELECT * FROM ebook_library
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (page_size, (page - 1) * page_size),
            ).fetchall()
    total = count_row[0] if count_row else 0
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return {
        "books": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def update_ebook(book_id: int, **fields):
    if not fields:
        return
    import time
    conn = _get_conn()
    now = time.time()
    fields["updated_at"] = now
    set_clause = ", ".join([f"{k}=?" for k in fields])
    params = list(fields.values()) + [book_id]
    with _lock:
        conn.execute(
            f"UPDATE ebook_library SET {set_clause} WHERE id=?", params
        )
        conn.commit()


def delete_ebook(book_id: int) -> bool:
    conn = _get_conn()
    with _lock:
        conn.execute("DELETE FROM ebook_chapters WHERE book_id=?", (book_id,))
        cur = conn.execute("DELETE FROM ebook_library WHERE id=?", (book_id,))
        conn.commit()
    return cur.rowcount > 0