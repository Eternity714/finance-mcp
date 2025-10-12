"""
宏观数据服务模块
提供中国宏观经济数据的获取、存储和分析功能
"""

from .macro_service import MacroDataService, get_macro_service
from .storage import (
    MacroDataStorage,
    MySQLMacroStorage,
    SQLiteMacroStorage,
    StorageManager,
    get_storage_manager,
    get_macro_storage,
    INDICATOR_TABLE_MAPPING,
    INDICATOR_TIME_FIELD,
    INDICATOR_FREQUENCY,
)

__all__ = [
    # 主服务
    "MacroDataService",
    "get_macro_service",
    # 存储层
    "MacroDataStorage",
    "MySQLMacroStorage",
    "SQLiteMacroStorage",
    "StorageManager",
    "get_storage_manager",
    "get_macro_storage",
    # 常量
    "INDICATOR_TABLE_MAPPING",
    "INDICATOR_TIME_FIELD",
    "INDICATOR_FREQUENCY",
]
