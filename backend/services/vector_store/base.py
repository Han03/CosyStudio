"""向量存储抽象基类。

定义向量存储的统一接口，支持未来切换不同的向量数据库后端
（如 ChromaDB、FAISS、Milvus 等）。
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any


class VectorStoreBase(ABC):
    """向量存储抽象基类。

    所有向量存储后端必须实现此接口。

    数据模型：
    - namespace: 顶层命名空间隔离（如 "rag"、"agent_memory"）
    - collection: 命名空间内的集合（如 "project:78"、"agent:abc123"）
    - content: 原始文本内容
    - embedding: 浮点向量（由外部编码模型生成）
    - metadata: 可选的 JSON 元数据
    """

    @abstractmethod
    def add(self, namespace: str, collection: str, content: str,
            embedding: List[float], metadata: Optional[Dict[str, Any]] = None) -> int:
        """添加单条文档，返回文档 ID。"""

    @abstractmethod
    def batch_add(self, namespace: str, collection: str,
                  contents: List[str], embeddings: List[List[float]],
                  metadatas: Optional[List[Optional[Dict[str, Any]]]] = None) -> List[int]:
        """批量添加文档，返回文档 ID 列表。"""

    @abstractmethod
    def search(self, namespace: str, collection: str,
               query_embedding: List[float], top_k: int = 10) -> List[Dict[str, Any]]:
        """在指定集合中搜索最相似的文档。

        Returns:
            文档列表，每项包含 id、content、score、metadata。
        """

    @abstractmethod
    def get(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 获取文档。"""

    @abstractmethod
    def delete(self, doc_id: int) -> bool:
        """按 ID 删除文档。"""

    @abstractmethod
    def delete_by_collection(self, namespace: str, collection: str) -> int:
        """删除指定集合中的所有文档，返回删除数量。"""

    @abstractmethod
    def count(self, namespace: Optional[str] = None,
              collection: Optional[str] = None) -> int:
        """统计文档数量。可按 namespace / collection 过滤。"""

    def list_documents(self, namespace: str, collection: str,
                       page: int = 1, page_size: int = 20,
                       chunk_type: str = "") -> dict:
        """分页列出文档（不含 embedding）。

        Args:
            namespace: 命名空间
            collection: 集合名
            page: 页码（从 1 开始）
            page_size: 每页条数
            chunk_type: 可选，按 chunk_type 过滤（空字符串表示不过滤）

        Returns:
            包含 total、page、page_size、items 的字典
        """
