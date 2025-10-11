"""
统一数据源连接管理器（简化版）
提供全局单例的数据源连接管理
"""

from typing import Dict, Any, Optional
import threading
import logging

from ...config.settings import get_settings
from .connections import (
    DataSourceConnection,
    TushareConnection,
    MySQLConnection,
    RedisConnection,
    TdxConnection,
)

logger = logging.getLogger(__name__)


class ConnectionRegistry:
    """
    连接注册表 - 统一管理所有数据源连接

    特点：
    - 全局单例
    - 懒加载（按需初始化）
    - 线程安全
    - 健康检查
    - 自动重连
    """

    _instance: Optional["ConnectionRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化连接注册表"""
        # 避免重复初始化
        if hasattr(self, "_initialized"):
            return

        self._connections: Dict[str, DataSourceConnection] = {}
        self._config = get_settings()
        self._initialized = True

        logger.info("✅ ConnectionRegistry 初始化完成")

    # ==================== Tushare 连接管理 ====================

    def _init_tushare(self) -> bool:
        """初始化 Tushare 连接"""
        if "tushare" in self._connections:
            return True

        try:
            if not self._config.TUSHARE_TOKEN:
                logger.warning("⚠️ TUSHARE_TOKEN 未配置，跳过初始化")
                return False

            conn = TushareConnection(
                {"token": self._config.TUSHARE_TOKEN, "timeout": 60, "retry": 3}
            )

            if conn.connect():
                self._connections["tushare"] = conn
                return True
            else:
                logger.error("❌ Tushare 连接初始化失败")
                return False

        except Exception as e:
            logger.error(f"❌ Tushare 连接初始化异常: {e}")
            return False

    def get_tushare(self):
        """
        获取 Tushare API 客户端

        Returns:
            tushare.pro.client.DataApi: Tushare API 客户端

        Raises:
            ConnectionError: 连接失败时抛出
        """
        if "tushare" not in self._connections:
            if not self._init_tushare():
                raise ConnectionError("Tushare 连接初始化失败")

        conn = self._connections["tushare"]

        # 健康检查
        if not conn.is_healthy():
            logger.warning("⚠️ Tushare 连接不健康，尝试重连")
            if not conn.reconnect():
                raise ConnectionError("Tushare 重连失败")

        return conn.get_client()

    # ==================== TDX 连接管理 ====================

    def _init_tdx(self) -> bool:
        """初始化 TDX (通达信) 连接"""
        if "tdx" in self._connections:
            return True

        try:
            # 检查是否安装了 pytdx
            try:
                from pytdx.hq import TdxHq_API
            except ImportError:
                logger.warning("⚠️ pytdx 库未安装，跳过 TDX 初始化")
                return False

            # TDX 连接不需要太多配置，使用默认服务器列表
            conn = TdxConnection({"timeout": 30, "retry": 3})

            if conn.connect():
                self._connections["tdx"] = conn
                logger.info("✅ TDX 连接初始化成功")
                return True
            else:
                logger.warning("⚠️ TDX 连接初始化失败，可能是网络问题")
                return False

        except Exception as e:
            logger.warning(f"⚠️ TDX 连接初始化异常: {e}")
            return False

    def get_tdx(self):
        """
        获取 TDX (通达信) API 客户端

        Returns:
            TdxHq_API: 通达信API 客户端

        Raises:
            ConnectionError: 连接失败时抛出
        """
        if "tdx" not in self._connections:
            if not self._init_tdx():
                raise ConnectionError("TDX 连接初始化失败")

        conn = self._connections["tdx"]

        # 健康检查
        if not conn.is_healthy():
            logger.warning("⚠️ TDX 连接不健康，尝试重连")
            if not conn.reconnect():
                raise ConnectionError("TDX 重连失败")

        return conn.get_client()

    # ==================== MySQL 连接管理 ====================

    def _init_mysql(self) -> bool:
        """初始化 MySQL 连接"""
        if "mysql" in self._connections:
            return True

        try:
            # 检查必要配置
            if not hasattr(self._config, "MYSQL_HOST") or not self._config.MYSQL_HOST:
                logger.warning("⚠️ MySQL 配置不完整，跳过初始化")
                return False

            conn = MySQLConnection(
                {
                    "host": self._config.MYSQL_HOST,
                    "port": getattr(self._config, "MYSQL_PORT", 3306),
                    "user": getattr(self._config, "MYSQL_USER", "root"),
                    "password": getattr(self._config, "MYSQL_PASSWORD", ""),
                    "database": getattr(self._config, "MYSQL_DATABASE", "stock_mcp"),
                    "pool_size": getattr(self._config, "MYSQL_POOL_SIZE", 10),
                    "charset": "utf8mb4",
                }
            )

            if conn.connect():
                self._connections["mysql"] = conn
                return True
            else:
                logger.error("❌ MySQL 连接初始化失败")
                return False

        except Exception as e:
            logger.error(f"❌ MySQL 连接初始化异常: {e}")
            return False

    def get_mysql(self) -> MySQLConnection:
        """
        获取 MySQL 连接管理器

        Returns:
            MySQLConnection: MySQL 连接管理器

        Raises:
            ConnectionError: 连接失败时抛出
        """
        if "mysql" not in self._connections:
            if not self._init_mysql():
                raise ConnectionError("MySQL 连接初始化失败")

        conn = self._connections["mysql"]

        # 健康检查
        if not conn.is_healthy():
            logger.warning("⚠️ MySQL 连接不健康，尝试重连")
            if not conn.reconnect():
                raise ConnectionError("MySQL 重连失败")

        return conn

    # ==================== Redis 连接管理 ====================

    def _init_redis(self) -> bool:
        """初始化 Redis 连接"""
        if "redis" in self._connections:
            return True

        try:
            # 检查必要配置
            if not hasattr(self._config, "REDIS_HOST") or not self._config.REDIS_HOST:
                logger.warning("⚠️ Redis 配置不完整，跳过初始化")
                return False

            conn = RedisConnection(
                {
                    "host": self._config.REDIS_HOST,
                    "port": getattr(self._config, "REDIS_PORT", 6379),
                    "db": getattr(self._config, "REDIS_DB", 0),
                    "password": getattr(self._config, "REDIS_PASSWORD", None),
                    "pool_size": getattr(self._config, "REDIS_POOL_SIZE", 10),
                    "decode_responses": True,
                }
            )

            if conn.connect():
                self._connections["redis"] = conn
                return True
            else:
                logger.error("❌ Redis 连接初始化失败")
                return False

        except Exception as e:
            logger.error(f"❌ Redis 连接初始化异常: {e}")
            return False

    def get_redis(self) -> RedisConnection:
        """
        获取 Redis 连接管理器

        Returns:
            RedisConnection: Redis 连接管理器

        Raises:
            ConnectionError: 连接失败时抛出
        """
        if "redis" not in self._connections:
            if not self._init_redis():
                raise ConnectionError("Redis 连接初始化失败")

        conn = self._connections["redis"]

        # 健康检查
        if not conn.is_healthy():
            logger.warning("⚠️ Redis 连接不健康，尝试重连")
            if not conn.reconnect():
                raise ConnectionError("Redis 重连失败")

        return conn

    # ==================== 通用方法 ====================

    def get_connection(self, source: str) -> Optional[DataSourceConnection]:
        """
        获取指定数据源连接

        Args:
            source: 数据源名称 (tushare/mysql/redis/tdx)

        Returns:
            Optional[DataSourceConnection]: 数据源连接，如果未配置则返回 None

        Raises:
            ValueError: 不支持的数据源
        """
        if source == "tushare":
            if "tushare" not in self._connections:
                self._init_tushare()
            return self._connections.get("tushare")
        elif source == "mysql":
            if "mysql" not in self._connections:
                self._init_mysql()
            return self._connections.get("mysql")
        elif source == "redis":
            if "redis" not in self._connections:
                self._init_redis()
            return self._connections.get("redis")
        elif source == "tdx":
            if "tdx" not in self._connections:
                self._init_tdx()
            return self._connections.get("tdx")
        else:
            raise ValueError(f"不支持的数据源: {source}")

    def health_check(self) -> Dict[str, Any]:
        """
        所有数据源健康检查

        Returns:
            Dict: 健康状态字典
        """
        health = {}

        for name, conn in self._connections.items():
            try:
                health[name] = {
                    "healthy": conn.is_healthy(),
                    "connected": conn.connected,
                    "stats": conn.get_stats(),
                }
            except Exception as e:
                health[name] = {
                    "healthy": False,
                    "connected": False,
                    "error": str(e),
                }

        return health

    def close_all(self):
        """关闭所有连接"""
        logger.info("🔄 正在关闭所有数据源连接...")

        for name, conn in self._connections.items():
            try:
                conn.disconnect()
                logger.info(f"✅ {name} 连接已关闭")
            except Exception as e:
                logger.error(f"❌ {name} 关闭失败: {e}")

        self._connections.clear()
        logger.info("✅ 所有连接已关闭")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取所有连接的统计信息

        Returns:
            Dict: 统计信息字典
        """
        stats = {
            "total_connections": len(self._connections),
            "connections": {},
        }

        for name, conn in self._connections.items():
            stats["connections"][name] = conn.get_stats()

        return stats


# ==================== 便捷函数 ====================

_global_registry: Optional[ConnectionRegistry] = None


def get_connection_registry() -> ConnectionRegistry:
    """
    获取全局连接注册表单例

    Returns:
        ConnectionRegistry: 连接注册表实例
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ConnectionRegistry()
    return _global_registry
