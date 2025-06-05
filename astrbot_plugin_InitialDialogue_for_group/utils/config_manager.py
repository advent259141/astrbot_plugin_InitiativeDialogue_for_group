# 配置管理器 - 处理配置加载和验证

import logging
from typing import Dict, Any, Optional, TypeVar, Generic, Union, List

T = TypeVar("T")
logger = logging.getLogger("config_manager")


class ConfigManager:
    """配置管理器，用于加载和管理各种配置"""

    def __init__(self, config: Dict[str, Any]):
        """初始化配置管理器

        Args:
            config: 主配置字典
        """
        self.config = config

    def get_module_config(self, module_name: str) -> Dict[str, Any]:
        """获取指定模块的配置

        Args:
            module_name: 模块名称

        Returns:
            Dict[str, Any]: 模块配置，如果不存在则返回空字典
        """
        return self.config.get(module_name, {})

    def get_value(self, path: str, default: T = None) -> Union[T, Any]:
        """获取指定路径的配置值

        Args:
            path: 配置路径，使用点分隔，例如 "module.submodule.key"
            default: 默认值

        Returns:
            配置值，如果不存在则返回默认值
        """
        parts = path.split(".")
        current = self.config

        try:
            for part in parts:
                if not isinstance(current, dict) or part not in current:
                    return default
                current = current[part]
            return current
        except Exception as e:
            logger.error(f"获取配置值 {path} 时出错: {str(e)}")
            return default

    def validate_config(self, requirements: Dict[str, Dict[str, Any]]) -> List[str]:
        """验证配置是否满足要求

        Args:
            requirements: 配置要求字典，格式为 {"path": {"type": type, "required": bool}}

        Returns:
            List[str]: 验证失败的配置项列表
        """
        failures = []

        for path, specs in requirements.items():
            value = self.get_value(path)

            # 检查是否必需
            if specs.get("required", False) and value is None:
                failures.append(f"必需的配置项 {path} 不存在")
                continue

            # 如果有值，检查类型
            if value is not None and "type" in specs:
                expected_type = specs["type"]
                if not isinstance(value, expected_type):
                    failures.append(
                        f"配置项 {path} 类型错误，预期 {expected_type.__name__}，实际为 {type(value).__name__}"
                    )

        return failures
