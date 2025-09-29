"""
股票实时行情服务 (Quote Service)

功能:
- 提供一个统一的接口，用于获取单个股票的实时或近实时行情数据。
- 整合多数据源（AKShare, YFinance, Tushare）并实现降级策略。
- 返回一个标准化的 `StockMarketDataDTO` 对象，使用 Decimal 类型保证精度。
- 利用 Redis 缓存（特别是 AKShareMarketCache）来提高性能。
"""

from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, List
import pandas as pd

from pydantic import BaseModel

# 导入统一的股票代码处理器
from ..utils.symbol_processor import get_symbol_processor

# 导入AKShare市场数据缓存管理器
from ..utils.redis_cache import AKShareMarketCache


class StockMarketDataDTO(BaseModel):
    """
    用于封装从市场获取的原始、通用股票行情数据的DTO。
    这个DTO不包含任何特定于用户的业务逻辑（如持仓市值），
    确保了此数据接口的通用性和可重用性。
    """

    ticker: str
    currentPrice: Optional[Decimal] = None
    dailyChangePercent: Optional[Decimal] = None
    peRatio: Optional[Decimal] = None
    marketCap: Optional[Decimal] = None
    source: Optional[str] = None


class QuoteService:
    """股票实时行情服务"""

    def __init__(self):
        # 初始化数据源服务
        self.services: Dict[str, object] = {}
        self._init_data_sources()

        # 初始化AKShare市场数据缓存管理器，这是获取实时数据的主要来源
        self.market_cache = AKShareMarketCache(cache_duration=3600)  # 1小时缓存

    def _init_data_sources(self):
        """初始化底层数据源服务"""
        try:
            from .tushare_service import TushareService

            self.services["tushare"] = TushareService()
            print("✅ [QuoteService] Tushare数据源已启用")
        except Exception as e:
            print(f"⚠️ [QuoteService] Tushare数据源初始化失败: {e}")

        try:
            from .akshare_service import AkshareService

            self.services["akshare"] = AkshareService()
            print("✅ [QuoteService] AKShare数据源已启用")
        except Exception as e:
            print(f"⚠️ [QuoteService] AKShare数据源初始化失败: {e}")

        try:
            from .yfinance_service import YFinanceService

            self.services["yfinance"] = YFinanceService()
            print("✅ [QuoteService] YFinance数据源已启用")
        except Exception as e:
            print(f"⚠️ [QuoteService] YFinance数据源初始化失败: {e}")

    def get_stock_quote(self, symbol: str) -> StockMarketDataDTO:
        """
        获取单个股票的行情数据，实现多数据源降级。

        Args:
            symbol: 原始股票代码 (e.g., "600519", "00700", "AAPL")

        Returns:
            StockMarketDataDTO: 包含行情数据的DTO对象
        """
        processor = get_symbol_processor()
        symbol_info = processor.process_symbol(symbol)
        display_symbol = symbol_info["formats"]["display"]

        # 根据市场决定数据源的优先级
        # 对于实时行情，AKShare的缓存通常是最高效的
        if symbol_info["is_china"]:
            data_sources = ["akshare", "tushare"]
        elif symbol_info["is_hk"]:
            data_sources = ["yfinance", "akshare", "tushare"]
        else:  # 美股
            data_sources = ["yfinance", "akshare"]

        print(f"🔍 [QuoteService] 开始获取 {display_symbol} 的行情数据")
        print(f"📊 [QuoteService] 数据源策略: {' → '.join(data_sources)}")

        last_error = None
        for source in data_sources:
            try:
                print(f"🔄 [QuoteService] 尝试从 {source} 获取数据...")
                quote_data = None
                if source == "akshare" and "akshare" in self.services:
                    quote_data = self._get_from_akshare_cache(symbol_info)
                elif source == "yfinance" and "yfinance" in self.services:
                    quote_data = self._get_from_yfinance(symbol_info)
                elif source == "tushare" and "tushare" in self.services:
                    quote_data = self._get_from_tushare(symbol_info)

                if quote_data:
                    print(
                        f"✅ [QuoteService] 成功从 {source} 获取到 {display_symbol} 的数据"
                    )
                    return quote_data

            except Exception as e:
                print(f"❌ [QuoteService] 从 {source} 获取数据失败: {e}")
                last_error = e
                continue

        print(
            f"⚠️ [QuoteService] 所有数据源均无法获取 {display_symbol} 的行情，返回空数据。"
        )
        return StockMarketDataDTO(ticker=display_symbol, source="fallback")

    def get_stock_quotes_batch(self, symbols: List[str]) -> List[StockMarketDataDTO]:
        """
        批量获取多个股票的行情数据。

        Args:
            symbols: 包含多个股票代码的列表 (e.g., ["600519", "00700", "AAPL"])

        Returns:
            List[StockMarketDataDTO]: 包含多个行情数据的DTO对象列表
        """
        print(f"📦 [QuoteService] 开始批量获取 {len(symbols)} 个股票的行情数据")
        quotes = []
        for symbol in symbols:
            # 依次调用单次获取方法
            quotes.append(self.get_stock_quote(symbol))
        return quotes

    def _safe_decimal(
        self, value: any, default: Optional[Decimal] = None
    ) -> Optional[Decimal]:
        """安全地将值转换为Decimal，处理无效操作和None"""
        if value is None or value == "" or pd.isna(value):
            return default
        try:
            # AKShare返回的可能是字符串'--'
            if isinstance(value, str) and not value.replace(".", "", 1).isdigit():
                return default
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return default

    def _get_from_akshare_cache(
        self, symbol_info: Dict
    ) -> Optional[StockMarketDataDTO]:
        """从AKShare的全市场缓存中提取数据"""
        market = symbol_info["market_simple_name"]
        cache_key = symbol_info["formats"]["cache_key"]

        market_data = None
        if market == "china":
            market_data = self.market_cache.get_china_stock_data(cache_key)
        elif market == "hk":
            market_data = self.market_cache.get_hk_stock_data(cache_key)
        elif market == "us":
            market_data = self.market_cache.get_us_stock_data(cache_key)

        if not market_data:
            return None

        # 将AKShare返回的字典映射到DTO
        return StockMarketDataDTO(
            ticker=symbol_info["formats"]["display"],
            currentPrice=self._safe_decimal(market_data.get("最新价")),
            dailyChangePercent=self._safe_decimal(market_data.get("涨跌幅")),
            peRatio=self._safe_decimal(
                market_data.get("市盈率-动态") or market_data.get("市盈率")
            ),
            marketCap=self._safe_decimal(market_data.get("总市值")),
            source="akshare_cache",
        )

    def _get_from_yfinance(self, symbol_info: Dict) -> Optional[StockMarketDataDTO]:
        """从YFinance获取数据"""
        yfinance_service = self.services.get("yfinance")
        if not yfinance_service:
            return None

        yfinance_symbol = symbol_info["formats"]["yfinance"]
        info = yfinance_service.get_fundamentals(yfinance_symbol)

        if not info:
            return None

        # YFinance数据映射
        return StockMarketDataDTO(
            ticker=symbol_info["formats"]["display"],
            currentPrice=self._safe_decimal(
                info.get("currentPrice") or info.get("regularMarketPrice")
            ),
            dailyChangePercent=(
                self._safe_decimal(
                    (info.get("currentPrice", 0) / info.get("previousClose", 1) - 1)
                    * 100
                )
                if info.get("previousClose")
                else None
            ),
            peRatio=self._safe_decimal(info.get("trailingPE") or info.get("forwardPE")),
            marketCap=self._safe_decimal(info.get("marketCap")),
            source="yfinance",
        )

    def _get_from_tushare(self, symbol_info: Dict) -> Optional[StockMarketDataDTO]:
        """从Tushare获取数据 (主要用于A股)"""
        if not symbol_info["is_china"]:
            return None  # Tushare的实时行情主要优势在A股

        tushare_service = self.services.get("tushare")
        if not tushare_service:
            return None

        tushare_symbol = symbol_info["formats"]["tushare"]
        market_data = tushare_service.get_market_data(tushare_symbol)

        if not market_data:
            return None

        # 如果Tushare返回的不是当天的数据，则认为获取失败，触发降级
        if not market_data.get("is_today", False):
            print(f"ℹ️ [QuoteService] Tushare 未能获取到当天数据，将尝试下一个数据源。")
            return None

        # Tushare数据映射
        market_cap_yuan = (market_data.get("total_mv", 0) or 0) * 10000

        return StockMarketDataDTO(
            ticker=symbol_info["formats"]["display"],
            # Tushare basic daily不直接提供当前价，这里可以留空或使用昨收
            currentPrice=None,
            dailyChangePercent=None,
            peRatio=self._safe_decimal(
                market_data.get("pe_ttm") or market_data.get("pe")
            ),
            marketCap=(
                self._safe_decimal(market_cap_yuan) if market_cap_yuan > 0 else None
            ),
            source="tushare",
        )
