"""
统一的股票代码处理工具
整合股票分类、标准化、转换等功能
"""

import re
from typing import Dict, Optional, List, Tuple
from .stock_market_classifier import get_stock_classifier, MarketType, ExchangeType


class StockSymbolProcessor:
    """股票代码处理器 - 统一处理股票代码的分类、标准化和转换"""

    def __init__(self):
        self.classifier = get_stock_classifier()

    def process_symbol(self, symbol: str) -> Dict:
        """
        全面处理股票代码，返回所有相关信息

        Args:
            symbol: 原始股票代码

        Returns:
            Dict: 包含分类、标准化后的各种格式
        """
        # 基础分类
        classification = self.classifier.classify_stock(symbol)

        # 生成各种标准化格式
        formats = self._generate_all_formats(symbol, classification)

        # 数据源策略
        data_sources = self._get_data_source_strategy(classification)

        # 合并结果
        result = {
            **classification,
            "formats": formats,
            "data_sources": data_sources,
            "original": symbol,
        }

        return result

    def _generate_all_formats(self, symbol: str, classification: Dict) -> Dict:
        """生成所有需要的代码格式"""
        return {
            "tushare": self.get_tushare_format(symbol, classification),
            "akshare": self.get_akshare_format(symbol, classification),
            "yfinance": self.get_yfinance_format(symbol, classification),
            "news_api": self.get_news_api_format(symbol, classification),
            "cache_key": self.get_cache_key(symbol, classification),
            "display": self.get_display_format(symbol, classification),
        }

    def get_tushare_format(self, symbol: str, classification: Dict = None) -> str:
        """获取Tushare API格式的代码"""
        if classification is None:
            classification = self.classifier.classify_stock(symbol)

        if classification["is_china"]:
            # A股：确保有交易所后缀
            clean_code = self._extract_base_code(symbol)
            if "." in symbol and symbol.count(".") == 1:
                return symbol

            if clean_code.isdigit() and len(clean_code) == 6:
                if clean_code.startswith(("60", "68")):
                    return f"{clean_code}.SH"
                elif clean_code.startswith(("00", "30")):
                    return f"{clean_code}.SZ"
                elif clean_code.startswith("8"):
                    return f"{clean_code}.BJ"
            return symbol

        elif classification["is_hk"]:
            # 港股：Tushare港股格式
            clean_code = self._extract_base_code(symbol)
            if clean_code.isdigit():
                return f"{clean_code.zfill(5)}.HK"
            return symbol

        else:
            # 美股：Tushare不支持，返回原始代码
            return self._extract_base_code(symbol).upper()

    def get_akshare_format(self, symbol: str, classification: Dict = None) -> str:
        """获取AKShare API格式的代码"""
        if classification is None:
            classification = self.classifier.classify_stock(symbol)

        if classification["is_china"]:
            # A股：纯数字代码
            return self._extract_base_code(symbol)

        elif classification["is_hk"]:
            # 港股：5位数字代码
            clean_code = self._extract_base_code(symbol)
            if clean_code.isdigit():
                return clean_code.zfill(5)
            return clean_code

        else:
            # 美股：去除后缀的大写代码
            return self._extract_base_code(symbol).upper()

    def get_yfinance_format(self, symbol: str, classification: Dict = None) -> str:
        """获取YFinance API格式的代码"""
        if classification is None:
            classification = self.classifier.classify_stock(symbol)

        if classification["is_china"]:
            # A股：添加Yahoo Finance后缀
            clean_code = self._extract_base_code(symbol)
            if clean_code.startswith(("60", "68")):
                return f"{clean_code}.SS"  # 上交所
            else:
                return f"{clean_code}.SZ"  # 深交所

        elif classification["is_hk"]:
            # 港股：添加.HK后缀
            clean_code = self._extract_base_code(symbol)
            if clean_code.isdigit():
                return f"{clean_code.zfill(4)}.HK"  # 港股YFinance是4位
            return f"{clean_code}.HK"

        else:
            # 美股：纯代码，去除后缀
            return self._extract_base_code(symbol).upper()

    def get_news_api_format(self, symbol: str, classification: Dict = None) -> str:
        """获取新闻API格式的代码"""
        if classification is None:
            classification = self.classifier.classify_stock(symbol)

        if classification["is_china"]:
            # A股新闻：纯数字代码
            return self._extract_base_code(symbol)

        elif classification["is_hk"]:
            # 港股新闻：标准5位.HK格式
            clean_code = self._extract_base_code(symbol)
            if clean_code.isdigit():
                return f"{clean_code.zfill(5)}.HK"
            elif clean_code.upper().endswith(".HK"):
                return symbol.upper()
            else:
                return f"{clean_code}.HK"

        else:
            # 美股新闻：纯代码，去除所有后缀
            clean_code = self._extract_base_code(symbol).upper()
            # 移除常见美股后缀
            us_suffixes = [".US", ".NASDAQ", ".NYSE", ".NMS"]
            for suffix in us_suffixes:
                if clean_code.endswith(suffix):
                    clean_code = clean_code.replace(suffix, "")
                    break
            return clean_code

    def get_cache_key(self, symbol: str, classification: Dict = None) -> str:
        """获取缓存键格式的代码"""
        if classification is None:
            classification = self.classifier.classify_stock(symbol)

        clean_code = self._extract_base_code(symbol)

        if classification["is_china"]:
            # A股缓存：6位数字
            return clean_code

        elif classification["is_hk"]:
            # 港股缓存：5位数字
            if clean_code.isdigit():
                return clean_code.zfill(5)
            return clean_code

        else:
            # 美股缓存：大写字母代码
            return clean_code.upper()

    def get_display_format(self, symbol: str, classification: Dict = None) -> str:
        """获取显示格式的代码"""
        if classification is None:
            classification = self.classifier.classify_stock(symbol)

        if classification["is_china"]:
            # A股显示：代码 + 交易所
            clean_code = self._extract_base_code(symbol)
            if clean_code.startswith(("60", "68")):
                return f"{clean_code}(SH)"
            elif clean_code.startswith(("00", "30")):
                return f"{clean_code}(SZ)"
            elif clean_code.startswith("8"):
                return f"{clean_code}(BJ)"
            return clean_code

        elif classification["is_hk"]:
            # 港股显示：5位代码.HK
            clean_code = self._extract_base_code(symbol)
            if clean_code.isdigit():
                return f"{clean_code.zfill(5)}.HK"
            return symbol

        else:
            # 美股显示：纯代码
            return self._extract_base_code(symbol).upper()

    def _extract_base_code(self, symbol: str) -> str:
        """提取基础股票代码，去除所有后缀"""
        if not symbol:
            return ""

        # 去除常见后缀
        suffixes = [
            ".SH",
            ".SZ",
            ".BJ",
            ".SS",
            ".XSHE",
            ".XSHG",  # A股后缀
            ".HK",
            ".hk",  # 港股后缀
            ".US",
            ".NASDAQ",
            ".NYSE",
            ".NMS",  # 美股后缀
        ]

        clean_symbol = symbol.strip().upper()
        for suffix in suffixes:
            if clean_symbol.endswith(suffix.upper()):
                clean_symbol = clean_symbol[: -len(suffix)]
                break

        return clean_symbol

    def _get_data_source_strategy(self, classification: Dict) -> Dict:
        """根据市场类型获取数据源策略"""
        if classification["is_china"]:
            return {
                "fundamentals": ["tushare", "akshare"],
                "market_data": ["tushare", "akshare"],
                "news": ["akshare", "eastmoney", "sina"],
                "priority": "tushare",
            }
        elif classification["is_hk"]:
            return {
                "fundamentals": ["tushare", "akshare", "yfinance"],
                "market_data": ["tushare", "akshare", "yfinance"],
                "news": ["akshare", "yfinance", "rss"],
                "priority": "tushare",
            }
        else:  # US market
            return {
                "fundamentals": ["yfinance", "akshare"],
                "market_data": ["yfinance", "akshare"],
                "news": ["yfinance", "finnhub", "alpha_vantage", "newsapi"],
                "priority": "yfinance",
            }

    def get_market_simple_name(self, symbol: str) -> str:
        """获取简化的市场名称"""
        classification = self.classifier.classify_stock(symbol)

        if classification["is_china"]:
            return "china"
        elif classification["is_hk"]:
            return "hk"
        elif classification["is_us"]:
            return "us"
        else:
            return "unknown"

    def batch_process_symbols(self, symbols: List[str]) -> Dict[str, Dict]:
        """批量处理股票代码"""
        results = {}
        for symbol in symbols:
            try:
                results[symbol] = self.process_symbol(symbol)
            except Exception as e:
                results[symbol] = {
                    "error": str(e),
                    "original": symbol,
                    "formats": {},
                    "data_sources": {},
                }
        return results

    def validate_symbol_format(self, symbol: str, expected_market: str = None) -> Dict:
        """验证股票代码格式"""
        result = {"is_valid": False, "market": None, "errors": [], "suggestions": []}

        if not symbol or not symbol.strip():
            result["errors"].append("股票代码不能为空")
            return result

        classification = self.classifier.classify_stock(symbol)

        if classification["market"] == "未知":
            result["errors"].append("无法识别的股票代码格式")
            result["suggestions"].append("请检查股票代码是否正确")
        else:
            result["is_valid"] = True
            result["market"] = classification["market"]

        # 如果指定了期望市场，进行验证
        if expected_market:
            expected_map = {"china": "is_china", "hk": "is_hk", "us": "is_us"}
            if expected_market in expected_map and not classification.get(
                expected_map[expected_market], False
            ):
                result["is_valid"] = False
                result["errors"].append(f"股票代码不属于{expected_market}市场")

        return result


