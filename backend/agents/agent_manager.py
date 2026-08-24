import os
import json
import uuid
from typing import List, Dict, Optional


def _build_default_params():
    """从 MODEL_CATEGORIES 派生默认 params 结构"""
    from core.model_manager import get_loadable_categories
    return {k: {} for k in get_loadable_categories()}


def _get_loadable_keys():
    """获取所有可加载分类的键列表"""
    from core.model_manager import get_loadable_categories
    return list(get_loadable_categories().keys())


class AgentManager:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.agents_file = os.path.join(data_dir, "agents.json")
        os.makedirs(data_dir, exist_ok=True)
        self._load_agents()

    def _load_agents(self):
        if os.path.exists(self.agents_file):
            with open(self.agents_file, "r", encoding="utf-8-sig") as f:
                self.agents = json.load(f)
            # 数据迁移：补全 params 字段
            need_save = False
            loadable_keys = _get_loadable_keys()
            for agent in self.agents:
                if "params" not in agent:
                    agent["params"] = _build_default_params()
                    need_save = True
                elif not isinstance(agent.get("params"), dict):
                    agent["params"] = _build_default_params()
                    need_save = True
                else:
                    # 补全所有可加载分类的键
                    for k in loadable_keys:
                        if k not in agent["params"] or not isinstance(agent["params"][k], dict):
                            agent["params"][k] = {}
                            need_save = True
                # 补全 voice_tones 字段
                if "voice_tones" not in agent or not isinstance(agent["voice_tones"], list):
                    agent["voice_tones"] = []
                    need_save = True
                # 补全 tags 字段
                if "tags" not in agent or not isinstance(agent["tags"], list):
                    agent["tags"] = []
                    need_save = True
            if need_save:
                self._save_agents()
        else:
            self.agents = []

    def _save_agents(self):
        with open(self.agents_file, "w", encoding="utf-8") as f:
            json.dump(self.agents, f, ensure_ascii=False, indent=2)

    def get_all_agents(self) -> List[Dict]:
        return self.agents

    def get_agents_paginated(self, page: int = 1, page_size: int = 9, tag: str = "",
                             search: str = "", gender: str = "", age: str = "") -> Dict:
        filtered = self.agents

        if tag:
            filtered = [a for a in filtered if tag in (a.get("tags") or [])]

        if gender:
            filtered = [a for a in filtered if a.get("gender", "") == gender]

        if age:
            filtered = [a for a in filtered if a.get("age", "") == age]

        if search:
            search_lower = search.lower()
            filtered = [
                a for a in filtered
                if search_lower in a.get("name", "").lower()
                or search_lower in a.get("description", "").lower()
                or any(search_lower in t.lower() for t in (a.get("tags") or []))
            ]

        total = len(filtered)
        start = (page - 1) * page_size
        end = start + page_size
        items = filtered[start:end]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 1
        }

    def get_all_tags(self) -> List[str]:
        tag_set = set()
        for agent in self.agents:
            for tag in (agent.get("tags") or []):
                if tag:
                    tag_set.add(tag)
        return sorted(list(tag_set))

    def get_agent(self, agent_id: str) -> Optional[Dict]:
        for agent in self.agents:
            if agent["id"] == agent_id:
                return agent
        return None

    def create_agent(self, name: str, description: str = "", voice: str = "Chelsie", params: Optional[Dict] = None, voice_tones: Optional[List[Dict]] = None, gender: str = "", age: str = "", tags: Optional[List[str]] = None) -> Dict:
        agent = {
            "id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "gender": gender,
            "age": age,
            "voice_path": "",
            "prompt_path": "",
            "created_at": os.path.getctime(self.data_dir),
            "trained": False,
            "voice": voice,
            "params": params if params else _build_default_params(),
            "voice_tones": voice_tones if voice_tones else [],
            "tags": tags if tags else []
        }
        self.agents.append(agent)
        self._save_agents()
        return agent

    def delete_agent(self, agent_id: str) -> Dict:
        agent = self.get_agent(agent_id)
        if not agent:
            return {"error": "智能体不存在"}

        agent_dir = os.path.join(self.data_dir, agent_id)
        if os.path.exists(agent_dir):
            import shutil
            shutil.rmtree(agent_dir)

        self.agents = [a for a in self.agents if a["id"] != agent_id]
        self._save_agents()
        return {"message": "智能体删除成功"}

    def update_agent(self, agent_id: str, **kwargs) -> Dict:
        agent = self.get_agent(agent_id)
        if not agent:
            return {"error": "智能体不存在"}

        agent.update(kwargs)
        self._save_agents()
        return agent
