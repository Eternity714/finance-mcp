"""
全市场数据缓存管理器
支持 Redis → 内存 → 本地文件 的三级缓存降级
"""

import json
import logging
import pickle
import threading
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

logger = logging.getLogger("market_data_cache")


class MarketDataCache:
    """
    全市场数据缓存管理器
    实现三级缓存降级：Redis → 内存 → 本地文件
    """

    def __init__(self, cache_dir: str = ".cache/market_data", ttl: int = 3600):
        """
        初始化缓存管理器

        Args:
            cache_dir: 本地缓存目录
            ttl: 缓存过期时间（秒），默认1小时
        """
        self.ttl = ttl
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 内存缓存
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = threading.Lock()

        # Redis缓存
        self.redis_client = None
        self._init_redis()

        logger.info(f"✅ 市场数据缓存初始化完成 (TTL={ttl}秒, 目录={cache_dir})")

    def _init_redis(self):
        """初始化Redis连接"""
        try:
            from .redis_cache import get_redis_cache

            redis_cache = get_redis_cache()
            if redis_cache and redis_cache.is_connected():
                self.redis_client = redis_cache.redis_client
                logger.info("✅ Redis缓存已启用")
            else:
                logger.warning("⚠️ Redis未连接，将使用内存+文件缓存")
        except Exception as e:
            logger.warning(f"⚠️ Redis初始化失败: {e}，将使用内存+文件缓存")
            self.redis_client = None

    def get(self, market: str, data_type: str = "spot") -> Optional[pd.DataFrame]:
        """
        获取缓存的全市场数据

        Args:
            market: 市场类型 (china/hk/us)
            data_type: 数据类型 (spot/info)

        Returns:
            pd.DataFrame or None
        """
        cache_key = self._get_cache_key(market, data_type)

        # 1. 尝试从内存缓存获取
        data = self._get_from_memory(cache_key)
        if data is not None:
            logger.debug(f"✅ 从内存缓存获取 {cache_key}")
            return data

        # 2. 尝试从Redis获取
        data = self._get_from_redis(cache_key)
        if data is not None:
            logger.debug(f"✅ 从Redis缓存获取 {cache_key}")
            # 写入内存缓存
            self._set_to_memory(cache_key, data)
            return data

        # 3. 尝试从本地文件获取
        data = self._get_from_file(cache_key)
        if data is not None:
            logger.debug(f"✅ 从文件缓存获取 {cache_key}")
            # 写入内存和Redis
            self._set_to_memory(cache_key, data)
            self._set_to_redis(cache_key, data)
            return data

        logger.debug(f"⚠️ 缓存未命中: {cache_key}")
        return None

    def set(self, market: str, data: pd.DataFrame, data_type: str = "spot") -> bool:
        """
        设置全市场数据缓存

        Args:
            market: 市场类型
            data: 数据DataFrame
            data_type: 数据类型

        Returns:
            bool: 是否设置成功
        """
        if data is None or data.empty:
            logger.warning(f"⚠️ 不缓存空数据: {market}/{data_type}")
            return False

        cache_key = self._get_cache_key(market, data_type)

        try:
            # 1. 写入内存
            self._set_to_memory(cache_key, data)

            # 2. 写入Redis
            self._set_to_redis(cache_key, data)

            # 3. 写入文件
            self._set_to_file(cache_key, data)

            logger.info(f"✅ 缓存已更新: {cache_key} ({len(data)} 条记录)")
            return True

        except Exception as e:
            logger.error(f"❌ 缓存设置失败: {cache_key}, {e}")
            return False

    def clear(self, market: str = None):
        """清除缓存"""
        if market:
            # 清除指定市场
            pattern = f"market_data:{market}:*"
            self._clear_by_pattern(pattern)
        else:
            # 清除所有缓存
            with self._cache_lock:
                self._memory_cache.clear()
            if self.redis_client:
                try:
                    keys = self.redis_client.keys("market_data:*")
                    if keys:
                        self.redis_client.delete(*keys)
                except Exception as e:
                    logger.warning(f"⚠️ Redis清除失败: {e}")
            # 清除文件缓存
            for file in self.cache_dir.glob("*.pkl"):
                file.unlink()
            logger.info("✅ 缓存已清除")

    # ==================== 私有方法 ====================

    def _get_cache_key(self, market: str, data_type: str) -> str:
        """生成缓存键"""
        return f"market_data:{market}:{data_type}"

    def _get_from_memory(self, key: str) -> Optional[pd.DataFrame]:
        """从内存获取"""
        with self._cache_lock:
            cache_item = self._memory_cache.get(key)
            if cache_item:
                # 检查是否过期
                if datetime.now() < cache_item["expires_at"]:
                    return cache_item["data"]
                else:
                    # 过期，删除
                    del self._memory_cache[key]
        return None

    def _set_to_memory(self, key: str, data: pd.DataFrame):
        """写入内存"""
        with self._cache_lock:
            self._memory_cache[key] = {
                "data": data.copy(),
                "expires_at": datetime.now() + timedelta(seconds=self.ttl),
            }

    def _get_from_redis(self, key: str) -> Optional[pd.DataFrame]:
        """从Redis获取"""
        if not self.redis_client:
            return None

        try:
            data = self.redis_client.get(key)
            if data:
                # 反序列化
                return pickle.loads(data)
        except Exception as e:
            logger.warning(f"⚠️ Redis读取失败: {key}, {e}")
        return None

    def _set_to_redis(self, key: str, data: pd.DataFrame):
        """写入Redis"""
        if not self.redis_client:
            return

        try:
            # 序列化
            serialized = pickle.dumps(data)
            self.redis_client.setex(key, self.ttl, serialized)
        except Exception as e:
            logger.warning(f"⚠️ Redis写入失败: {key}, {e}")

    def _get_from_file(self, key: str) -> Optional[pd.DataFrame]:
        """从文件获取"""
        file_path = self.cache_dir / f"{key.replace(':', '_')}.pkl"

        if not file_path.exists():
            return None

        try:
            # 检查文件修改时间
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            if datetime.now() > mtime + timedelta(seconds=self.ttl):
                # 过期，删除
                file_path.unlink()
                return None

            # 读取文件
            with open(file_path, "rb") as f:
                return pickle.load(f)

        except Exception as e:
            logger.warning(f"⚠️ 文件读取失败: {file_path}, {e}")
            # 损坏的文件，删除
            try:
                file_path.unlink()
            except:
                pass
        return None

    def _set_to_file(self, key: str, data: pd.DataFrame):
        """写入文件"""
        file_path = self.cache_dir / f"{key.replace(':', '_')}.pkl"

        try:
            with open(file_path, "wb") as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.warning(f"⚠️ 文件写入失败: {file_path}, {e}")

    def _clear_by_pattern(self, pattern: str):
        """按模式清除缓存"""
        # 清除内存
        with self._cache_lock:
            keys_to_delete = [
                k for k in self._memory_cache.keys() if k.startswith(pattern)
            ]
            for k in keys_to_delete:
                del self._memory_cache[k]

        # 清除Redis
        if self.redis_client:
            try:
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
            except Exception as e:
                logger.warning(f"⚠️ Redis清除失败: {e}")

        # 清除文件
        pattern_file = pattern.replace(":", "_").replace("*", "")
        for file in self.cache_dir.glob(f"{pattern_file}*.pkl"):
            file.unlink()

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._cache_lock:
            memory_count = len(self._memory_cache)

        # 文件缓存数量
        file_count = len(list(self.cache_dir.glob("*.pkl")))

        # Redis信息
        redis_keys = 0
        if self.redis_client:
            try:
                redis_keys = len(self.redis_client.keys("market:*"))
            except:
                pass

        return {
            "内存缓存数量": memory_count,
            "文件缓存数量": file_count,
            "Redis缓存数量": redis_keys,
            "Redis可用": self.redis_client is not None,
            "缓存目录": str(self.cache_dir),
            "TTL(秒)": self.ttl,
        }


# ==================== 全局实例 ====================

_global_cache = None


def get_market_data_cache(
    cache_dir: str = ".cache/market_data", ttl: int = 3600
) -> MarketDataCache:
    """获取全市场数据缓存管理器单例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = MarketDataCache(cache_dir=cache_dir, ttl=ttl)
    return _global_cache
