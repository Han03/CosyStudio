"""剧本生成与管理服务。

核心流程：
1. 根据书籍 ID 创建剧本生成任务（异步）
2. 逐章节读取电子书内容，调用 Qwen 大模型生成演播剧本
3. 将 Qwen 返回的演播剧本拆分为多条台词（角色、指令、内容）
4. 存入 script_lines 表

台词格式（Qwen 返回 JSON）：
[
  {"role": "旁白", "instruction": "用平静自然的语气朗读", "content": "那是一个阳光明媚的早晨..."},
  {"role": "主角", "instruction": "用疑惑的语气提问", "content": "这是哪里？"},
  ...
]
"""

import re
import os
import json
import time
import asyncio
from typing import Optional, List, Dict, Any, Tuple, Callable

from utils.logger import log_manager
from repositories import (
    get_script, update_script, add_script_chapters, get_script_chapter_count,
    get_script_chapter, get_max_chapter_index, delete_script_lines_by_chapter,
    delete_script_chapter, update_script_chapter, get_ebook, get_chapters,
    get_scripts_by_book, add_script, get_script_chapters_all, add_script_lines,
    get_script_characters, add_script_characters, get_script_line_count,
    get_script_lines, get_script_lines_paged, get_script_chapters_with_lines,
    update_script_line, insert_line_at_position, delete_script_line,
    delete_script_lines, delete_script, _get_conn, _lock
)
from services.ebook_library import get_ebook_library_service
from services.media_manager import get_media_manager
from domain.agent_tasks import agent_task_manager
from services.json_parser import parse_json_response, try_parse_ndjson, extract_json_lines_stream, extract_json_objects_stream, try_parse_json_object


