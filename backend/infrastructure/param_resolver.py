"""参数解析器：合并全局默认参数与智能体覆盖参数"""


def get_effective_params(agent: dict, model_type: str) -> dict:
    """
    合并全局默认参数与智能体覆盖参数（浅合并）。

    Args:
        agent: 智能体 dict，可能包含 params 字段
        model_type: 模型分类键，如 "qwen" | "cosyvoice" | "dreamlite"

    Returns:
        合并后的完整参数 dict（智能体覆盖优先）
    """
    from core.model_manager import get_category

    meta = get_category(model_type)
    if not meta or not meta.get("loadable"):
        return {}

    params_config_key = meta["params_config_key"]
    from core.config_manager import get_config
    config = get_config()
    global_params = config.get(params_config_key, {}).copy()

    if not isinstance(agent, dict):
        return global_params

    agent_overrides = agent.get("params", {}).get(model_type, {})
    if not isinstance(agent_overrides, dict):
        agent_overrides = {}

    return {**global_params, **agent_overrides}
