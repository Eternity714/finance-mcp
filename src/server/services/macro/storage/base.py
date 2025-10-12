"""
宏观数据存储抽象基类
支持 MySQL → SQLite → Parquet → JSON 的渐进式降级
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MacroDataStorage(ABC):
    """宏观数据存储抽象接口"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.storage_type = self.__class__.__name__.replace("MacroStorage", "").lower()
        self._connected = False

    @abstractmethod
    def connect(self) -> bool:
        """连接存储"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查存储是否可用"""
        pass

    @abstractmethod
    def get_latest_period(self, indicator: str) -> Optional[str]:
        """获取指定指标的最新数据时期"""
        pass

    @abstractmethod
    def save_data(self, indicator: str, data: pd.DataFrame) -> bool:
        """保存数据到存储"""
        pass

    @abstractmethod
    def get_data(
        self, indicator: str, start_period: str = None, end_period: str = None
    ) -> pd.DataFrame:
        """获取指定时间范围的数据"""
        pass

    @abstractmethod
    def get_recent_data(self, indicator: str, periods: int) -> pd.DataFrame:
        """获取最近N期数据"""
        pass

    @abstractmethod
    def delete_data(self, indicator: str, period: str = None) -> bool:
        """删除数据（用于数据修正）"""
        pass

    def get_storage_info(self) -> Dict[str, Any]:
        """获取存储信息"""
        return {
            "type": self.storage_type,
            "available": self.is_available(),
            "connected": self._connected,
            "config": {
                k: "***" if "password" in k.lower() else v
                for k, v in self.config.items()
            },
        }

    @property
    def connected(self) -> bool:
        """连接状态"""
        return self._connected


# 指标与表名的映射
INDICATOR_TABLE_MAPPING = {
    "gdp": "cn_gdp",
    "cpi": "cn_cpi",
    "ppi": "cn_ppi",
    "money_supply": "cn_money_supply",
    "social_financing": "cn_social_financing",
    "pmi": "cn_pmi",
    "lpr": "cn_lpr",
}

# 指标时间字段映射
INDICATOR_TIME_FIELD = {
    "gdp": "quarter",
    "cpi": "month",
    "ppi": "month",
    "money_supply": "month",
    "social_financing": "month",
    "pmi": "month",
    "lpr": "date",
}

# 指标数据类型（用于时间范围计算）
INDICATOR_FREQUENCY = {
    "gdp": "quarterly",
    "cpi": "monthly",
    "ppi": "monthly",
    "money_supply": "monthly",
    "social_financing": "monthly",
    "pmi": "monthly",
    "lpr": "irregular",
}
