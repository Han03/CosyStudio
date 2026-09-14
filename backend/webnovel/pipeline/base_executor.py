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

    def get_step_info(self) -> Dict[str, Any]:
        """获取步骤信息。"""
        return {
            "name": self.step_name,
            "description": self.step_description,
            "weight": self.step_weight,
        }