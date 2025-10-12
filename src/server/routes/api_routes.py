"""
HTTP POST API 路由
用于接收客户端发送的请求
"""

import logging
from typing import List
import pandas as pd
import numpy as np

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 导入服务
from ..services.quote_service import QuoteService, StockMarketDataDTO
from ..services.calendar_service import CalendarService
from ..services.macro.macro_service import get_macro_service

# 导入响应封装器
from ..utils.response_wrapper import success_response, error_response

logger = logging.getLogger(__name__)
router = APIRouter()

# 初始化服务实例
calendar_service = CalendarService()
macro_service = get_macro_service()


def clean_dataframe_for_json(df: pd.DataFrame) -> list:
    """
    清理DataFrame中的无效浮点数值，使其符合JSON标准

    Args:
        df: 要清理的DataFrame

    Returns:
        清理后的dict列表
    """
    if df.empty:
        return []

    try:
        # 清理无效的浮点数值
        df_cleaned = df.copy()

        # 处理无穷大值
        df_cleaned = df_cleaned.replace([np.inf, -np.inf], None)

        # 将NaN替换为None
        df_cleaned = df_cleaned.where(pd.notna(df_cleaned), None)

        # 转换为dict列表
        records = df_cleaned.to_dict("records")

        # 进一步清理每个记录中的数值
        cleaned_records = []
        for record in records:
            cleaned_record = {}
            for key, value in record.items():
                if value is None:
                    cleaned_record[key] = None
                elif isinstance(value, (int, float)):
                    # 检查是否是有效的JSON数值
                    if np.isnan(value) or np.isinf(value):
                        cleaned_record[key] = None
                    else:
                        cleaned_record[key] = value
                else:
                    cleaned_record[key] = value
            cleaned_records.append(cleaned_record)

        return cleaned_records

    except Exception as e:
        logger.error(f"❌ 清理DataFrame失败: {e}")
        # 降级处理：逐一检查和清理
        try:
            records = df.to_dict("records")
            cleaned_records = []
            for record in records:
                cleaned_record = {}
                for key, value in record.items():
                    try:
                        if pd.isna(value) or (
                            isinstance(value, float)
                            and (np.isnan(value) or np.isinf(value))
                        ):
                            cleaned_record[key] = None
                        else:
                            cleaned_record[key] = value
                    except (TypeError, ValueError):
                        cleaned_record[key] = str(value) if value is not None else None
                cleaned_records.append(cleaned_record)
            return cleaned_records
        except Exception as e2:
            logger.error(f"❌ DataFrame转换失败: {e2}")
            return []


@router.get("/stock/price")
async def get_stock_price_data(symbol: str, start_date: str, end_date: str):
    """获取股票价格数据和分析报告"""
    try:
        if not symbol:
            raise HTTPException(status_code=400, detail="缺少股票代码")
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="缺少日期参数")

        # 使用市场数据服务
        from ..services.market_service import get_market_service

        market_service = get_market_service()

        report = market_service.generate_market_report(symbol, start_date, end_date)

        return success_response(data=report, message="成功获取股票价格数据和分析报告")

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
        from ..services.fundamentals_service import get_fundamentals_service

        fundamentals_service = get_fundamentals_service()

        report = fundamentals_service.generate_fundamental_report(symbol)

        return success_response(data=report, message="成功获取基本面财务报告")

    except Exception as e:
        logger.error(f"获取基本面分析失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/news")
