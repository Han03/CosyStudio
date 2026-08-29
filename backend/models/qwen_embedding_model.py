import os
import torch
import logging
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Qwen3-Embedding 官方 instruction prefix（来自 config_sentence_transformers.json）
_QUERY_INSTRUCTION = (
    "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:"
)
_DOCUMENT_INSTRUCTION = ""


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

    def encode(self, texts: List[str], batch_size: int = 32,
               is_query: bool = False) -> List[List[float]]:
        """
        对文本列表进行编码，返回嵌入向量列表。

        使用 last-token pooling（Qwen3-Embedding 官方推荐）+ L2 归一化。
        query 文本会自动添加 instruction prefix 以提升检索效果。

        Args:
            texts: 文本列表
            batch_size: 批处理大小
            is_query: 是否为查询文本（True 时添加 instruction prefix）

        Returns:
            嵌入向量列表，每个向量是已归一化的 float 列表
        """
        if not self.is_loaded():
            logger.error("[QwenEmbedding] 模型未加载，无法编码")
            return []

        # 为 query 添加 instruction prefix，document 不添加
        instruction = _QUERY_INSTRUCTION if is_query else _DOCUMENT_INSTRUCTION
        if instruction:
            texts = [f"{instruction}{t}" for t in texts]

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
                    hidden_states = outputs.last_hidden_state

                    # Last-token pooling：取每个序列最后一个有效 token 的隐藏状态
                    # （Qwen3-Embedding 为 decoder-only 架构，官方配置 pooling_mode_lasttoken=true）
                    attention_mask = inputs["attention_mask"]
                    # 找到每个序列最后一个非 padding token 的位置
                    seq_lengths = attention_mask.sum(dim=1) - 1  # (batch_size,)
                    batch_indices = torch.arange(hidden_states.size(0), device=hidden_states.device)
                    last_token_embeddings = hidden_states[batch_indices, seq_lengths, :]

                    # L2 归一化（模型 pipeline 包含 Normalize 层）
                    normalized = torch.nn.functional.normalize(
                        last_token_embeddings, p=2, dim=1
                    )
                    all_embeddings.extend(normalized.cpu().numpy().tolist())
            except Exception as e:
                logger.error(f"[QwenEmbedding] 编码失败: {e}")
                all_embeddings.extend([[]] * len(batch_texts))

        return all_embeddings

    def similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的相似度（余弦相似度）。

        由于 encode 已做 L2 归一化，相似度直接用点积即可。

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

            vec1 = np.array(embeddings[0])
            vec2 = np.array(embeddings[1])
            # 已归一化的向量，点积即余弦相似度
            similarity = float(np.dot(vec1, vec2))
            return max(0.0, similarity)
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
            # query 用 is_query=True，documents 用默认 is_query=False
            query_embeddings = self.encode([query], is_query=True)
            doc_embeddings = self.encode(documents)

            if not query_embeddings or not query_embeddings[0]:
                return []

            query_vec = np.array(query_embeddings[0])
            similarities = []

            for i, doc_emb in enumerate(doc_embeddings):
                if not doc_emb:
                    similarities.append((i, 0.0))
                    continue
                doc_vec = np.array(doc_emb)
                # 已归一化，点积即余弦相似度
                similarity = float(np.dot(query_vec, doc_vec))
                similarities.append((i, max(0.0, similarity)))

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