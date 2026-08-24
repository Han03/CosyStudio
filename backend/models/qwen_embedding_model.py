import os
import torch
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class QwenEmbeddingModel:
    def __init__(self, model_path):
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self.device = None
        self._loaded = False
        self._load_model()

    def _load_model(self):
        logger.info(f"[QwenEmbedding] 开始加载模型，路径: {self.model_path}")

        if torch.cuda.is_available():
            self.device = torch.device("cuda")
            logger.info(f"[QwenEmbedding] GPU可用，设备: {torch.cuda.get_device_name(0)}")
        else:
            self.device = torch.device("cpu")
            logger.warning("[QwenEmbedding] GPU不可用，将使用CPU")

        try:
            from transformers import AutoTokenizer, AutoModel

            logger.info("[QwenEmbedding] 正在加载tokenizer...")
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_path,
                trust_remote_code=True
            )
            logger.info("[QwenEmbedding] Tokenizer加载完成")

            logger.info("[QwenEmbedding] 正在加载模型...")
            self.model = AutoModel.from_pretrained(
                self.model_path,
                trust_remote_code=True,
                dtype=torch.float16 if self.device.type == "cuda" else torch.float32,
            )

            self.model = self.model.to(self.device)
            self.model.eval()

            self._loaded = True
            logger.info(f"[QwenEmbedding] 模型加载成功，设备: {self.device}")

        except Exception as e:
            logger.error(f"[QwenEmbedding] 加载模型失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def is_loaded(self):
        return self._loaded and self.model is not None

    def encode(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        对文本列表进行编码，返回嵌入向量列表。

        Args:
            texts: 文本列表
            batch_size: 批处理大小

        Returns:
            嵌入向量列表，每个向量是float列表
        """
        if not self.is_loaded():
            logger.error("[QwenEmbedding] 模型未加载，无法编码")
            return []

        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            try:
                with torch.no_grad():
                    inputs = self.tokenizer(
                        batch_texts,
                        padding=True,
                        truncation=True,
                        max_length=512,
                        return_tensors="pt"
                    ).to(self.device)

                    outputs = self.model(**inputs)
                    embeddings = outputs.last_hidden_state[:, 0, :].cpu().numpy().tolist()
                    all_embeddings.extend(embeddings)
            except Exception as e:
                logger.error(f"[QwenEmbedding] 编码失败: {e}")
                all_embeddings.extend([[]] * len(batch_texts))

        return all_embeddings

    def similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的相似度（余弦相似度）。

        Args:
            text1: 第一个文本
            text2: 第二个文本

        Returns:
            相似度分数（0-1）
        """
        if not self.is_loaded():
            logger.error("[QwenEmbedding] 模型未加载，无法计算相似度")
            return 0.0

        try:
            embeddings = self.encode([text1, text2])
            if len(embeddings) < 2 or not embeddings[0] or not embeddings[1]:
                return 0.0

            import numpy as np
            vec1 = np.array(embeddings[0])
            vec2 = np.array(embeddings[1])
            similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
            return float(similarity)
        except Exception as e:
            logger.error(f"[QwenEmbedding] 计算相似度失败: {e}")
            return 0.0

    def rank(self, query: str, documents: List[str], top_k: int = 5) -> List[dict]:
        """
        对文档列表按与查询的相似度进行排序。

        Args:
            query: 查询文本
            documents: 文档列表
            top_k: 返回前k个结果

        Returns:
            排序后的结果列表，每个元素包含文档和相似度分数
        """
        if not self.is_loaded():
            logger.error("[QwenEmbedding] 模型未加载，无法排序")
            return []

        try:
            all_texts = [query] + documents
            embeddings = self.encode(all_texts)

            if len(embeddings) < len(all_texts):
                return []

            query_embedding = embeddings[0]
            doc_embeddings = embeddings[1:]

            import numpy as np
            query_vec = np.array(query_embedding)
            similarities = []

            for i, doc_embedding in enumerate(doc_embeddings):
                if not doc_embedding:
                    similarities.append((i, 0.0))
                    continue
                doc_vec = np.array(doc_embedding)
                similarity = np.dot(query_vec, doc_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(doc_vec))
                similarities.append((i, float(similarity)))

            similarities.sort(key=lambda x: x[1], reverse=True)

            results = []
            for idx, score in similarities[:top_k]:
                results.append({
                    "document": documents[idx],
                    "score": score,
                    "index": idx
                })

            return results
        except Exception as e:
            logger.error(f"[QwenEmbedding] 排序失败: {e}")
            return []

    def release(self):
        """释放模型资源"""
        try:
            if self.model is not None:
                if self.device and self.device.type == "cuda":
                    self.model = self.model.to(torch.device("cpu"))
                del self.model
                self.model = None
                logger.info("[QwenEmbedding] 模型已释放")

            if self.tokenizer is not None:
                del self.tokenizer
                self.tokenizer = None

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            self._loaded = False
            logger.info("[QwenEmbedding] 内存已清理")
        except Exception as e:
            logger.error(f"[QwenEmbedding] 释放模型失败: {e}")