"""
Redis 缓存层，用于缓存热点宏观数据
"""

import json
import pickle
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging
import pandas as pd

from ....core.connection_registry import get_connection_registry

logger = logging.getLogger(__name__)


class MacroDataCache:
    """宏观数据Redis缓存"""

    def __init__(self):
        """初始化缓存"""
        self.connection_registry = get_connection_registry()
        self.cache_prefix = "macro_data:"

        # 缓存过期时间设置（秒）
        self.cache_ttl = {
            "latest_data": 3600,  # 最新数据缓存1小时
            "range_data": 1800,  # 范围数据缓存30分钟
            "indicator_list": 86400,  # 指标列表缓存24小时
            "sync_status": 300,  # 同步状态缓存5分钟
        }

        logger.info("✅ MacroDataCache 初始化成功")

    @property
    def redis_client(self):
        """获取Redis客户端"""
        redis_conn = self.connection_registry.get_redis()
        return redis_conn.get_client() if redis_conn else None

    def _make_key(self, category: str, *args) -> str:
        """生成缓存键"""
        key_parts = [self.cache_prefix, category] + [str(arg) for arg in args]
        return ":".join(key_parts)

    def _serialize_dataframe(self, df: pd.DataFrame) -> bytes:
        """序列化DataFrame"""
        if df.empty:
            return b""
        return pickle.dumps(df)

    def _deserialize_dataframe(self, data: bytes) -> pd.DataFrame:
        """反序列化DataFrame"""
        if not data:
            return pd.DataFrame()
        try:
            # 确保数据是bytes类型
            if isinstance(data, str):
                data = data.encode("utf-8")
            return pickle.loads(data)
        except (pickle.UnpicklingError, UnicodeDecodeError, TypeError) as e:
            logger.error(f"❌ 反序列化DataFrame失败: {e}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"❌ 反序列化DataFrame失败: {e}")
            return pd.DataFrame()

    def get_latest_data(
        self, indicator: str, periods: int = 1
    ) -> Optional[pd.DataFrame]:
        """
        获取缓存的最新数据

        Args:
            indicator: 指标名称
            periods: 期数

        Returns:
            DataFrame或None
        """
        if not self.redis_client:
            return None

        try:
            key = self._make_key("latest", indicator, periods)
            data = self.redis_client.get(key)

            if data:
                df = self._deserialize_dataframe(data)
                logger.debug(f"🎯 缓存命中: {indicator} 最新{periods}期数据")
                return df

            return None

        except Exception as e:
            logger.error(f"❌ 获取缓存数据失败: {e}")
            return None

    def set_latest_data(self, indicator: str, periods: int, data: pd.DataFrame):
        """
        缓存最新数据

        Args:
            indicator: 指标名称
            periods: 期数
            data: 数据
        """
        if not self.redis_client or data.empty:
            return

        try:
            key = self._make_key("latest", indicator, periods)
            serialized_data = self._serialize_dataframe(data)

            self.redis_client.setex(key, self.cache_ttl["latest_data"], serialized_data)

            logger.debug(f"💾 缓存已保存: {indicator} 最新{periods}期数据")

        except Exception as e:
            logger.error(f"❌ 保存缓存数据失败: {e}")

    def get_range_data(
        self, indicator: str, start_time: str, end_time: str
    ) -> Optional[pd.DataFrame]:
        """
        获取缓存的范围数据

        Args:
            indicator: 指标名称
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            DataFrame或None
        """
        if not self.redis_client:
            return None

        try:
            key = self._make_key("range", indicator, start_time, end_time)
            data = self.redis_client.get(key)

            if data:
                df = self._deserialize_dataframe(data)
                logger.debug(
                    f"🎯 缓存命中: {indicator} {start_time}~{end_time} 范围数据"
                )
                return df

            return None

        except Exception as e:
            logger.error(f"❌ 获取范围缓存数据失败: {e}")
            return None

    def set_range_data(
        self, indicator: str, start_time: str, end_time: str, data: pd.DataFrame
    ):
        """
        缓存范围数据

        Args:
            indicator: 指标名称
            start_time: 开始时间
            end_time: 结束时间
            data: 数据
        """
        if not self.redis_client or data.empty:
            return

        try:
            key = self._make_key("range", indicator, start_time, end_time)
            serialized_data = self._serialize_dataframe(data)

            self.redis_client.setex(key, self.cache_ttl["range_data"], serialized_data)

            logger.debug(f"💾 缓存已保存: {indicator} {start_time}~{end_time} 范围数据")

        except Exception as e:
            logger.error(f"❌ 保存范围缓存数据失败: {e}")

    def get_sync_status(self) -> Optional[Dict[str, Any]]:
        """获取缓存的同步状态"""
        if not self.redis_client:
            return None

        try:
            key = self._make_key("sync_status")
            data = self.redis_client.get(key)

            if data:
                # 确保数据是字符串格式
                if isinstance(data, bytes):
                    try:
                        data_str = data.decode("utf-8")
                    except UnicodeDecodeError:
                        logger.warning("⚠️ 同步状态缓存数据格式异常，清除缓存")
                        self.redis_client.delete(key)
                        return None
                else:
                    data_str = str(data)

                status = json.loads(data_str)
                logger.debug("🎯 缓存命中: 同步状态")
                return status

            return None

        except Exception as e:
            logger.error(f"❌ 获取同步状态缓存失败: {e}")
            return None

    def set_sync_status(self, status: Dict[str, Any]):
        """缓存同步状态"""
        if not self.redis_client:
            return

        try:
            key = self._make_key("sync_status")
            data = json.dumps(status, ensure_ascii=False, default=str)

            self.redis_client.setex(key, self.cache_ttl["sync_status"], data)

            logger.debug("💾 缓存已保存: 同步状态")

        except Exception as e:
            logger.error(f"❌ 保存同步状态缓存失败: {e}")

    def invalidate_indicator(self, indicator: str):
        """
        失效指定指标的所有缓存

        Args:
            indicator: 指标名称
        """
        if not self.redis_client:
            return

        try:
            # 查找所有相关的缓存键
            pattern = self._make_key("*", indicator, "*")
            keys = self.redis_client.keys(pattern)

            if keys:
                self.redis_client.delete(*keys)
                logger.info(f"🗑️ 已清除 {indicator} 的 {len(keys)} 个缓存")

        except Exception as e:
            logger.error(f"❌ 清除指标缓存失败: {e}")

    def invalidate_all(self):
        """清除所有宏观数据缓存"""
        if not self.redis_client:
            return

        try:
            pattern = self.cache_prefix + "*"
            keys = self.redis_client.keys(pattern)

            if keys:
                self.redis_client.delete(*keys)
                logger.info(f"🗑️ 已清除所有宏观数据缓存 ({len(keys)} 个)")

        except Exception as e:
            logger.error(f"❌ 清除所有缓存失败: {e}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        if not self.redis_client:
            return {"status": "redis_unavailable"}

        try:
            pattern = self.cache_prefix + "*"
            keys = self.redis_client.keys(pattern)

            stats = {"total_keys": len(keys), "categories": {}, "memory_usage_bytes": 0}

            # 按类别统计
            for key in keys:
                try:
                    key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                    parts = key_str.split(":")
                    if len(parts) >= 3:
                        category = parts[2]  # macro_data:category:...
                        stats["categories"][category] = (
                            stats["categories"].get(category, 0) + 1
                        )

                    # 计算内存使用（近似）
                    memory = self.redis_client.memory_usage(key)
                    if memory:
                        stats["memory_usage_bytes"] += memory

                except Exception:
                    continue

            return stats

        except Exception as e:
            logger.error(f"❌ 获取缓存统计失败: {e}")
            return {"status": "error", "error": str(e)}
