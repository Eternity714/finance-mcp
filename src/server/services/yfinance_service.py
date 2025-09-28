"""
YFinance 数据服务
封装 yfinance 库，提供统一的接口获取全球市场数据。
"""

import pandas as pd
from typing import Dict, Optional, Any
import logging

from ...config.settings import get_settings

try:
    import yfinance as yf
except ImportError:
    yf = None

logger = logging.getLogger("yfinance_service")


class YFinanceService:
    """封装 yfinance 的数据服务。"""

    def __init__(self, proxy: Optional[str] = None):
        """初始化 YFinance 服务"""
        if yf is None:
            self.connected = False
            logger.error("❌ yfinance 未安装，请执行 'pip install yfinance'")
            raise ImportError("yfinance 未安装")

        settings = get_settings()
        # 优先使用传入的代理，其次是配置文件的，最后是None
        self.proxy = proxy or settings.yfinance_proxy

        if self.proxy:
            logger.info(f"🔧 YFinanceService 将使用代理: {self.proxy}")
        else:
            logger.info("🔧 YFinanceService 未配置代理")

        self.connected = True
        logger.info("✅ YFinanceService 初始化成功")

    def get_stock_daily(
        self, symbol: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """
        获取股票日线历史数据。

        Args:
            symbol: 股票代码 (yfinance 格式, e.g., 'AAPL', '0700.HK')
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            包含日线数据的 DataFrame，失败则返回 None。
        """
        if not self.connected:
            raise ConnectionError("YFinanceService 未连接")

        try:
            logger.info(f"🌍 [yfinance] 正在获取 {symbol} 的日线数据...")
            ticker = yf.Ticker(symbol)
            data = ticker.history(start=start_date, end=end_date, proxy=self.proxy)

            if data.empty:
                logger.warning(f"⚠️ [yfinance] 未返回 {symbol} 的数据")
                return None

            # 标准化列名以匹配项目格式
            data.reset_index(inplace=True)
            data.rename(
                columns={
                    "Date": "date",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                },
                inplace=True,
            )
            # 确保 'date' 列是 datetime 类型
            data["date"] = pd.to_datetime(data["date"])

            logger.info(f"✅ [yfinance] 成功获取 {symbol} 的 {len(data)} 条记录")
            return data

        except Exception as e:
            logger.error(f"❌ [yfinance] 获取 {symbol} 日线数据失败: {e}")
            raise  # 重新抛出异常，由上层服务处理

    def get_fundamentals(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取股票的基本面数据。

        Args:
            symbol: 股票代码 (yfinance 格式)

        Returns:
            包含基本面数据的字典，失败则返回 None。
        """
        if not self.connected:
            raise ConnectionError("YFinanceService 未连接")

        try:
            logger.info(f"🌍 [yfinance] 正在获取 {symbol} 的基本面数据...")
            ticker = yf.Ticker(symbol)
            info = ticker.get_info(proxy=self.proxy)

            if not info or "symbol" not in info:
                logger.warning(f"⚠️ [yfinance] 未返回 {symbol} 的有效基本面信息")
                return None

            logger.info(f"✅ [yfinance] 成功获取 {symbol} 的基本面数据")
            return info

        except Exception as e:
            logger.error(f"❌ [yfinance] 获取 {symbol} 基本面数据失败: {e}")
            raise  # 重新抛出异常

    def get_stock_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取股票的基本信息 (get_fundamentals 的别名，用于接口统一)。
        """
        return self.get_fundamentals(symbol)
