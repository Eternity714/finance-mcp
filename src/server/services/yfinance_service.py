"""
YFinance 数据服务 - 使用统一连接管理
封装 yfinance 库，提供统一的接口获取全球市场（特别是美股和港股）数据。
"""

import pandas as pd
from typing import Dict, Optional, Any
import logging

try:
    import yfinance as yf
except ImportError:
    yf = None

from ...config.settings import get_settings

logger = logging.getLogger("yfinance_service")


class YFinanceService:
    """封装 yfinance 的数据服务（简化连接管理）"""

    def __init__(self, proxy: Optional[str] = None):
        """初始化 YFinance 服务"""
        if yf is None:
            logger.error("❌ yfinance 未安装，请执行 'pip install yfinance'")
            raise ImportError("yfinance 未安装")

        settings = get_settings()
        # 优先使用传入的代理，其次是配置文件的，最后是None
        self.proxy = proxy or getattr(settings, "yfinance_proxy", None)

        if self.proxy:
            logger.info(f"🔧 YFinanceService 将使用代理: {self.proxy}")
        else:
            logger.info("🔧 YFinanceService 未配置代理")

        logger.info("✅ YFinanceService 初始化成功")

    @property
    def connected(self) -> bool:
        """YFinance 不需要连接状态，始终返回 True"""
        return yf is not None

    def _get_ticker(self, symbol: str):
        """获取 yfinance Ticker 对象"""
        if not self.connected:
            raise ConnectionError("YFinanceService 未连接")
        return yf.Ticker(symbol)

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
        try:
            logger.info(f"🌍 [yfinance] 正在获取 {symbol} 的日线数据...")
            ticker = self._get_ticker(symbol)
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
        try:
            logger.info(f"🌍 [yfinance] 正在获取 {symbol} 的基本面数据...")
            ticker = self._get_ticker(symbol)
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

    def get_income_statement(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        获取公司的损益表。

        Args:
            symbol: 股票代码 (yfinance 格式)

        Returns:
            包含损益表数据的 DataFrame，失败则引发异常。
        """
        try:
            logger.info(f"🌍 [yfinance] 正在获取 {symbol} 的损益表...")
            ticker = self._get_ticker(symbol)
            income_stmt = ticker.financials
            if income_stmt.empty:
                logger.warning(f"⚠️ [yfinance] 未返回 {symbol} 的损益表数据")
                return None
            logger.info(f"✅ [yfinance] 成功获取 {symbol} 的损益表")
            return income_stmt
        except Exception as e:
            logger.error(f"❌ [yfinance] 获取 {symbol} 损益表失败: {e}")
            raise

    def get_balance_sheet(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        获取公司的资产负债表。

        Args:
            symbol: 股票代码 (yfinance 格式)

        Returns:
            包含资产负债表数据的 DataFrame，失败则引发异常。
        """
        try:
            logger.info(f"🌍 [yfinance] 正在获取 {symbol} 的资产负债表...")
            ticker = self._get_ticker(symbol)
            balance_sheet = ticker.balance_sheet
            if balance_sheet.empty:
                logger.warning(f"⚠️ [yfinance] 未返回 {symbol} 的资产负债表数据")
                return None
            logger.info(f"✅ [yfinance] 成功获取 {symbol} 的资产负债表")
            return balance_sheet
        except Exception as e:
            logger.error(f"❌ [yfinance] 获取 {symbol} 资产负债表失败: {e}")
            raise

    def get_cash_flow(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        获取公司的现金流量表。

        Args:
            symbol: 股票代码 (yfinance 格式)

        Returns:
            包含现金流量表数据的 DataFrame，失败则引发异常。
        """
        try:
            logger.info(f"🌍 [yfinance] 正在获取 {symbol} 的现金流量表...")
            ticker = self._get_ticker(symbol)
            cash_flow = ticker.cashflow
            if cash_flow.empty:
                logger.warning(f"⚠️ [yfinance] 未返回 {symbol} 的现金流量表数据")
                return None
            logger.info(f"✅ [yfinance] 成功获取 {symbol} 的现金流量表")
            return cash_flow
        except Exception as e:
            logger.error(f"❌ [yfinance] 获取 {symbol} 现金流量表失败: {e}")
            raise

    def get_dividends(self, symbol: str) -> Optional[pd.DataFrame]:
        """获取历史股息数据"""
        try:
            logger.info(f"🌍 [yfinance] 正在获取 {symbol} 的股息数据...")
            ticker = self._get_ticker(symbol)
            dividends = ticker.dividends
            logger.info(f"✅ [yfinance] 成功获取 {symbol} 的股息数据")
            return dividends
        except Exception as e:
            logger.error(f"❌ [yfinance] 获取 {symbol} 股息数据失败: {e}")
            raise
