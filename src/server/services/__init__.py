# Services module
"""
股票数据服务模块
包含市场数据、基本面分析、新闻聚合、交易日历等服务
"""

# 主要服务类
from .calendar_service import CalendarService

# 核心服务
from .market_service import (
    MarketDataService,
    get_market_service,
    generate_market_analysis_report,
)
from .fundamentals_service import (
    FundamentalsService,
    get_fundamentals_service,
    generate_fundamental_analysis_report,
)

# 导出的服务
__all__ = [
    "CalendarService",
    "MarketDataService",
    "get_market_service",
    "generate_market_analysis_report",
    "FundamentalsService",
    "get_fundamentals_service",
    "generate_fundamental_analysis_report",
]
