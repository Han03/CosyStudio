import os
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class ExecutorResult:
    success: bool = True
    error_message: str = ""
    output_data: Dict[str, Any] = field(default_factory=dict)
    step_summary: str = ""


class BaseExecutor:
    """基础执行器接口。"""

    step_name: str = ""
    step_description: str = ""
    step_weight: int = 10

    def __init__(self, script_id: int, chapter_index: int, task_id: int):
        self.script_id = script_id
        self.chapter_index = chapter_index
        self.task_id = task_id

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行步骤。"""
        raise NotImplementedError("子类必须实现 execute 方法")

    def _load_prompt(self, prompt_name: str) -> Dict[str, str]:
        """加载prompt模板。从 prompts/webnovel/{prompt_name}_prompt.md 读取。

        支持 YAML front matter 格式：
            ---
            system_prompt: ...
            user_prompt: |
              多行内容...
            ---
        """
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts", f"{prompt_name}_prompt.md"
        )
        if not os.path.exists(prompt_path):
            return {"system_prompt": "", "user_prompt": ""}

        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()

        content = content.strip()

        # 去除 YAML front matter 分隔符
        if content.startswith("---"):
            content = content[3:].strip()
        if content.endswith("---"):
            content = content[:-3].strip()

        lines = content.split("\n")
        system_prompt = ""
        user_prompt = ""
        in_user_prompt = False
        in_multiline = False

        for line in lines:
            if line.startswith("system_prompt:"):
                in_user_prompt = False
                in_multiline = False
                value = line.replace("system_prompt:", "").strip()
                if value.startswith("|"):
                    in_multiline = True
                    system_prompt = ""
                else:
                    system_prompt = value
            elif line.startswith("user_prompt:"):
                in_user_prompt = True
                in_multiline = False
                value = line.replace("user_prompt:", "").strip()
                if value.startswith("|"):
                    in_multiline = True
                    user_prompt = ""
                else:
                    user_prompt = value
            elif in_user_prompt and in_multiline:
                user_prompt += line + "\n"
            elif not in_user_prompt and in_multiline:
                system_prompt += line + "\n"

        return {"system_prompt": system_prompt.strip(), "user_prompt": user_prompt.strip()}

    def _format_character_states(self, states: list) -> str:
        """格式化上章末角色状态（最多 6 角色，一行一条）。"""
        if not states:
            return "（无上一章状态记录）"
        parts = []
        for s in states[:6]:
            name = s.get("character_name", "")
            loc = s.get("location", "") or ""
            state = s.get("state_summary", "") or ""
            emotion = s.get("emotion", "") or ""
            knowledge = s.get("knowledge", "") or ""
            line = f"- {name}"
            if loc:
                line += f"（{loc}）"
            if state:
                line += f": {state}"
            if emotion:
                line += f"；情绪:{emotion}"
            if knowledge:
                line += f"；已知:{knowledge[:60]}"
            parts.append(line)
        return "\n".join(parts) if parts else "（无上一章状态记录）"

    def _format_undisclosed(self, loops: list) -> str:
        """格式化不可提前揭示的伏笔清单。"""
        if not loops:
            return "（无）"
        parts = []
        for lp in loops[:6]:
            content = lp.get("content", "")
            planted = lp.get("planted_chapter", 0)
            tier = lp.get("tier", "")
            line = f"- 「{content}」（第{planted}章埋设"
            if tier:
                line += f"，等级:{tier}"
            line += "）"
            parts.append(line)
        return "\n".join(parts)

    def get_step_info(self) -> Dict[str, Any]:
        """获取步骤信息。"""
        return {
            "name": self.step_name,
            "description": self.step_description,
            "weight": self.step_weight,
        }