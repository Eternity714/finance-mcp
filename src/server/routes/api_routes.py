"""
HTTP POST API 路由
用于接收客户端发送的请求
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/stock/price")
async def get_stock_price_data(symbol: str, start_date: str, end_date: str):
    """获取股票价格数据和分析报告"""
    try:
        if not symbol:
            raise HTTPException(status_code=400, detail="缺少股票代码")
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="缺少日期参数")

        # 使用市场数据服务
        from ..services.market_service import MarketDataService

        market_service = MarketDataService()

        report = market_service.generate_stock_report(symbol, start_date, end_date)

        return {
            "status": "success",
            "data": report,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"获取股票价格数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/fundamental")
async def get_financial_report(symbol: str):
    """获取基本面财务报告"""
    try:
        if not symbol:
            raise HTTPException(status_code=400, detail="缺少股票代码")

        # 使用基本面分析服务
        from ..services.fundamentals_service import FundamentalsAnalysisService

        fundamentals_service = FundamentalsAnalysisService()

        report = fundamentals_service.generate_fundamentals_report(symbol)

        return {
            "status": "success",
            "data": report,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"获取基本面分析失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/news")
async def get_latest_news(symbol: str, days_back: int = 30):
    """获取股票最新新闻"""
    try:
        if not symbol:
            raise HTTPException(status_code=400, detail="缺少股票代码")

        # 使用新闻服务
        from ..services.news_service import RealtimeNewsAggregator
        from ...config.settings import get_settings

        settings = get_settings()
        news_service = RealtimeNewsAggregator(settings)

        # 获取实时股票新闻
        news_items = news_service.get_realtime_stock_news(symbol, days_back)

        # 格式化新闻报告
        report = news_service.format_news_report(news_items, symbol)

        return {
            "status": "success",
            "data": report,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"获取最新新闻失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
