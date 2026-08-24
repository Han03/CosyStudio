import asyncio
import json
import threading
from typing import Dict, Set


class WebSocketBroadcastManager:
    """
    WebSocket广播管理器 - 管理剧本编辑器的WebSocket连接，支持音频生成完成通知

    用法：
        from infrastructure.websocket_broadcast import ws_broadcast_manager
        await ws_broadcast_manager.broadcast_audio_generated(script_id, line_id)
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        """初始化广播管理器"""
        self._script_connections: Dict[int, Set] = {}
        self._loop = asyncio.get_event_loop()

    def register_connection(self, script_id: int, websocket):
        """注册剧本WebSocket连接"""
        if script_id not in self._script_connections:
            self._script_connections[script_id] = set()
        self._script_connections[script_id].add(websocket)

    def unregister_connection(self, script_id: int, websocket):
        """注销剧本WebSocket连接"""
        if script_id in self._script_connections:
            self._script_connections[script_id].discard(websocket)
            if not self._script_connections[script_id]:
                del self._script_connections[script_id]

    async def broadcast_audio_generated(self, script_id: int, line_id: int):
        """广播音频生成完成通知"""
        connections = self._script_connections.get(script_id, set())
        if not connections:
            return

        message = {
            "type": "audio_generated",
            "line_id": line_id,
            "script_id": script_id,
        }

        disconnected = []
        for conn in connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)

        for conn in disconnected:
            self.unregister_connection(script_id, conn)

    async def broadcast_script_lines_update(self, script_id: int, line_ids: list):
        """广播台词更新通知"""
        connections = self._script_connections.get(script_id, set())
        if not connections:
            return

        message = {
            "type": "script_lines_update",
            "script_id": script_id,
            "line_ids": line_ids,
        }

        disconnected = []
        for conn in connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)

        for conn in disconnected:
            self.unregister_connection(script_id, conn)

    async def broadcast_line_generating(self, script_id: int, line_id: int):
        """广播台词生成中通知"""
        connections = self._script_connections.get(script_id, set())
        if not connections:
            return

        message = {
            "type": "line_generating",
            "script_id": script_id,
            "line_id": line_id,
        }

        disconnected = []
        for conn in connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)

        for conn in disconnected:
            self.unregister_connection(script_id, conn)

    async def broadcast_line_generated(self, script_id: int, line_id: int):
        """广播台词生成完成通知"""
        connections = self._script_connections.get(script_id, set())
        if not connections:
            return

        message = {
            "type": "line_generated",
            "script_id": script_id,
            "line_id": line_id,
        }

        disconnected = []
        for conn in connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)

        for conn in disconnected:
            self.unregister_connection(script_id, conn)

    async def broadcast_characters_updated(self, script_id: int, characters: list):
        """广播角色数据变更（包含完整角色信息，前端增量合并）"""
        connections = self._script_connections.get(script_id, set())
        if not connections:
            return

        message = {
            "type": "characters_updated",
            "script_id": script_id,
            "characters": characters,
        }

        disconnected = []
        for conn in connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)

        for conn in disconnected:
            self.unregister_connection(script_id, conn)

    async def broadcast_continue_task_update(self, script_id: int, task_id: int, status: dict):
        """广播创作任务状态更新"""
        connections = self._script_connections.get(script_id, set())
        if not connections:
            return

        message = {
            "type": "continue_task_update",
            "script_id": script_id,
            "task_id": task_id,
            "status": status,
        }

        disconnected = []
        for conn in connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)

        for conn in disconnected:
            self.unregister_connection(script_id, conn)

    async def broadcast_chapter_applied(self, script_id: int, chapter_index: int, title: str, content: str):
        """广播创作结果已应用到章节通知。

        前端收到后应刷新章节列表、切换到目标章节并更新内容显示。
        """
        connections = self._script_connections.get(script_id, set())
        if not connections:
            return

        message = {
            "type": "chapter_applied",
            "script_id": script_id,
            "chapter_index": chapter_index,
            "title": title,
            "content": content,
        }

        disconnected = []
        for conn in connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)

        for conn in disconnected:
            self.unregister_connection(script_id, conn)

    async def broadcast_chapter_plans_generated(self, script_id: int, outline_id: int, success: bool, message: str, plan_count: int = 0):
        """广播章节规划生成完成通知。

        智能拆章完成后通知前端刷新章节规划列表。
        """
        connections = self._script_connections.get(script_id, set())
        if not connections:
            return

        message_data = {
            "type": "chapter_plans_generated",
            "script_id": script_id,
            "outline_id": outline_id,
            "success": success,
            "message": message,
            "plan_count": plan_count,
        }

        disconnected = []
        for conn in connections:
            try:
                await conn.send_json(message_data)
            except Exception:
                disconnected.append(conn)

        for conn in disconnected:
            self.unregister_connection(script_id, conn)

    async def broadcast_init_progress(self, script_id: int, status: str, step: str, message: str, progress: int = 0):
        """广播深度初始化进度

        Args:
            script_id: 剧本ID
            status: 状态 running/completed/failed/interrupted
            step: 当前节点名称
            message: 进度描述消息
            progress: 进度百分比 0-100
        """
        connections = self._script_connections.get(script_id, set())
        if not connections:
            return

        message_data = {
            "type": "init_progress",
            "script_id": script_id,
            "status": status,
            "step": step,
            "message": message,
            "progress": progress,
        }

        disconnected = []
        for conn in connections:
            try:
                await conn.send_json(message_data)
            except Exception:
                disconnected.append(conn)

        for conn in disconnected:
            self.unregister_connection(script_id, conn)


# 创建全局单例实例
ws_broadcast_manager = WebSocketBroadcastManager()
