import torch
import logging
from typing import List

logger = logging.getLogger(__name__)

# Qwen3-Reranker 官方 instruction prefix（Instruct 部分，置于 chat template 内）
_DEFAULT_INSTRUCTION = (
    "Given a web search query, retrieve relevant passages that answer the query"
)

# 官方 chat template 前后缀：system 限定模型只能回答 yes/no，
# assistant 输出到 <think>\n\n</think>\n\n 后，下一个 token 即为 yes/no 判断。
# 缺失该模板时模型会试图续写/回答而非判断相关性，导致打分失效。
_PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on the "
    "Query and the Instruct provided. Note that the answer can only be \"yes\" or \"no\"."
    "<|im_end|>\n<|im_start|>user\n"
)
_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


class QwenRerankerModel:
    def __init__(self, model_path):
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self.device = None
        self._loaded = False
        self._load_model()

    def _load_model(self):
        logger.info(f"[QwenReranker] 开始加载模型，路径: {self.model_path}")

        if torch.cuda.is_available():
            self.device = torch.device("cuda")
            logger.info(f"[QwenReranker] GPU可用，设备: {torch.cuda.get_device_name(0)}")
        else:
            self.device = torch.device("cpu")
            logger.warning("[QwenReranker] GPU不可用，将使用CPU")

        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM

            logger.info("[QwenReranker] 正在加载tokenizer...")
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_path,
                trust_remote_code=True,
                padding_side="left",  # 官方要求：取末位 logits 打分，左填充保证末位是真实 token
            )
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            # 预编码 chat template 前后缀，打分时拼在每条序列两侧，
            # 截断只作用于中间正文，模板本身不会被破坏。
            self._prefix_ids = self.tokenizer.encode(_PREFIX, add_special_tokens=False)
            self._suffix_ids = self.tokenizer.encode(_SUFFIX, add_special_tokens=False)
            logger.info("[QwenReranker] Tokenizer加载完成")

            logger.info("[QwenReranker] 正在加载模型...")
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                trust_remote_code=True,
                dtype=torch.float16 if self.device.type == "cuda" else torch.float32,
            )

            self.model = self.model.to(self.device)
            self.model.eval()

            self._loaded = True
            logger.info(f"[QwenReranker] 模型加载成功，设备: {self.device}")

        except Exception as e:
            logger.error(f"[QwenReranker] 加载模型失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def is_loaded(self):
        return self._loaded and self.model is not None

    def score(self, query: str, documents: List[str],
              max_length: int = 1024) -> List[float]:
        """
        计算 query 与每个 document 的相关性分数。

        使用 Qwen3-Reranker 官方 Transformers 打分方式：将 query/document 填入
        chat template（system 限定只回答 yes/no），取序列最后一个位置上
        yes/no 两个词表位置的 log_softmax 概率，yes 的概率即为相关性分数。

        Args:
            query: 查询文本
            documents: 候选片段列表
            max_length: 输入序列最大长度

        Returns:
            相关性分数列表（0-1），与 documents 顺序一致
        """
        if not self.is_loaded():
            logger.error("[QwenReranker] 模型未加载，无法打分")
            return []

        if not documents:
            return []

        try:
            # 官方格式：<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}
            pairs = [
                f"<Instruct>: {_DEFAULT_INSTRUCTION}\n<Query>: {query}\n<Document>: {doc}"
                for doc in documents
            ]

            # 只分词正文（不填充，截断时预留前后缀长度），再拼上模板前后缀；
            # 注意：不能把 token id 列表传回 tokenizer()（只接受文本，会报
            # ValueError: text input must be of type `str`...），须用 pad()。
            body_ids = self.tokenizer(
                pairs,
                padding=False,
                truncation="longest_first",
                max_length=max_length - len(self._prefix_ids) - len(self._suffix_ids),
            )["input_ids"]

            full_ids = [
                self._prefix_ids + ids + self._suffix_ids for ids in body_ids
            ]

            # transformers 5.x 的 pad() 不支持 truncation 参数，截断已在上面完成；
            # 且元素须为含 input_ids 的 dict（不再接受裸 id 列表）；
            # 左填充（加载时已设置）保证每行末位是模板结尾而非 pad。
            model_inputs = self.tokenizer.pad(
                [{"input_ids": ids} for ids in full_ids],
                return_tensors="pt",
                padding=True,
            ).to(self.device)

            _yes_token_id = self.tokenizer.convert_tokens_to_ids("yes")
            _no_token_id = self.tokenizer.convert_tokens_to_ids("no")

            with torch.no_grad():
                # 末位 logits 预测下一个 token（模板结尾后正是 yes/no 判断位）
                logits = self.model(**model_inputs).logits[:, -1, :]
                yes_no_logits = logits[:, [_no_token_id, _yes_token_id]]
                probs = torch.log_softmax(yes_no_logits, dim=-1)
                scores = probs[:, 1].exp().cpu().numpy().tolist()

            return scores
        except Exception as e:
            logger.error(f"[QwenReranker] 打分失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def rerank(self, query: str, documents: List[str], top_k: int = 5,
               max_length: int = 1024) -> List[dict]:
        """
        对片段列表按与查询的相关性进行重排序。

        Args:
            query: 查询文本
            documents: 候选片段列表
            top_k: 返回前k个结果
            max_length: 输入序列最大长度

        Returns:
            排序后的结果列表，每个元素包含片段、分数和原始索引
        """
        if not self.is_loaded():
            logger.error("[QwenReranker] 模型未加载，无法重排序")
            return []

        try:
            scores = self.score(query, documents, max_length=max_length)
            if not scores:
                return []

            ranked = sorted(
                enumerate(scores), key=lambda x: x[1], reverse=True
            )

            results = []
            for idx, score in ranked[:top_k]:
                results.append({
                    "document": documents[idx],
                    "score": float(score),
                    "index": idx
                })

            return results
        except Exception as e:
            logger.error(f"[QwenReranker] 重排序失败: {e}")
            return []

    def release(self):
        """释放模型资源"""
        try:
            if self.model is not None:
                if self.device and self.device.type == "cuda":
                    self.model = self.model.to(torch.device("cpu"))
                del self.model
                self.model = None
                logger.info("[QwenReranker] 模型已释放")

            if self.tokenizer is not None:
                del self.tokenizer
                self.tokenizer = None

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            self._loaded = False
            logger.info("[QwenReranker] 内存已清理")
        except Exception as e:
            logger.error(f"[QwenReranker] 释放模型失败: {e}")
