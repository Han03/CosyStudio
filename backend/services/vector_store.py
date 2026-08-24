"""向量存储模块，用于存储和检索对话记忆摘要。

使用 QwenEmbeddingModel 进行文本编码，SQLite + numpy 余弦相似度进行持久化和检索，
按 agent_id 进行隔离，确保每个智能体的记忆独立管理。
"""

import os
import json
import time
import sqlite3
import threading
from typing import List, Dict, Optional, Any

import numpy as np

from utils.logger import logger
from core.global_manager import global_manager


from core.paths import CACHE_DIR as _DB_DIR
_DB_PATH = os.path.join(_DB_DIR, "vector_store.db")

_conn: Optional[sqlite3.Connection] = None
_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（懒加载，自动建表）。"""
    global _conn
    if _conn is None:
        os.makedirs(_DB_DIR, exist_ok=True)
        _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.text_factory = str
        _conn.execute("PRAGMA encoding='UTF-8'")
        _init_tables(_conn)
    return _conn


def _init_tables(conn: sqlite3.Connection):
    """初始化向量存储表。"""
    with _lock:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                embedding BLOB NOT NULL,
                metadata TEXT,
                created_at REAL NOT NULL
            )"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_memories_agent_id
                ON memories(agent_id)"""
        )
        conn.commit()


def _get_embedding_model():
    """获取嵌入模型。"""
    from core.model_manager import ensure_qwen_embedding_loaded
    ensure_qwen_embedding_loaded()
    return global_manager.qwen_embedding_model


def _encode_text(text: str) -> Optional[List[float]]:
    """对文本进行编码。"""
    model = _get_embedding_model()
    if not model or not model.is_loaded():
        logger.warning("[VectorStore] 嵌入模型未加载，无法编码")
        return None
    embeddings = model.encode([text])
    return embeddings[0] if embeddings else None


def _cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """计算余弦相似度。"""
    if vec1.ndim == 1:
        vec1 = vec1.reshape(1, -1)
    if vec2.ndim == 1:
        vec2 = vec2.reshape(1, -1)
    dot_product = np.dot(vec1, vec2.T)
    norm1 = np.linalg.norm(vec1, axis=1, keepdims=True)
    norm2 = np.linalg.norm(vec2, axis=1, keepdims=True)
    similarity = dot_product / (norm1 * norm2.T)
    return float(similarity[0, 0])


def add_summary(agent_id: str, summary: str, metadata: Optional[Dict[str, Any]] = None):
    """
    添加对话记忆摘要到向量库。

    Args:
        agent_id: 智能体ID
        summary: 记忆摘要文本
        metadata: 元数据（如媒体文件路径等），可选
    """
    embedding = _encode_text(summary)
    if embedding is None:
        logger.warning(f"[VectorStore] agent={agent_id} 嵌入编码失败，跳过存储")
        return False

    conn = _get_conn()
    try:
        with _lock:
            conn.execute(
                """INSERT INTO memories (agent_id, summary, embedding, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (agent_id, summary, json.dumps(embedding), json.dumps(metadata) if metadata else None, time.time())
            )
            conn.commit()
        logger.info(f"[VectorStore] agent={agent_id} 记忆摘要已存储")
        return True
    except Exception as e:
        logger.error(f"[VectorStore] 添加摘要失败: {e}")
        return False


def search(agent_id: str, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    在向量库中搜索与查询最相似的记忆摘要。

    Args:
        agent_id: 智能体ID
        query: 查询文本
        top_k: 返回前k个结果

    Returns:
        相似记忆列表，每个元素包含 summary、score 和 metadata
    """
    query_embedding = _encode_text(query)
    if query_embedding is None:
        logger.warning(f"[VectorStore] agent={agent_id} 查询编码失败，返回空结果")
        return []

    conn = _get_conn()
    try:
        with _lock:
            cursor = conn.execute(
                """SELECT id, summary, embedding, metadata, created_at
                   FROM memories WHERE agent_id = ?""",
                (agent_id,)
            )
            rows = cursor.fetchall()

        if not rows:
            return []

        query_vec = np.array(query_embedding)
        results = []

        for row in rows:
            try:
                embedding = np.array(json.loads(row["embedding"]))
                similarity = _cosine_similarity(query_vec, embedding)
                results.append({
                    "id": row["id"],
                    "summary": row["summary"],
                    "score": similarity,
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                    "created_at": row["created_at"]
                })
            except Exception as e:
                logger.warning(f"[VectorStore] 解析向量失败: {e}")
                continue

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    except Exception as e:
        logger.error(f"[VectorStore] 搜索失败: {e}")
        return []


def get_all_memories(agent_id: str) -> List[Dict[str, Any]]:
    """
    获取指定智能体的所有记忆摘要。

    Args:
        agent_id: 智能体ID

    Returns:
        记忆列表
    """
    conn = _get_conn()
    try:
        with _lock:
            cursor = conn.execute(
                """SELECT id, summary, metadata, created_at
                   FROM memories WHERE agent_id = ? ORDER BY created_at DESC""",
                (agent_id,)
            )
            rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append({
                "id": row["id"],
                "summary": row["summary"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                "created_at": row["created_at"]
            })
        return results

    except Exception as e:
        logger.error(f"[VectorStore] 获取记忆失败: {e}")
        return []


def delete_memory(agent_id: str, memory_id: int) -> bool:
    """
    删除指定记忆。

    Args:
        agent_id: 智能体ID
        memory_id: 记忆ID

    Returns:
        是否删除成功
    """
    conn = _get_conn()
    try:
        with _lock:
            cursor = conn.execute(
                "DELETE FROM memories WHERE agent_id = ? AND id = ?",
                (agent_id, memory_id)
            )
            conn.commit()
        return cursor.rowcount > 0

    except Exception as e:
        logger.error(f"[VectorStore] 删除记忆失败: {e}")
        return False


def clear_memories(agent_id: str) -> bool:
    """
    清空指定智能体的所有记忆。

    Args:
        agent_id: 智能体ID

    Returns:
        是否清空成功
    """
    conn = _get_conn()
    try:
        with _lock:
            cursor = conn.execute(
                "DELETE FROM memories WHERE agent_id = ?",
                (agent_id,)
            )
            conn.commit()
        logger.info(f"[VectorStore] agent={agent_id} 已清空所有记忆")
        return True

    except Exception as e:
        logger.error(f"[VectorStore] 清空记忆失败: {e}")
        return False


def count_memories(agent_id: str) -> int:
    """
    获取指定智能体的记忆数量。

    Args:
        agent_id: 智能体ID

    Returns:
        记忆数量
    """
    conn = _get_conn()
    try:
        with _lock:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE agent_id = ?",
                (agent_id,)
            )
            row = cursor.fetchone()
        return row[0] if row else 0

    except Exception as e:
        logger.error(f"[VectorStore] 统计记忆失败: {e}")
        return 0
