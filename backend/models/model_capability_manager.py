from core.config_manager import (
    get_model_capabilities,
    get_enabled_capabilities,
    update_model_capabilities,
    update_capability,
    add_capability,
    delete_capability,
    CAPABILITY_TYPES,
    PLATFORM_CODES
)
from utils.logger import log_manager

_logger = log_manager.get_logger("capability_manager")


class CapabilityManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_capability_types(self):
        """获取所有能力类型"""
        return CAPABILITY_TYPES

    def get_platform_codes(self):
        """获取所有平台编码"""
        return PLATFORM_CODES

    def get_all_capabilities(self):
        """获取所有模型能力配置"""
        return get_model_capabilities()

    def get_capabilities_by_type(self, capability_type: str):
        """按能力类型获取配置"""
        if capability_type not in CAPABILITY_TYPES:
            _logger.warning(f"未知的能力类型: {capability_type}")
            return []
        return get_enabled_capabilities(capability_type)

    def get_best_capability(self, capability_type: str):
        """获取优先级最高的可用能力配置"""
        capabilities = self.get_capabilities_by_type(capability_type)
        if not capabilities:
            _logger.warning(f"没有可用的{CAPABILITY_TYPES.get(capability_type, capability_type)}能力")
            return None
        return capabilities[0]

    def get_capability(self, capability_type: str, capability_id: str):
        """获取指定ID的能力配置"""
        capabilities = get_model_capabilities().get(capability_type, [])
        for cap in capabilities:
            if cap.get("id") == capability_id:
                return cap
        return None

    def update_capability_config(self, capability_type: str, capability_id: str, updates: dict):
        """更新能力配置"""
        _logger.info(f"更新能力配置: {capability_type}/{capability_id}")
        return update_capability(capability_type, capability_id, updates)

    def add_capability_config(self, capability_type: str, capability: dict):
        """添加能力配置"""
        if capability_type not in CAPABILITY_TYPES:
            raise ValueError(f"未知的能力类型: {capability_type}")
        if capability.get("platform_code") not in PLATFORM_CODES:
            raise ValueError(f"未知的平台编码: {capability.get('platform_code')}")
        _logger.info(f"添加能力配置: {capability_type}/{capability.get('id')}")
        return add_capability(capability_type, capability)

    def delete_capability_config(self, capability_type: str, capability_id: str):
        """删除能力配置"""
        _logger.info(f"删除能力配置: {capability_type}/{capability_id}")
        return delete_capability(capability_type, capability_id)

    def update_all_capabilities(self, capabilities: dict):
        """更新所有能力配置"""
        _logger.info("更新所有能力配置")
        return update_model_capabilities(capabilities)

    def is_capability_available(self, capability_type: str):
        """检查指定能力类型是否有可用配置"""
        capabilities = self.get_capabilities_by_type(capability_type)
        return len(capabilities) > 0

    def get_platform_info(self, platform_code: str):
        """获取平台信息"""
        return PLATFORM_CODES.get(platform_code)

    def get_capability_type_name(self, capability_type: str):
        """获取能力类型名称"""
        return CAPABILITY_TYPES.get(capability_type, capability_type)

    def reorder_capabilities(self, capability_type: str, capability_ids: list):
        """重新排序能力配置，根据传入的ID列表顺序更新优先级"""
        if capability_type not in CAPABILITY_TYPES:
            raise ValueError(f"未知的能力类型: {capability_type}")
        
        all_capabilities = get_model_capabilities()
        capabilities = all_capabilities.get(capability_type, [])
        capability_map = {cap.get("id"): cap for cap in capabilities}
        
        reordered = []
        for idx, cap_id in enumerate(capability_ids):
            if cap_id in capability_map:
                cap = capability_map[cap_id].copy()
                cap["priority"] = len(capability_ids) - idx
                reordered.append(cap)
        
        for cap_id in capability_map:
            if cap_id not in capability_ids:
                reordered.append(capability_map[cap_id])
        
        all_capabilities[capability_type] = reordered
        update_model_capabilities(all_capabilities)
        return reordered


capability_manager = CapabilityManager()