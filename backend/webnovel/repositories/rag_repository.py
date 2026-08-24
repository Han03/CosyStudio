"""webnovel_rag_chunks 数据访问层。

提供项目级别的语义检索能力，用于存储章节摘要、设定片段、事实记录等，
并通过 embedding 余弦相似度进行检索。
"""

import json
import time
from typing import Optional, List, Dict, Any
from repositories.base_repository import _get_conn, _lock, safe_str, safe_int


def add_rag_chunk(
    project_id: int,
    content: str,
    chunk_type: str = "chapter",
    chapter_number: int = 0,
    metadata: str = ""
) -> Dict:
    """添加 RAG 片段（不含 embedding，由上层计算后调用 update_rag_embedding 写入）。"""
    with _lock:
        conn = _get_conn()
        now = time.time()
        cursor = conn.execute(
            """INSERT INTO webnovel_rag_chunks
               (project_id, chunk_type, chapter_number, content, embedding, metadata, created_at)
               VALUES (?, ?, ?, ?, '', ?, ?)""",
            (safe_int(project_id), safe_str(chunk_type),
             safe_int(chapter_number), safe_str(content),
             safe_str(metadata), now)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "project_id": project_id, "content": content}


def update_rag_embedding(chunk_id: int, embedding: List[float]) -> bool:
    """更新 RAG 片段的 embedding 向量（JSON 格式存储）。"""
    with _lock:
        conn = _get_conn()
        conn.execute(
            "UPDATE webnovel_rag_chunks SET embedding = ? WHERE id = ?",
            (json.dumps(embedding), chunk_id)
        )
        conn.commit()
        return True


def get_rag_chunks_by_project(project_id: int, chunk_type: str = "") -> List[Dict]:
    """获取项目的所有 RAG 片段。"""
    conn = _get_conn()
    if chunk_type:
        cursor = conn.execute(
            "SELECT * FROM webnovel_rag_chunks WHERE project_id = ? AND chunk_type = ? ORDER BY chapter_number",
            (project_id, chunk_type)
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM webnovel_rag_chunks WHERE project_id = ? ORDER BY chapter_number",
            (project_id,)
        )
    return [dict(row) for row in cursor.fetchall()]


def search_rag_chunks(project_id: int, query_embedding: List[float], limit: int = 5) -> List[Dict]:
    """基于余弦相似度检索 RAG 片段。

    Args:
        project_id: 项目 ID
        query_embedding: 查询向量
        limit: 返回前 k 个结果

    Returns:
        匹配的片段列表，每项包含 content、score、metadata 等
    """
    import numpy as np

    conn = _get_conn()
    try:
        with _lock:
            cursor = conn.execute(
                """SELECT id, content, embedding, metadata, chunk_type, chapter_number
                   FROM webnovel_rag_chunks
                   WHERE project_id = ? AND embedding != '' """,
                (project_id,)
            )
            rows = cursor.fetchall()

        if not rows:
            return []

        query_vec = np.array(query_embedding, dtype=np.float32)
        results = []

        for row in rows:
            try:
                emb = np.array(json.loads(row["embedding"]), dtype=np.float32)
                dot = np.dot(query_vec, emb)
                norm_q = np.linalg.norm(query_vec)
                norm_e = np.linalg.norm(emb)
                if norm_q == 0 or norm_e == 0:
                    continue
                score = float(dot / (norm_q * norm_e))
                results.append({
                    "id": row["id"],
                    "content": row["content"],
                    "score": score,
                    "metadata": row["metadata"],
                    "chunk_type": row["chunk_type"],
                    "chapter_number": row["chapter_number"],
                })
            except Exception:
                continue

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    except Exception:
        return []


def delete_rag_chunks_by_project(project_id: int) -> bool:
    """删除项目的所有 RAG 片段。"""
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM webnovel_rag_chunks WHERE project_id = ?", (project_id,))
        conn.commit()
        return True
