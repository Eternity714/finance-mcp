"""
数据源连接抽象基类
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DataSourceConnection(ABC):
    """数据源连接抽象基类"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化连接

        Args:
            config: 连接配置字典
        """
        self.config = config
        self._client = None
        self._connected = False
        self._connection_time: Optional[datetime] = None
        self._error_count = 0
        self._max_errors = config.get("max_errors", 3)

    @abstractmethod
    def connect(self) -> bool:
        """
        建立连接

        Returns:
            bool: 是否连接成功
        """
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """
        断开连接

        Returns:
            bool: 是否断开成功
        """
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        """
        健康检查

        Returns:
            bool: 连接是否健康
        """
        pass

    def reconnect(self) -> bool:
        """
        重新连接

        Returns:
            bool: 是否重连成功
        """
        logger.info(f"🔄 尝试重新连接 {self.__class__.__name__}")
        self.disconnect()
        return self.connect()

    def get_client(self) -> Any:
        """
        获取客户端实例

        Returns:
            客户端实例
        """
        if not self._connected:
            logger.warning(f"⚠️ 连接未建立，尝试自动连接")
            self.connect()

        return self._client

    @property
    def connected(self) -> bool:
        """连接状态"""
        return self._connected

    @property
    def connection_time(self) -> Optional[datetime]:
        """连接建立时间"""
        return self._connection_time

    @property
    def error_count(self) -> int:
        """错误次数"""
        return self._error_count

    def increment_error(self):
        """增加错误计数"""
        self._error_count += 1
        if self._error_count >= self._max_errors:
            logger.error(
                f"❌ {self.__class__.__name__} 错误次数过多 ({self._error_count})"
            )

    def reset_error(self):
        """重置错误计数"""
        self._error_count = 0

    def get_stats(self) -> Dict[str, Any]:
        """
        获取连接统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "connected": self._connected,
            "connection_time": (
                self._connection_time.isoformat() if self._connection_time else None
            ),
            "error_count": self._error_count,
            "healthy": self.is_healthy() if self._connected else False,
        }
