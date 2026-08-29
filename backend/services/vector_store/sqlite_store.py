"""基于 SQLite 的向量存储实现。

使用 SQLite 持久化文档和 embedding 向量，numpy 计算余弦相似度。
这是当前的默认后端，未来可替换为 ChromaDB / FAISS / Milvus 等。
"""

import os
import json
import sqlite3
import threading
import time
from typing import List, Dict, Optional, Any

import numpy as np

from utils.logger import logger
from .base import VectorStoreBase

from core.paths import CACHE_DIR as _DB_DIR
_DB_PATH = os.path.join(_DB_DIR, "vector_store.db")

_conn: Optional[sqlite3.Connection] = None
_lock = threading.Lock()

# 模块级单例
_instance: Optional["SQLiteVectorStore"] = None


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
            """CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                collection TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding TEXT NOT NULL,
                metadata TEXT,
                created_at REAL NOT NULL
            )"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_documents_ns_coll
                ON documents(namespace, collection)"""
        )
        conn.commit()

        # 一次性数据迁移：从主库 webnovel_rag_chunks → vector_store documents
        _migrate_rag_chunks(conn)


def _migrate_rag_chunks(conn: sqlite3.Connection):
    """将 app.db 中的 webnovel_rag_chunks 迁移到向量库。

    幂等设计：若目标已存在 rag namespace 数据则跳过迁移，但仍清理旧表。
    """
    try:
        from core.paths import CACHE_DIR
        main_db_path = os.path.join(CACHE_DIR, "app.db")
        if not os.path.exists(main_db_path):
            return

        def _drop_old_table(main_conn):
            """清理旧表（无论是否已迁移）。"""
            try:
                main_conn.execute("DROP TABLE IF EXISTS webnovel_rag_chunks")
                main_conn.commit()
                logger.info("[VectorStore] 已清理旧表 webnovel_rag_chunks")
            except Exception as e:
                logger.warning(f"[VectorStore] 清理旧表失败: {e}")

        # 检查是否已迁移过
        row = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE namespace = 'rag'"
        ).fetchone()
        if row and row[0] > 0:
            # 已迁移过，仅清理旧表
            main_conn = sqlite3.connect(main_db_path, check_same_thread=False)
            try:
                _drop_old_table(main_conn)
            finally:
                main_conn.close()
            return

        main_conn = sqlite3.connect(main_db_path, check_same_thread=False)
        main_conn.row_factory = sqlite3.Row
        try:
            # 检查源表是否存在
            tables = main_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='webnovel_rag_chunks'"
            ).fetchall()
            if not tables:
                return

            rows = main_conn.execute(
                """SELECT project_id, chunk_type, chapter_number, content, embedding, metadata, created_at
                   FROM webnovel_rag_chunks WHERE embedding != ''"""
            ).fetchall()

            if not rows:
                logger.info("[VectorStore] webnovel_rag_chunks 无数据，跳过迁移")
                _drop_old_table(main_conn)
                return

            batch = []
            for r in rows:
                batch.append((
                    "rag",
                    f"project:{r['project_id']}",
                    r["content"],
                    r["embedding"],  # 已是 JSON 文本
                    json.dumps({
                        "chunk_type": r["chunk_type"],
                        "chapter_number": r["chapter_number"],
                        **(json.loads(r["metadata"]) if r["metadata"] else {}),
                    }, ensure_ascii=False),
                    r["created_at"] or time.time(),
                ))

            # 注意：此处已在 _init_tables 的 _lock 保护范围内，不可再次获取锁
            conn.executemany(
                """INSERT INTO documents (namespace, collection, content, embedding, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                batch,
            )
            conn.commit()

            logger.info(f"[VectorStore] 已迁移 {len(batch)} 条 RAG 片段到向量库")
            _drop_old_table(main_conn)

        finally:
            main_conn.close()

    except Exception as e:
        logger.warning(f"[VectorStore] RAG 数据迁移失败（不影响正常使用）: {e}")


class SQLiteVectorStore(VectorStoreBase):
    """基于 SQLite + numpy 余弦相似度的向量存储实现。"""

    def add(self, namespace: str, collection: str, content: str,
            embedding: List[float], metadata: Optional[Dict[str, Any]] = None) -> int:
        conn = _get_conn()
        try:
            with _lock:
                cursor = conn.execute(
                    """INSERT INTO documents
                       (namespace, collection, content, embedding, metadata, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (namespace, collection, content, json.dumps(embedding),
                     json.dumps(metadata, ensure_ascii=False) if metadata else None,
                     time.time()),
                )
                conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"[VectorStore] 添加文档失败: {e}")
            return -1

    def batch_add(self, namespace: str, collection: str,
                  contents: List[str], embeddings: List[List[float]],
                  metadatas: Optional[List[Optional[Dict[str, Any]]]] = None) -> List[int]:
        if not contents:
            return []
        if metadatas is None:
            metadatas = [None] * len(contents)

        conn = _get_conn()
        ids = []
        now = time.time()
        try:
            with _lock:
                for i, (content, emb) in enumerate(zip(contents, embeddings)):
                    meta = metadatas[i] if i < len(metadatas) else None
                    cursor = conn.execute(
                        """INSERT INTO documents
                           (namespace, collection, content, embedding, metadata, created_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (namespace, collection, content, json.dumps(emb),
                         json.dumps(meta, ensure_ascii=False) if meta else None, now),
                    )
                    ids.append(cursor.lastrowid)
                conn.commit()
        except Exception as e:
            logger.error(f"[VectorStore] 批量添加失败: {e}")
        return ids

    def search(self, namespace: str, collection: str,
               query_embedding: List[float], top_k: int = 10) -> List[Dict[str, Any]]:
        conn = _get_conn()
        try:
            with _lock:
                cursor = conn.execute(
                    """SELECT id, content, embedding, metadata, created_at
                       FROM documents
                       WHERE namespace = ? AND collection = ? AND embedding != ''""",
                    (namespace, collection),
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
                        "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                        "created_at": row["created_at"],
                    })
                except Exception:
                    continue

            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]

        except Exception as e:
            logger.error(f"[VectorStore] 搜索失败: {e}")
            return []

    def get(self, doc_id: int) -> Optional[Dict[str, Any]]:
        conn = _get_conn()
        try:
            with _lock:
                row = conn.execute(
                    "SELECT * FROM documents WHERE id = ?", (doc_id,)
                ).fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "namespace": row["namespace"],
                "collection": row["collection"],
                "content": row["content"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "created_at": row["created_at"],
            }
        except Exception as e:
            logger.error(f"[VectorStore] 获取文档失败: {e}")
            return None

    def delete(self, doc_id: int) -> bool:
        conn = _get_conn()
        try:
            with _lock:
                cursor = conn.execute(
                    "DELETE FROM documents WHERE id = ?", (doc_id,)
                )
                conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"[VectorStore] 删除文档失败: {e}")
            return False

    def delete_by_collection(self, namespace: str, collection: str) -> int:
        conn = _get_conn()
        try:
            with _lock:
                cursor = conn.execute(
                    "DELETE FROM documents WHERE namespace = ? AND collection = ?",
                    (namespace, collection),
                )
                conn.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"[VectorStore] 删除集合失败: {e}")
            return 0

    def count(self, namespace: Optional[str] = None,
              collection: Optional[str] = None) -> int:
        conn = _get_conn()
        try:
            with _lock:
                if namespace and collection:
                    row = conn.execute(
                        "SELECT COUNT(*) FROM documents WHERE namespace = ? AND collection = ?",
                        (namespace, collection),
                    ).fetchone()
                elif namespace:
                    row = conn.execute(
                        "SELECT COUNT(*) FROM documents WHERE namespace = ?",
                        (namespace,),
                    ).fetchone()
                else:
                    row = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"[VectorStore] 统计失败: {e}")
            return 0

    def list_documents(self, namespace: str, collection: str,
                       page: int = 1, page_size: int = 20,
                       chunk_type: str = "") -> dict:
        """分页列出文档（不含 embedding），可按 chunk_type 过滤。"""
        conn = _get_conn()
        try:
            with _lock:
                # 构建 WHERE 条件
                where = "namespace = ? AND collection = ?"
                params: list = [namespace, collection]

                if chunk_type:
                    # metadata 是 JSON 字符串（以 { 开头），用 LIKE 匹配 chunk_type
                    # 前后加 % 通配符：前导 % 匹配 {" 等前缀，中间 % 兼容冒号后有无空格
                    where += " AND metadata LIKE ?"
                    params.append(f'{{"chunk_type": "{chunk_type}"%')

                # 先查总数
                count_row = conn.execute(
                    f"SELECT COUNT(*) FROM documents WHERE {where}", params
                ).fetchone()
                total = count_row[0] if count_row else 0

                # 分页查询（按 id 倒序，最新的在前）
                offset = (max(1, page) - 1) * page_size
                cursor = conn.execute(
                    f"""SELECT id, content, metadata, created_at
                        FROM documents
                        WHERE {where}
                        ORDER BY id DESC
                        LIMIT ? OFFSET ?""",
                    params + [page_size, offset],
                )
                rows = cursor.fetchall()

            items = []
            for row in rows:
                meta = json.loads(row["metadata"]) if row["metadata"] else {}
                items.append({
                    "id": row["id"],
                    "content": row["content"],
                    "metadata": meta,
                    "chunk_type": meta.get("chunk_type", ""),
                    "chapter_number": meta.get("chapter_number", 0),
                    "created_at": row["created_at"],
                })

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": items,
            }
        except Exception as e:
            logger.error(f"[VectorStore] 分页列出文档失败: {e}")
            return {"total": 0, "page": page, "page_size": page_size, "items": []}


def get_vector_store() -> SQLiteVectorStore:
    """获取向量存储单例。"""
    global _instance
    if _instance is None:
        _instance = SQLiteVectorStore()
        # 确保数据库和表已初始化
        _get_conn()
    return _instance
