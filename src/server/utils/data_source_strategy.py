"""
数据源策略工具类
根据股票类型智能选择和排序数据源优先级
"""

from typing import List, Dict
from .symbol_processor import get_symbol_processor
import logging

logger = logging.getLogger("data_source_strategy")


class DataSourceStrategy:
    """数据源策略管理器"""

    def __init__(self):
        self.symbol_processor = get_symbol_processor()

    def get_market_data_sources(self, symbol: str) -> List[str]:
        """
        获取市场数据(K线、行情)的数据源优先级列表

        Args:
            symbol: 股票代码

        Returns:
            List[str]: 数据源优先级列表
        """
        classification = self.symbol_processor.classifier.classify_stock(symbol)

        if classification["is_china"]:
            # A股：Tushare > 通达信 > AKShare
            return ["tushare", "tdx", "akshare"]
        elif classification["is_hk"]:
            # 港股：AKShare > Tushare > YFinance
            return ["akshare", "tushare", "yfinance"]
        elif classification["is_us"]:
            # 美股：YFinance > AKShare
            return ["yfinance", "akshare"]
        else:
            # 未知市场：尝试所有数据源
            return ["yfinance", "akshare", "tushare", "tdx"]

    def get_fundamental_data_sources(self, symbol: str) -> List[str]:
        """
        获取基本面数据(财务报表、指标)的数据源优先级列表

        Args:
            symbol: 股票代码

        Returns:
            List[str]: 数据源优先级列表
        """
        classification = self.symbol_processor.classifier.classify_stock(symbol)

        if classification["is_china"]:
            # A股：Tushare（最完整的财务数据） > AKShare
            return ["tushare", "akshare"]
        elif classification["is_hk"]:
            # 港股：AKShare > Tushare > YFinance
            return ["akshare", "tushare", "yfinance"]
        elif classification["is_us"]:
            # 美股：YFinance（最完整的财务数据） > AKShare
            return ["yfinance", "akshare"]
        else:
            # 未知市场
            return ["yfinance", "akshare", "tushare"]

    def get_news_data_sources(self, symbol: str) -> List[str]:
        """
        获取新闻数据的数据源优先级列表

        Args:
            symbol: 股票代码

        Returns:
            List[str]: 数据源优先级列表
        """
        classification = self.symbol_processor.classifier.classify_stock(symbol)

        if classification["is_china"]:
            # A股新闻：AKShare > Tushare
            return ["akshare", "tushare"]
        elif classification["is_hk"]:
            # 港股新闻：AKShare > YFinance
            return ["akshare", "yfinance"]
        elif classification["is_us"]:
            # 美股新闻：YFinance > AKShare
            return ["yfinance", "akshare"]
        else:
            return ["akshare", "yfinance"]

    def get_all_data_sources(self, symbol: str) -> Dict[str, List[str]]:
        """
        获取某个股票所有类型数据的数据源策略

        Args:
            symbol: 股票代码

        Returns:
            Dict[str, List[str]]: 包含market、fundamental、news的数据源列表
        """
        return {
            "market": self.get_market_data_sources(symbol),
            "fundamental": self.get_fundamental_data_sources(symbol),
            "news": self.get_news_data_sources(symbol),
        }

    def log_strategy(self, symbol: str):
        """
        打印股票的数据源策略日志

        Args:
            symbol: 股票代码
        """
        classification = self.symbol_processor.classifier.classify_stock(symbol)
        strategies = self.get_all_data_sources(symbol)

        logger.info(f"📊 股票 {symbol} 的数据源策略:")
        logger.info(f"  市场类型: {classification['market_name']}")
        logger.info(f"  交易所: {classification['exchange']}")
        logger.info(f"  市场数据源: {' → '.join(strategies['market'])}")
        logger.info(f"  基本面数据源: {' → '.join(strategies['fundamental'])}")
        logger.info(f"  新闻数据源: {' → '.join(strategies['news'])}")


# 全局策略管理器实例
_strategy_manager = None


def get_data_source_strategy() -> DataSourceStrategy:
    """获取数据源策略管理器单例"""
    global _strategy_manager
    if _strategy_manager is None:
        _strategy_manager = DataSourceStrategy()
    return _strategy_manager


# 便捷函数
def get_market_data_sources(symbol: str) -> List[str]:
    """获取市场数据源列表的便捷函数"""
    return get_data_source_strategy().get_market_data_sources(symbol)


def get_fundamental_data_sources(symbol: str) -> List[str]:
    """获取基本面数据源列表的便捷函数"""
    return get_data_source_strategy().get_fundamental_data_sources(symbol)


def get_news_data_sources(symbol: str) -> List[str]:
    """获取新闻数据源列表的便捷函数"""
    return get_data_source_strategy().get_news_data_sources(symbol)


def get_all_data_sources(symbol: str) -> Dict[str, List[str]]:
    """获取所有数据源策略的便捷函数"""
    return get_data_source_strategy().get_all_data_sources(symbol)


def log_data_source_strategy(symbol: str):
    """打印数据源策略的便捷函数"""
    get_data_source_strategy().log_strategy(symbol)
