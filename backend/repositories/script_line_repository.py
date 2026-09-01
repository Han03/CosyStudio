from typing import Any, Dict, List, Optional

from .base_repository import _get_conn, _lock


def add_script_lines(script_id: int, lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not lines:
        return []
    import time
    conn = _get_conn()
    now = time.time()

    with _lock:
        chapter_index = lines[0].get("chapter_index", 0)

        tail = conn.execute(
            "SELECT id FROM script_lines WHERE script_id=? AND chapter_index=? "
            "AND next_id IS NULL ORDER BY id DESC LIMIT 1",
            (script_id, chapter_index),
        ).fetchone()
        tail_id = tail[0] if tail else None

        cursor = conn.cursor()
        inserted_lines = []
        for idx, l in enumerate(lines):
            prev_id = tail_id if idx == 0 else (inserted_lines[-1]['id'] if inserted_lines else None)

            cursor.execute(
                """INSERT INTO script_lines
                   (script_id, chapter_index, line_no, role, instruction, content, seed, type, prev_id, next_id, created_at, tone)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (script_id, l.get("chapter_index", 0), l.get("line_no", 0),
                 l.get("role", ""), l.get("instruction", ""), l.get("content", ""),
                 l.get("seed", 0), l.get("type", "narration"), prev_id, None, now, l.get("tone", "")),
            )
            new_id = cursor.lastrowid

            inserted_lines.append({
                'id': new_id,
                'chapter_index': l.get("chapter_index", 0),
                'line_no': l.get("line_no", 0),
                'role': l.get("role", ""),
                'instruction': l.get("instruction", ""),
                'content': l.get("content", ""),
                'seed': l.get("seed", 0),
                'type': l.get("type", "narration"),
                'prev_id': prev_id,
                'next_id': None,
            })

        for i in range(len(inserted_lines)):
            if i > 0:
                inserted_lines[i]['prev_id'] = inserted_lines[i-1]['id']
                conn.execute(
                    "UPDATE script_lines SET prev_id=? WHERE id=? AND script_id=?",
                    (inserted_lines[i-1]['id'], inserted_lines[i]['id'], script_id),
                )
            if i < len(inserted_lines) - 1:
                inserted_lines[i]['next_id'] = inserted_lines[i+1]['id']
                conn.execute(
                    "UPDATE script_lines SET next_id=? WHERE id=? AND script_id=?",
                    (inserted_lines[i+1]['id'], inserted_lines[i]['id'], script_id),
                )

        if tail_id:
            conn.execute(
                "UPDATE script_lines SET next_id=? WHERE id=? AND script_id=?",
                (inserted_lines[0]['id'], tail_id, script_id),
            )

        role_counts = {}
        for line in lines:
            role = line.get("role", "旁白")
            role_counts[role] = role_counts.get(role, 0) + 1
        for role, count in role_counts.items():
            conn.execute(
                "UPDATE script_characters SET line_count = line_count + ? WHERE script_id=? AND role=?",
                (count, script_id, role),
            )

        conn.commit()
        return inserted_lines


def insert_line_at_position(script_id: int, chapter_index: int, role: str,
                             instruction: str, content: str,
                             insert_after_id: Optional[int] = None,
                             insert_before_id: Optional[int] = None) -> Optional[dict]:
    import time
    conn = _get_conn()
    now = time.time()

    with _lock:
        max_no = conn.execute(
            "SELECT MAX(line_no) FROM script_lines WHERE script_id=? AND chapter_index=?",
            (script_id, chapter_index),
        ).fetchone()[0] or 0
        line_no = max_no + 1

        prev_id = None
        next_id = None

        if insert_after_id:
            row = conn.execute(
                "SELECT next_id FROM script_lines WHERE id=? AND script_id=?",
                (insert_after_id, script_id),
            ).fetchone()
            if row:
                prev_id = insert_after_id
                next_id = row[0]
                if next_id is not None:
                    nx = conn.execute(
                        "SELECT id FROM script_lines WHERE id=? AND script_id=?",
                        (next_id, script_id),
                    ).fetchone()
                    if not nx:
                        next_id = None
        elif insert_before_id:
            row = conn.execute(
                "SELECT prev_id FROM script_lines WHERE id=? AND script_id=?",
                (insert_before_id, script_id),
            ).fetchone()
            if row:
                next_id = insert_before_id
                prev_id = row[0]
                if prev_id is not None:
                    pv = conn.execute(
                        "SELECT id FROM script_lines WHERE id=? AND script_id=?",
                        (prev_id, script_id),
                    ).fetchone()
                    if not pv:
                        prev_id = None
        else:
            tail = conn.execute(
                "SELECT id FROM script_lines WHERE script_id=? AND chapter_index=? "
                "AND next_id IS NULL ORDER BY id DESC LIMIT 1",
                (script_id, chapter_index),
            ).fetchone()
            if tail:
                prev_id = tail[0]

        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO script_lines
               (script_id, chapter_index, line_no, role, instruction, content, type, prev_id, next_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (script_id, chapter_index, line_no, role, instruction, content, "narration", prev_id, next_id, now),
        )
        new_id = cursor.lastrowid

        if prev_id:
            conn.execute(
                "UPDATE script_lines SET next_id=? WHERE id=? AND script_id=?",
                (new_id, prev_id, script_id),
            )
        if next_id:
            conn.execute(
                "UPDATE script_lines SET prev_id=? WHERE id=? AND script_id=?",
                (new_id, next_id, script_id),
            )

        conn.commit()
        return {
            'id': new_id,
            'chapter_index': chapter_index,
            'line_no': line_no,
            'role': role,
            'instruction': instruction,
            'content': content,
            'type': 'narration',
            'prev_id': prev_id,
            'next_id': next_id,
        }


def reorder_script_lines(script_id: int, chapter_index: int, line_id: int, target_prev_id: int, target_next_id: int) -> bool:
    conn = _get_conn()
    with _lock:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT prev_id, next_id FROM script_lines WHERE id=? AND script_id=?",
            (line_id, script_id),
        )
        row = cursor.fetchone()
        if not row:
            return False
        old_prev_id, old_next_id = row

        if old_prev_id:
            cursor.execute(
                "UPDATE script_lines SET next_id=? WHERE id=? AND script_id=?",
                (old_next_id, old_prev_id, script_id),
            )

        if old_next_id:
            cursor.execute(
                "UPDATE script_lines SET prev_id=? WHERE id=? AND script_id=?",
                (old_prev_id, old_next_id, script_id),
            )

        cursor.execute(
            "UPDATE script_lines SET prev_id=?, next_id=? WHERE id=? AND script_id=?",
            (target_prev_id, target_next_id, line_id, script_id),
        )

        if target_prev_id:
            cursor.execute(
                "UPDATE script_lines SET next_id=? WHERE id=? AND script_id=?",
                (line_id, target_prev_id, script_id),
            )

        if target_next_id:
            cursor.execute(
                "UPDATE script_lines SET prev_id=? WHERE id=? AND script_id=?",
                (line_id, target_next_id, script_id),
            )

        conn.commit()
        return True


def get_script_lines(script_id: int,
                     chapter_index: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        if chapter_index is not None:
            rows = conn.execute(
                """SELECT sl.id, sl.script_id, sl.chapter_index, sl.line_no, sl.role,
                          sl.instruction, sl.content, sl.seed, sl.created_at, sl.type,
                          sl.prev_id, sl.next_id, sl.tone
                   FROM script_lines sl
                   WHERE sl.script_id=? AND sl.chapter_index=?""",
                (script_id, chapter_index),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT sl.id, sl.script_id, sl.chapter_index, sl.line_no, sl.role,
                          sl.instruction, sl.content, sl.seed, sl.created_at, sl.type,
                          sl.prev_id, sl.next_id, sl.tone
                   FROM script_lines sl
                   WHERE sl.script_id=?""",
                (script_id,),
            ).fetchall()
    
    lines = [dict(r) for r in rows]

    if chapter_index is not None:
        lines = [l for l in lines if l['chapter_index'] == chapter_index]

    if not lines:
        return []

    line_map = {l['id']: l for l in lines if l['id'] is not None}
    if not line_map:
        return lines

    traversed = set()
    result = []

    while len(traversed) < len(line_map):
        head = None
        for l in lines:
            lid = l['id']
            if lid is None or lid in traversed:
                continue
            pid = l['prev_id']
            if pid is None or pid not in line_map or pid in traversed:
                head = lid
                break
        if head is None:
            for l in lines:
                lid = l['id']
                if lid is not None and lid not in traversed:
                    head = lid
                    break
        if head is None:
            break

        current = head
        while current is not None and current not in traversed:
            if current not in line_map:
                break
            traversed.add(current)
            result.append(line_map[current])
            current = line_map[current]['next_id']

    for l in lines:
        if l['id'] is None:
            result.append(l)

    return result


def get_script_lines_paged(
    script_id: int,
    page: int = 1,
    page_size: int = 50,
    chapter_index: Optional[int] = None,
) -> Dict[str, Any]:
    _sl_select = """SELECT sl.id, sl.script_id, sl.chapter_index, sl.line_no, sl.role,
                           sl.instruction, sl.content, sl.seed, sl.created_at, sl.type,
                           sl.prev_id, sl.next_id, sl.tone"""
    conn = _get_conn()
    with _lock:
        if chapter_index is not None:
            count_row = conn.execute(
                "SELECT COUNT(*) FROM script_lines WHERE script_id=? AND chapter_index=?",
                (script_id, chapter_index),
            ).fetchone()
            rows = conn.execute(
                f"""{_sl_select} FROM script_lines sl
                    WHERE sl.script_id=? AND sl.chapter_index=?
                    ORDER BY sl.line_no ASC LIMIT ? OFFSET ?""",
                (script_id, chapter_index, page_size, (page - 1) * page_size),
            ).fetchall()
        else:
            count_row = conn.execute(
                "SELECT COUNT(*) FROM script_lines WHERE script_id=?",
                (script_id,),
            ).fetchone()
            rows = conn.execute(
                f"""{_sl_select} FROM script_lines sl
                    WHERE sl.script_id=?
                    ORDER BY sl.chapter_index ASC, sl.line_no ASC LIMIT ? OFFSET ?""",
                (script_id, page_size, (page - 1) * page_size),
            ).fetchall()
    total = count_row[0] if count_row else 0
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return {
        "lines": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def update_script_line(line_id: int, **fields):
    if not fields:
        return
    import time
    conn = _get_conn()
    with _lock:
        if "role" in fields:
            row = conn.execute(
                "SELECT script_id, role FROM script_lines WHERE id=?", (line_id,)
            ).fetchone()
            if row:
                script_id, old_role = row[0], row[1]
                new_role = fields["role"]
                if old_role != new_role:
                    if old_role:
                        conn.execute(
                            "UPDATE script_characters SET line_count = MAX(line_count - 1, 0) WHERE script_id=? AND role=?",
                            (script_id, old_role),
                        )
                    if new_role:
                        existing = conn.execute(
                            "SELECT id FROM script_characters WHERE script_id=? AND role=?",
                            (script_id, new_role),
                        ).fetchone()
                        if not existing:
                            conn.execute(
                                """INSERT INTO script_characters (script_id, role, line_count, created_at)
                                   VALUES (?, ?, 1, ?)""",
                                (script_id, new_role, time.time()),
                            )
                        else:
                            conn.execute(
                                "UPDATE script_characters SET line_count = line_count + 1 WHERE script_id=? AND role=?",
                                (script_id, new_role),
                            )
        set_clause = ", ".join([f"{k}=?" for k in fields])
        params = list(fields.values()) + [line_id]
        conn.execute(
            f"UPDATE script_lines SET {set_clause} WHERE id=?", params
        )
        conn.commit()


def delete_script_line(line_id: int) -> bool:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT prev_id, next_id, script_id, role FROM script_lines WHERE id=?", (line_id,)
        ).fetchone()
        if not row:
            return False
        prev_id, next_id, script_id, role = row

        if prev_id:
            conn.execute("UPDATE script_lines SET next_id=? WHERE id=?", (next_id, prev_id))
        if next_id:
            conn.execute("UPDATE script_lines SET prev_id=? WHERE id=?", (prev_id, next_id))

        conn.execute("DELETE FROM script_lines WHERE id=?", (line_id,))

        conn.execute(
            "UPDATE script_characters SET line_count = line_count - 1 WHERE script_id=? AND role=?",
            (script_id, role),
        )

        conn.commit()
        return True


def delete_script_lines_by_chapter(script_id: int, chapter_index: int) -> int:
    conn = _get_conn()
    with _lock:
        # 先统计该章节各角色的台词数，用于回退角色表的 line_count
        rows = conn.execute(
            "SELECT role, COUNT(*) as cnt FROM script_lines "
            "WHERE script_id=? AND chapter_index=? GROUP BY role",
            (script_id, chapter_index),
        ).fetchall()
        role_counts = {r[0] or "旁白": r[1] for r in rows}

        cur = conn.execute(
            "DELETE FROM script_lines WHERE script_id=? AND chapter_index=?",
            (script_id, chapter_index),
        )

        # 回退角色的 line_count
        for role, count in role_counts.items():
            conn.execute(
                "UPDATE script_characters SET line_count = MAX(line_count - ?, 0) "
                "WHERE script_id=? AND role=?",
                (count, script_id, role),
            )

        conn.commit()
    return cur.rowcount


def delete_script_lines(script_id: int) -> int:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "DELETE FROM script_lines WHERE script_id=?",
            (script_id,),
        )
        conn.commit()
    return cur.rowcount


