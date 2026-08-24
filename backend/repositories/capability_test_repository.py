from typing import Any, Dict, List, Optional

from .base_repository import _get_conn, _lock


def add_capability_test(
    capability_type: str,
    capability_id: str,
    platform_code: str,
    model_code: str,
    input_data: str,
    output_data: str = "",
    status: str = "success",
    error_message: str = "",
    duration: float = 0.0,
) -> int:
    import time
    conn = _get_conn()
    now = time.time()
    with _lock:
        cur = conn.execute(
            """INSERT INTO capability_test_history
               (capability_type, capability_id, platform_code, model_code,
                input_data, output_data, status, error_message, duration, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (capability_type, capability_id, platform_code, model_code,
             input_data, output_data, status, error_message, duration, now),
        )
        conn.commit()
        return cur.lastrowid


def get_capability_tests_paged(
    capability_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    conn = _get_conn()
    with _lock:
        if capability_type:
            count_row = conn.execute(
                "SELECT COUNT(*) FROM capability_test_history WHERE capability_type=?",
                (capability_type,),
            ).fetchone()
            rows = conn.execute(
                """SELECT * FROM capability_test_history
                   WHERE capability_type=?
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (capability_type, page_size, (page - 1) * page_size),
            ).fetchall()
        else:
            count_row = conn.execute(
                "SELECT COUNT(*) FROM capability_test_history"
            ).fetchone()
            rows = conn.execute(
                """SELECT * FROM capability_test_history
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (page_size, (page - 1) * page_size),
            ).fetchall()
    total = count_row[0] if count_row else 0
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return {
        "records": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def get_capability_test(test_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT * FROM capability_test_history WHERE id=?",
            (test_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_capability_test(test_id: int) -> bool:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "DELETE FROM capability_test_history WHERE id=?",
            (test_id,),
        )
        conn.commit()
    return cur.rowcount > 0


def delete_all_capability_tests() -> int:
    conn = _get_conn()
    with _lock:
        cur = conn.execute("DELETE FROM capability_test_history")
        conn.commit()
    return cur.rowcount