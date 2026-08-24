"""Prompt 参数管理器。

提供带参 Prompt 语句的参数替换功能。
预设多个参数,每个参数的值为数组,渲染时随机选择一个值替换。

用法:
    from services.prompt_param_manager import get_prompt_param_manager

    manager = get_prompt_param_manager()
    template = "请生成一条{名言风格}风格的{文化背景}名言"
    prompt = manager.render(template)
    # 返回: "请生成一条幽默风格的东方文化名言"
"""

import re
import random
import logging

logger = logging.getLogger(__name__)

_PRESET_PARAMS = {
    "历史时期": [
        "古代",
        "中世纪",
        "文艺复兴时期",
        "近现代",
        "当代",
        "未来",
        "春秋时期",
        "战国时期",
    ],
    "行业": [
        "科技",
        "艺术",
        "商业",
        "教育",
        "医疗",
        "体育",
        "金融",
        "文学",
    ],
    "年龄段": [
        "少年",
        "青年",
        "中年",
        "老年",
        "儿童",
    ],
    "地球范围": [
        "全球",
        "亚洲",
        "欧洲",
        "美洲",
        "中国",
        "日本",
        "美国",
        "英国",
    ],
    "个人情感": [
        "乐观",
        "坚强",
        "感恩",
        "宁静",
        "勇敢",
        "宽容",
        "谦逊",
        "自由",
    ],
    "名言风格": [
        "哲理",
        "励志",
        "幽默",
        "唯美",
        "深邃",
        "简洁",
        "诗意",
        "犀利",
    ],
    "文化背景": [
        "东方文化",
        "西方文化",
        "儒家思想",
        "道家思想",
        "佛教文化",
        "古希腊",
        "古罗马",
        "现代主义",
    ],
    "主题": [
        "人生",
        "梦想",
        "爱情",
        "友谊",
        "成功",
        "失败",
        "时间",
        "自由",
    ],
    "季节": [
        "春天",
        "夏天",
        "秋天",
        "冬天",
        "清晨",
        "黄昏",
        "雨夜",
        "雪天",
    ],
}


class PromptParamManager:
    """Prompt 参数管理器。

    渲染带参 Prompt 语句,将 {参数名} 占位符替换为预设数组中的随机值。
    """

    def __init__(self):
        self._params = dict(_PRESET_PARAMS)
        self._pattern = re.compile(r"\{([^}]+)\}")

    def render(self, template: str) -> str:
        """渲染带参 Prompt 语句。

        :param template: 带 {参数名} 占位符的 Prompt 模板
        :return: 所有占位符已替换为随机值的完整 Prompt
        """
        if not template:
            return template

        def _replace(match):
            param_name = match.group(1).strip()
            if param_name in self._params:
                values = self._params[param_name]
                if values:
                    return random.choice(values)
            return match.group(0)

        result = self._pattern.sub(_replace, template)
        logger.debug(f"[PromptParam] 模板: {template} -> 渲染: {result}")
        return result

    def add_param(self, name: str, values: list):
        """添加自定义参数。

        :param name: 参数名
        :param values: 参数值数组
        """
        if not isinstance(values, list) or not values:
            return
        self._params[name] = values
        logger.info(f"[PromptParam] 添加参数: {name} = {values}")

    def get_param(self, name: str) -> list:
        """获取参数值数组。

        :param name: 参数名
        :return: 参数值数组,不存在返回空列表
        """
        return self._params.get(name, [])

    def list_params(self) -> list:
        """列出所有参数名。"""
        return list(self._params.keys())


_param_manager = None


def get_prompt_param_manager() -> PromptParamManager:
    """获取全局 Prompt 参数管理器单例。"""
    global _param_manager
    if _param_manager is None:
        _param_manager = PromptParamManager()
    return _param_manager


__all__ = ["PromptParamManager", "get_prompt_param_manager"]