def get_script_line_by_id(line_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            """SELECT sl.id, sl.script_id, sl.chapter_index, sl.line_no, sl.role,
                      sl.instruction, sl.content, sl.seed, sl.created_at, sl.type,
                      sl.prev_id, sl.next_id, sl.tone
               FROM script_lines sl
               WHERE sl.id=?""",
            (line_id,)
        ).fetchone()
    return dict(row) if row else None


def get_script_line_count(script_id: int) -> int:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT COUNT(*) FROM script_lines WHERE script_id=?", (script_id,)
        ).fetchone()
    return row[0] if row else 0


def get_script_chapters_with_lines(script_id: int) -> List[int]:
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            "SELECT DISTINCT chapter_index FROM script_lines WHERE script_id=? ORDER BY chapter_index",
            (script_id,),
        ).fetchall()
    return [r[0] for r in rows]


def get_lines_by_role(script_id: int, role: str, limit: int = 5) -> List[Dict[str, Any]]:
    """按角色名查询台词样本（用于角色属性提取）。"""
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            """SELECT id, role, content, instruction, type, chapter_index, line_no
               FROM script_lines
               WHERE script_id=? AND role=?
               ORDER BY chapter_index, line_no
               LIMIT ?""",
            (script_id, role, limit),
        ).fetchall()
    return [dict(r) for r in rows]