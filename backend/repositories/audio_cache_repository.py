from typing import Any, Dict, Optional

from .base_repository import _get_conn, _lock, _content_hash


def get_audio_cache(content: str, agent_id: str, seed: int = 0,
                    instruction: str = "", speed: float = 1.0) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    chash = _content_hash(content)
    with _lock:
        row = conn.execute(
            """SELECT * FROM ebook_sentence_audio_cache
               WHERE content_hash=? AND agent_id=? AND seed=?
                 AND instruction=? AND speed=?
               ORDER BY id DESC LIMIT 1""",
            (chash, agent_id, seed, instruction, speed),
        ).fetchone()
    return dict(row) if row else None


def save_audio_cache(content: str, agent_id: str, seed: int,
                     instruction: str, speed: float,
                     audio_path: str, duration: float, file_size: int) -> int:
    import time
    conn = _get_conn()
    chash = _content_hash(content)
    now = time.time()
    with _lock:
        existing = conn.execute(
            "SELECT id FROM ebook_sentence_audio_cache WHERE content_hash=? AND agent_id=? AND seed=? AND instruction=? AND speed=?",
            (chash, agent_id, seed, instruction, speed),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE ebook_sentence_audio_cache
                   SET audio_path=?, duration=?, file_size=?, created_at=?
                   WHERE id=?""",
                (audio_path, duration, file_size, now, existing["id"]),
            )
            conn.commit()
            return existing["id"]
        cur = conn.execute(
            """INSERT INTO ebook_sentence_audio_cache
               (content_hash, agent_id, seed, instruction, speed,
                audio_path, duration, file_size, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (chash, agent_id, seed, instruction, speed,
             audio_path, duration, file_size, now),
        )
        conn.commit()
        return cur.lastrowid