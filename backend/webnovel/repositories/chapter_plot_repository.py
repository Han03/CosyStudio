"""webnovel_chapter_plot 数据访问层。

存储每章创作前由 LLM 生成的详细剧情列表（场景级细粒度），
供草稿生成器作为核心输入使用。

表结构采用一对多行级存储：每个剧情点独立一行，
通过 (project_id, chapter_index) 关联，plot_order 排序。
"""

import time
from typing import Optional, List, Dict
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_chapter_plot(project_id: int, chapter_index: int, plot_list: list = None) -> dict:
    """添加章节剧情列表。先删除旧数据，再逐条插入每个剧情点。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        # 先删除该章节的旧剧情
        conn.execute(
            "DELETE FROM webnovel_chapter_plot WHERE project_id = ? AND chapter_index = ?",
            (safe_int(project_id), safe_int(chapter_index))
        )
        # 逐条插入
        for order, plot in enumerate(plot_list or []):
            if not isinstance(plot, dict):
                continue
            chars = plot.get("characters", [])
            chars_str = ",".join(chars) if isinstance(chars, list) else str(chars)
            conn.execute(
                """INSERT INTO webnovel_chapter_plot
                    (project_id, chapter_index, plot_order, scene, description, characters, emotion, conflict, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (safe_int(project_id), safe_int(chapter_index), order,
                 safe_str(plot.get("scene", "")),
                 safe_str(plot.get("description", "")),
                 chars_str,
                 safe_str(plot.get("emotion", "")),
                 safe_str(plot.get("conflict", "")),
                 now)
            )
        conn.commit()
        return {"project_id": project_id, "chapter_index": chapter_index, "plot_count": len(plot_list or [])}


def get_chapter_plot(project_id: int, chapter_index: int) -> Optional[dict]:
    """获取指定章节的剧情列表。

    返回格式：{"project_id": ..., "chapter_index": ..., "plot_list": [{...}, ...]}
    其中 plot_list 为按 plot_order 排序的剧情点列表，每个剧情点为 dict。
    """
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """SELECT plot_order, scene, description, characters, emotion, conflict
               FROM webnovel_chapter_plot
               WHERE project_id = ? AND chapter_index = ?
               ORDER BY plot_order""",
            (project_id, chapter_index)
        )
        rows = cursor.fetchall()
        if not rows:
            return None
        plot_list = []
        for row in rows:
            chars_raw = row["characters"] if row["characters"] else ""
            chars_list = [c.strip() for c in chars_raw.split(",") if c.strip()] if chars_raw else []
            plot_list.append({
                "scene": row["scene"] or "",
                "description": row["description"] or "",
                "characters": chars_list,
                "emotion": row["emotion"] or "",
                "conflict": row["conflict"] or "",
            })
        return {
            "project_id": project_id,
            "chapter_index": chapter_index,
            "plot_list": plot_list,
        }


def get_chapter_plots_by_project(project_id: int) -> List[dict]:
    """获取项目下所有章节的剧情列表，按 chapter_index 和 plot_order 排序。

    返回格式：[{"chapter_index": N, "plot_list": [{...}, ...]}, ...]
    """
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            """SELECT chapter_index, plot_order, scene, description, characters, emotion, conflict
               FROM webnovel_chapter_plot
               WHERE project_id = ?
               ORDER BY chapter_index, plot_order""",
            (project_id,)
        )
        rows = cursor.fetchall()
        # 按 chapter_index 分组
        chapters: Dict[int, list] = {}
        for row in rows:
            ch = row["chapter_index"]
            if ch not in chapters:
                chapters[ch] = []
            chars_raw = row["characters"] if row["characters"] else ""
            chars_list = [c.strip() for c in chars_raw.split(",") if c.strip()] if chars_raw else []
            chapters[ch].append({
                "scene": row["scene"] or "",
                "description": row["description"] or "",
                "characters": chars_list,
                "emotion": row["emotion"] or "",
                "conflict": row["conflict"] or "",
            })
        return [
            {"chapter_index": ch, "plot_list": plots}
            for ch, plots in chapters.items()
        ]


def delete_chapter_plot(project_id: int, chapter_index: int) -> bool:
    """删除指定章节的所有剧情行。"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "DELETE FROM webnovel_chapter_plot WHERE project_id = ? AND chapter_index = ?",
            (project_id, chapter_index)
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_chapter_plots_by_project(project_id: int) -> None:
    """删除项目下所有章节的剧情数据。"""
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM webnovel_chapter_plot WHERE project_id = ?", (project_id,))
        conn.commit()
