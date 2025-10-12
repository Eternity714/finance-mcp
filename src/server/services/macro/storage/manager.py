"""
宏观数据存储管理器
自动选择最佳的存储方案（MySQL → SQLite → 其他）
"""

import logging
from typing import Optional, Dict, Any, List

from .base import MacroDataStorage
from .mysql_storage import MySQLMacroStorage
from .sqlite_storage import SQLiteMacroStorage

logger = logging.getLogger(__name__)


class StorageManager:
    """存储管理器 - 自动选择最佳存储方案"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.storage: Optional[MacroDataStorage] = None
        self.storage_type = None

    def get_storage(self) -> MacroDataStorage:
        """获取最佳可用的存储实例"""
        if self.storage is not None:
            return self.storage

        # 尝试各种存储方案
        storage_options = [
            ("mysql", MySQLMacroStorage),
            ("sqlite", SQLiteMacroStorage),
        ]

        for storage_name, storage_class in storage_options:
            try:
                logger.info(f"🔄 尝试初始化 {storage_name.upper()} 存储...")

                storage_config = self.config.get(storage_name, {})
                storage_instance = storage_class(storage_config)

                if storage_instance.connect() and storage_instance.is_available():
                    self.storage = storage_instance
                    self.storage_type = storage_name
                    logger.info(f"✅ 成功初始化 {storage_name.upper()} 存储")
                    return self.storage
                else:
                    logger.warning(f"⚠️ {storage_name.upper()} 存储不可用")

            except Exception as e:
                logger.warning(f"⚠️ {storage_name.upper()} 存储初始化失败: {e}")
                continue

        # 如果所有存储都失败，抛出异常
        raise RuntimeError("❌ 无法初始化任何存储方案")

    def get_storage_info(self) -> Dict[str, Any]:
        """获取当前存储信息"""
        if self.storage is None:
            return {"type": "none", "available": False}

        info = self.storage.get_storage_info()
        info["selected_type"] = self.storage_type
        return info

    def test_all_storages(self) -> Dict[str, Dict[str, Any]]:
        """测试所有存储方案的可用性"""
        results = {}

        storage_classes = {
            "mysql": MySQLMacroStorage,
            "sqlite": SQLiteMacroStorage,
        }

        for name, storage_class in storage_classes.items():
            try:
                storage_config = self.config.get(name, {})
                storage_instance = storage_class(storage_config)

                # 测试连接
                can_connect = storage_instance.connect()
                is_available = storage_instance.is_available() if can_connect else False

                results[name] = {
                    "can_connect": can_connect,
                    "is_available": is_available,
                    "info": (
                        storage_instance.get_storage_info() if can_connect else None
                    ),
                    "error": None,
                }

                # 清理连接
                if hasattr(storage_instance, "close"):
                    storage_instance.close()

            except Exception as e:
                results[name] = {
                    "can_connect": False,
                    "is_available": False,
                    "info": None,
                    "error": str(e),
                }

        return results

    def close(self):
        """关闭存储连接"""
        if self.storage and hasattr(self.storage, "close"):
            self.storage.close()
            self.storage = None
            self.storage_type = None


# 全局存储管理器单例
_global_storage_manager: Optional[StorageManager] = None


def get_storage_manager(config: Dict[str, Any] = None) -> StorageManager:
    """获取全局存储管理器单例"""
    global _global_storage_manager
    if _global_storage_manager is None:
        _global_storage_manager = StorageManager(config)
    return _global_storage_manager


def get_macro_storage() -> MacroDataStorage:
    """获取宏观数据存储实例（便捷函数）"""
    return get_storage_manager().get_storage()
