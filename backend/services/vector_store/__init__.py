"""向量存储模块。

提供两类能力：
1. 通用向量存储抽象（VectorStoreBase / SQLiteVectorStore）—— 支持切换后端
2. 智能体对话记忆 API（add_summary / search / ...）—— 向后兼容
3. RAG 语义检索服务（RAGService / get_rag_service）
"""

import json
import time
from typing import List, Dict, Optional, Any

from utils.logger import logger

# ------------------------------------------------------------------
# 核心类 & 工厂
# ------------------------------------------------------------------
from .base import VectorStoreBase
from .sqlite_store import SQLiteVectorStore, get_vector_store
from .rag_service import RAGService, get_rag_service

# ------------------------------------------------------------------
# 智能体对话记忆 —— 向后兼容
#
# 命名空间约定：namespace="agent_memory", collection=agent_id
# ------------------------------------------------------------------

_AGENT_NS = "agent_memory"


def _encode_text(text: str) -> Optional[List[float]]:
    """对文本进行 embedding 编码（智能体记忆专用）。"""
    from core.model_manager import ensure_qwen_embedding_loaded
    from core.global_manager import global_manager
    ensure_qwen_embedding_loaded()
    model = global_manager.qwen_embedding_model
    if not model or not model.is_loaded():
        logger.warning("[VectorStore] 嵌入模型未加载")
        return None
    embeddings = model.encode([text])
    return embeddings[0] if embeddings else None


def add_summary(agent_id: str, summary: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
    """添加对话记忆摘要到向量库。"""
    embedding = _encode_text(summary)
    if embedding is None:
        return False
    store = get_vector_store()
    doc_id = store.add(_AGENT_NS, agent_id, summary, embedding, metadata)
    return doc_id > 0


def search(agent_id: str, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """在向量库中搜索与查询最相似的记忆摘要。"""
    query_embedding = _encode_text(query)
    if query_embedding is None:
        return []
    store = get_vector_store()
    raw = store.search(_AGENT_NS, agent_id, query_embedding, top_k=top_k)
    # 保持与原 API 一致的字段名
    results = []
    for doc in raw:
        results.append({
            "id": doc["id"],
            "summary": doc["content"],
            "score": doc["score"],
            "metadata": doc.get("metadata"),
            "created_at": doc.get("created_at"),
        })
    return results


def get_all_memories(agent_id: str) -> List[Dict[str, Any]]:
    """获取指定智能体的所有记忆摘要。"""
    store = get_vector_store()
    from .sqlite_store import _get_conn
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT id, content, metadata, created_at
               FROM documents
               WHERE namespace = ? AND collection = ?
               ORDER BY created_at DESC""",
            (_AGENT_NS, agent_id),
        ).fetchall()
        results = []
        for row in rows:
            results.append({
                "id": row["id"],
                "summary": row["content"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                "created_at": row["created_at"],
            })
        return results
    except Exception as e:
        logger.error(f"[VectorStore] 获取记忆失败: {e}")
        return []


def delete_memory(agent_id: str, memory_id: int) -> bool:
    """删除指定记忆。"""
    store = get_vector_store()
    return store.delete(memory_id)


def clear_memories(agent_id: str) -> bool:
    """清空指定智能体的所有记忆。"""
    store = get_vector_store()
    store.delete_by_collection(_AGENT_NS, agent_id)
    logger.info(f"[VectorStore] agent={agent_id} 已清空所有记忆")
    return True


def count_memories(agent_id: str) -> int:
    """获取指定智能体的记忆数量。"""
    store = get_vector_store()
    return store.count(_AGENT_NS, agent_id)


__all__ = [
    # 核心类
    "VectorStoreBase", "SQLiteVectorStore", "get_vector_store",
    # RAG 服务
    "RAGService", "get_rag_service",
    # 智能体记忆 API（向后兼容）
    "add_summary", "search", "get_all_memories",
    "delete_memory", "clear_memories", "count_memories",
]
