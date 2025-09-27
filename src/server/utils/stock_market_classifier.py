"""
统一的股票市场分类器
支持A股、港股、美股的精确识别
"""

import re
from typing import Dict, Optional
from enum import Enum


class MarketType(Enum):
    """市场类型枚举"""

    A_STOCK = "A股"
    HK_STOCK = "港股"
    US_STOCK = "美股"
    UNKNOWN = "未知"


class ExchangeType(Enum):
    """交易所类型枚举"""

    # A股交易所
    SSE = "上交所"  # 上海证券交易所
    SZSE = "深交所"  # 深圳证券交易所
    BSE = "北交所"  # 北京证券交易所

    # 港股交易所
    HKEX = "港交所"  # 香港交易所

    # 美股交易所
    NYSE = "纽交所"  # 纽约证券交易所
    NASDAQ = "纳斯达克"  # 纳斯达克

    UNKNOWN = "未知交易所"


class BoardType(Enum):
    """板块类型枚举"""

    # A股板块
    MAIN_BOARD = "主板"
    SME_BOARD = "中小板"  # 已并入主板
    CHINEXT = "创业板"
    STAR_MARKET = "科创板"
    NEW_THIRD_BOARD = "新三板"
    BEIJING_STOCK_EXCHANGE = "北交所"

    # 港股板块
    HK_MAIN_BOARD = "港股主板"
    HK_GEM = "港股创业板"

    # 美股板块
    US_MAIN = "美股主要市场"

    UNKNOWN_BOARD = "未知板块"