# 全局处理器实例
_processor = None


def get_symbol_processor() -> StockSymbolProcessor:
    """获取股票代码处理器实例（单例模式）"""
    global _processor
    if _processor is None:
        _processor = StockSymbolProcessor()
    return _processor


# 便利函数
def process_symbol(symbol: str) -> Dict:
    """处理股票代码的便利函数"""
    return get_symbol_processor().process_symbol(symbol)


def get_tushare_format(symbol: str) -> str:
    """获取Tushare格式代码的便利函数"""
    return get_symbol_processor().get_tushare_format(symbol)


def get_akshare_format(symbol: str) -> str:
    """获取AKShare格式代码的便利函数"""
    return get_symbol_processor().get_akshare_format(symbol)


def get_yfinance_format(symbol: str) -> str:
    """获取YFinance格式代码的便利函数"""
    return get_symbol_processor().get_yfinance_format(symbol)


def get_news_api_format(symbol: str) -> str:
    """获取新闻API格式代码的便利函数"""
    return get_symbol_processor().get_news_api_format(symbol)


def get_cache_key(symbol: str) -> str:
    """获取缓存键的便利函数"""
    return get_symbol_processor().get_cache_key(symbol)


def get_market_simple_name(symbol: str) -> str:
    """获取市场简化名称的便利函数"""
    return get_symbol_processor().get_market_simple_name(symbol)


def get_data_source_strategy(symbol: str) -> Dict:
    """获取数据源策略的便利函数"""
    processor = get_symbol_processor()
    classification = processor.classifier.classify_stock(symbol)
    return processor._get_data_source_strategy(classification)
