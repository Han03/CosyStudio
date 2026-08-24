import json
from typing import Any, Dict, List, Optional

from .base_repository import _get_conn, _lock, _loads


def upsert_interface(
    site_domain: str,
    name: str,
    iface_type: str,
    url: str,
    method: str = "GET",
    content_type: str = "application/json",
    input_params: Optional[Dict[str, Any]] = None,
    output_params: Optional[Dict[str, Any]] = None,
) -> int:
    import time
    conn = _get_conn()
    now = time.time()
    inp = json.dumps(input_params, ensure_ascii=False) if input_params else ""
    outp = json.dumps(output_params, ensure_ascii=False) if output_params else ""
    with _lock:
        row = conn.execute(
            "SELECT id FROM ebook_interfaces WHERE site_domain=? AND url=? AND type=?",
            (site_domain, url, iface_type),
        ).fetchone()
        if row is None:
            cur = conn.execute(
                """INSERT INTO ebook_interfaces
                   (site_domain, name, type, url, method, content_type,
                    input_params, output_params, is_active, status, verified_at,
                    last_error, added_at)
                   VALUES (?,?,?,?,?,?,?, ?, 1,'untested',NULL,?,?)""",
                (site_domain, name, iface_type, url, method, content_type,
                 inp, outp, "", now),
            )
            conn.commit()
            return cur.lastrowid
        else:
            conn.execute(
                """UPDATE ebook_interfaces
                   SET name=?, method=?, content_type=?, input_params=?, output_params=?
                   WHERE id=?""",
                (name, method, content_type, inp, outp, row["id"]),
            )
            conn.commit()
            return row["id"]


def get_interfaces(
    iface_type: Optional[str] = None,
    status: Optional[str] = None,
    active_only: bool = False,
) -> List[Dict[str, Any]]:
    conn = _get_conn()
    sql = "SELECT * FROM ebook_interfaces WHERE 1=1"
    params: List[Any] = []
    if iface_type:
        sql += " AND type=?"
        params.append(iface_type)
    if status:
        sql += " AND status=?"
        params.append(status)
    if active_only:
        sql += " AND is_active=1"
    sql += " ORDER BY added_at DESC"
    with _lock:
        rows = conn.execute(sql, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["input_params"] = _loads(d.get("input_params"))
        d["output_params"] = _loads(d.get("output_params"))
        results.append(d)
    return results


def get_interface(iface_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        row = conn.execute("SELECT * FROM ebook_interfaces WHERE id=?", (iface_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["input_params"] = _loads(d.get("input_params"))
    d["output_params"] = _loads(d.get("output_params"))
    return d


def update_interface_status(iface_id: int, status: str, last_error: str = ""):
    import time
    conn = _get_conn()
    now = time.time()
    with _lock:
        conn.execute(
            "UPDATE ebook_interfaces SET status=?, verified_at=?, last_error=? WHERE id=?",
            (status, now, last_error, iface_id),
        )
        conn.commit()


def set_interface_active(iface_id: int, is_active: bool):
    conn = _get_conn()
    with _lock:
        conn.execute(
            "UPDATE ebook_interfaces SET is_active=? WHERE id=?",
            (1 if is_active else 0, iface_id),
        )
        conn.commit()


def delete_interface(iface_id: int) -> bool:
    conn = _get_conn()
    with _lock:
        cur = conn.execute("DELETE FROM ebook_interfaces WHERE id=?", (iface_id,))
        conn.commit()
    return cur.rowcount > 0


def get_interfaces_by_site(site_domain: str) -> List[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            "SELECT * FROM ebook_interfaces WHERE site_domain=? ORDER BY type, added_at DESC",
            (site_domain,),
        ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["input_params"] = _loads(d.get("input_params"))
        d["output_params"] = _loads(d.get("output_params"))
        results.append(d)
    return results