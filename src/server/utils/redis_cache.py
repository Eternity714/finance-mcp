"""
Redis缓存管理器
专门为AKShare全市场数据和基本面数据提供高性能缓存
"""

import redis
import pickle
import time
import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging
import json
import hashlib

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis缓存管理器"""

    def __init__(self, host="localhost", port=6379, db=0, decode_responses=False):
        """
        初始化Redis连接

        Args:
            host: Redis主机地址
            port: Redis端口
            db: Redis数据库编号
            decode_responses: 是否自动解码响应（DataFrame需要设为False）
        """
        try:
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=decode_responses,
                socket_connect_timeout=5,
                socket_timeout=5,
            )

            # 测试连接
            self.redis_client.ping()
            self.connected = True
            logger.info(f"✅ Redis连接成功: {host}:{port}")

        except Exception as e:
            self.connected = False
            logger.error(f"❌ Redis连接失败: {e}")
            logger.warning("🔄 将使用内存缓存作为降级方案")
            self._memory_cache = {}

    def _get_cache_key(self, prefix: str, identifier: str) -> str:
        """生成缓存键"""
        return f"stock_srv:{prefix}:{identifier}"

    def _serialize_dataframe(self, df: pd.DataFrame) -> bytes:
        """序列化DataFrame"""
        return pickle.dumps(df)

    def _deserialize_dataframe(self, data: bytes) -> pd.DataFrame:
        """反序列化DataFrame"""
        return pickle.loads(data)

    def set_market_data(self, data: pd.DataFrame, expire_seconds: int = 86400) -> bool:
        """
        缓存全市场数据

        Args:
            data: 全市场股票数据DataFrame
            expire_seconds: 缓存过期时间（秒）

        Returns:
            bool: 是否缓存成功
        """
        try:
            if not self.connected:
                # 降级到内存缓存
                self._memory_cache["market_data"] = {
                    "data": data,
                    "timestamp": time.time(),
                    "expire_seconds": expire_seconds,
                }
                logger.info("📝 全市场数据已缓存到内存")
                return True

            cache_key = self._get_cache_key("market", "all_stocks")
            serialized_data = self._serialize_dataframe(data)

            # 使用Redis pipeline提高性能
            pipe = self.redis_client.pipeline()
            pipe.set(cache_key, serialized_data)
            pipe.expire(cache_key, expire_seconds)

            # 同时缓存元数据
            metadata = {
                "total_stocks": len(data),
                "columns": list(data.columns),
                "cached_at": datetime.now().isoformat(),
                "expire_seconds": expire_seconds,
            }
            metadata_key = self._get_cache_key("market", "metadata")
            pipe.set(metadata_key, json.dumps(metadata))
            pipe.expire(metadata_key, expire_seconds)

            pipe.execute()

            logger.info(
                f"✅ 全市场数据已缓存到Redis: {len(data)}只股票，过期时间{expire_seconds}秒"
            )
            return True

        except Exception as e:
            logger.error(f"❌ 缓存全市场数据失败: {e}")
            return False

    def get_market_data(self) -> Optional[pd.DataFrame]:
        """
        获取缓存的全市场数据

        Returns:
            Optional[pd.DataFrame]: 全市场数据，如果缓存不存在或过期则返回None
        """
        try:
            if not self.connected:
                # 从内存缓存获取
                cached = self._memory_cache.get("market_data")
                if cached:
                    now = time.time()
                    if now - cached["timestamp"] < cached["expire_seconds"]:
                        logger.info("📖 从内存缓存获取全市场数据")
                        return cached["data"]
                    else:
                        del self._memory_cache["market_data"]
                        logger.info("⏰ 内存缓存已过期")
                return None

            cache_key = self._get_cache_key("market", "all_stocks")
            cached_data = self.redis_client.get(cache_key)

            if cached_data:
                df = self._deserialize_dataframe(cached_data)
                logger.info(f"📖 从Redis缓存获取全市场数据: {len(df)}只股票")
                return df
            else:
                logger.info("💾 Redis缓存中无全市场数据")
                return None

        except Exception as e:
            logger.error(f"❌ 获取缓存全市场数据失败: {e}")
            return None

    def get_stock_from_market_cache(self, symbol: str) -> Optional[pd.Series]:
        """
        从缓存的全市场数据中获取单只股票数据

        Args:
            symbol: 股票代码（不含交易所后缀）

        Returns:
            Optional[pd.Series]: 股票数据，如果不存在则返回None
        """
        try:
            market_data = self.get_market_data()
            if market_data is None or market_data.empty:
                return None

            # 查找股票数据
            stock_data = market_data[market_data["代码"] == symbol]
            if not stock_data.empty:
                logger.info(f"🎯 从市场缓存中找到股票 {symbol}")
                return stock_data.iloc[0]
            else:
                logger.info(f"🔍 市场缓存中未找到股票 {symbol}")
                return None

        except Exception as e:
            logger.error(f"❌ 从市场缓存获取股票{symbol}失败: {e}")
            return None

    def set_fundamental_data(
        self, symbol: str, data: Dict[str, Any], expire_seconds: int = 86400
    ) -> bool:
        """
        缓存基本面数据

        Args:
            symbol: 股票代码
            data: 基本面数据字典
            expire_seconds: 缓存过期时间（秒），默认1小时

        Returns:
            bool: 是否缓存成功
        """
        try:
            if not self.connected:
                return False

            cache_key = self._get_cache_key("fundamental", symbol)

            # 添加缓存时间戳
            data_with_meta = {
                "data": data,
                "cached_at": datetime.now().isoformat(),
                "symbol": symbol,
            }

            self.redis_client.setex(
                cache_key,
                expire_seconds,
                json.dumps(data_with_meta, ensure_ascii=False),
            )

            logger.info(f"✅ 基本面数据已缓存: {symbol}，过期时间{expire_seconds}秒")
            return True

        except Exception as e:
            logger.error(f"❌ 缓存基本面数据失败 {symbol}: {e}")
            return False

    def get_fundamental_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的基本面数据

        Args:
            symbol: 股票代码

        Returns:
            Optional[Dict]: 基本面数据，如果缓存不存在或过期则返回None
        """
        try:
            if not self.connected:
                return None

            cache_key = self._get_cache_key("fundamental", symbol)
            cached_data = self.redis_client.get(cache_key)

            if cached_data:
                data_with_meta = json.loads(cached_data)
                logger.info(f"📖 从Redis获取基本面缓存: {symbol}")
                return data_with_meta["data"]
            else:
                logger.info(f"💾 Redis中无基本面缓存: {symbol}")
                return None

        except Exception as e:
            logger.error(f"❌ 获取基本面缓存失败 {symbol}: {e}")
            return None

    def cache_stock_info(
        self, symbol: str, info: Dict[str, Any], expire_seconds: int = 86400
    ) -> bool:
        """缓存股票基本信息"""
        try:
            if not self.connected:
                return False

            cache_key = self._get_cache_key("info", symbol)
            self.redis_client.setex(
                cache_key, expire_seconds, json.dumps(info, ensure_ascii=False)
            )
            return True
        except Exception as e:
            logger.error(f"❌ 缓存股票信息失败 {symbol}: {e}")
            return False

    def get_stock_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取缓存的股票基本信息"""
        try:
            if not self.connected:
                return None

            cache_key = self._get_cache_key("info", symbol)
            cached_data = self.redis_client.get(cache_key)

            if cached_data:
                return json.loads(cached_data)
            return None
        except Exception as e:
            logger.error(f"❌ 获取股票信息缓存失败 {symbol}: {e}")
            return None

    def clear_cache(self, pattern: str = "stock_srv:*") -> int:
        """
        清除缓存

        Args:
            pattern: 缓存键模式，默认清除所有stock_srv相关缓存

        Returns:
            int: 清除的缓存数量
        """
        try:
            if not self.connected:
                cleared = len(self._memory_cache)
                self._memory_cache.clear()
                logger.info(f"🧹 清除内存缓存: {cleared}项")
                return cleared

            keys = self.redis_client.keys(pattern)
            if keys:
                deleted = self.redis_client.delete(*keys)
                logger.info(f"🧹 清除Redis缓存: {deleted}项")
                return deleted
            else:
                logger.info("🧹 无缓存需要清除")
                return 0

        except Exception as e:
            logger.error(f"❌ 清除缓存失败: {e}")
            return 0

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            if not self.connected:
                return {
                    "type": "memory",
                    "connected": False,
                    "memory_cache_size": len(self._memory_cache),
                }

            info = self.redis_client.info()

            # 获取stock_srv相关的键数量
            stock_keys = self.redis_client.keys("stock_srv:*")

            return {
                "type": "redis",
                "connected": True,
                "redis_version": info.get("redis_version"),
                "used_memory": info.get("used_memory_human"),
                "total_keys": (
                    info.get("db0", {}).get("keys", 0) if "db0" in info else 0
                ),
                "stock_srv_keys": len(stock_keys),
                "uptime_seconds": info.get("uptime_in_seconds"),
            }

        except Exception as e:
            logger.error(f"❌ 获取缓存统计失败: {e}")
            return {"type": "unknown", "connected": False, "error": str(e)}

    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        try:
            if not self.connected:
                return False
            return bool(self.redis_client.exists(key))
        except Exception as e:
            logger.error(f"❌ 检查键存在失败: {e}")
            return False

    def get_ttl(self, key: str) -> int:
        """获取键的TTL"""
        try:
            if not self.connected:
                return -2
            return self.redis_client.ttl(key)
        except Exception as e:
            logger.error(f"❌ 获取TTL失败: {e}")
            return -2


# 全局缓存实例
_redis_cache = None


def get_redis_cache() -> RedisCache:
    """获取Redis缓存实例（单例模式）"""
    global _redis_cache
    if _redis_cache is None:
        _redis_cache = RedisCache()
    return _redis_cache


class AKShareMarketCache:
    """AKShare多市场数据缓存管理器（专门优化性能）"""

    def __init__(self, cache_duration: int = 86400):
        """
        初始化AKShare市场数据缓存

        Args:
            cache_duration: 缓存时长（秒），默认24小时
        """
        self.redis_cache = get_redis_cache()
        self.cache_duration = cache_duration

        # 不同市场的缓存键
        self.cache_keys = {
            "china": "akshare:market_data:china_stocks",
            "hk": "akshare:market_data:hk_stocks",
            "us": "akshare:market_data:us_stocks",
        }

        # 不同市场的获取时间和内存备份
        self._last_fetch_time = {"china": 0, "hk": 0, "us": 0}
        self._memory_backup = {"china": None, "hk": None, "us": None}

    def get_china_market_data(self) -> Optional[pd.DataFrame]:
        """
        获取A股全市场数据（优先从缓存）

        Returns:
            DataFrame: A股全市场股票数据
        """
        return self._get_market_data_by_type("china")

    def get_hk_market_data(self) -> Optional[pd.DataFrame]:
        """
        获取港股全市场数据（优先从缓存）

        Returns:
            DataFrame: 港股全市场股票数据
        """
        return self._get_market_data_by_type("hk")

    def get_us_market_data(self) -> Optional[pd.DataFrame]:
        """
        获取美股全市场数据（优先从缓存）

        Returns:
            DataFrame: 美股全市场股票数据
        """
        return self._get_market_data_by_type("us")

    def _get_market_data_by_type(self, market_type: str) -> Optional[pd.DataFrame]:
        """
        通用的市场数据获取方法

        Args:
            market_type: 市场类型 ("china", "hk", "us")

        Returns:
            DataFrame: 对应市场的股票数据
        """
        cache_key = self.cache_keys[market_type]

        # 先尝试从Redis缓存获取
        cached_data = self._get_market_data_from_redis(cache_key)
        if cached_data is not None:
            market_name = {"china": "A股", "hk": "港股", "us": "美股"}[market_type]
            logger.info(
                f"📋 使用Redis缓存的{market_name}数据: {len(cached_data)}只股票"
            )
            self._memory_backup[market_type] = cached_data  # 更新内存备份
            return cached_data

        # Redis缓存未命中，检查内存备份
        current_time = time.time()
        if (
            self._memory_backup[market_type] is not None
            and current_time - self._last_fetch_time[market_type] < self.cache_duration
        ):
            market_name = {"china": "A股", "hk": "港股", "us": "美股"}[market_type]
            logger.info(
                f"📋 使用内存备份的{market_name}数据: {len(self._memory_backup[market_type])}只股票"
            )
            return self._memory_backup[market_type]

        # 所有缓存都未命中，从AKShare获取数据
        return self._fetch_fresh_data_by_type(market_type)

    def _get_market_data_from_redis(self, cache_key: str) -> Optional[pd.DataFrame]:
        """从Redis获取市场数据"""
        try:
            if not self.redis_cache.connected:
                return None

            cached_data = self.redis_cache.redis_client.get(cache_key)
            if cached_data:
                return self.redis_cache._deserialize_dataframe(cached_data)
            return None
        except Exception as e:
            logger.error(f"❌ 从Redis获取数据失败: {e}")
            return None

    def _fetch_fresh_data_by_type(self, market_type: str) -> Optional[pd.DataFrame]:
        """根据市场类型从AKShare获取新数据"""
        try:
            import akshare as ak

            market_name = {"china": "A股", "hk": "港股", "us": "美股"}[market_type]
            logger.info(f"🔄 从AKShare获取{market_name}全市场数据...")
            start_time = time.time()

            # 根据市场类型调用不同的AKShare接口
            if market_type == "china":
                market_data = ak.stock_zh_a_spot_em()
            elif market_type == "hk":
                market_data = ak.stock_hk_spot_em()
            elif market_type == "us":
                # 美股数据 - 使用东方财富美股实时行情接口
                market_data = ak.stock_us_spot_em()
            else:
                logger.error(f"❌ 不支持的市场类型: {market_type}")
                return None

            end_time = time.time()
            duration = end_time - start_time

            if market_data is not None and not market_data.empty:
                # 更新缓存时间
                self._last_fetch_time[market_type] = time.time()
                self._memory_backup[market_type] = market_data

                # 缓存到Redis
                if self.redis_cache.connected:
                    self._set_market_data_to_redis(
                        self.cache_keys[market_type], market_data, self.cache_duration
                    )

                logger.info(
                    f"✅ AKShare {market_name}数据获取成功: {len(market_data)}只股票, "
                    f"耗时: {duration:.2f}秒"
                )
                return market_data
            else:
                logger.error(f"❌ AKShare返回空{market_name}数据")
                return self._memory_backup[market_type]  # 返回内存备份

        except Exception as e:
            logger.error(f"❌ AKShare {market_name}数据获取失败: {e}")
            return self._memory_backup[market_type]  # 返回内存备份

    def _set_market_data_to_redis(
        self, cache_key: str, data: pd.DataFrame, expire_seconds: int
    ) -> bool:
        """将市场数据缓存到Redis"""
        try:
            serialized_data = self.redis_cache._serialize_dataframe(data)

            # 使用Redis pipeline提高性能
            pipe = self.redis_cache.redis_client.pipeline()
            pipe.set(cache_key, serialized_data)
            pipe.expire(cache_key, expire_seconds)
            pipe.execute()

            return True
        except Exception as e:
            logger.error(f"❌ 缓存市场数据到Redis失败: {e}")
            return False

    def get_china_stock_data(self, symbol: str) -> Optional[dict]:
        """
        从缓存的A股全市场数据中获取单只股票数据

        Args:
            symbol: 股票代码（不带后缀）

        Returns:
            dict: A股股票市场数据或None
        """
        return self._get_stock_data_by_market("china", symbol)

    def get_hk_stock_data(self, symbol: str) -> Optional[dict]:
        """
        从缓存的港股全市场数据中获取单只股票数据

        Args:
            symbol: 港股代码（不带后缀）

        Returns:
            dict: 港股股票市场数据或None
        """
        return self._get_stock_data_by_market("hk", symbol)

    def get_us_stock_data(self, symbol: str) -> Optional[dict]:
        """
        从缓存的美股全市场数据中获取单只股票数据

        Args:
            symbol: 美股代码

        Returns:
            dict: 美股股票市场数据或None
        """
        return self._get_stock_data_by_market("us", symbol)

    def _get_stock_data_by_market(
        self, market_type: str, symbol: str
    ) -> Optional[dict]:
        """
        通用的单只股票数据获取方法

        Args:
            market_type: 市场类型 ("china", "hk", "us")
            symbol: 股票代码

        Returns:
            dict: 股票市场数据或None
        """
        # 获取对应市场的全市场数据
        if market_type == "china":
            market_data = self.get_china_market_data()
        elif market_type == "hk":
            market_data = self.get_hk_market_data()
        elif market_type == "us":
            market_data = self.get_us_market_data()
        else:
            logger.error(f"❌ 不支持的市场类型: {market_type}")
            return None

        if market_data is None or market_data.empty:
            market_name = {"china": "A股", "hk": "港股", "us": "美股"}[market_type]
            logger.warning(f"⚠️ 无法获取{market_name}全市场数据")
            return None

        # 查找指定股票
        try:
            # 对于美股，需要特殊处理代码格式匹配
            if market_type == "us":
                # 美股代码格式：105.AAPL, 106.MSFT 等
                # 尝试多种匹配方式
                pattern = f".{symbol}"
                stock_data = market_data[market_data["代码"].str.endswith(pattern)]
                if stock_data.empty:
                    # 尝试直接匹配（用户可能传入完整格式）
                    stock_data = market_data[market_data["代码"] == symbol]
            else:
                # A股和港股使用精确匹配
                stock_data = market_data[market_data["代码"] == symbol]

            if stock_data.empty:
                market_name = {"china": "A股", "hk": "港股", "us": "美股"}[market_type]
                if market_type == "us":
                    logger.warning(
                        f"⚠️ 未找到{market_name}股票 {symbol} 的市场数据，"
                        f"尝试过格式: xxx.{symbol}"
                    )
                else:
                    logger.warning(f"⚠️ 未找到{market_name}股票 {symbol} 的市场数据")
                return None

            # 转换为字典
            stock_info = stock_data.iloc[0].to_dict()
            market_name = {"china": "A股", "hk": "港股", "us": "美股"}[market_type]

            # 根据不同市场显示不同的关键指标
            if market_type == "china":
                pe_info = stock_info.get("市盈率-动态", "N/A")
                pb_info = stock_info.get("市净率", "N/A")
                logger.info(
                    f"✅ 获取{market_name}股票数据: {symbol} - PE: {pe_info}, PB: {pb_info}"
                )
            else:
                price_info = stock_info.get("最新价", "N/A")
                change_info = stock_info.get("涨跌幅", "N/A")
                logger.info(
                    f"✅ 获取{market_name}股票数据: {symbol} - 价格: {price_info}, 涨跌幅: {change_info}"
                )

            return stock_info

        except Exception as e:
            market_name = {"china": "A股", "hk": "港股", "us": "美股"}[market_type]
            logger.error(f"❌ 提取{market_name}股票数据失败: {symbol}, 错误: {e}")
            return None

    def get_multiple_stocks_data(
        self, market_type: str, symbols: List[str]
    ) -> Dict[str, dict]:
        """
        批量获取多只股票的市场数据

        Args:
            market_type: 市场类型 ("china", "hk", "us")
            symbols: 股票代码列表

        Returns:
            dict: {symbol: stock_data}
        """
        # 获取对应市场的全市场数据
        if market_type == "china":
            market_data = self.get_china_market_data()
        elif market_type == "hk":
            market_data = self.get_hk_market_data()
        elif market_type == "us":
            market_data = self.get_us_market_data()
        else:
            logger.error(f"❌ 不支持的市场类型: {market_type}")
            return {}

        if market_data is None or market_data.empty:
            return {}

        results = {}
        try:
            for symbol in symbols:
                stock_data = market_data[market_data["代码"] == symbol]
                if not stock_data.empty:
                    results[symbol] = stock_data.iloc[0].to_dict()

            market_name = {"china": "A股", "hk": "港股", "us": "美股"}[market_type]
            logger.info(
                f"✅ 批量获取{market_name}股票数据: {len(results)}/{len(symbols)} 成功"
            )
            return results

        except Exception as e:
            market_name = {"china": "A股", "hk": "港股", "us": "美股"}[market_type]
            logger.error(f"❌ 批量获取{market_name}股票数据失败: {e}")
            return {}

    def clear_cache(self, market_type: str = None) -> bool:
        """
        清除市场数据缓存

        Args:
            market_type: 市场类型，None表示清除所有市场缓存
        """
        if market_type is None:
            # 清除所有市场的缓存
            success_count = 0
            for mtype in ["china", "hk", "us"]:
                if self._clear_single_market_cache(mtype):
                    success_count += 1
            logger.info(f"🗑️ 已清除 {success_count}/3 个市场的缓存数据")
            return success_count > 0
        else:
            # 清除指定市场的缓存
            return self._clear_single_market_cache(market_type)

    def _clear_single_market_cache(self, market_type: str) -> bool:
        """清除单个市场的缓存数据"""
        try:
            cache_key = self.cache_keys[market_type]

            redis_result = True
            if self.redis_cache.connected:
                redis_result = bool(self.redis_cache.redis_client.delete(cache_key))

            self._memory_backup[market_type] = None
            self._last_fetch_time[market_type] = 0

            market_name = {"china": "A股", "hk": "港股", "us": "美股"}[market_type]
            if redis_result:
                logger.info(f"🗑️ {market_name}缓存已清除（Redis + 内存）")
            return redis_result
        except Exception as e:
            logger.error(f"❌ 清除{market_type}市场缓存失败: {e}")
            return False

    def get_cache_info(self, market_type: str = None) -> dict:
        """
        获取缓存状态信息

        Args:
            market_type: 市场类型，None表示获取所有市场信息
        """
        if market_type is None:
            # 返回所有市场的缓存信息
            all_info = {}
            for mtype in ["china", "hk", "us"]:
                all_info[mtype] = self._get_single_market_cache_info(mtype)
            return all_info
        else:
            # 返回指定市场的缓存信息
            return self._get_single_market_cache_info(market_type)

    def _get_single_market_cache_info(self, market_type: str) -> dict:
        """获取单个市场的缓存状态信息"""
        cache_key = self.cache_keys[market_type]
        redis_exists = False
        redis_ttl = -2

        if self.redis_cache.connected:
            try:
                redis_exists = bool(self.redis_cache.redis_client.exists(cache_key))
                if redis_exists:
                    redis_ttl = self.redis_cache.redis_client.ttl(cache_key)
            except Exception as e:
                logger.error(f"❌ 获取Redis缓存信息失败: {e}")

        memory_valid = (
            self._memory_backup[market_type] is not None
            and time.time() - self._last_fetch_time[market_type] < self.cache_duration
        )

        return {
            "market_type": market_type,
            "redis": {
                "exists": redis_exists,
                "ttl": redis_ttl,
                "connected": self.redis_cache.connected,
            },
            "memory": {
                "valid": memory_valid,
                "last_fetch": self._last_fetch_time[market_type],
                "records": (
                    len(self._memory_backup[market_type])
                    if self._memory_backup[market_type] is not None
                    else 0
                ),
            },
            "cache_duration": self.cache_duration,
        }

    def force_refresh(
        self, market_type: str = None
    ) -> Dict[str, Optional[pd.DataFrame]]:
        """
        强制刷新缓存数据

        Args:
            market_type: 市场类型，None表示刷新所有市场
        """
        if market_type is None:
            # 刷新所有市场
            results = {}
            for mtype in ["china", "hk", "us"]:
                market_name = {"china": "A股", "hk": "港股", "us": "美股"}[mtype]
                logger.info(f"🔄 强制刷新{market_name}数据缓存...")
                self._clear_single_market_cache(mtype)
                results[mtype] = self._fetch_fresh_data_by_type(mtype)
            return results
        else:
            # 刷新指定市场
            market_name = {"china": "A股", "hk": "港股", "us": "美股"}[market_type]
            logger.info(f"🔄 强制刷新{market_name}数据缓存...")
            self._clear_single_market_cache(market_type)
            result = self._fetch_fresh_data_by_type(market_type)
            return {market_type: result}
