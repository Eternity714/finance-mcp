"""
HTTP POST API 路由
用于接收客户端发送的请求
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

# 导入新的行情服务和数据传输对象
from ..services.quote_service import QuoteService, StockMarketDataDTO
from ..services.calendar_service import CalendarService

logger = logging.getLogger(__name__)
router = APIRouter()

# 初始化服务实例
calendar_service = CalendarService()


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


@router.get("/stock/quote", response_model=StockMarketDataDTO)
async def get_stock_quote(symbol: str):
    """
    获取股票的实时或近实时行情数据。

    返回一个标准化的 StockMarketDataDTO 对象，其中包含价格、涨跌幅、市盈率和市值等信息。
    """
    try:
        if not symbol:
            raise HTTPException(status_code=400, detail="缺少股票代码")

        # 使用新创建的行情服务
        quote_service = QuoteService()

        # 调用服务获取标准化的行情数据DTO
        quote_dto = quote_service.get_stock_quote(symbol)

        return quote_dto

    except Exception as e:
        logger.error(f"获取股票行情数据失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"获取股票行情数据时发生内部错误: {e}"
        )


class QuoteListRequest(BaseModel):
    """批量获取行情的请求体模型"""

    symbols: List[str]


@router.post("/stock/quotes", response_model=List[StockMarketDataDTO])
async def get_stock_quotes(request: QuoteListRequest):
    """
    批量获取多个股票的实时或近实时行情数据。

    传入一个包含多个股票代码的列表，返回一个包含相应行情数据的列表。
    """
    try:
        if not request.symbols:
            raise HTTPException(status_code=400, detail="股票代码列表不能为空")

        # 使用行情服务
        quote_service = QuoteService()

        # 调用新的批量获取方法
        quote_dtos = quote_service.get_stock_quotes_batch(request.symbols)

        return quote_dtos

    except Exception as e:
        logger.error(f"批量获取股票行情数据失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"批量获取股票行情数据时发生内部错误: {e}"
        )


# 日历服务 API 端点
@router.get("/calendar/trading-days")
async def get_trading_days(symbol: str, start_date: str, end_date: str):
    """获取指定股票的交易日列表"""
    try:
        if not symbol:
            raise HTTPException(status_code=400, detail="缺少股票代码参数")
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="缺少日期参数")

        result = calendar_service.get_trading_days(symbol, start_date, end_date)
        return {
            "success": True,
            "data": result,
            "message": f"成功获取 {symbol} 的交易日历",
        }

    except ValueError as e:
        logger.error(f"参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取交易日失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/calendar/is-trading-day")
async def check_trading_day(symbol: str, check_date: str):
    """检查指定日期是否为交易日"""
    try:
        if not symbol:
            raise HTTPException(status_code=400, detail="缺少股票代码参数")
        if not check_date:
            raise HTTPException(status_code=400, detail="缺少日期参数")

        result = calendar_service.is_trading_day(symbol, check_date)
        return {
            "success": True,
            "data": result,
            "message": f"成功检查 {symbol} 在 {check_date} 的交易状态",
        }

    except ValueError as e:
        logger.error(f"参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"检查交易日失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/calendar/trading-hours")
async def get_trading_hours(symbol: str, check_date: str):
    """获取指定日期的交易时间信息"""
    try:
        if not symbol:
            raise HTTPException(status_code=400, detail="缺少股票代码参数")
        if not check_date:
            raise HTTPException(status_code=400, detail="缺少日期参数")

        result = calendar_service.get_trading_hours(symbol, check_date)
        return {
            "success": True,
            "data": result,
            "message": f"成功获取 {symbol} 在 {check_date} 的交易时间",
        }

    except ValueError as e:
        logger.error(f"参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取交易时间失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/calendar/supported-exchanges")
async def get_supported_exchanges():
    """获取支持的交易所列表"""
    try:
        result = calendar_service.get_supported_exchanges()
        return {"success": True, "data": result, "message": "成功获取支持的交易所列表"}

    except Exception as e:
        logger.error(f"获取交易所列表失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")
