"""
日历服务 - 基于 pandas_market_calendars
提供全球交易所的交易日历查询功能。
"""

import pandas as pd
import pandas_market_calendars as mcal
from typing import Dict, List, Optional, Any
from datetime import datetime, date, timedelta
import logging
import os
import sys

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入项目模块
try:
    from src.server.utils.stock_market_classifier import classify_stock, ExchangeType
except ImportError:
    from server.utils.stock_market_classifier import classify_stock, ExchangeType

logger = logging.getLogger("calendar_service")


class CalendarService:
    """基于 pandas_market_calendars 的日历服务"""

    def __init__(self):
        """初始化日历服务"""
        try:
            # 测试 pandas_market_calendars 是否可用
            available_calendars = mcal.get_calendar_names()
            logger.info(
                f"✅ pandas_market_calendars 初始化成功，支持 {len(available_calendars)} 个交易所"
            )
            self.connected = True

            # 缓存常用日历实例，提高性能
            self._calendar_cache = {}

        except Exception as e:
            logger.error(f"❌ pandas_market_calendars 初始化失败: {e}")
            self.connected = False
            raise ConnectionError(f"pandas_market_calendars 初始化失败: {e}") from e

    def _get_exchange_code(self, symbol: str) -> str:
        """
        根据股票代码获取对应的交易所代码

        Args:
            symbol: 股票代码

        Returns:
            str: pandas_market_calendars 支持的交易所代码

        Raises:
            ValueError: 如果无法识别交易所或不支持
        """
        try:
            classification = classify_stock(symbol)
            exchange = classification["exchange"]

            # 映射到 pandas_market_calendars 的交易所代码
            exchange_mapping = {
                ExchangeType.SSE.value: "SSE",  # 上交所
                ExchangeType.SZSE.value: "XSHG",  # 深交所 (使用上交所的日历，因为基本一致)
                ExchangeType.BSE.value: "SSE",  # 北交所 (使用上交所的日历)
                ExchangeType.HKEX.value: "HKEX",  # 港交所
                ExchangeType.NYSE.value: "NYSE",  # 纽交所
                ExchangeType.NASDAQ.value: "NASDAQ",  # 纳斯达克
            }

            if exchange in exchange_mapping:
                return exchange_mapping[exchange]
            else:
                # 对于未映射的交易所，根据市场类型选择默认值
                market = classification["market"]
                if market == "A股":
                    return "SSE"  # A股默认使用上交所日历
                elif market == "港股":
                    return "HKEX"
                elif market == "美股":
                    return "NYSE"  # 美股默认使用纽交所日历
                else:
                    raise ValueError(f"不支持的市场类型: {market}")

        except Exception as e:
            logger.error(f"获取交易所代码失败，symbol: {symbol}, error: {e}")
            raise ValueError(f"无法识别股票代码 {symbol} 对应的交易所") from e

    def _get_calendar(self, exchange_code: str):
        """
        获取日历实例，使用缓存提高性能

        Args:
            exchange_code: 交易所代码

        Returns:
            日历实例
        """
        if exchange_code not in self._calendar_cache:
            try:
                self._calendar_cache[exchange_code] = mcal.get_calendar(exchange_code)
                logger.debug(f"创建日历实例: {exchange_code}")
            except Exception as e:
                logger.error(f"创建日历实例失败: {exchange_code}, error: {e}")
                raise ValueError(f"不支持的交易所: {exchange_code}") from e

        return self._calendar_cache[exchange_code]

    def _parse_date(self, date_input) -> str:
        """
        解析日期输入，统一转换为 YYYY-MM-DD 格式

        Args:
            date_input: 日期输入，支持 str, datetime, date

        Returns:
            str: YYYY-MM-DD 格式的日期字符串
        """
        if isinstance(date_input, str):
            # 尝试解析各种字符串格式
            try:
                if len(date_input) == 8 and date_input.isdigit():
                    # YYYYMMDD 格式
                    return f"{date_input[:4]}-{date_input[4:6]}-{date_input[6:8]}"
                else:
                    # 其他格式，尝试自动解析
                    parsed_date = pd.to_datetime(date_input)
                    return parsed_date.strftime("%Y-%m-%d")
            except Exception as e:
                raise ValueError(f"无法解析日期字符串: {date_input}") from e

        elif isinstance(date_input, datetime):
            return date_input.strftime("%Y-%m-%d")
        elif isinstance(date_input, date):
            return date_input.strftime("%Y-%m-%d")
        else:
            raise ValueError(f"不支持的日期类型: {type(date_input)}")

    def get_trading_days(
        self, symbol: str, start_date: Any, end_date: Any
    ) -> Dict[str, Any]:
        """
        获取指定股票在指定日期范围内的所有交易日

        Args:
            symbol: 股票代码
            start_date: 开始日期 (支持 str, datetime, date)
            end_date: 结束日期 (支持 str, datetime, date)

        Returns:
            Dict: 包含交易日信息的字典
            {
                "symbol": str,               # 股票代码
                "exchange": str,             # 交易所
                "market": str,               # 市场
                "start_date": str,           # 开始日期
                "end_date": str,             # 结束日期
                "trading_days": List[str],   # 交易日列表 (YYYY-MM-DD 格式)
                "trading_days_count": int,   # 交易日数量
                "total_days": int,           # 总天数
                "timezone": str              # 时区信息
            }

        Raises:
            ValueError: 参数错误
            ConnectionError: 服务连接失败
        """
        if not self.connected:
            raise ConnectionError("日历服务未连接")

        try:
            # 解析日期
            start_str = self._parse_date(start_date)
            end_str = self._parse_date(end_date)

            # 验证日期范围
            if start_str > end_str:
                raise ValueError("开始日期不能晚于结束日期")

            # 获取交易所代码和日历实例
            exchange_code = self._get_exchange_code(symbol)
            calendar = self._get_calendar(exchange_code)

            # 获取股票分类信息
            classification = classify_stock(symbol)

            # 获取交易日
            valid_days = calendar.valid_days(start_date=start_str, end_date=end_str)
            trading_days = [day.strftime("%Y-%m-%d") for day in valid_days]

            # 计算总天数
            start_dt = pd.to_datetime(start_str)
            end_dt = pd.to_datetime(end_str)
            total_days = (end_dt - start_dt).days + 1

            # 获取时区信息
            timezone = str(calendar.tz) if hasattr(calendar, "tz") else "Unknown"

            result = {
                "symbol": symbol,
                "exchange": exchange_code,
                "market": classification["market"],
                "market_name": classification["market_name"],
                "start_date": start_str,
                "end_date": end_str,
                "trading_days": trading_days,
                "trading_days_count": len(trading_days),
                "total_days": total_days,
                "timezone": timezone,
            }

            logger.info(
                f"获取交易日成功: {symbol}, {start_str} 到 {end_str}, 共 {len(trading_days)} 个交易日"
            )
            return result

        except Exception as e:
            logger.error(
                f"获取交易日失败: symbol={symbol}, start={start_date}, end={end_date}, error={e}"
            )
            raise

    def is_trading_day(self, symbol: str, check_date: Any) -> Dict[str, Any]:
        """
        判断指定日期是否为交易日

        Args:
            symbol: 股票代码
            check_date: 要检查的日期 (支持 str, datetime, date)

        Returns:
            Dict: 判断结果
            {
                "symbol": str,           # 股票代码
                "exchange": str,         # 交易所
                "market": str,           # 市场
                "check_date": str,       # 检查日期 (YYYY-MM-DD)
                "is_trading_day": bool,  # 是否为交易日
                "day_of_week": str,      # 星期几
                "timezone": str,         # 时区信息
                "next_trading_day": str, # 下一个交易日 (如果当天不是交易日)
                "prev_trading_day": str  # 上一个交易日 (如果当天不是交易日)
            }

        Raises:
            ValueError: 参数错误
            ConnectionError: 服务连接失败
        """
        if not self.connected:
            raise ConnectionError("日历服务未连接")

        try:
            # 解析日期
            check_str = self._parse_date(check_date)
            check_dt = pd.to_datetime(check_str)

            # 获取交易所代码和日历实例
            exchange_code = self._get_exchange_code(symbol)
            calendar = self._get_calendar(exchange_code)

            # 获取股票分类信息
            classification = classify_stock(symbol)

            # 检查是否为交易日
            valid_days = calendar.valid_days(start_date=check_str, end_date=check_str)
            is_trading = len(valid_days) > 0

            # 获取星期几
            day_of_week = check_dt.strftime("%A")

            # 获取时区信息
            timezone = str(calendar.tz) if hasattr(calendar, "tz") else "Unknown"

            # 如果不是交易日，获取前后最近的交易日
            next_trading_day = None
            prev_trading_day = None

            if not is_trading:
                # 查找下一个交易日 (未来30天内)
                future_end = (check_dt + timedelta(days=30)).strftime("%Y-%m-%d")
                future_days = calendar.valid_days(
                    start_date=(check_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
                    end_date=future_end,
                )
                if len(future_days) > 0:
                    next_trading_day = future_days[0].strftime("%Y-%m-%d")

                # 查找上一个交易日 (过去30天内)
                past_start = (check_dt - timedelta(days=30)).strftime("%Y-%m-%d")
                past_days = calendar.valid_days(
                    start_date=past_start,
                    end_date=(check_dt - timedelta(days=1)).strftime("%Y-%m-%d"),
                )
                if len(past_days) > 0:
                    prev_trading_day = past_days[-1].strftime("%Y-%m-%d")

            result = {
                "symbol": symbol,
                "exchange": exchange_code,
                "market": classification["market"],
                "market_name": classification["market_name"],
                "check_date": check_str,
                "is_trading_day": is_trading,
                "day_of_week": day_of_week,
                "timezone": timezone,
                "next_trading_day": next_trading_day,
                "prev_trading_day": prev_trading_day,
            }

            logger.info(f"交易日判断: {symbol}, {check_str}, 结果: {is_trading}")
            return result

        except Exception as e:
            logger.error(
                f"交易日判断失败: symbol={symbol}, date={check_date}, error={e}"
            )
            raise

    def get_trading_hours(self, symbol: str, check_date: Any) -> Dict[str, Any]:
        """
        获取指定日期的交易时间信息 (额外功能)

        Args:
            symbol: 股票代码
            check_date: 查询日期

        Returns:
            Dict: 交易时间信息
        """
        if not self.connected:
            raise ConnectionError("日历服务未连接")

        try:
            # 解析日期
            check_str = self._parse_date(check_date)

            # 获取交易所代码和日历实例
            exchange_code = self._get_exchange_code(symbol)
            calendar = self._get_calendar(exchange_code)

            # 获取股票分类信息
            classification = classify_stock(symbol)

            # 获取交易时间表
            schedule = calendar.schedule(start_date=check_str, end_date=check_str)

            if schedule.empty:
                return {
                    "symbol": symbol,
                    "exchange": exchange_code,
                    "market": classification["market"],
                    "check_date": check_str,
                    "is_trading_day": False,
                    "trading_hours": None,
                }

            # 提取交易时间信息
            row = schedule.iloc[0]
            market_open = row["market_open"]
            market_close = row["market_close"]

            trading_hours = {
                "market_open": market_open.strftime("%H:%M:%S %Z"),
                "market_close": market_close.strftime("%H:%M:%S %Z"),
                "trading_duration": str(market_close - market_open),
            }

            # 检查是否有午间休市
            if "break_start" in schedule.columns and "break_end" in schedule.columns:
                break_start = row["break_start"]
                break_end = row["break_end"]
                if pd.notna(break_start) and pd.notna(break_end):
                    trading_hours["break_start"] = break_start.strftime("%H:%M:%S %Z")
                    trading_hours["break_end"] = break_end.strftime("%H:%M:%S %Z")
                    trading_hours["break_duration"] = str(break_end - break_start)

            result = {
                "symbol": symbol,
                "exchange": exchange_code,
                "market": classification["market"],
                "check_date": check_str,
                "is_trading_day": True,
                "trading_hours": trading_hours,
            }

            return result

        except Exception as e:
            logger.error(
                f"获取交易时间失败: symbol={symbol}, date={check_date}, error={e}"
            )
            raise

    def get_supported_exchanges(self) -> Dict[str, Any]:
        """
        获取支持的交易所列表

        Returns:
            Dict: 支持的交易所信息
        """
        try:
            available_calendars = mcal.get_calendar_names()

            # 按地区分类
            regions = {
                "美国": ["NYSE", "NASDAQ", "AMEX", "BATS", "IEX"],
                "中国": ["SSE", "HKEX", "XSHG"],
                "欧洲": ["LSE", "EUREX", "XETR", "XPAR", "XAMS", "XBRU", "XMIL"],
                "亚太": ["JPX", "ASX", "BSE", "NSE"],
                "加拿大": ["TSX"],
                "其他": [],
            }

            classified = {region: [] for region in regions.keys()}
            unclassified = []

            for name in sorted(available_calendars):
                found = False
                for region, exchanges in regions.items():
                    if region != "其他" and name in exchanges:
                        classified[region].append(name)
                        found = True
                        break
                if not found:
                    unclassified.append(name)

            classified["其他"] = unclassified

            return {
                "total_count": len(available_calendars),
                "regions": classified,
                "all_exchanges": sorted(available_calendars),
            }

        except Exception as e:
            logger.error(f"获取支持的交易所列表失败: {e}")
            raise
