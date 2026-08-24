"""通话会话管理模块，支持多轮对话上下文与文件持久化。"""

import json
import os
import threading
from collections import OrderedDict
from typing import Dict, Any, List, Optional

from utils.logger import logger
from services.vector_store import add_summary


# 历史持久化根目录
from core.paths import CACHE_DIR
CACHE_DIR = os.path.join(CACHE_DIR, "conversations")

# 记忆摘要提示词
SUMMARY_PROMPT = """请将以下对话内容总结为一段简洁的记忆摘要，保留关键信息和要点：

用户：{user_message}

助手：{assistant_message}

记忆摘要："""


class ConversationSession:
    """单个通话会话，存储多轮文本对话历史。

    支持存储图像、音频等媒体信息，文件保存到 media 目录，历史中记录文件路径。

    会话以 agent_id 为唯一标识，历史持久化到
    backend/cache/conversations/{agent_id}.json，后端重启后可恢复。

    当历史消息超过 max_turns 限制时，会自动生成记忆摘要并存储到向量库，
    同时记录相关媒体文件路径到 metadata。
    """

    def __init__(self, agent_id: str, max_turns: int = 10):
        self.agent_id = agent_id
        self.max_turns = max_turns  # 保留最近 N 轮（1 轮 = user + assistant）
        self.messages = []  # [{"role": "user"|"assistant", "content": "...", "media": {...}}]
        self._lock = threading.Lock()
        self._cache_file = os.path.join(CACHE_DIR, f"{agent_id}.json")
        # 当前轮次的媒体元数据（图片、音频文件路径等）
        self._current_media_metadata = {}
        # 创建时从文件加载历史
        self._load_from_file()

    def add_user_message(self, content: str, media: Optional[Dict[str, Any]] = None):
        with self._lock:
            message = {"role": "user", "content": content}
            if media:
                message["media"] = media
            self.messages.append(message)
            self._trim()
            self._save_to_file()

    def add_assistant_message(self, content: str, media: Optional[Dict[str, Any]] = None):
        with self._lock:
            message = {"role": "assistant", "content": content}
            if media:
                message["media"] = media
            self.messages.append(message)
            self._trim()
            self._save_to_file()

    def set_current_media_metadata(self, metadata: Dict[str, Any]):
        """设置当前轮次的媒体元数据（图片、音频文件路径等）。"""
        with self._lock:
            self._current_media_metadata = metadata.copy()

    def get_current_media_metadata(self) -> Dict[str, Any]:
        """获取当前轮次的媒体元数据。"""
        with self._lock:
            return self._current_media_metadata.copy()

    def get_history(self) -> list:
        with self._lock:
            return list(self.messages)

    def clear(self):
        with self._lock:
            self.messages = []
            self._save_to_file()

    def _trim(self):
        max_msgs = self.max_turns * 2
        if len(self.messages) > max_msgs:
            removed_count = len(self.messages) - max_msgs
            removed_count -= removed_count % 2
            if removed_count > 0:
                removed_messages = self.messages[:removed_count]
                self.messages = self.messages[-max_msgs:]
                logger.debug(f"[Session:{self.agent_id}] 历史已截断至 {max_msgs} 条，移除 {removed_count} 条")

                self._generate_and_store_summary(removed_messages)

    def _generate_and_store_summary(self, removed_messages: List[dict]):
        """生成被移除消息的记忆摘要并存储到向量库。"""
        try:
            user_msg = None
            assistant_msg = None
            for msg in removed_messages:
                if msg["role"] == "user":
                    user_msg = msg["content"]
                elif msg["role"] == "assistant":
                    assistant_msg = msg["content"]

            if not user_msg or not assistant_msg:
                return

            summary = self._generate_summary(user_msg, assistant_msg)
            if not summary:
                return

            metadata = self._current_media_metadata.copy()
            add_summary(self.agent_id, summary, metadata)
            logger.info(f"[Session:{self.agent_id}] 记忆摘要已生成并存储")

            self._current_media_metadata.clear()

        except Exception as e:
            logger.error(f"[Session:{self.agent_id}] 生成记忆摘要失败: {e}")

    def _generate_summary(self, user_message: str, assistant_message: str) -> Optional[str]:
        """使用Qwen模型生成对话摘要。"""
        from core.global_manager import global_manager
        from core.model_manager import ensure_qwen_loaded
        ensure_qwen_loaded()
        qwen_model = global_manager.qwen_model
        if not qwen_model:
            logger.warning("[Session] Qwen模型未加载，无法生成摘要")
            return None

        try:
            prompt = SUMMARY_PROMPT.format(
                user_message=user_message,
                assistant_message=assistant_message
            )

            input_ids = qwen_model.tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=2048
            ).to(qwen_model.device)

            import torch
            with torch.no_grad():
                outputs = qwen_model.model.generate(
                    **input_ids,
                    max_new_tokens=128,
                    temperature=0.1,
                    top_p=0.5,
                    top_k=10,
                    repetition_penalty=1.0,
                    pad_token_id=qwen_model.tokenizer.eos_token_id
                )

            summary = qwen_model.tokenizer.decode(
                outputs[0][input_ids["input_ids"].shape[1]:],
                skip_special_tokens=True
            ).strip()

            return summary

        except Exception as e:
            logger.error(f"[Session] 生成摘要异常: {e}")
            return None

    def _load_from_file(self):
        """从缓存文件加载历史。"""
        try:
            if os.path.exists(self._cache_file):
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.messages = data.get("messages", [])
                logger.info(f"[Session:{self.agent_id}] 从文件加载历史，{len(self.messages)} 条消息")
        except Exception as e:
            logger.warning(f"[Session:{self.agent_id}] 加载历史文件失败: {e}")
            self.messages = []

    def _save_to_file(self):
        """保存历史到缓存文件。"""
        try:
            os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump({"agent_id": self.agent_id, "messages": self.messages}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[Session:{self.agent_id}] 保存历史文件失败: {e}")

    def __repr__(self):
        return f"ConversationSession(agent={self.agent_id}, msgs={len(self.messages)})"


class ConversationManager:
    """全局会话管理器，以 agent_id 为 key 管理通话会话。

    会话不随 WebSocket 连接关闭而销毁，历史持久化到文件，
    下次进入同一智能体页面时可恢复上下文。
    """

    def __init__(self, max_sessions: int = 100):
        self._sessions = OrderedDict()  # key: agent_id
        self._lock = threading.Lock()
        self.max_sessions = max_sessions

    def get_or_create_session(self, agent_id: str) -> ConversationSession:
        """以 agent_id 为 key 获取或创建会话。

        同一智能体复用同一会话，历史跨连接保留。
        """
        with self._lock:
            if agent_id in self._sessions:
                logger.debug(f"[Conversation] 复用会话（agent={agent_id}）")
                return self._sessions[agent_id]
            session = ConversationSession(agent_id)
            self._sessions[agent_id] = session
            self._evict_if_needed()
            logger.info(f"[Conversation] 创建会话（agent={agent_id}），历史 {len(session.messages)} 条")
            return session

    def get_session(self, agent_id: str) -> ConversationSession:
        with self._lock:
            return self._sessions.get(agent_id)

    def remove_session(self, agent_id: str):
        """仅从内存移除（不删文件），下次访问会重新从文件加载。"""
        with self._lock:
            if agent_id in self._sessions:
                del self._sessions[agent_id]
                logger.info(f"[Conversation] 从内存移除会话（agent={agent_id}）")

    def clear_session(self, agent_id: str):
        """清空指定智能体的历史（内存 + 文件）。"""
        with self._lock:
            session = self._sessions.get(agent_id)
        if session:
            session.clear()
            logger.info(f"[Conversation] 已清空历史（agent={agent_id}）")
        else:
            # 内存中没有会话对象，直接删文件
            cache_file = os.path.join(CACHE_DIR, f"{agent_id}.json")
            try:
                if os.path.exists(cache_file):
                    os.remove(cache_file)
                    logger.info(f"[Conversation] 已删除历史文件（agent={agent_id}）")
            except Exception as e:
                logger.warning(f"[Conversation] 删除历史文件失败: {e}")

    def _evict_if_needed(self):
        while len(self._sessions) > self.max_sessions:
            evicted_id, _ = self._sessions.popitem(last=False)
            logger.info(f"[Conversation] 会话数超限，从内存淘汰最旧会话（agent={evicted_id}）")


_conversation_manager = None


def get_conversation_manager() -> ConversationManager:
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
    return _conversation_manager
