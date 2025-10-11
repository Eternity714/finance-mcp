"""
通达信(TDX)数据服务 - 使用统一连接管理
基于 cankao/tdx_utils.py 的功能，集成连接池和健康检查
"""

import pandas as pd
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import logging
import warnings

try:
    from pytdx.hq import TdxHq_API
except ImportError:
    TdxHq_API = None

from ..utils.stockUtils import StockUtils
from ..exception.exception import DataNotFoundError
from ..core.connection_registry import get_connection_registry

logger = logging.getLogger("tdx_service")
warnings.filterwarnings("ignore")


class DataNotFoundError(Exception):
    """当API调用成功但未返回任何数据时引发的自定义异常"""

    pass


class TdxService:
    """封装通达信行情接口的数据服务（使用统一连接管理）"""

    def __init__(self):
        """初始化通达信服务"""
        self.connection_registry = get_connection_registry()

        # 验证 TDX 连接是否可用（不强制要求）
        try:
            tdx_conn = self.connection_registry.get_connection("tdx")
            if tdx_conn and tdx_conn.is_healthy():
                logger.info("✅ TdxService 初始化成功")
            else:
                logger.warning("⚠️ TDX 未配置或初始化失败，服务不可用")
        except Exception as e:
            logger.warning(f"⚠️ TdxService 初始化失败: {e}")

    @property
    def api(self):
        """延迟获取 TDX API 客户端"""
        try:
            return self.connection_registry.get_tdx()
        except Exception:
            return None

    @property
    def connected(self) -> bool:
        """检查连接状态"""
        try:
            conn = self.connection_registry.get_connection("tdx")
            return conn and conn.is_healthy()
        except Exception:
            return False

    def _get_market_code(self, symbol: str) -> int:
        """
        根据股票代码判断市场
        Returns:
            int: 市场代码 (0=深圳, 1=上海)
        """
        if symbol.startswith(("0", "3")):
            return 0  # 深圳
        elif symbol.startswith(("6", "9")):  # 6 for SH A-shares, 9 for SH B-shares
            return 1  # 上海
        else:
            # 默认深圳，可以根据更复杂的规则调整
            return 0

    # ==================== A股数据接口 ====================

    def get_stock_daily(
        self, symbol: str, start_date: str, end_date: str, period: str = "D"
    ) -> pd.DataFrame:
        """
        获取A股日线、周线或月线历史数据

        Args:
            symbol (str): 股票代码 (e.g., "600519")
            start_date (str): 开始日期 "YYYY-MM-DD"
            end_date (str): 结束日期 "YYYY-MM-DD"
            period (str): 周期 'D'=日线, 'W'=周线, 'M'=月线

        Returns:
            pd.DataFrame: 标准化后的历史行情数据
        """
        if not self.connected or not self.api:
            raise ConnectionError("通达信未连接")

        try:
            market_code = self._get_market_code(symbol)
            logger.info(f"🔄 通达信获取 {symbol} 数据 ({start_date} 到 {end_date})")

            # 计算需要获取的数据量
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            days_diff = (end_dt - start_dt).days

            # 根据周期调整数据量，并增加buffer
            if period == "D":
                count = min(days_diff + 10, 800)
            elif period == "W":
                count = min(days_diff // 7 + 10, 800)
            elif period == "M":
                count = min(days_diff // 30 + 10, 800)
            else:
                count = 800

            # 获取K线数据
            category_map = {"D": 9, "W": 5, "M": 6}
            category = category_map.get(period.upper(), 9)

            data = self.api.get_security_bars(category, market_code, symbol, 0, count)

            if not data:
                logger.warning(f"⚠️ 通达信返回空数据: {symbol}")
                raise DataNotFoundError(f"未获取到 {symbol} 的历史数据")

            # 转换为DataFrame并进行处理
            df = pd.DataFrame(data)
            df["datetime"] = pd.to_datetime(df["datetime"])
            df = df.set_index("datetime")
            df = df.sort_index()

            # 筛选日期范围
            df = df[start_date:end_date]

            if df.empty:
                raise DataNotFoundError(
                    f"在指定日期范围 {start_date} 到 {end_date} 内未找到 {symbol} 的数据"
                )

            # 标准化列名
            df = df.rename(
                columns={
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "vol": "volume",
                    "amount": "turnover",
                }
            )
            df.index.name = "date"
            df.reset_index(inplace=True)

            # 添加股票代码和来源
            df["code"] = symbol
            df["source"] = "tdx"

            logger.info(f"✅ 获取 {symbol} 数据成功: {len(df)} 条")
            return df[
                [
                    "date",
                    "code",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "turnover",
                    "source",
                ]
            ]

        except Exception as e:
            logger.error(f"❌ 获取 {symbol} 数据失败: {e}")
            raise

    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """
        获取股票基本信息（主要为股票名称）
        通达信接口限制较多，主要用于获取名称。
        """
        if not self.connected or not self.api:
            raise ConnectionError("通达信未连接")

        try:
            market_code = self._get_market_code(symbol)
            # get_security_list 接口不稳定且信息有限，这里使用 get_security_quotes 获取实时快照中的名称
            data = self.api.get_security_quotes([(market_code, symbol)])

            if not data:
                raise DataNotFoundError(f"无法从通达信获取 {symbol} 的信息")

            quote = data[0]
            stock_name = quote.get("name", f"股票{symbol}")

            return {
                "symbol": symbol,
                "name": stock_name,
                "source": "tdx",
            }
        except Exception as e:
            logger.error(f"❌ 获取 {symbol} 股票信息失败: {e}")
            # 降级返回默认信息
            return {
                "symbol": symbol,
                "name": f"股票{symbol}",
                "source": "tdx_fallback",
            }

    def get_stock_quote(self, symbol: str) -> Dict[str, Any]:
        """获取股票实时行情快照"""
        if not self.connected or not self.api:
            raise ConnectionError("通达信未连接")

        try:
            market_code = self._get_market_code(symbol)
            data = self.api.get_security_quotes([(market_code, symbol)])

            if not data:
                raise DataNotFoundError(f"未获取到 {symbol} 的实时行情")

            quote = data[0]
            last_close = quote.get("last_close", 0)
            price = quote.get("price", 0)
            change_percent = (
                ((price - last_close) / last_close * 100) if last_close > 0 else 0
            )

            return {
                "code": symbol,
                "name": quote.get("name", f"股票{symbol}"),
                "price": price,
                "last_close": last_close,
                "open": quote.get("open", 0),
                "high": quote.get("high", 0),
                "low": quote.get("low", 0),
                "volume": quote.get("vol", 0),
                "turnover": quote.get("amount", 0),
                "change": price - last_close,
                "change_percent": change_percent,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source": "tdx",
            }
        except Exception as e:
            logger.error(f"❌ 获取 {symbol} 实时行情失败: {e}")
            raise


# ==================== 便捷函数 ====================

_global_service: Optional[TdxService] = None


def get_tdx_service() -> TdxService:
    """获取通达信服务单例"""
    global _global_service
    if _global_service is None or not _global_service.connected:
        try:
            _global_service = TdxService()
        except (ImportError, ConnectionError) as e:
            logger.error(f"初始化 TdxService 失败: {e}")
            raise
    return _global_service
