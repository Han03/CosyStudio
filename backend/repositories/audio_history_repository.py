from typing import Any, Dict, List, Optional

from .base_repository import _get_conn, _lock


def save_audio_history(line_id: int, content: str, role: str, tone: str, instruction: str, agent_id: str, seed: int, audio_path: str, tts_capability_id: str = '',
                        audio_volume: float = 1.0, audio_pitch: int = 0, fade_in: float = 0.0, fade_out: float = 0.0,
                        audio_adjust_enabled: int = 0, range_start: float = 0.0, range_end: float = 0.0):
    import time
    conn = _get_conn()
    with _lock:
        conn.execute(
            """INSERT INTO script_line_audio_history 
               (line_id, content, role, tone, instruction, agent_id, tts_capability_id, seed, audio_path,
                audio_volume, audio_pitch, fade_in, fade_out, audio_adjust_enabled, range_start, range_end,
                created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (line_id, content, role, tone, instruction, agent_id, tts_capability_id, seed, audio_path,
             audio_volume, audio_pitch, fade_in, fade_out, audio_adjust_enabled, range_start, range_end,
             time.time())
        )
        conn.commit()


def get_audio_history_by_line_id(line_id: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            """SELECT * FROM script_line_audio_history 
               WHERE line_id=? ORDER BY created_at DESC""",
            (line_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_matching_audio_history(line_id: int, content: str, role: str, tone: str, instruction: str, agent_id: str, seed: int, tts_capability_id: str = '') -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            """SELECT * FROM script_line_audio_history 
               WHERE line_id=? AND content=? AND role=? AND tone=? AND instruction=? AND agent_id=? AND tts_capability_id=? AND seed=?
               ORDER BY created_at DESC LIMIT 1""",
            (line_id, content, role, tone, instruction, agent_id, tts_capability_id, seed)
        ).fetchone()
    return dict(row) if row else None


def get_audio_history_by_id(history_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT * FROM script_line_audio_history WHERE id=?", (history_id,)
        ).fetchone()
    return dict(row) if row else None


def save_chapter_audio_history(script_id: int, chapter_index: int, chapter_title: str,
                                audio_path: str, srt_path: str, duration: float,
                                line_count: int, generated_count: int, file_size: int) -> int:
    import time
    conn = _get_conn()
    with _lock:
        cursor = conn.execute(
            """INSERT INTO chapter_audio_history
               (script_id, chapter_index, chapter_title, audio_path, srt_path,
                duration, line_count, generated_count, file_size, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (script_id, chapter_index, chapter_title, audio_path, srt_path,
             duration, line_count, generated_count, file_size, time.time())
        )
        conn.commit()
        return cursor.lastrowid


def get_chapter_audio_history(script_id: int, chapter_index: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            """SELECT * FROM chapter_audio_history
               WHERE script_id=? AND chapter_index=?
               ORDER BY created_at DESC""",
            (script_id, chapter_index)
        ).fetchall()
    return [dict(r) for r in rows]


def get_chapter_audio_history_by_id(history_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT * FROM chapter_audio_history WHERE id=?", (history_id,)
        ).fetchone()
    return dict(row) if row else None


def update_matching_audio_history_params(line_id: int, content: str, role: str, tone: str,
                                         instruction: str, agent_id: str, seed: int,
                                         tts_capability_id: str,
                                         audio_volume: float, audio_pitch: int,
                                         fade_in: float, fade_out: float, audio_adjust_enabled: int,
                                         range_start: float, range_end: float):
    """更新当前匹配的音频历史记录的调整参数。

    使用与 get_matching_audio_history 相同的 8 字段条件定位记录，
    确保保存的参数写入前端正在使用的那条历史记录。
    """
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            """SELECT id FROM script_line_audio_history 
               WHERE line_id=? AND content=? AND role=? AND tone=? 
                     AND instruction=? AND agent_id=? AND tts_capability_id=? AND seed=?
               ORDER BY created_at DESC LIMIT 1""",
            (line_id, content, role, tone, instruction, agent_id, tts_capability_id, seed)
        ).fetchone()
        if row:
            conn.execute(
                """UPDATE script_line_audio_history 
                   SET audio_volume=?, audio_pitch=?, fade_in=?, fade_out=?,
                       audio_adjust_enabled=?, range_start=?, range_end=?
                   WHERE id=?""",
                (audio_volume, audio_pitch, fade_in, fade_out, audio_adjust_enabled,
                 range_start, range_end, row['id'])
            )
            conn.commit()