class StockMarketClassifier:
    """股票市场分类器"""

    def __init__(self):
        # A股代码规则
        self.a_stock_patterns = {
            # 上海证券交易所
            r"^60\d{4}$": {
                "exchange": ExchangeType.SSE,
                "board": BoardType.MAIN_BOARD,
                "suffix": ".SH",
            },
            r"^601\d{3}$": {
                "exchange": ExchangeType.SSE,
                "board": BoardType.MAIN_BOARD,
                "suffix": ".SH",
            },
            r"^603\d{3}$": {
                "exchange": ExchangeType.SSE,
                "board": BoardType.MAIN_BOARD,
                "suffix": ".SH",
            },
            r"^605\d{3}$": {
                "exchange": ExchangeType.SSE,
                "board": BoardType.MAIN_BOARD,
                "suffix": ".SH",
            },
            r"^688\d{3}$": {
                "exchange": ExchangeType.SSE,
                "board": BoardType.STAR_MARKET,
                "suffix": ".SH",
            },
            r"^900\d{3}$": {
                "exchange": ExchangeType.SSE,
                "board": BoardType.MAIN_BOARD,
                "suffix": ".SH",
            },  # B股
            # 深圳证券交易所
            r"^000\d{3}$": {
                "exchange": ExchangeType.SZSE,
                "board": BoardType.MAIN_BOARD,
                "suffix": ".SZ",
            },
            r"^001\d{3}$": {
                "exchange": ExchangeType.SZSE,
                "board": BoardType.MAIN_BOARD,
                "suffix": ".SZ",
            },
            r"^002\d{3}$": {
                "exchange": ExchangeType.SZSE,
                "board": BoardType.SME_BOARD,
                "suffix": ".SZ",
            },
            r"^003\d{3}$": {
                "exchange": ExchangeType.SZSE,
                "board": BoardType.MAIN_BOARD,
                "suffix": ".SZ",
            },
            r"^300\d{3}$": {
                "exchange": ExchangeType.SZSE,
                "board": BoardType.CHINEXT,
                "suffix": ".SZ",
            },
            r"^200\d{3}$": {
                "exchange": ExchangeType.SZSE,
                "board": BoardType.MAIN_BOARD,
                "suffix": ".SZ",
            },  # B股
            # 北京证券交易所
            r"^8\d{5}$": {
                "exchange": ExchangeType.BSE,
                "board": BoardType.BEIJING_STOCK_EXCHANGE,
                "suffix": ".BJ",
            },
            r"^43\d{4}$": {
                "exchange": ExchangeType.BSE,
                "board": BoardType.NEW_THIRD_BOARD,
                "suffix": ".NQ",
            },
            r"^83\d{4}$": {
                "exchange": ExchangeType.BSE,
                "board": BoardType.NEW_THIRD_BOARD,
                "suffix": ".NQ",
            },
        }

        # 港股代码规则
        self.hk_stock_patterns = {
            # 港股主板 (5位数字，前导0)
            r"^0\d{4}$": {
                "exchange": ExchangeType.HKEX,
                "board": BoardType.HK_MAIN_BOARD,
                "suffix": ".HK",
            },
            r"^[1-9]\d{4}$": {
                "exchange": ExchangeType.HKEX,
                "board": BoardType.HK_MAIN_BOARD,
                "suffix": ".HK",
            },
            # 港股创业板 (08开头)
            r"^08\d{3}$": {
                "exchange": ExchangeType.HKEX,
                "board": BoardType.HK_GEM,
                "suffix": ".HK",
            },
        }

        # 美股代码规则
        self.us_stock_patterns = {
            # 1-4位字母组合
            r"^[A-Z]{1,4}$": {
                "exchange": ExchangeType.NASDAQ,
                "board": BoardType.US_MAIN,
                "suffix": "",
            },
            # 包含数字的美股代码较少见，但也存在
            r"^[A-Z]+\d*[A-Z]*$": {
                "exchange": ExchangeType.NYSE,
                "board": BoardType.US_MAIN,
                "suffix": "",
            },
        }

    def classify_stock(self, symbol: str) -> Dict:
        """
        对股票代码进行市场分类

        Args:
            symbol: 股票代码 (如: '600519', '00700.HK', 'AAPL')

        Returns:
            Dict: 包含市场信息的字典
        """
        if not symbol:
            return self._create_result(
                MarketType.UNKNOWN,
                ExchangeType.UNKNOWN,
                BoardType.UNKNOWN_BOARD,
                symbol,
            )

        # 清理和标准化输入
        original_symbol = symbol
        cleaned_symbol = self._clean_symbol(symbol)

        # 1. 检查是否已包含市场后缀
        market_info = self._check_suffix_based_classification(symbol)
        if market_info:
            return market_info

        # 2. 基于代码模式进行分类

        # 检查A股
        a_stock_info = self._classify_a_stock(cleaned_symbol)
        if a_stock_info:
            return a_stock_info

        # 检查港股
        hk_stock_info = self._classify_hk_stock(cleaned_symbol)
        if hk_stock_info:
            return hk_stock_info

        # 检查美股
        us_stock_info = self._classify_us_stock(cleaned_symbol)
        if us_stock_info:
            return us_stock_info

        # 未知类型
        return self._create_result(
            MarketType.UNKNOWN,
            ExchangeType.UNKNOWN,
            BoardType.UNKNOWN_BOARD,
            original_symbol,
        )

    def _clean_symbol(self, symbol: str) -> str:
        """清理股票代码"""
        return symbol.strip().upper()

    def _check_suffix_based_classification(self, symbol: str) -> Optional[Dict]:
        """基于后缀进行分类"""
        symbol_upper = symbol.upper()

        # 港股后缀
        if symbol_upper.endswith(".HK"):
            clean_code = symbol_upper.replace(".HK", "")
            hk_info = self._classify_hk_stock(clean_code)
            if hk_info:
                hk_info["original_symbol"] = symbol
                return hk_info

        # A股后缀
        if symbol_upper.endswith(".SH"):
            clean_code = symbol_upper.replace(".SH", "")
            a_info = self._classify_a_stock(clean_code)
            if a_info and a_info["exchange"] == ExchangeType.SSE.value:
                a_info["original_symbol"] = symbol
                return a_info

        if symbol_upper.endswith(".SZ"):
            clean_code = symbol_upper.replace(".SZ", "")
            a_info = self._classify_a_stock(clean_code)
            if a_info and a_info["exchange"] == ExchangeType.SZSE.value:
                a_info["original_symbol"] = symbol
                return a_info

        # 其他A股后缀
        for suffix in [".SS", ".XSHE", ".XSHG"]:
            if symbol_upper.endswith(suffix):
                clean_code = symbol_upper.replace(suffix, "")
                return self._classify_a_stock(clean_code)

        # 美股后缀处理
        us_suffixes = [".NMS", ".NASDAQ", ".NYSE", ".US"]
        for suffix in us_suffixes:
            if symbol_upper.endswith(suffix):
                clean_code = symbol_upper.replace(suffix, "")
                us_info = self._classify_us_stock(clean_code)
                if us_info:
                    us_info["original_symbol"] = symbol
                    return us_info

        return None

    def _classify_a_stock(self, symbol: str) -> Optional[Dict]:
        """分类A股"""
        for pattern, info in self.a_stock_patterns.items():
            if re.match(pattern, symbol):
                return self._create_result(
                    MarketType.A_STOCK,
                    info["exchange"],
                    info["board"],
                    symbol,
                    info["suffix"],
                )
        return None

    def _classify_hk_stock(self, symbol: str) -> Optional[Dict]:
        """分类港股"""
        # 标准化港股代码 (补齐到5位)
        if symbol.isdigit():
            if len(symbol) <= 5:
                padded_symbol = symbol.zfill(5)
                for pattern, info in self.hk_stock_patterns.items():
                    if re.match(pattern, padded_symbol):
                        return self._create_result(
                            MarketType.HK_STOCK,
                            info["exchange"],
                            info["board"],
                            padded_symbol,
                            info["suffix"],
                        )
        return None

    def _classify_us_stock(self, symbol: str) -> Optional[Dict]:
        """分类美股"""
        for pattern, info in self.us_stock_patterns.items():
            if re.match(pattern, symbol):
                # 根据字母数量判断交易所 (简化规则)
                exchange = (
                    ExchangeType.NASDAQ if len(symbol) >= 4 else ExchangeType.NYSE
                )
                return self._create_result(
                    MarketType.US_STOCK, exchange, info["board"], symbol, info["suffix"]
                )
        return None

    def _create_result(
        self,
        market: MarketType,
        exchange: ExchangeType,
        board: BoardType,
        symbol: str,
        suffix: str = "",
    ) -> Dict:
        """创建分类结果"""
        full_symbol = (
            f"{symbol}{suffix}" if suffix and not symbol.endswith(suffix) else symbol
        )

        return {
            "market": market.value,
            "market_type": market,
            "exchange": exchange.value,
            "exchange_type": exchange,
            "board": board.value,
            "board_type": board,
            "symbol": symbol,
            "full_symbol": full_symbol,
            "original_symbol": symbol,
            "currency": self._get_currency(market),
            "is_china": market == MarketType.A_STOCK,
            "is_hk": market == MarketType.HK_STOCK,
            "is_us": market == MarketType.US_STOCK,
            "market_name": self._get_market_name(market),
        }

    def _get_currency(self, market: MarketType) -> str:
        """获取市场货币"""
        currency_map = {
            MarketType.A_STOCK: "CNY",
            MarketType.HK_STOCK: "HKD",
            MarketType.US_STOCK: "USD",
            MarketType.UNKNOWN: "UNKNOWN",
        }
        return currency_map.get(market, "UNKNOWN")

    def _get_market_name(self, market: MarketType) -> str:
        """获取市场中文名称"""
        name_map = {
            MarketType.A_STOCK: "中国A股",
            MarketType.HK_STOCK: "香港股市",
            MarketType.US_STOCK: "美国股市",
            MarketType.UNKNOWN: "未知市场",
        }
        return name_map.get(market, "未知市场")

    def is_china_stock(self, symbol: str) -> bool:
        """判断是否为中国股票(A股)"""
        result = self.classify_stock(symbol)
        return result["is_china"]

    def is_hk_stock(self, symbol: str) -> bool:
        """判断是否为港股"""
        result = self.classify_stock(symbol)
        return result["is_hk"]

    def is_us_stock(self, symbol: str) -> bool:
        """判断是否为美股"""
        result = self.classify_stock(symbol)
        return result["is_us"]

    def get_standard_symbol(self, symbol: str) -> str:
        """获取标准化的股票代码"""
        result = self.classify_stock(symbol)
        return result["full_symbol"]


# 全局分类器实例
_classifier = None


def get_stock_classifier() -> StockMarketClassifier:
    """获取股票分类器实例"""
    global _classifier
    if _classifier is None:
        _classifier = StockMarketClassifier()
    return _classifier


# 便利函数
def classify_stock(symbol: str) -> Dict:
    """分类股票代码"""
    return get_stock_classifier().classify_stock(symbol)


def is_china_stock(symbol: str) -> bool:
    """判断是否为A股"""
    return get_stock_classifier().is_china_stock(symbol)


def is_hk_stock(symbol: str) -> bool:
    """判断是否为港股"""
    return get_stock_classifier().is_hk_stock(symbol)


def is_us_stock(symbol: str) -> bool:
    """判断是否为美股"""
    return get_stock_classifier().is_us_stock(symbol)


def get_standard_symbol(symbol: str) -> str:
    """获取标准化股票代码"""
    return get_stock_classifier().get_standard_symbol(symbol)