class ScriptService:
    """剧本生成与管理服务。"""

    def __init__(self):
        self._logger = log_manager.get_logger("script_service")
        self._ebook_service = get_ebook_library_service()
        self._media = get_media_manager()
        self._running_tasks: dict = {}
        self._stop_flags: dict = {}
        self._generation_queues: dict = {}
        self._generation_listeners: dict = {}

    def register_task(self, script_id: int, task: asyncio.Task):
        self._running_tasks[script_id] = task

    def is_stopped(self, script_id: int) -> bool:
        """检查指定剧本的生成是否已被请求停止。"""
        return self._stop_flags.get(script_id, False)

    def stop_generation(self, script_id: int) -> dict:
        """停止剧本生成任务，将状态从 running 改为 ready。

        设置停止标志，生成循环检测到标志后主动退出。
        """
        from core.global_manager import global_manager

        script = get_script(script_id)
        if script is None:
            return {"success": False, "message": "剧本不存在"}

        if script.get("status") != "running":
            return {"success": False, "message": "剧本未处于生成状态"}

        self._stop_flags[script_id] = True
        self._logger.info(f"[ScriptService] 已设置停止标志: script_id={script_id}")

        task = self._running_tasks.pop(script_id, None)
        if task is not None and not task.done():
            task.cancel()
            self._logger.info(f"[ScriptService] 已取消生成任务: script_id={script_id}")

        task_id = script.get("task_id", "")
        if task_id:
            agent_task_manager.update_task(task_id, status="failed", error="用户手动停止")

        if global_manager.is_model_busy():
            global_manager.release_model()

        update_script(script_id, status="ready", progress_message="", generating_chapter_index=0)
        self._logger.info(f"[ScriptService] 剧本生成已停止: script_id={script_id}")
        return {"success": True, "message": "剧本生成已停止"}

    def clear_stop_flag(self, script_id: int):
        """清除停止标志（在开始新生成任务时调用）。"""
        self._stop_flags.pop(script_id, None)

    def get_generation_queue(self, script_id: int):
        """获取剧本的生成消息队列，不存在则创建。"""
        if script_id not in self._generation_queues:
            self._generation_queues[script_id] = asyncio.Queue()
        return self._generation_queues[script_id]

    def register_listener(self, script_id: int, listener_id: str, callback):
        """注册生成事件监听器。"""
        if script_id not in self._generation_listeners:
            self._generation_listeners[script_id] = {}
        self._generation_listeners[script_id][listener_id] = callback

    def unregister_listener(self, script_id: int, listener_id: str):
        """注销生成事件监听器。"""
        if script_id in self._generation_listeners:
            self._generation_listeners[script_id].pop(listener_id, None)

    def notify_listeners(self, script_id: int, event_type: str, data: dict):
        """通知所有监听器。"""
        if script_id not in self._generation_listeners:
            return
        for listener_id, callback in list(self._generation_listeners[script_id].items()):
            try:
                callback(event_type, data)
            except Exception as e:
                self._logger.warning(f"[ScriptService] 监听器回调失败: {listener_id}, {e}")

    async def _broadcast_generation_event(self, script_id: int, event_type: str, data: dict):
        """广播生成事件到消息队列。"""
        queue = self.get_generation_queue(script_id)
        try:
            await queue.put({"type": event_type, "data": data})
        except Exception as e:
            self._logger.warning(f"[ScriptService] 队列广播失败: {e}")

    # ===================== Qwen 调用 =====================

    # 剧本生成专用身份描述（会通过 agent_role 模板包装为系统提示）
    _SCRIPT_AGENT_DESC = (
        "你是一位专业的有声书剧本编剧，擅长将小说章节内容逐句拆分为演播剧本。"
        "你必须严格按照用户要求的格式输出：每行一个JSON对象，不要输出JSON数组，"
        "不要输出任何解释文字，不要使用markdown代码块。"
    )

    # 剧本生成专用生成参数
    _SCRIPT_GENERATE_PARAMS = {
        "temperature": 0.3,
        "top_p": 0.8,
        "top_k": 20,
        "do_sample": True,
        "repetition_penalty": 1.05,
        "max_new_tokens": 3072,
    }

    async def _call_qwen_json(self, prompt: str, context: str, retries: int = 2) -> Any:
        """调用 Qwen 并解析 JSON，失败跳过"""
        from core.model_executor import ModelExecutor
        
        executor = ModelExecutor()
        
        try:
            result = ""
            async for chunk in executor.execute_text_predict(
                prompt,
                system_prompt=self._SCRIPT_AGENT_DESC,
                stream=False,
                generate_params=self._SCRIPT_GENERATE_PARAMS
            ):
                if chunk.get("error"):
                    self._logger.warning(f"[QWEN_SCRIPT] 生成失败: {chunk['error']}")
                    return []
                if chunk.get("type") == "text":
                    result += chunk.get("content", "")
            
            self._logger.info(f"[QWEN_SCRIPT] {context} , 返回长度={len(result) if result else 0}")

            parsed = parse_json_response(result)
            if parsed is not None:
                return parsed
        except Exception as e:
            self._logger.warn(f"[QWEN_SCRIPT] 生成失败返回空内容 , exception = {e}")
            return []

        return None

    # JSON 解析工具已迁移到 services/json_parser.py

    # ===================== 章节文件管理 =====================

    def _get_chapter_dir(self, script_id: int) -> str:
        """获取剧本章节文件目录的绝对路径。"""
        scripts_dir = self._media.ensure_module_dir("document", "scripts")
        chapter_dir = os.path.join(scripts_dir, str(script_id), "chapters")
        os.makedirs(chapter_dir, exist_ok=True)
        return chapter_dir

    def _split_and_save_chapters(self, script_id: int, book_id: int) -> int:
        """将原文件按章节拆分保存为独立文件，并写入 script_chapters 表。

        Returns: 拆分的章节数量
        """
        chapters = get_chapters(book_id)
        if not chapters:
            return 0

        chapter_dir = self._get_chapter_dir(script_id)
        records = []

        for ch in chapters:
            idx = ch["chapter_index"]
            title = ch.get("title", "")
            try:
                chapter_data = self._ebook_service.get_chapter_content(book_id, idx)
                content = chapter_data["content"] if chapter_data else ""
            except Exception as e:
                self._logger.warning(f"[ScriptService] 读取章节{idx}内容失败: {e}")
                content = ""

            filename = f"{idx}.txt"
            filepath = os.path.join(chapter_dir, filename)
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                self._logger.error(f"[ScriptService] 保存章节文件失败: {e}")
                continue

            relative_path = f"document/scripts/{script_id}/chapters/{filename}"
            word_count = ch.get("word_count", 0) or len(content)
            records.append({
                "chapter_index": idx,
                "title": title,
                "file_path": relative_path,
                "word_count": word_count,
            })

        if records:
            add_script_chapters(script_id, records)
            self._logger.info(f"[ScriptService] 拆分 {len(records)} 个章节文件: script_id={script_id}")

        return len(records)

    def _ensure_chapters_migrated(self, script_id: int) -> bool:
        """确保旧剧本已将 ebook_chapters 迁移到 script_chapters。

        若 script_chapters 表中无该剧本的记录，则从 ebook_chapters 拆分保存。
        返回 True 表示已迁移或已存在记录，False 表示无法迁移（无 ebook_chapters）。
        """
        if get_script_chapter_count(script_id) > 0:
            return True
        script = get_script(script_id)
        if script is None:
            return False
        book_id = script.get("book_id")
        if not book_id:
            return False
        count = self._split_and_save_chapters(script_id, book_id)
        if count > 0:
            update_script(script_id, chapter_count=count)
            self._logger.info(f"[ScriptService] 旧剧本章节已迁移: script_id={script_id}, count={count}")
            return True
        return False

    def _read_script_chapter_content(self, script_id: int, chapter_index: int) -> Optional[str]:
        """从独立章节文件读取内容。文件不存在返回 None。"""
        chapter = get_script_chapter(script_id, chapter_index)
        if not chapter or not chapter.get("file_path"):
            return None
        file_info = self._media.get_file_by_path(chapter["file_path"])
        if not file_info:
            return None
        try:
            with open(file_info["absolute_path"], "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            self._logger.warning(f"[ScriptService] 读取章节文件失败: {e}")
            return None

    def _get_chapter_content_with_fallback(self, script_id: int, book_id: int,
                                            chapter_index: int) -> Optional[str]:
        """优先从独立文件读取，回退到原文件 seek 读取。"""
        content = self._read_script_chapter_content(script_id, chapter_index)
        if content is not None:
            return content
        if book_id:
            chapter_data = self._ebook_service.get_chapter_content(book_id, chapter_index)
            if chapter_data:
                return chapter_data.get("content", "")
        return None

    def add_chapter(self, script_id: int, title: str, content: str = "",
                    chapter_index: Optional[int] = None) -> Dict[str, Any]:
        """新增章节，保存为独立文件。

        Args:
            chapter_index: 目标章节索引。如果该索引已有章节则覆写内容；
                           如果为 None 则追加到末尾（max_idx + 1）。
        """
        script = get_script(script_id)
        if script is None:
            raise ValueError("剧本不存在")

        self._ensure_chapters_migrated(script_id)

        if chapter_index is not None:
            existing = get_script_chapter(script_id, chapter_index)
            if existing and existing.get("file_path"):
                # 目标索引已有章节 → 覆写内容
                self.update_chapter_content(script_id, chapter_index, content)
                return {
                    "chapter_index": chapter_index,
                    "title": existing.get("title", title),
                    "file_path": existing["file_path"],
                    "word_count": len(content) if content else 0,
                }
            # 目标索引无章节 → 在该索引创建
            new_idx = chapter_index
        else:
            max_idx = get_max_chapter_index(script_id)
            new_idx = max_idx + 1

        chapter_dir = self._get_chapter_dir(script_id)
        filename = f"{new_idx}.txt"
        filepath = os.path.join(chapter_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content or "")

        relative_path = f"document/scripts/{script_id}/chapters/{filename}"
        word_count = len(content) if content else 0
        add_script_chapters(script_id, [{
            "chapter_index": new_idx,
            "title": title,
            "file_path": relative_path,
            "word_count": word_count,
        }])

        new_count = get_script_chapter_count(script_id)
        update_script(script_id, chapter_count=new_count)

        self._logger.info(f"[ScriptService] 新增章节: script_id={script_id}, idx={new_idx}, title={title}")
        return {
            "chapter_index": new_idx,
            "title": title,
            "file_path": relative_path,
            "word_count": word_count,
        }

    def delete_chapter(self, script_id: int, chapter_index: int) -> Tuple[bool, str]:
        """删除章节：删除文件、DB记录、该章节台词。"""
        self._ensure_chapters_migrated(script_id)
        chapter = get_script_chapter(script_id, chapter_index)
        if not chapter:
            return False, "章节不存在"

        if chapter.get("file_path"):
            file_info = self._media.get_file_by_path(chapter["file_path"])
            if file_info and os.path.exists(file_info["absolute_path"]):
                try:
                    os.remove(file_info["absolute_path"])
                except Exception as e:
                    self._logger.warning(f"[ScriptService] 删除章节文件失败: {e}")

        delete_script_lines_by_chapter(script_id, chapter_index)
        delete_script_chapter(script_id, chapter_index)

        new_count = get_script_chapter_count(script_id)
        update_script(script_id, chapter_count=new_count)

        self._logger.info(f"[ScriptService] 删除章节: script_id={script_id}, idx={chapter_index}")
        return True, f"章节 {chapter_index} 已删除"

    def update_chapter_content(self, script_id: int, chapter_index: int, content: str) -> bool:
        """覆写章节文件内容，更新 word_count。"""
        from repositories import add_chapter_version
        self._ensure_chapters_migrated(script_id)
        chapter = get_script_chapter(script_id, chapter_index)
        if not chapter or not chapter.get("file_path"):
            return False
        file_info = self._media.get_file_by_path(chapter["file_path"])
        if not file_info:
            return False
        old_content = ""
        try:
            with open(file_info["absolute_path"], "r", encoding="utf-8") as f:
                old_content = f.read()
        except Exception:
            pass
        if old_content and old_content.strip():
            add_chapter_version(script_id, chapter_index, old_content)
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        with open(file_info["absolute_path"], "w", encoding="utf-8") as f:
            f.write(content)
        update_script_chapter(script_id, chapter_index, word_count=len(content))
        return True

    def update_chapter_title(self, script_id: int, chapter_index: int, title: str) -> bool:
        return update_script_chapter(script_id, chapter_index, title=title)

    def get_chapter_content(self, script_id: int, chapter_index: int) -> Optional[Dict[str, Any]]:
        """获取章节内容（优先独立文件，回退原文件）。"""
        script = get_script(script_id)
        if script is None:
            return None
        book_id = script.get("book_id")

        chapter = get_script_chapter(script_id, chapter_index)
        if chapter:
            content = self._read_script_chapter_content(script_id, chapter_index)
            if content is not None:
                return {
                    "chapter_index": chapter_index,
                    "chapter_title": chapter.get("title", ""),
                    "content": content,
                    "word_count": chapter.get("word_count", 0),
                }

        if book_id:
            chapter_data = self._ebook_service.get_chapter_content(book_id, chapter_index)
            if chapter_data:
                return chapter_data

        return None

    # ===================== 剧本生成 =====================

    def create_script(self, book_id: int, name: str = "",
                      description: str = "") -> Dict[str, Any]:
        """创建剧本主体（仅创建剧本，不生成台词）。

        若该书已有剧本，则直接返回已有剧本，不重复创建。

        返回: {"success": bool, "script_id": int, "message": str}
        """
        book = get_ebook(book_id)
        if book is None:
            return {"success": False, "message": "电子书不存在"}

        chapters = get_chapters(book_id)
        if not chapters:
            return {"success": False, "message": "电子书没有章节，无法生成剧本"}

        existing = get_scripts_by_book(book_id)
        if existing and len(existing) > 0:
            script = existing[0]
            self._logger.info(
                f"[ScriptService] 书籍已有剧本，直接返回: book_id={book_id}, script_id={script['id']}"
            )
            return {
                "success": True,
                "script_id": script["id"],
                "message": "剧本已存在",
            }

        script_name = name or f"{book['title']}"

        script_id = add_script(
            book_id=book_id,
            name=script_name,
            description=description,
            chapter_count=len(chapters),
            task_id="",
            status="ready",
        )

        self._split_and_save_chapters(script_id, book_id)

        self._logger.info(f"[ScriptService] 剧本已加载: script_id={script_id}, book_id={book_id}")
        return {
            "success": True,
            "script_id": script_id,
            "message": "剧本已加载",
        }

    def create_script_task(self, book_id: int, name: str = "",
                          description: str = "") -> Dict[str, Any]:
        """创建剧本生成任务（非阻塞，包含完整生成流程）。

        返回: {"success": bool, "script_id": int, "task_id": str, "message": str}
        """
        book = get_ebook(book_id)
        if book is None:
            return {"success": False, "message": "电子书不存在"}

        chapters = get_chapters(book_id)
        if not chapters:
            return {"success": False, "message": "电子书没有章节，无法生成剧本"}

        script_name = name or f"{book['title']}"
        task_id = agent_task_manager.create_task(
            agent_id=f"book_{book_id}",
            name=f"生成剧本: {script_name}",
            description=description or f"为《{book['title']}》生成演播剧本",
        )

        script_id = add_script(
            book_id=book_id,
            name=script_name,
            description=description,
            chapter_count=len(chapters),
            task_id=task_id,
            status="pending",
        )

        self._split_and_save_chapters(script_id, book_id)

        asyncio.create_task(self._generate_script_async(script_id, book_id, chapters, task_id))

        self._logger.info(f"[ScriptService] 剧本生成任务已创建: script_id={script_id}, task_id={task_id}")
        return {
            "success": True,
            "script_id": script_id,
            "task_id": task_id,
            "message": "剧本生成任务已创建",
        }

    async def generate_script_stream(
        self,
        script_id: int,
        book_id: int,
        on_line_added: Optional[Callable[[int, List[Dict[str, Any]]], None]] = None,
        on_character_added: Optional[Callable[[int, List[str]], None]] = None,
    ) -> bool:
        """流式生成剧本，逐章节生成，每生成一条台词就调用回调。

        Args:
            script_id: 剧本 ID
            book_id: 书籍 ID
            on_line_added: 回调函数，签名为 on_line_added(script_id, lines)，
                           每当有新的台词生成时调用
            on_character_added: 回调函数，签名为 on_character_added(script_id, roles)，
                                每当发现新角色时调用

        Returns:
            True 表示完全成功，False 表示有错误
        """
        script = get_script(script_id)
        if script is None:
            self._logger.error(f"[ScriptService] 剧本不存在: script_id={script_id}")
            return False

        task_id = script.get("task_id", "")
        chapters = get_script_chapters_all(script_id)
        if not chapters:
            chapters = get_chapters(book_id)
        if not chapters:
            self._logger.error(f"[ScriptService] 书籍没有章节: book_id={book_id}")
            if task_id:
                agent_task_manager.update_task(
                    task_id, status="failed", error="书籍没有章节"
                )
            update_script(script_id, status="failed")
            return False

        total = len(chapters)
        self.clear_stop_flag(script_id)
        if task_id:
            agent_task_manager.update_task(
                task_id, status="running", progress=0,
                message=f"开始生成剧本，共 {total} 章"
            )
        update_script(script_id, status="running")
        total_lines = 0
        has_error = False

        async def _on_line_added(sid: int, lines: List[Dict[str, Any]]):
            nonlocal total_lines

            new_roles = await asyncio.to_thread(self._save_new_characters, sid, lines)

            inserted = await asyncio.to_thread(add_script_lines, sid, lines)
            total_lines += len(inserted)

            chapter_idx = inserted[0]["chapter_index"] if inserted else 0

            self.notify_listeners(sid, "lines_added", {
                "lines": inserted,
                "chapter_index": chapter_idx,
            })

            try:
                from infrastructure.websocket_broadcast import ws_broadcast_manager
                for line in inserted:
                    line_id = line.get("id")
                    if line_id:
                        asyncio.create_task(ws_broadcast_manager.broadcast_line_generated(sid, line_id))
                # 广播本次涉及角色的最新数据（含 line_count），前端增量合并，避免频繁调用角色查询接口
                involved_roles = list({line.get("role", "旁白") for line in lines if line.get("role")})
                if involved_roles:
                    all_chars = await asyncio.to_thread(get_script_characters, sid)
                    updated_chars = [c for c in all_chars if c.get("role") in involved_roles]
                    if updated_chars:
                        asyncio.create_task(ws_broadcast_manager.broadcast_characters_updated(sid, updated_chars))
            except Exception as e:
                self._logger.warning(f"[ScriptService] WebSocket通知失败: {e}")

            if new_roles and on_character_added:
                try:
                    on_character_added(sid, new_roles)
                except Exception as e:
                    self._logger.warning(f"[ScriptService] 角色回调执行失败: {e}")

            if on_line_added:
                try:
                    on_line_added(sid, inserted)
                except Exception as e:
                    self._logger.warning(f"[ScriptService] 外部回调执行失败: {e}")

        for i, chapter in enumerate(chapters):
            if self.is_stopped(script_id):
                self._logger.info(f"[ScriptService] 检测到停止标志，中断章节循环: script_id={script_id}")
                break

            chapter_index = chapter["chapter_index"]
            chapter_title = chapter["title"]

            if task_id:
                agent_task_manager.update_task(
                    task_id,
                    progress=int(i / total * 100),
                    message=f"正在生成第 {i+1}/{total} 章: {chapter_title}",
                )
            update_script(script_id, progress_message=f"正在生成第 {i+1}/{total} 章: {chapter_title}", generating_chapter_index=chapter_index)

            try:
                chapter_text = self._get_chapter_content_with_fallback(script_id, book_id, chapter_index)
                if not chapter_text:
                    self._logger.warning(f"[ScriptService] 读取章节内容失败: chapter_index={chapter_index}")
                    continue

                if len(chapter_text) > 8000:
                    chapter_text = chapter_text[:8000] + "\n...(内容已截断)"

                lines = await self._generate_chapter_lines_stream(
                    script_id, chapter_index, chapter_title, chapter_text,
                    on_line_added=_on_line_added,
                )

                if lines:
                    self._logger.info(
                        f"[ScriptService] 章节{chapter_index} 生成 {len(lines)} 条台词"
                    )
                else:
                    self._logger.warning(
                        f"[ScriptService] 章节{chapter_index} 未生成台词"
                    )

            except Exception as e:
                has_error = True
                error_msg = f"生成章节{chapter_index}失败: {str(e)}"
                self._logger.error(f"[ScriptService] {error_msg}")
                if task_id:
                    agent_task_manager.update_task(
                        task_id,
                        status="failed",
                        error=error_msg,
                        progress=int(i / total * 100),
                    )
                update_script(script_id, status="failed", error=error_msg)
                break

        if has_error:
            self._logger.error(
                f"[ScriptService] 剧本生成失败: script_id={script_id}, 已生成 {total_lines} 条语句"
            )
            return False

        if self.is_stopped(script_id):
            self._logger.info(
                f"[ScriptService] 剧本生成已被用户停止: script_id={script_id}, 已生成 {total_lines} 条语句"
            )
            update_script(script_id, status="ready", progress_message="", generating_chapter_index=0)
            return True

        update_script(script_id, status="ready", chapter_count=total, progress_message="", generating_chapter_index=0)
        if task_id:
            agent_task_manager.update_task(
                task_id,
                status="ready",
                progress=100,
                message=f"剧本生成完成，共 {total} 章 {total_lines} 条台词",
                result={"script_id": script_id, "total_lines": total_lines},
            )
        self._logger.info(
            f"[ScriptService] 剧本生成完成: script_id={script_id}, 总句数={total_lines}"
        )
        return True

    async def _generate_script_async(self, script_id: int, book_id: int,
                                     chapters: List[Dict[str, Any]], task_id: str):
        """异步生成剧本：调用流式生成方法。"""
        await self.generate_script_stream(script_id, book_id)

    # JSON 流式解析工具已迁移到 services/json_parser.py

    def _build_line_from_object(self, item: Dict[str, Any],
                                chapter_index: int, line_no: int,
                                recent_context: List[Dict[str, Any]]
                                ) -> Optional[Dict[str, Any]]:
        """将解析出的 JSON 对象转为台词，并执行逐条后处理。"""
        if not isinstance(item, dict):
            return None
        role = item.get("role", "旁白").strip() or "旁白"
        content = item.get("content", "").strip()
        if not content:
            return None
        content = self._clean_dialogue_content(role, content)
        if not content:
            return None
        new_line = {
            "chapter_index": chapter_index,
            "line_no": line_no,
            "role": role,
            "instruction": item.get("instruction", "").strip(),
            "content": content,
            "type": item.get("type", ""),
        }
        processed = self._post_process_line(new_line, recent_context)
        return processed

    async def _generate_chapter_lines_stream(
        self,
        script_id: int,
        chapter_index: int,
        chapter_title: str,
        chapter_text: str,
        on_line_added: Optional[Callable[[int, List[Dict[str, Any]]], None]] = None,
    ) -> List[Dict[str, Any]]:
        """流式生成单章节台词，边生成边解析边回调。

        采用 NDJSON 格式（每行一个 JSON 对象），Qwen 每输出一行就立即解析
        并通过 on_line_added 回调发送，避免后处理阻塞流式输出。

        Args:
            script_id: 剧本 ID
            chapter_index: 章节序号
            chapter_title: 章节标题
            chapter_text: 章节文本
            on_line_added: 回调函数，签名为 on_line_added(script_id, lines)，
                           每当解析出新的台词时调用

        Returns:
            所有已解析的台词列表
        """
        from core.model_executor import ModelExecutor
        
        executor = ModelExecutor()
        
        segments = self._split_chapter_text(chapter_text, max_len=2000)
        all_lines: List[Dict[str, Any]] = []
        line_no_offset = 0
        recent_context: List[Dict[str, Any]] = []

        for seg_idx, segment in enumerate(segments):
            if self.is_stopped(script_id):
                self._logger.info(f"[QWEN_SCRIPT_STREAM] 检测到停止标志，退出生成: script_id={script_id}")
                break

            prompt = self._build_prompt(chapter_title, segment, seg_idx, len(segments))
            context = f"剧本流式生成 script={script_id} chapter={chapter_index} seg={seg_idx+1}/{len(segments)}"
            self._logger.info(f"[QWEN_SCRIPT_STREAM] {context}")

            seg_lines: List[Dict[str, Any]] = []
            buffer = ""

            try:
                async for chunk in executor.execute_text_predict(
                    prompt,
                    system_prompt=self._SCRIPT_AGENT_DESC,
                    stream=True,
                    generate_params=self._SCRIPT_GENERATE_PARAMS
                ):
                    if self.is_stopped(script_id):
                        self._logger.info(f"[QWEN_SCRIPT_STREAM] 检测到停止标志，中断消费: script_id={script_id}")
                        break

                    if chunk.get("error"):
                        self._logger.warning(f"[QWEN_SCRIPT_STREAM] 生成错误: {chunk['error']}")
                        break

                    chunk_type = chunk.get("type")
                    if chunk_type == "text":
                        buffer += chunk.get("content", "")
                    elif chunk_type == "correction":
                        continue
                    elif chunk_type == "finish":
                        break

                    # 按行增量解析：遇到换行立即解析上一行
                    new_objs, buffer = extract_json_lines_stream(buffer)
                    if new_objs:
                        for item in new_objs:
                            new_line = self._build_line_from_object(
                                item, chapter_index,
                                line_no_offset + len(seg_lines) + 1,
                                recent_context,
                            )
                            if new_line is None:
                                continue
                            seg_lines.append(new_line)
                            recent_context.append(new_line)
                            if len(recent_context) > 30:
                                recent_context = recent_context[-20:]

                            if on_line_added:
                                try:
                                    if asyncio.iscoroutinefunction(on_line_added):
                                        await on_line_added(script_id, [new_line])
                                    else:
                                        on_line_added(script_id, [new_line])
                                except Exception as e:
                                    self._logger.warning(f"[ScriptService] 回调执行失败: {e}")

            except Exception as e:
                self._logger.warn(f"[QWEN_SCRIPT_STREAM] 生成失败 , exception = {e}")

            # 处理当前段剩余 buffer 中未以换行结尾的最后一行
            if buffer.strip():
                obj = try_parse_json_object(buffer.strip())
                if obj is not None:
                    new_line = self._build_line_from_object(
                        obj, chapter_index,
                        line_no_offset + len(seg_lines) + 1,
                        recent_context,
                    )
                    if new_line is not None:
                        seg_lines.append(new_line)
                        recent_context.append(new_line)
                        if len(recent_context) > 30:
                            recent_context = recent_context[-20:]
                        if on_line_added:
                            try:
                                if asyncio.iscoroutinefunction(on_line_added):
                                    await on_line_added(script_id, [new_line])
                                else:
                                    on_line_added(script_id, [new_line])
                            except Exception as e:
                                self._logger.warning(f"[ScriptService] 回调执行失败: {e}")

            if seg_lines:
                all_lines.extend(seg_lines)
                line_no_offset += len(seg_lines)
                self._logger.info(
                    f"[ScriptService] 章节{chapter_index}第{seg_idx+1}段 生成 {len(seg_lines)} 条台词"
                )

        # 重新编号 line_no（后处理已在逐条中完成，无需批量处理）
        line_no = 0
        for line in all_lines:
            line_no += 1
            line["line_no"] = line_no

        return all_lines

    def _post_process_line(self, line: Dict[str, Any],
                           recent_lines: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """对单条语句进行后处理，使用最近几条语句作为上下文推断说话人。

        Args:
            line: 待处理的单条语句
            recent_lines: 最近的语句列表（用于说话人推断上下文）

        Returns:
            处理后的语句，若内容为空则返回 None
        """
        role = line.get("role", "旁白").strip() or "旁白"
        content = line.get("content", "").strip()
        line_type = line.get("type", "")

        if not content:
            return None

        is_dialogue = False
        quote_chars = '"\'\u2018\u2019\u201c\u201d'

        if line_type == "dialogue":
            is_dialogue = True
        elif role != "旁白":
            is_dialogue = True
        elif len(content) >= 2 and content[0] in quote_chars and content[-1] in quote_chars:
            is_dialogue = True

        if is_dialogue and role in ("旁白", "效果音", ""):
            inferred = self._infer_speaker_from_recent(recent_lines)
            if inferred:
                line["role"] = inferred
                role = inferred
            else:
                line["role"] = "未知"
                role = "未知"

        if is_dialogue:
            content = self._strip_quotes(content)
            line["content"] = content

        return line if content else None

    @staticmethod
    def _infer_speaker_from_recent(recent_lines: List[Dict[str, Any]]) -> str:
        """根据最近的语句列表推断当前对话的说话人。"""
        dialogue_speakers = []
        for line in reversed(recent_lines[-20:]):
            r = line.get("role", "旁白")
            lt = line.get("type", "")
            if r not in ("旁白", "效果音", "") or lt == "dialogue":
                dialogue_speakers.append(r)

        if not dialogue_speakers:
            return ""

        if len(dialogue_speakers) >= 2 and dialogue_speakers[0] != dialogue_speakers[1]:
            return dialogue_speakers[1]

        return dialogue_speakers[0]

    def _post_process_lines(self, lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """后处理生成的台词，修复常见问题。"""
        if not lines:
            return lines

        result = []
        last_speaker = "旁白"
        last_dialogue_speaker = "未知"

        for line in lines:
            role = line.get("role", "旁白").strip() or "旁白"
            content = line.get("content", "").strip()
            line_type = line.get("type", "")

            if not content:
                continue

            is_dialogue = False
            quote_chars = '"\'\u2018\u2019\u201c\u201d'

            if line_type == "dialogue":
                is_dialogue = True
            elif role != "旁白":
                is_dialogue = True
            elif len(content) >= 2 and content[0] in quote_chars and content[-1] in quote_chars:
                is_dialogue = True

            if is_dialogue and role in ("旁白", "效果音", ""):
                inferred = self._infer_speaker(lines, len(result))
                if inferred:
                    line["role"] = inferred
                    role = inferred
                else:
                    line["role"] = "未知"
                    role = "未知"

            if is_dialogue:
                last_dialogue_speaker = role
                content = self._strip_quotes(content)
                line["content"] = content

            if content:
                result.append(line)
                last_speaker = role

        return result

    @staticmethod
    def _strip_quotes(content: str) -> str:
        """去掉字符串首尾的引号（各种类型）。"""
        quote_chars = '"\'\u2018\u2019\u201c\u201d'
        result = content.strip()
        changed = True
        while changed and len(result) >= 2:
            changed = False
            if result[0] in quote_chars:
                result = result[1:]
                changed = True
            if result and result[-1] in quote_chars:
                result = result[:-1]
                changed = True
            result = result.strip()
        return result

    @staticmethod
    def _infer_speaker(lines: List[Dict[str, Any]], current_idx: int) -> str:
        """根据上下文推断当前对话的说话人。"""
        dialogue_speakers = []
        for i in range(current_idx - 1, max(-1, current_idx - 20), -1):
            r = lines[i].get("role", "旁白")
            lt = lines[i].get("type", "")
            if r not in ("旁白", "效果音", "") or lt == "dialogue":
                dialogue_speakers.append(r)

        if not dialogue_speakers:
            return ""

        if len(dialogue_speakers) >= 2 and dialogue_speakers[0] != dialogue_speakers[1]:
            return dialogue_speakers[1]

        return dialogue_speakers[0]

    async def _generate_chapter_lines(self, script_id: int, chapter_index: int,
                                      chapter_title: str, chapter_text: str) -> List[Dict[str, Any]]:
        """调用 Qwen 为单个章节生成台词。

        对于长章节，按段落分割后分段处理，最后合并结果。
        """
        # 按自然段落分割，每段控制在 1500 字以内
        segments = self._split_chapter_text(chapter_text, max_len=2000)

        all_lines = []
        line_no_offset = 0

        for seg_idx, segment in enumerate(segments):
            prompt = self._build_prompt(chapter_title, segment, seg_idx, len(segments))
            context = f"剧本生成 script={script_id} chapter={chapter_index} seg={seg_idx+1}/{len(segments)}"

            result = await self._call_qwen_json(prompt, context)
            if result is None:
                continue

            # 统一处理返回格式
            if isinstance(result, dict):
                lines_data = result.get("lines", result.get("script", []))
            elif isinstance(result, list):
                lines_data = result
            else:
                continue

            # 规范化每条语句
            for item in lines_data:
                if not isinstance(item, dict):
                    continue
                role = item.get("role", "旁白").strip() or "旁白"
                content = item.get("content", "").strip()
                if not content:
                    continue
                # 清理对话内容中混入的叙述前缀（如"杨峰一愣："）
                content = self._clean_dialogue_content(role, content)
                if not content:
                    continue
                all_lines.append({
                    "chapter_index": chapter_index,
                    "line_no": line_no_offset + 1,
                    "role": role,
                    "instruction": item.get("instruction", "").strip(),
                    "content": content,
                    "type": item.get("type", ""),
                })
                line_no_offset += 1

        all_lines = self._post_process_lines(all_lines)
        line_no = 0
        for line in all_lines:
            line_no += 1
            line["line_no"] = line_no

        return all_lines

    @staticmethod
    def _clean_dialogue_content(role: str, content: str) -> str:
        """清理对话内容中混入的叙述前缀和多余引号。"""
        if role == "旁白":
            return content.strip()
        # 引号字符集合：直引号、弯引号（中文/英文）
        quote_chars = '"\'\u2018\u2019\u201c\u201d'  # "'‘’“”
        # 匹配 "角色名+动作/状态描述+：" 后跟引号台词的模式
        pattern = r'^[\u4e00-\u9fa5\w]{1,8}[^' + quote_chars + r']*[：:]\s*[' + quote_chars + r'](.{2,})[' + quote_chars + r']\s*$'
        match = re.match(pattern, content)
        if match:
            return match.group(1).strip()
        # 去掉开头的 "XX说：" / "XX道：" 等前缀
        content = re.sub(
            r'^[\u4e00-\u9fa5\w]{1,8}(说|道|问|答|喊|叫|笑|怒|叹)[^' + quote_chars + r']*[：:]\s*',
            '',
            content,
        )
        # 去掉首尾的引号（各种引号格式）
        content = content.strip()
        # 首尾都是引号（不要求类型相同）则去掉
        if len(content) >= 3:
            first_char = content[0]
            last_char = content[-1]
            if first_char in quote_chars and last_char in quote_chars:
                content = content[1:-1].strip()
        return content.strip()

    def _split_chapter_text(self, text: str, max_len: int = 2000) -> List[str]:
        """将章节文本按自然段落分割为不超过 max_len 字的片段。"""
        if len(text) <= max_len:
            return [text]

        paragraphs = text.split("\n")
        segments = []
        current = ""

        for para in paragraphs:
            if len(current) + len(para) + 1 > max_len and current:
                segments.append(current.strip())
                current = para
            else:
                current = current + "\n" + para if current else para

        if current.strip():
            segments.append(current.strip())

        return segments

    def _build_prompt(self, chapter_title: str, chapter_text: str,
                      seg_idx: int = 0, seg_total: int = 1) -> str:
        """构造 Qwen 提示词（NDJSON 格式：每行一个 JSON 对象）。"""
        seg_info = ""
        if seg_total > 1:
            seg_info = f"（本段为该章节的第 {seg_idx+1}/{seg_total} 段，只处理本段）"

        example = (
            '{"role":"旁白","instruction":"用平静自然的语气朗读","content":"夜色渐深，树林里传来一阵脚步声。","type":"narration"}\n'
            '{"role":"张三","instruction":"非常愤怒地说这句话","content":"你为什么要这么做？","type":"dialogue"}\n'
            '{"role":"旁白","instruction":"用平静自然的语气朗读","content":"张三指着李四的鼻子骂道。","type":"narration"}\n'
            '{"role":"李四","instruction":"用疑惑的语气提问","content":"我怎么了？","type":"dialogue"}'
        )

        return (
            "小说转演播剧本，逐行输出JSON。" + seg_info + "\n\n"
            "字段：role(角色名/旁白) instruction(语气指令) content(原文) type(narration/dialogue)\n\n"
            "【对话识别】\n"
            "所有「」“”''引号包裹的文字=对话，type=dialogue，role=说话人名，绝对不能是旁白！\n"
            "哪怕只有一个字、一个叹词，只要在引号里就是对话！\n\n"
            "【说话人判断】\n"
            "1. 附近有「XX说/道/问/答/喊/叫/骂/吩咐/冷笑/叹」→ XX\n"
            "2. 「XX：『...』」→ XX\n"
            "3. 两人交替对话，上句A说这句就是B说\n"
            "4. 只有两人在场景里，根据对话内容判断是谁说的\n"
            "5. 实在不确定填「未知」，但尽量从上下文推断\n"
            "6. 同一角色用同一名字（最先出现的称呼）\n\n"
            "【语气指令instruction】根据对话内容和上下文情绪，生成自然语言指令，指导TTS语音合成的语气表达。\n"
            "要求：简明描述该句应有的语气情绪。例如：\n"
            "  - 旁白：用平静自然的语气朗读\n"
            "  - 愤怒：非常愤怒地说这句话 / 用生气的语气说话\n"
            "  - 疑惑：用疑惑的语气提问\n"
            "  - 悲伤：用悲伤低沉的语气说话\n"
            "  - 开心：请非常开心地说这句话\n"
            "  - 惊讶：用惊讶的语气说话\n"
            "  - 紧张：用紧张急促的语气说话\n"
            "  - 恐惧：用害怕恐惧的语气说话\n\n"
            "【格式】\n"
            "- 对话content=引号内纯文字，去掉引号\n"
            "- 「XX说/道」等描述单独做旁白，放在对话后面\n"
            "- 按原文顺序，一句一条，不概括，不漏句，不改写，不添加原文没有的内容\n"
            "- 每行输出一个JSON对象，不要输出JSON数组，不要使用markdown代码块\n\n"
            "示例（每行一个JSON）：\n" + example + "\n\n"
            f"章节：{chapter_title}\n\n"
            f"内容：\n{chapter_text}\n\n"
            "开始输出（每行一个JSON）："
        )

    # ===================== 查询 =====================

    def get_scripts(self, book_id: int) -> List[Dict[str, Any]]:
        """获取书籍的剧本列表。"""
        scripts = get_scripts_by_book(book_id)
        for s in scripts:
            s["line_count"] = get_script_line_count(s["id"])
            s["created_at_str"] = self._format_time(s.get("created_at"))
        return scripts

    def get_script(self, script_id: int) -> Optional[Dict[str, Any]]:
        """获取剧本详情。"""
        script = get_script(script_id)
        if script is None:
            return None
        script["line_count"] = get_script_line_count(script_id)
        script["chapters_with_lines"] = get_script_chapters_with_lines(script_id)
        script["created_at_str"] = self._format_time(script.get("created_at"))
        script["updated_at_str"] = self._format_time(script.get("updated_at"))

        # 附加任务状态（优先使用数据库中的进度信息）
        if script.get("task_id"):
            task = agent_task_manager.get_task(script["task_id"])
            if task:
                script["task_status"] = task["status"]
                script["task_progress"] = task["progress"]
                script["task_message"] = task["message"]
        
        # 使用数据库中的进度信息（即使任务信息丢失也能显示）
        if script.get("progress_message"):
            script["task_message"] = script["progress_message"]
        return script

    def get_script_lines(self, script_id: int,
                         chapter_index: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取台词列表。"""
        return get_script_lines(script_id, chapter_index)

    def get_script_lines_paged(self, script_id: int,
                               page: int = 1,
                               page_size: int = 50,
                               chapter_index: Optional[int] = None) -> Dict[str, Any]:
        """分页获取台词列表。"""
        return get_script_lines_paged(script_id, page=page, page_size=page_size,
                                         chapter_index=chapter_index)

    def get_script_chapters(self, script_id: int) -> List[Dict[str, Any]]:
        """获取剧本章节列表（含台词数量）。优先从 script_chapters 读取，回退 ebook_chapters。"""
        script = get_script(script_id)
        if script is None:
            return []
        chapters_with_lines = set(get_script_chapters_with_lines(script_id))

        script_chapters = get_script_chapters_all(script_id)
        if script_chapters:
            result = []
            for ch in script_chapters:
                idx = ch["chapter_index"]
                line_count = len(get_script_lines(script_id, idx))
                result.append({
                    "chapter_index": idx,
                    "chapter_title": ch.get("title", ""),
                    "line_count": line_count,
                    "has_lines": idx in chapters_with_lines,
                })
            return result

        chapters = get_chapters(script["book_id"])
        result = []
        for ch in chapters:
            idx = ch["chapter_index"]
            line_count = len(get_script_lines(script_id, idx))
            result.append({
                "chapter_index": idx,
                "chapter_title": ch["title"],
                "line_count": line_count,
                "has_lines": idx in chapters_with_lines,
            })
        return result

    def get_characters(self, script_id: int) -> List[Dict[str, Any]]:
        """获取剧本中所有角色（从角色表读取）。"""
        characters = get_script_characters(script_id)
        if not characters:
            self._sync_characters_from_lines(script_id)
            characters = get_script_characters(script_id)
        roles = sorted(characters, key=lambda r: (r["role"] != "旁白", r["role"]))
        return roles

    def add_character(self, script_id: int, role: str) -> Dict[str, Any]:
        """新增角色到剧本。若已存在则返回已有记录。"""
        role = (role or "").strip()
        if not role:
            raise ValueError("角色名不能为空")
        existing = get_script_characters(script_id)
        for ch in existing:
            if ch["role"] == role:
                return ch
        inserted = add_script_characters(script_id, [role])
        self._logger.info(f"[ScriptService] 新增角色: script_id={script_id}, role={role}")
        return inserted[0] if inserted else {"script_id": script_id, "role": role, "line_count": 0}

    def delete_character(self, script_id: int, role: str) -> bool:
        """删除剧本角色（仅当该角色无台词时允许删除）。"""
        from repositories import get_script_lines
        lines = get_script_lines(script_id)
        if any(l.get("role") == role for l in lines):
            raise ValueError("该角色仍有台词，无法删除")
        conn = _get_conn()
        with _lock:
            cur = conn.execute(
                "DELETE FROM script_characters WHERE script_id=? AND role=?",
                (script_id, role),
            )
            conn.execute(
                "DELETE FROM script_character_configs WHERE script_id=? AND role=?",
                (script_id, role),
            )
            conn.commit()
        return cur.rowcount > 0

    def _sync_characters_from_lines(self, script_id: int) -> None:
        """从现有语句中同步角色到角色表（用于初始化）。"""
        all_lines = get_script_lines(script_id)
        role_map: Dict[str, int] = {}
        for line in all_lines:
            role = line.get("role", "旁白")
            role_map[role] = role_map.get(role, 0) + 1
        add_script_characters(script_id, list(role_map.keys()))
        for role, count in role_map.items():
            conn = _get_conn()
            with _lock:
                conn.execute(
                    "UPDATE script_characters SET line_count = ? WHERE script_id=? AND role=?",
                    (count, script_id, role),
                )
                conn.commit()

    def _save_new_characters(self, script_id: int, lines: List[Dict[str, Any]]) -> List[str]:
        """解析新生成的台词中的角色，将新角色入库。
        
        返回新增的角色列表。
        """
        existing_roles = set(r["role"] for r in get_script_characters(script_id))
        new_roles = []
        for line in lines:
            role = line.get("role", "旁白")
            if role and role not in existing_roles:
                existing_roles.add(role)
                new_roles.append(role)
        if new_roles:
            add_script_characters(script_id, new_roles)
            self._logger.info(f"[ScriptService] 新增角色已入库: script_id={script_id}, roles={new_roles}")
        return new_roles

    async def generate_chapter_script_stream(
        self,
        script_id: int,
        chapter_index: int,
        on_line_added: Optional[Callable[[int, List[Dict[str, Any]]], None]] = None,
        on_character_added: Optional[Callable[[int, List[str]], None]] = None,
        is_part_of_full: bool = False,
    ) -> bool:
        """为单个章节流式生成台词。
        
        Args:
            script_id: 剧本 ID
            chapter_index: 章节序号
            on_line_added: 回调函数，签名为 on_line_added(script_id, lines)
            on_character_added: 回调函数，签名为 on_character_added(script_id, roles)
        
        Returns:
            True 表示成功，False 表示失败
        """
        script = get_script(script_id)
        if script is None:
            self._logger.error(f"[ScriptService] 剧本不存在: script_id={script_id}")
            return False

        book_id = script.get("book_id")

        sc = get_script_chapter(script_id, chapter_index)
        if sc:
            chapter_title = sc.get("title", "")
            chapter_text = self._read_script_chapter_content(script_id, chapter_index)
            if chapter_text is None:
                if book_id:
                    cd = self._ebook_service.get_chapter_content(book_id, chapter_index)
                    chapter_text = cd.get("content", "") if cd else ""
                else:
                    chapter_text = ""
        else:
            if not book_id:
                self._logger.error(f"[ScriptService] 剧本缺少书籍ID: script_id={script_id}")
                return False
            chapters = get_chapters(book_id)
            chapter = next((c for c in chapters if c["chapter_index"] == chapter_index), None)
            if chapter is None:
                self._logger.error(f"[ScriptService] 章节不存在: chapter_index={chapter_index}")
                return False
            chapter_title = chapter["title"]
            chapter_text_data = self._ebook_service.get_chapter_content(book_id, chapter_index)
            chapter_text = chapter_text_data.get("content", "") if chapter_text_data else ""

        if not chapter_text:
            self._logger.error(f"[ScriptService] 读取章节内容失败: chapter_index={chapter_index}")
            return False

        if len(chapter_text) > 8000:
            chapter_text = chapter_text[:8000] + "\n...(内容已截断)"

        self.clear_stop_flag(script_id)
        update_script(script_id, status="running", progress_message=f"正在生成第 {chapter_index} 章台词", generating_chapter_index=chapter_index)

        has_error = False
        total_lines = 0
        self._logger.info(f"[ScriptService] 开始生成章节{chapter_index} (is_part_of_full={is_part_of_full})")

        async def _on_line_added(sid: int, lines: List[Dict[str, Any]]):
            nonlocal total_lines

            new_roles = await asyncio.to_thread(self._save_new_characters, sid, lines)

            inserted = await asyncio.to_thread(add_script_lines, sid, lines)
            total_lines += len(inserted)
            self._logger.info(f"[ScriptService] 回调: 收到 {len(lines)} 条, 插入 {len(inserted)} 条")

            self.notify_listeners(sid, "lines_added", {
                "lines": inserted,
                "chapter_index": chapter_index,
            })

            try:
                from infrastructure.websocket_broadcast import ws_broadcast_manager
                for line in inserted:
                    line_id = line.get("id")
                    if line_id:
                        asyncio.create_task(ws_broadcast_manager.broadcast_line_generated(sid, line_id))
                # 广播本次涉及角色的最新数据（含 line_count），前端增量合并，避免频繁调用角色查询接口
                involved_roles = list({line.get("role", "旁白") for line in lines if line.get("role")})
                if involved_roles:
                    all_chars = await asyncio.to_thread(get_script_characters, sid)
                    updated_chars = [c for c in all_chars if c.get("role") in involved_roles]
                    if updated_chars:
                        asyncio.create_task(ws_broadcast_manager.broadcast_characters_updated(sid, updated_chars))
            except Exception as e:
                self._logger.warning(f"[ScriptService] WebSocket通知失败: {e}")

            if new_roles and on_character_added:
                try:
                    on_character_added(sid, new_roles)
                except Exception as e:
                    self._logger.warning(f"[ScriptService] 角色回调执行失败: {e}")

            if on_line_added:
                try:
                    on_line_added(sid, inserted)
                except Exception as e:
                    self._logger.warning(f"[ScriptService] 语句回调执行失败: {e}")

        try:
            lines = await self._generate_chapter_lines_stream(
                script_id, chapter_index, chapter_title, chapter_text,
                on_line_added=_on_line_added,
            )

            if lines:
                self._logger.info(
                    f"[ScriptService] 章节{chapter_index} 生成 {len(lines)} 条台词"
                )
            else:
                self._logger.warning(
                    f"[ScriptService] 章节{chapter_index} 未生成台词"
                )

        except Exception as e:
            has_error = True
            error_msg = f"生成章节{chapter_index}失败: {str(e)}"
            self._logger.error(f"[ScriptService] {error_msg}")
            if not is_part_of_full:
                update_script(script_id, status="failed", error=error_msg, progress_message="", generating_chapter_index=-1)
            return False

        if self.is_stopped(script_id):
            self._logger.info(
                f"[ScriptService] 章节{chapter_index} 生成已被用户停止: script_id={script_id}, 句数={total_lines}"
            )
            update_script(script_id, status="ready", progress_message="", generating_chapter_index=0)
            return True

        if not is_part_of_full:
            update_script(script_id, status="ready", progress_message="", generating_chapter_index=0)
        self._logger.info(
            f"[ScriptService] 章节{chapter_index} 生成完成: script_id={script_id}, 句数={total_lines}"
        )
        return True

    async def regenerate_script_stream(
        self,
        script_id: int,
    ) -> bool:
        """清空已有台词并重新生成整个剧本。"""
        self._logger.info(f"[ScriptService] 开始全剧本重新生成: script_id={script_id}")
        
        from core.global_manager import global_manager
        
        delete_script_lines(script_id)
        update_script(script_id, status="running", error=None)
        
        script = get_script(script_id)
        if script is None:
            self._logger.error(f"[ScriptService] 剧本不存在: script_id={script_id}")
            global_manager.release_model()
            return False

        book_id = script.get("book_id")

        chapters = get_script_chapters_all(script_id)
        if not chapters and book_id:
            chapters = get_chapters(book_id)
        
        try:
            for chapter in chapters:
                chapter_index = chapter["chapter_index"]
                self._logger.info(f"[ScriptService] 生成章节{chapter_index}...")
                try:
                    await self.generate_chapter_script_stream(
                        script_id, chapter_index, is_part_of_full=True
                    )
                except Exception as e:
                    self._logger.error(f"[ScriptService] 生成章节{chapter_index}失败: {e}")
        finally:
            global_manager.release_model()
        
        update_script(script_id, status="ready")
        self._logger.info(f"[ScriptService] 生成全部台词完成: script_id={script_id}")
        return True

    # ===================== 编辑 =====================

    def update_line(self, line_id: int, role: str = None, instruction: str = None,
                    content: str = None, tone: str = None, seed: int = None) -> bool:
        """更新单条台词。"""
        fields = {}
        if role is not None:
            fields["role"] = role
        if instruction is not None:
            fields["instruction"] = instruction
        if content is not None:
            fields["content"] = content
        if tone is not None:
            fields["tone"] = tone
        if seed is not None:
            fields["seed"] = seed
        if not fields:
            return False
        update_script_line(line_id, **fields)
        return True

    def update_lines_batch(self, lines: List[Dict[str, Any]]) -> int:
        """批量更新台词。

        lines 元素: {"id", "role", "instruction", "content", "tone", "seed"}
        """
        count = 0
        for l in lines:
            line_id = l.get("id")
            if line_id is None:
                continue
            self.update_line(
                line_id,
                role=l.get("role"),
                instruction=l.get("instruction"),
                content=l.get("content"),
                tone=l.get("tone"),
                seed=l.get("seed"),
            )
            count += 1
        return count

    def add_line(self, script_id: int, chapter_index: int, role: str,
                 instruction: str, content: str) -> Optional[int]:
        """新增单条台词。"""
        existing = get_script_lines(script_id, chapter_index)
        line_no = max([l["line_no"] for l in existing], default=0) + 1
        add_script_lines(script_id, [{
            "chapter_index": chapter_index,
            "line_no": line_no,
            "role": role,
            "instruction": instruction,
            "content": content,
        }])
        return line_no

    def add_line_at_position(self, script_id: int, chapter_index: int, role: str,
                             instruction: str, content: str,
                             insert_after_id: Optional[int] = None,
                             insert_before_id: Optional[int] = None) -> Optional[dict]:
        """在指定位置新增台词，返回新行数据。"""
        return insert_line_at_position(
            script_id, chapter_index, role, instruction, content,
            insert_after_id, insert_before_id,
        )

    def delete_line(self, line_id: int) -> bool:
        """删除单条台词，维护链表结构。"""
        return delete_script_line(line_id)

    def clear_chapter_lines(self, script_id: int, chapter_index: int) -> dict:
        """清空指定章节的所有台词。"""
        script = get_script(script_id)
        if script is None:
            return {"success": False, "message": "剧本不存在"}

        deleted = delete_script_lines_by_chapter(script_id, chapter_index)
        self._logger.info(
            f"[ScriptService] 清空章节{chapter_index}台词: "
            f"script_id={script_id}, 删除{deleted}条"
        )
        return {"success": True, "deleted": deleted, "message": f"已清空{deleted}条台词"}

    # ===================== 删除 =====================

    def delete_script(self, script_id: int) -> Tuple[bool, str]:
        """删除剧本及其所有台词。"""
        script = get_script(script_id)
        if script is None:
            return False, "剧本不存在"

        # 清理任务
        if script.get("task_id"):
            agent_task_manager.remove_task(script["task_id"])

        delete_script(script_id)
        self._logger.info(f"[ScriptService] 已删除剧本: {script['name']} (id={script_id})")
        return True, f"已删除剧本: {script['name']}"

    @staticmethod
    def _format_time(ts: Optional[float]) -> str:
        if not ts:
            return ""
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        except Exception:
            return ""


_script_service: Optional[ScriptService] = None


def get_script_service() -> ScriptService:
    global _script_service
    if _script_service is None:
        _script_service = ScriptService()
    return _script_service
