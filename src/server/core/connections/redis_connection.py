"""
Redis 数据源连接管理
"""

from typing import Dict, Any, Optional
from datetime import datetime
import logging
import json

try:
    import redis
    from redis import ConnectionPool
except ImportError:
    redis = None
    ConnectionPool = None

from .base import DataSourceConnection

logger = logging.getLogger(__name__)


class RedisConnection(DataSourceConnection):
    """Redis 数据源连接（连接池）"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 Redis 连接池

        Args:
            config: 配置字典，需包含:
                - host: Redis 主机
                - port: Redis 端口
                - db: 数据库编号（可选，默认0）
                - password: 密码（可选）
                - pool_size: 连接池大小（可选，默认10）
                - decode_responses: 是否自动解码（可选，默认True）
        """
        super().__init__(config)

        self.host = config.get("host", "localhost")
        self.port = config.get("port", 6379)
        self.db = config.get("db", 0)
        self.password = config.get("password")
        self.pool_size = config.get("pool_size", 10)
        self.decode_responses = config.get("decode_responses", True)

        if redis is None:
            logger.error("❌ redis 库未安装")
            raise ImportError("redis 库未安装，请执行: pip install redis")

    def connect(self) -> bool:
        """建立 Redis 连接池"""
        try:
            logger.info(f"🔄 正在连接 Redis: {self.host}:{self.port}/{self.db}")

            # 创建连接池
            pool = ConnectionPool(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                max_connections=self.pool_size,
                decode_responses=self.decode_responses,
            )

            # 创建 Redis 客户端
            self._client = redis.Redis(connection_pool=pool)

            # 测试连接
            if self.is_healthy():
                self._connected = True
                self._connection_time = datetime.now()
                self.reset_error()
                logger.info(f"✅ Redis 连接成功 (池大小: {self.pool_size})")
                return True
            else:
                logger.error("❌ Redis 健康检查失败")
                return False

        except Exception as e:
            logger.error(f"❌ Redis 连接失败: {e}")
            self._connected = False
            self.increment_error()
            return False

    def disconnect(self) -> bool:
        """关闭 Redis 连接"""
        try:
            if self._client:
                self._client.close()
                self._client = None
                self._connected = False
                logger.info("✅ Redis 连接已关闭")
            return True
        except Exception as e:
            logger.error(f"❌ Redis 关闭失败: {e}")
            return False

    def is_healthy(self) -> bool:
        """
        健康检查

        通过 PING 命令测试连接是否正常
        """
        if not self._client:
            return False

        try:
            # 执行 PING 命令
            result = self._client.ping()

            if result:
                self.reset_error()
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"❌ Redis 健康检查失败: {e}")
            self.increment_error()
            return False

    def get_client(self) -> redis.Redis:
        """
        获取 Redis 客户端

        Returns:
            redis.Redis: Redis 客户端实例
        """
        return super().get_client()

    # ==================== 便捷方法 ====================

    def get(self, key: str) -> Optional[str]:
        """
        获取缓存值

        Args:
            key: 缓存键

        Returns:
            str: 缓存值，不存在返回 None
        """
        try:
            return self._client.get(key)
        except Exception as e:
            logger.error(f"❌ Redis GET 失败: {e}")
            return None

    def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None,
        px: Optional[int] = None,
    ) -> bool:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ex: 过期时间（秒）
            px: 过期时间（毫秒）

        Returns:
            bool: 是否设置成功
        """
        try:
            return self._client.set(key, value, ex=ex, px=px)
        except Exception as e:
            logger.error(f"❌ Redis SET 失败: {e}")
            return False

    def get_json(self, key: str) -> Optional[Any]:
        """
        获取 JSON 格式的缓存值

        Args:
            key: 缓存键

        Returns:
            Any: 解析后的 JSON 数据
        """
        try:
            value = self._client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"❌ Redis GET JSON 失败: {e}")
            return None

    def set_json(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """
        设置 JSON 格式的缓存值

        Args:
            key: 缓存键
            value: 要序列化的数据
            ex: 过期时间（秒）

        Returns:
            bool: 是否设置成功
        """
        try:
            json_value = json.dumps(value, ensure_ascii=False)
            return self._client.set(key, json_value, ex=ex)
        except Exception as e:
            logger.error(f"❌ Redis SET JSON 失败: {e}")
            return False

    def delete(self, *keys: str) -> int:
        """
        删除缓存键

        Args:
            keys: 要删除的键

        Returns:
            int: 删除的键数量
        """
        try:
            return self._client.delete(*keys)
        except Exception as e:
            logger.error(f"❌ Redis DELETE 失败: {e}")
            return 0

    def exists(self, *keys: str) -> int:
        """
        检查键是否存在

        Args:
            keys: 要检查的键

        Returns:
            int: 存在的键数量
        """
        try:
            return self._client.exists(*keys)
        except Exception as e:
            logger.error(f"❌ Redis EXISTS 失败: {e}")
            return 0

    def expire(self, key: str, seconds: int) -> bool:
        """
        设置键的过期时间

        Args:
            key: 缓存键
            seconds: 过期时间（秒）

        Returns:
            bool: 是否设置成功
        """
        try:
            return self._client.expire(key, seconds)
        except Exception as e:
            logger.error(f"❌ Redis EXPIRE 失败: {e}")
            return False
