"""
宏观数据存储模块
"""

from .base import (
    MacroDataStorage,
    INDICATOR_TABLE_MAPPING,
    INDICATOR_TIME_FIELD,
    INDICATOR_FREQUENCY,
)
from .mysql_storage import MySQLMacroStorage
from .sqlite_storage import SQLiteMacroStorage
from .manager import StorageManager, get_storage_manager, get_macro_storage

__all__ = [
    # 基础类
    "MacroDataStorage",
    # 具体实现
    "MySQLMacroStorage",
    "SQLiteMacroStorage",
    # 管理器
    "StorageManager",
    "get_storage_manager",
    "get_macro_storage",
    # 常量
    "INDICATOR_TABLE_MAPPING",
    "INDICATOR_TIME_FIELD",
    "INDICATOR_FREQUENCY",
]
