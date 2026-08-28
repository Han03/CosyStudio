"""RAG 语义检索服务。

封装 WebNovel 项目的 RAG 向量检索能力：
- 章节摘要 / 段落切片的存储与检索
- 项目设定（角色、世界观、力量体系等）的索引
- 按 chunk_type 过滤、按相似度排序

底层通过 VectorStoreBase 抽象接口操作向量库，
未来可无缝切换至 ChromaDB / FAISS / Milvus 等后端。

embedding 计算由调用方通过 ModelExecutor 完成后传入，
RAGService 本身不做推理调用，保持与 async/sync 上下文无关。
"""

import json
import threading
from typing import List, Dict, Optional, Any

from utils.logger import logger
from .base import VectorStoreBase


class RAGService:
    """WebNovel RAG 语义检索服务。"""

    NAMESPACE = "rag"
    SETTINGS_TYPES = frozenset({
        "character", "worldview", "power_system", "golden_finger",
        "volume_outline", "foreshadow", "villain",
    })

    def __init__(self, vector_store: VectorStoreBase):
        self._store = vector_store

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _collection(self, project_id: int) -> str:
        return f"project:{project_id}"

    @staticmethod
    def _build_metadata(chunk_type: str, chapter_number: int = 0,
                        extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        meta: Dict[str, Any] = {"chunk_type": chunk_type, "chapter_number": chapter_number}
        if extra:
            meta.update(extra)
        return meta

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def add_chunks(self, project_id: int,
                   chunks: List[Dict[str, Any]],
                   embeddings: List[List[float]]) -> List[int]:
        """批量添加 RAG 片段。

        Args:
            project_id: 项目 ID
            chunks: 片段列表，每项需含 content、chunk_type；
                    可选 chapter_number、metadata。
            embeddings: 预计算的 embedding 列表（长度须与 chunks 一致）。

        Returns:
            新创建的文档 ID 列表。
        """
        if not chunks or not embeddings:
            return []

        contents = [c["content"] for c in chunks]

        metadatas = []
        for c in chunks:
            extra = c.get("metadata")
            if isinstance(extra, str):
                try:
                    extra = json.loads(extra)
                except Exception:
                    extra = {}
            elif extra is None:
                extra = {}
            metadatas.append(self._build_metadata(
                c.get("chunk_type", "chapter"),
                c.get("chapter_number", 0),
                extra,
            ))

        return self._store.batch_add(
            self.NAMESPACE, self._collection(project_id),
            contents, embeddings, metadatas,
        )

    def delete_by_type(self, project_id: int, chunk_type: str) -> int:
        """删除项目指定 chunk_type 的所有片段。"""
        collection = self._collection(project_id)
        deleted = 0
        for doc in self._get_all_docs(collection, chunk_type):
            if self._store.delete(doc["id"]):
                deleted += 1
        return deleted

    def clear_project(self, project_id: int) -> int:
        """清空项目的所有 RAG 片段。"""
        return self._store.delete_by_collection(
            self.NAMESPACE, self._collection(project_id),
        )

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    def search(self, project_id: int, query_embedding: List[float],
               limit: int = 10) -> List[Dict[str, Any]]:
        """基于预计算 embedding 搜索。

        Args:
            project_id: 项目 ID
            query_embedding: 查询向量（由调用方通过 ModelExecutor 计算）
            limit: 返回前 k 个结果

        Returns:
            匹配的片段列表，每项包含 content、score、chunk_type、chapter_number 等
        """
        raw = self._store.search(
            self.NAMESPACE, self._collection(project_id),
            query_embedding, top_k=limit,
        )
        return self._format_results(raw)

    def get_chunks(self, project_id: int, chunk_type: str = "") -> List[Dict[str, Any]]:
        """获取项目的所有 RAG 片段（不含 embedding），可按类型过滤。"""
        return self._get_all_docs(
            self._collection(project_id),
            chunk_type or "",
        )

    def has_settings_chunks(self, project_id: int) -> bool:
        """检查项目是否存在设定类型的 RAG 片段。"""
        collection = self._collection(project_id)
        for doc in self._get_all_docs_raw(collection):
            meta = doc.get("metadata", {})
            if meta.get("chunk_type") in self.SETTINGS_TYPES:
                return True
        return False

    def count(self, project_id: int) -> int:
        """统计项目的 RAG 片段总数。"""
        return self._store.count(self.NAMESPACE, self._collection(project_id))

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _get_all_docs_raw(self, collection: str) -> List[Dict[str, Any]]:
        """获取集合中所有文档（不含 embedding），内部用。"""
        from .sqlite_store import _get_conn
        conn = _get_conn()
        try:
            rows = conn.execute(
                """SELECT id, content, metadata, created_at
                   FROM documents WHERE namespace = ? AND collection = ?""",
                (self.NAMESPACE, collection),
            ).fetchall()
            results = []
            for row in rows:
                results.append({
                    "id": row["id"],
                    "content": row["content"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "created_at": row["created_at"],
                })
            return results
        except Exception:
            return []

    def _get_all_docs(self, collection: str, chunk_type: str = "") -> List[Dict[str, Any]]:
        """获取集合中所有文档（不含 embedding），可按 chunk_type 过滤。"""
        docs = self._get_all_docs_raw(collection)
        if chunk_type:
            docs = [d for d in docs if d.get("metadata", {}).get("chunk_type") == chunk_type]
        # 提取 chapter_number / chunk_type 到顶层方便使用
        for d in docs:
            meta = d.get("metadata", {})
            d["chunk_type"] = meta.get("chunk_type", "")
            d["chapter_number"] = meta.get("chapter_number", 0)
        docs.sort(key=lambda x: x["chapter_number"])
        return docs

    @staticmethod
    def _format_results(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将向量库搜索结果格式化为 RAG 片段格式。"""
        results = []
        for doc in raw:
            meta = doc.get("metadata", {})
            results.append({
                "id": doc["id"],
                "content": doc["content"],
                "score": doc["score"],
                "metadata": json.dumps(meta, ensure_ascii=False) if meta else "",
                "chunk_type": meta.get("chunk_type", ""),
                "chapter_number": meta.get("chapter_number", 0),
            })
        return results


# ------------------------------------------------------------------
# 模块级单例
# ------------------------------------------------------------------

_rag_service: Optional[RAGService] = None
_rag_lock = threading.Lock()


def get_rag_service() -> RAGService:
    """获取 RAG 服务单例。"""
    global _rag_service
    if _rag_service is None:
        with _rag_lock:
            if _rag_service is None:
                from .sqlite_store import get_vector_store
                _rag_service = RAGService(get_vector_store())
    return _rag_service
