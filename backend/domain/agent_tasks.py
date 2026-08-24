import uuid
import asyncio
from datetime import datetime
from typing import Dict, Optional, Any

class AgentTaskManager:
    """异步任务管理器"""
    
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
    
    def create_task(self, agent_id: str, name: str, description: str) -> str:
        """创建新任务，返回任务ID"""
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            'id': task_id,
            'agent_id': agent_id,
            'name': name,
            'description': description,
            'status': 'pending',  # pending | running | ready | failed
            'progress': 0,
            'message': '任务已创建',
            'result': None,
            'error': None,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息"""
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> list:
        """获取所有任务"""
        return list(self.tasks.values())
    
    def get_agent_tasks(self, agent_id: str) -> list:
        """获取指定智能体的所有任务"""
        return [t for t in self.tasks.values() if t.get('agent_id') == agent_id]
    
    def update_task(self, task_id: str, status: str = None, progress: int = None,
                   message: str = None, result: Any = None, error: str = None):
        """更新任务状态"""
        if task_id not in self.tasks:
            return
        
        task = self.tasks[task_id]
        if status is not None:
            task['status'] = status
        if progress is not None:
            task['progress'] = progress
        if message is not None:
            task['message'] = message
        if result is not None:
            task['result'] = result
        if error is not None:
            task['error'] = error
        task['updated_at'] = datetime.now().isoformat()
    
    def remove_task(self, task_id: str):
        """删除任务"""
        if task_id in self.tasks:
            del self.tasks[task_id]
    
    def cleanup_old_tasks(self, max_age_seconds: int = 3600):
        """清理超过指定时间的已完成/失败任务"""
        now = datetime.now()
        to_remove = []
        for task_id, task in self.tasks.items():
            updated = datetime.fromisoformat(task['updated_at'])
            if (now - updated).total_seconds() > max_age_seconds:
                if task['status'] in ('ready', 'failed'):
                    to_remove.append(task_id)
        for task_id in to_remove:
            del self.tasks[task_id]

# 全局任务管理器实例
agent_task_manager = AgentTaskManager()
