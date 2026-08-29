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
from typing import List, Dict, Optional, Any, Tuple

from utils.logger import logger
from .base import VectorStoreBase


class RAGService:
    """WebNovel RAG 语义检索服务。"""

    NAMESPACE = "rag"
    SETTINGS_TYPES = frozenset({
        "character", "worldview", "power_system", "golden_finger",
        "volume_outline", "foreshadow", "villain",
    })

    # 默认最低相似度阈值（低于此值的结果会被过滤）
    DEFAULT_MIN_SCORE = 0.25

    # 按 chunk_type 设置差异化阈值：不同类型的数据质量/语义空间不同，
    # 高质量结构化摘要要求更高阈值，设定类数据语义空间宽泛可放宽。
    # 注意：阈值按 Qwen3-Embedding-0.6B 实测分布校准（中文小说语料上，
    # 相关片段余弦相似度实测约 0.30~0.51，无关片段低于 0.25），
    # 旧值 0.65~0.80 会把所有相关结果误杀导致 RAG 注入永远为空。
    CHUNK_TYPE_MIN_SCORES = {
        "chapter_summary": 0.30,    # LLM 结构化摘要，质量较高
        "chapter": 0.28,            # 机械截断摘要（机械拼接，语义稀释）
        "chapter_paragraph": 0.22,  # 段落切片，语义被前后叙事稀释，分数普遍偏低
        "character": 0.20,          # 角色卡，语义空间差异大
        "foreshadow": 0.22,         # 伏笔信息
        "worldview": 0.20,          # 世界观设定
        "power_system": 0.20,       # 力量体系
        "golden_finger": 0.20,      # 金手指设定
        "villain": 0.20,            # 反派信息
        "volume_outline": 0.22,     # 卷纲
    }

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

    def delete_by_chapter_number(self, project_id: int, chunk_type: str,
                                 chapter_number: int) -> int:
        """删除指定章节的指定类型片段（精确删除，不影响其他章节）。

        Args:
            project_id: 项目 ID
            chunk_type: 片段类型（如 "chapter"、"chapter_paragraph"）
            chapter_number: 章节号

        Returns:
            删除的文档数量
        """
        collection = self._collection(project_id)
        deleted = 0
        for doc in self._get_all_docs(collection, chunk_type):
            if doc.get("chapter_number") == chapter_number:
                if self._store.delete(doc["id"]):
                    deleted += 1
        return deleted

    def delete_by_char_id(self, project_id: int, char_id: int) -> int:
        """删除指定角色卡的全部 character 片段（角色卡变更后增量重建用）。

        Args:
            project_id: 项目 ID
            char_id: 角色卡 ID（与索引时 metadata 中的 char_id 对应）

        Returns:
            删除的文档数量
        """
        collection = self._collection(project_id)
        deleted = 0
        for doc in self._get_all_docs(collection, "character"):
            if doc.get("metadata", {}).get("char_id") == char_id:
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
               limit: int = 10,
               chunk_types: Optional[List[str]] = None,
               min_score: Optional[float] = None) -> List[Dict[str, Any]]:
        """基于预计算 embedding 搜索。

        Args:
            project_id: 项目 ID
            query_embedding: 查询向量（由调用方通过 ModelExecutor 计算）
            limit: 返回前 k 个结果
            chunk_types: 可选，按类型过滤（如 ["chapter", "foreshadow"]）。
                         为 None 时不过滤。
            min_score: 最低相似度阈值。为 None 时使用分级阈值（按 chunk_type）。
                       设为 0 可禁用阈值过滤。

        Returns:
            匹配的片段列表，每项包含 content、score、chunk_type、chapter_number 等
        """
        # 有类型过滤时多取一些原始结果，过滤后仍有充足数据
        fetch_k = limit * 5 if chunk_types else limit * 3
        raw = self._store.search(
            self.NAMESPACE, self._collection(project_id),
            query_embedding, top_k=fetch_k,
        )
        results = self._format_results(raw)

        # ── 相似度硬阈值过滤 ──
        if min_score is None:
            # 使用分级阈值：按每条结果的 chunk_type 选择对应阈值
            results = self._filter_by_chunk_type_scores(results)
        elif min_score > 0:
            results = [r for r in results if r.get("score", 0) >= min_score]
        # min_score == 0 时不过滤

        if chunk_types:
            results = [r for r in results if r.get("chunk_type") in chunk_types]
        return results[:limit]

    def _filter_by_chunk_type_scores(
        self, results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """按 chunk_type 分级阈值过滤结果。"""
        filtered = []
        for r in results:
            chunk_type = r.get("chunk_type", "")
            threshold = self.CHUNK_TYPE_MIN_SCORES.get(
                chunk_type, self.DEFAULT_MIN_SCORE
            )
            if r.get("score", 0) >= threshold:
                filtered.append(r)
        return filtered

    def get_chunks(self, project_id: int, chunk_type: str = "") -> List[Dict[str, Any]]:
        """获取项目的所有 RAG 片段（不含 embedding），可按类型过滤。"""
        return self._get_all_docs(
            self._collection(project_id),
            chunk_type or "",
        )

    def get_paragraphs_context(
        self, project_id: int, chapter_number: int,
        para_index: int, context_range: int = 1,
    ) -> List[Tuple[str, int]]:
        """获取指定段落的上下文段落（前后各 context_range 段）。

        用于查询时对 chapter_paragraph 结果扩展上下文：
        存储时每个 chunk 只含单段（精准 embedding），
        查询时调用本方法取回相邻段落供用户阅读。

        Args:
            project_id: 项目 ID
            chapter_number: 章节号
            para_index: 命中段落的索引
            context_range: 前后各取几段，默认 1

        Returns:
            按段落顺序排列的 (文本, para_index) 元组列表
        """
        collection = self._collection(project_id)
        all_paras = self._get_all_docs(collection, "chapter_paragraph")

        # 按 chapter_number 过滤，提取 para_index，按索引排序
        chapter_paras = sorted(
            [
                d for d in all_paras
                if d.get("chapter_number") == chapter_number
                and "para_index" in d.get("metadata", {})
            ],
            key=lambda d: d["metadata"]["para_index"],
        )

        start = max(0, para_index - context_range)
        end = para_index + context_range + 1

        result = []
        for d in chapter_paras:
            idx = d["metadata"]["para_index"]
            if start <= idx < end:
                result.append((d["content"], idx))
        return result

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

    def list_chunks_paginated(self, project_id: int, page: int = 1,
                              page_size: int = 20,
                              chunk_type: str = "") -> Dict[str, Any]:
        """分页列出项目的所有 RAG 片段（不含 embedding）。

        Args:
            project_id: 项目 ID
            page: 页码（从 1 开始）
            page_size: 每页条数
            chunk_type: 可选，按类型过滤（空字符串表示不过滤）

        Returns:
            包含 total、page、page_size、items、total_pages 的字典
        """
        result = self._store.list_documents(
            self.NAMESPACE, self._collection(project_id),
            page=page, page_size=page_size, chunk_type=chunk_type,
        )
        total = result.get("total", 0)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        result["total_pages"] = total_pages
        return result

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