async def get_latest_news(symbol: str, days_back: int = 30):
    """获取股票最新新闻"""
    try:
        if not symbol:
            raise HTTPException(status_code=400, detail="缺少股票代码")

        # 使用多数据源新闻服务
        from ..services.new_service import get_news_service

        news_service = get_news_service(use_proxy=False)

        # 调用服务获取新闻（使用当前日期向前查询）
        result = news_service.get_news_for_date(symbol, None, days_back)

        if not result.get("success", False):
            error_msg = result.get("error", "获取新闻失败")
            raise HTTPException(status_code=400, detail=error_msg)

        return success_response(
            data=result,
            message=f"成功获取 {symbol} 最近 {days_back} 天的新闻",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取最新新闻失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/news/date")
async def get_news_by_date(symbol: str, target_date: str = None, days_before: int = 30):
    """获取指定日期的股票新闻

    Args:
        symbol: 股票代码
        target_date: 目标日期 (YYYY-MM-DD格式)，默认为当前日期
        days_before: 向前查询的天数，默认30天

    Returns:
        包含新闻数据和元数据的统一响应格式
    """
    try:
        if not symbol:
            raise HTTPException(status_code=400, detail="缺少股票代码")

        # 使用多数据源新闻服务
        from ..services.new_service import get_news_service

        news_service = get_news_service(use_proxy=False)

        # 调用服务获取指定日期的新闻
        result = news_service.get_news_for_date(symbol, target_date, days_before)

        if not result.get("success", False):
            error_msg = result.get("error", "获取新闻失败")
            raise HTTPException(status_code=400, detail=error_msg)

        return success_response(
            data=result,
            message=f"成功获取 {symbol} 在 {target_date or '当前日期'} 的新闻",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取指定日期新闻失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/quote")
async def get_stock_quote(symbol: str):
    """
    获取股票的实时或近实时行情数据。

    返回统一格式的响应，data字段包含价格、涨跌幅、市盈率和市值等信息。
    """
    try:
        if not symbol:
            raise HTTPException(status_code=400, detail="缺少股票代码")

        # 使用新创建的行情服务
        quote_service = QuoteService()

        # 调用服务获取标准化的行情数据DTO
        quote_dto = quote_service.get_stock_quote(symbol)

        return success_response(data=quote_dto, message=f"成功获取 {symbol} 的实时行情")

    except Exception as e:
        logger.error(f"获取股票行情数据失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"获取股票行情数据时发生内部错误: {e}"
        )


class QuoteListRequest(BaseModel):
    """批量获取行情的请求体模型"""

    symbols: List[str]


@router.post("/stock/quotes")
async def get_stock_quotes(request: QuoteListRequest):
    """
    批量获取多个股票的实时或近实时行情数据。

    传入一个包含多个股票代码的列表，返回包含相应行情数据的统一响应。
    """
    try:
        if not request.symbols:
            raise HTTPException(status_code=400, detail="股票代码列表不能为空")

        # 使用行情服务
        quote_service = QuoteService()

        # 调用新的批量获取方法
        quote_dtos = quote_service.get_stock_quotes_batch(request.symbols)

        return success_response(
            data=quote_dtos, message=f"批量获取行情完成，共{len(quote_dtos)}个股票"
        )

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
        return success_response(data=result, message=f"成功获取 {symbol} 的交易日历")

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
        return success_response(
            data=result, message=f"成功检查 {symbol} 在 {check_date} 的交易状态"
        )

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
        return success_response(
            data=result, message=f"成功获取 {symbol} 在 {check_date} 的交易时间"
        )

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
        return success_response(data=result, message="成功获取支持的交易所列表")

    except Exception as e:
        logger.error(f"获取交易所列表失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


# ==================== 宏观数据 API 端点 ====================


@router.get("/macro/smart-dashboard")
async def get_smart_macro_dashboard():
    """
    获取智能宏观数据仪表板 - 自动聚合各指标的最佳期数数据

    自动为不同指标设置最佳的默认期数：
    - GDP: 最近4个季度 (1年)
    - CPI/PPI: 最近12个月 (1年)
    - PMI: 最近12个月 (1年)
    - 货币供应量: 最近12个月 (1年)
    - 社会融资: 最近12个月 (1年)
    - LPR: 最近12期 (通常月度发布)

    Returns:
        包含所有主要宏观指标数据的统一响应
    """
    try:
        dashboard_data = macro_service.get_macro_dashboard_data()

        # 转换DataFrame为dict，使用数据清理函数
        result = {"data": {}, "metadata": dashboard_data["metadata"]}

        for indicator, df in dashboard_data["data"].items():
            result["data"][indicator] = clean_dataframe_for_json(df)

        total_records = sum(len(data) for data in result["data"].values())

        return success_response(
            data=result,
            message=(
                f"成功获取智能宏观数据仪表板，"
                f"共{len(result['data'])}个指标，{total_records}条记录"
            ),
        )

    except Exception as e:
        logger.error(f"获取智能宏观数据仪表板失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/gdp")
async def get_gdp_data(
    periods: int = None, start_quarter: str = None, end_quarter: str = None
):
    """获取GDP数据"""
    try:
        # 参数校验：periods 和 start/end_quarter 是互斥的
        if periods is not None and (
            start_quarter is not None or end_quarter is not None
        ):
            raise HTTPException(
                status_code=400,
                detail="参数错误: 'periods' 不能与 'start_quarter'/'end_quarter' 同时使用。",
            )

        data = macro_service.get_gdp(
            periods=periods, start_quarter=start_quarter, end_quarter=end_quarter
        )

        # 使用数据清理函数
        result = clean_dataframe_for_json(data)

        return success_response(
            data=result, message=f"成功获取GDP数据，共{len(result)}条记录"
        )

    except Exception as e:
        logger.error(f"获取GDP数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/cpi")
async def get_cpi_data(
    periods: int = None, start_month: str = None, end_month: str = None
):
    """获取CPI数据"""
    try:
        data = macro_service.get_cpi(
            periods=periods, start_month=start_month, end_month=end_month
        )

        # 使用数据清理函数
        result = clean_dataframe_for_json(data)

        return success_response(
            data=result, message=f"成功获取CPI数据，共{len(result)}条记录"
        )

    except Exception as e:
        logger.error(f"获取CPI数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/ppi")
async def get_ppi_data(
    periods: int = None, start_month: str = None, end_month: str = None
):
    """获取PPI数据"""
    try:
        data = macro_service.get_ppi(
            periods=periods, start_month=start_month, end_month=end_month
        )

        # 使用数据清理函数
        result = clean_dataframe_for_json(data)

        return success_response(
            data=result, message=f"成功获取PPI数据，共{len(result)}条记录"
        )

    except Exception as e:
        logger.error(f"获取PPI数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/pmi")
async def get_pmi_data(
    periods: int = None, start_month: str = None, end_month: str = None
):
    """获取PMI数据"""
    try:
        data = macro_service.get_pmi(
            periods=periods, start_month=start_month, end_month=end_month
        )

        # 使用数据清理函数
        result = clean_dataframe_for_json(data)

        return success_response(
            data=result, message=f"成功获取PMI数据，共{len(result)}条记录"
        )

    except Exception as e:
        logger.error(f"获取PMI数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/money-supply")
async def get_money_supply_data(
    periods: int = None, start_month: str = None, end_month: str = None
):
    """获取货币供应量数据"""
    try:
        data = macro_service.get_money_supply(
            periods=periods, start_month=start_month, end_month=end_month
        )

        # 使用数据清理函数
        result = clean_dataframe_for_json(data)

        return success_response(
            data=result, message=f"成功获取货币供应量数据，共{len(result)}条记录"
        )

    except Exception as e:
        logger.error(f"获取货币供应量数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/social-financing")
async def get_social_financing_data(
    periods: int = None, start_month: str = None, end_month: str = None
):
    """获取社会融资数据"""
    try:
        data = macro_service.get_social_financing(
            periods=periods, start_month=start_month, end_month=end_month
        )

        # 使用数据清理函数
        result = clean_dataframe_for_json(data)

        return success_response(
            data=result, message=f"成功获取社会融资数据，共{len(result)}条记录"
        )

    except Exception as e:
        logger.error(f"获取社会融资数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/lpr")
async def get_lpr_data(
    periods: int = None, start_date: str = None, end_date: str = None
):
    """获取LPR数据"""
    try:
        data = macro_service.get_lpr(
            periods=periods, start_date=start_date, end_date=end_date
        )

        # 使用数据清理函数
        result = clean_dataframe_for_json(data)

        return success_response(
            data=result, message=f"成功获取LPR数据，共{len(result)}条记录"
        )

    except Exception as e:
        logger.error(f"获取LPR数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 宏观数据组合API ====================


@router.get("/macro/economic-cycle")
async def get_economic_cycle_data(start: str, end: str):
    """获取经济周期相关数据（GDP + PMI + CPI）"""
    try:
        if not start or not end:
            raise HTTPException(status_code=400, detail="缺少start或end参数")

        data = macro_service.get_economic_cycle_data(start, end)

        # 转换DataFrame为dict，使用数据清理函数
        result = {}
        for key, df in data.items():
            result[key] = clean_dataframe_for_json(df)

        return success_response(
            data=result, message=f"成功获取经济周期数据 ({start} - {end})"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取经济周期数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/monetary-policy")
async def get_monetary_policy_data(start: str, end: str):
    """获取货币政策相关数据（货币供应量 + 社融 + LPR）"""
    try:
        if not start or not end:
            raise HTTPException(status_code=400, detail="缺少start或end参数")

        data = macro_service.get_monetary_policy_data(start, end)

        result = {}
        for key, df in data.items():
            result[key] = clean_dataframe_for_json(df)

        return success_response(
            data=result, message=f"成功获取货币政策数据 ({start} - {end})"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取货币政策数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/inflation")
async def get_inflation_data(start: str, end: str):
    """获取通胀相关数据（CPI + PPI）"""
    try:
        if not start or not end:
            raise HTTPException(status_code=400, detail="缺少start或end参数")

        data = macro_service.get_inflation_data(start, end)

        result = {}
        for key, df in data.items():
            result[key] = clean_dataframe_for_json(df)

        return success_response(
            data=result, message=f"成功获取通胀数据 ({start} - {end})"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取通胀数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/latest")
async def get_latest_macro_data(periods: int = 1):
    """获取所有宏观指标的最新数据"""
    try:
        data = macro_service.get_latest_all_indicators(periods=periods)

        result = {}
        for key, df in data.items():
            result[key] = clean_dataframe_for_json(df)

        return success_response(
            data=result, message=f"成功获取所有宏观指标最新{periods}期数据"
        )

    except Exception as e:
        logger.error(f"获取最新宏观数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 宏观数据同步管理API ====================


@router.post("/macro/sync")
async def trigger_macro_sync(indicator: str = None, force: bool = False):
    """手动触发宏观数据同步"""
    try:
        result = macro_service.manual_sync(indicator=indicator, force=force)

        return success_response(
            data=result, message=f"成功触发{'全量' if not indicator else indicator}同步"
        )

    except Exception as e:
        logger.error(f"触发同步失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/sync/status")
async def get_macro_sync_status():
    """获取宏观数据同步状态"""
    try:
        status = macro_service.get_sync_status()

        return success_response(data=status, message="成功获取同步状态")

    except Exception as e:
        logger.error(f"获取同步状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/health")
async def get_macro_service_health():
    """获取宏观数据服务健康状态"""
    try:
        health = macro_service.get_service_health()

        return success_response(data=health, message="成功获取服务健康状态")

    except Exception as e:
        logger.error(f"获取服务健康状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/macro/cache")
async def clear_macro_cache(indicator: str = None):
    """清除宏观数据缓存"""
    try:
        macro_service.clear_cache(indicator=indicator)

        return success_response(
            data={"cleared": indicator or "all"},
            message=f"成功清除{'全部' if not indicator else indicator}缓存",
        )

    except Exception as e:
        logger.error(f"清除缓存失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/cache/stats")
async def get_macro_cache_stats():
    """获取宏观数据缓存统计"""
    try:
        stats = macro_service.get_cache_stats()

        return success_response(data=stats, message="成功获取缓存统计信息")

    except Exception as e:
        logger.error(f"获取缓存统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
