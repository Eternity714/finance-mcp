"""
AKShare 数据服务 - 优化版本
基于参考文件 cankao/akshare_utils.py 的经过验证的API实现
"""

import pandas as pd
from typing import Dict, Optional, Any
import threading
import socket
import requests
import warnings
import logging
from datetime import datetime

try:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except Exception:
    HTTPAdapter = None
    Retry = None

try:
    import akshare as ak
except ImportError:
    ak = None

from ..utils.symbol_processor import get_symbol_processor
from ..exception.exception import DataNotFoundError

logger = logging.getLogger("akshare_service")
logging.basicConfig(level=logging.INFO)
warnings.filterwarnings("ignore")


class AkshareService:
    """封装 AKShare 的数据服务（经过验证优化的版本）"""

    def __init__(self):
        """初始化AKShare服务"""
        if ak is None:
            self.connected = False
            logger.error("❌ AKShare未安装，请执行 'pip install akshare'")
            raise ImportError("akshare 未安装")

        try:
            # 测试连接
            _ = ak.stock_info_a_code_name()
            self.connected = True

            # 设置更长的超时时间
            self._configure_timeout()

            self.symbol_processor = get_symbol_processor()
            logger.info("✅ AKShare初始化成功")
        except Exception as e:
            self.connected = False
            logger.error(f"❌ AKShare连接失败: {e}")
            raise ConnectionError(f"AKShare 连接失败: {e}") from e

    def _configure_timeout(self, default_timeout: int = 60):
        """配置AKShare的超时设置"""
        try:
            socket.setdefaulttimeout(default_timeout)

            if HTTPAdapter and Retry:
                retry_strategy = Retry(
                    total=3,
                    backoff_factor=1,
                    status_forcelist=[429, 500, 502, 503, 504],
                )
                adapter = HTTPAdapter(max_retries=retry_strategy)
                session = requests.Session()
                session.mount("http://", adapter)
                session.mount("https://", adapter)
                self._session = session

                logger.info("🔧 AKShare超时配置完成: 60秒超时，3次重试")
        except Exception as e:
            logger.error(f"⚠️ AKShare超时配置失败: {e}")
            logger.info("🔧 使用默认超时设置")

    # ==================== A股数据接口 ====================

    def get_stock_daily(
        self, symbol: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取A股日线数据"""
        if not self.connected:
            raise ConnectionError("AKShare未连接")

        try:
            ak_symbol = self.symbol_processor.get_akshare_format(symbol)

            logger.info(
                f"📊 AKShare获取A股日线: {symbol} -> {ak_symbol} ({start_date} ~ {end_date})"
            )

            df = ak.stock_zh_a_hist(
                symbol=ak_symbol,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="",
            )

            if df is None or df.empty:
                raise DataNotFoundError(
                    f"未获取到 {symbol} 在 {start_date}~{end_date} 的日线数据"
                )

            # 标准化列名
            mapping = {
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
            }
            for k, v in mapping.items():
                if k in df.columns:
                    df = df.rename(columns={k: v})

            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.sort_values("date")

            logger.info(f"✅ 成功获取A股数据: {ak_symbol}, {len(df)}条记录")
            return df

        except Exception as e:
            logger.error(f"❌ 获取A股日线失败: {symbol}, 错误: {e}")
            raise

    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """获取A股基本信息"""
        if not self.connected:
            raise ConnectionError("AKShare未连接")

        try:
            ak_symbol = self.symbol_processor.get_akshare_format(symbol)

            info_df = ak.stock_info_a_code_name()
            row = info_df[info_df["code"] == ak_symbol]

            if row.empty:
                raise DataNotFoundError(f"未找到 {symbol} 的基本信息")

            return {
                "symbol": ak_symbol,
                "name": row.iloc[0]["name"],
                "source": "akshare",
            }
        except Exception as e:
            logger.error(f"❌ 获取A股信息失败: {symbol}, 错误: {e}")
            raise

    def get_financial_data(self, symbol: str) -> Dict[str, Optional[pd.DataFrame]]:
        """获取股票财务数据"""
        if not self.connected:
            logger.error(f"❌ AKShare未连接，无法获取{symbol}财务数据")
            return {}

        try:
            ak_symbol = self.symbol_processor.get_akshare_format(symbol)

            logger.info(f"🔍 开始获取 {symbol} -> {ak_symbol} 的AKShare财务数据")
            financial_data: Dict[str, Optional[pd.DataFrame]] = {}

            # 1. 主要财务指标
            try:
                logger.debug(f"📊 获取 {ak_symbol} 主要财务指标...")
                main_indicators = ak.stock_financial_abstract(symbol=ak_symbol)
                if main_indicators is not None and not main_indicators.empty:
                    financial_data["main_indicators"] = main_indicators
                    logger.info(
                        f"✅ 获取主要财务指标成功: {len(main_indicators)}条记录"
                    )
                else:
                    logger.warning(f"⚠️ {symbol}主要财务指标为空")
            except Exception as e:
                logger.warning(f"❌ 获取主要财务指标失败: {e}")

            # 2. 资产负债表
            try:
                if hasattr(ak, "stock_balance_sheet_by_report_em"):
                    balance_sheet = ak.stock_balance_sheet_by_report_em(
                        symbol=ak_symbol
                    )
                    if balance_sheet is not None and not balance_sheet.empty:
                        financial_data["balance_sheet"] = balance_sheet
                        logger.debug(f"✅ 获取资产负债表: {len(balance_sheet)}条")
            except Exception as e:
                logger.debug(f"获取资产负债表失败: {e}")

            # 3. 利润表
            try:
                if hasattr(ak, "stock_profit_sheet_by_report_em"):
                    income_statement = ak.stock_profit_sheet_by_report_em(
                        symbol=ak_symbol
                    )
                    if income_statement is not None and not income_statement.empty:
                        financial_data["income_statement"] = income_statement
                        logger.debug(f"✅ 获取利润表: {len(income_statement)}条")
            except Exception as e:
                logger.debug(f"获取利润表失败: {e}")

            # 4. 现金流量表
            try:
                if hasattr(ak, "stock_cash_flow_sheet_by_report_em"):
                    cash_flow = ak.stock_cash_flow_sheet_by_report_em(symbol=ak_symbol)
                    if cash_flow is not None and not cash_flow.empty:
                        financial_data["cash_flow"] = cash_flow
                        logger.debug(f"✅ 获取现金流量表: {len(cash_flow)}条")
            except Exception as e:
                logger.debug(f"获取现金流量表失败: {e}")

            if financial_data:
                logger.info(
                    f"✅ 财务数据获取完成: {symbol}, 包含{len(financial_data)}个数据集"
                )
            else:
                logger.warning(f"⚠️ 未能获取{symbol}的任何财务数据")

            return financial_data

        except Exception as e:
            logger.exception(f"❌ 获取财务数据失败: {symbol}, 错误: {e}")
            return {}

    # ==================== 财务数据增强接口 ====================

    def get_hk_financial_report(
        self, symbol: str, report_type: str = "资产负债表", indicator: str = "年度"
    ) -> Optional[pd.DataFrame]:
        """
        获取港股财务报表

        Args:
            symbol: 股票代码（如 00700）
            report_type: 报表类型，可选 {"资产负债表", "利润表", "现金流量表"}
            indicator: 报告期类型，可选 {"年度", "报告期"}

        Returns:
            财务报表数据
        """
        if not self.connected:
            return None

        try:
            # 确保股票代码格式正确（5位数字）
            ak_symbol = symbol.lstrip("0").zfill(5)

            logger.info(
                f"📊 获取港股财务报表: {symbol} -> {ak_symbol}, {report_type}, {indicator}"
            )

            df = ak.stock_financial_hk_report_em(
                stock=ak_symbol, symbol=report_type, indicator=indicator
            )

            if df is not None and not df.empty:
                logger.info(f"✅ 获取港股{report_type}成功: {len(df)}条记录")
                return df
            else:
                logger.warning(f"⚠️ 港股{report_type}数据为空")
                return None

        except Exception as e:
            logger.error(f"❌ 获取港股{report_type}失败: {e}")
            return None

    def get_hk_financial_indicator(
        self, symbol: str, indicator: str = "年度"
    ) -> Optional[pd.DataFrame]:
        """
        获取港股主要财务指标

        Args:
            symbol: 股票代码（如 00700）
            indicator: 报告期类型，可选 {"年度", "报告期"}

        Returns:
            主要财务指标数据
        """
        if not self.connected:
            return None

        try:
            ak_symbol = symbol.lstrip("0").zfill(5)

            logger.info(f"📊 获取港股主要指标: {symbol} -> {ak_symbol}, {indicator}")

            df = ak.stock_financial_hk_analysis_indicator_em(
                symbol=ak_symbol, indicator=indicator
            )

            if df is not None and not df.empty:
                logger.info(f"✅ 获取港股主要指标成功: {len(df)}条记录")
                return df
            else:
                logger.warning(f"⚠️ 港股主要指标数据为空")
                return None

        except Exception as e:
            logger.error(f"❌ 获取港股主要指标失败: {e}")
            return None

    def get_us_financial_report(
        self, symbol: str, report_type: str = "资产负债表", indicator: str = "年报"
    ) -> Optional[pd.DataFrame]:
        """
        获取美股财务报表

        Args:
            symbol: 股票代码（如 TSLA）
            report_type: 报表类型，可选 {"资产负债表", "综合损益表", "现金流量表"}
            indicator: 报告期类型，可选 {"年报", "单季报", "累计季报"}

        Returns:
            财务报表数据
        """
        if not self.connected:
            return None

        try:
            logger.info(f"📊 获取美股财务报表: {symbol}, {report_type}, {indicator}")

            df = ak.stock_financial_us_report_em(
                stock=symbol, symbol=report_type, indicator=indicator
            )

            if df is not None and not df.empty:
                logger.info(f"✅ 获取美股{report_type}成功: {len(df)}条记录")
                return df
            else:
                logger.warning(f"⚠️ 美股{report_type}数据为空")
                return None

        except Exception as e:
            logger.error(f"❌ 获取美股{report_type}失败: {e}")
            return None

    def get_us_financial_indicator(
        self, symbol: str, indicator: str = "年报"
    ) -> Optional[pd.DataFrame]:
        """
        获取美股主要财务指标

        Args:
            symbol: 股票代码（如 TSLA）
            indicator: 报告期类型，可选 {"年报", "单季报", "累计季报"}

        Returns:
            主要财务指标数据
        """
        if not self.connected:
            return None

        try:
            logger.info(f"📊 获取美股主要指标: {symbol}, {indicator}")

            df = ak.stock_financial_us_analysis_indicator_em(
                symbol=symbol, indicator=indicator
            )

            if df is not None and not df.empty:
                logger.info(f"✅ 获取美股主要指标成功: {len(df)}条记录")
                return df
            else:
                logger.warning(f"⚠️ 美股主要指标数据为空")
                return None

        except Exception as e:
            logger.error(f"❌ 获取美股主要指标失败: {e}")
            return None

    def get_stock_basic_info_xq(
        self, symbol: str, market: str = "cn"
    ) -> Optional[Dict[str, Any]]:
        """
        获取雪球的股票基本信息

        Args:
            symbol: 股票代码
            market: 市场类型，可选 {"cn", "us", "hk"}

        Returns:
            基本信息字典
        """
        if not self.connected:
            return None

        try:
            logger.info(f"📊 从雪球获取{market}股票基本信息: {symbol}")

            if market == "cn":
                # A股：需要带市场前缀，如 SH600519
                if not symbol.startswith(("SH", "SZ")):
                    if symbol.startswith("6"):
                        symbol = f"SH{symbol}"
                    else:
                        symbol = f"SZ{symbol}"
                df = ak.stock_individual_basic_info_xq(symbol=symbol)

            elif market == "us":
                df = ak.stock_individual_basic_info_us_xq(symbol=symbol)

            elif market == "hk":
                # 港股：确保5位数字格式
                symbol = symbol.lstrip("0").zfill(5)
                df = ak.stock_individual_basic_info_hk_xq(symbol=symbol)
            else:
                logger.error(f"❌ 不支持的市场类型: {market}")
                return None

            if df is not None and not df.empty:
                # 转换为字典
                result = dict(zip(df["item"], df["value"]))
                logger.info(f"✅ 获取雪球基本信息成功: {len(result)}个字段")
                return result
            else:
                logger.warning(f"⚠️ 雪球基本信息数据为空")
                return None

        except Exception as e:
            logger.error(f"❌ 获取雪球基本信息失败: {e}")
            return None

    # ==================== 港股数据接口 ====================

    def get_hk_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取港股日线数据（带超时保护）"""
        if not self.connected:
            raise ConnectionError("AKShare未连接")

        ak_symbol = self.symbol_processor.get_akshare_format(symbol)
        logger.info(
            f"🇭🇰 AKShare获取港股数据: {symbol} -> {ak_symbol} ({start_date} ~ {end_date})"
        )

        result = [None]
        exception = [None]

        def fetch_data():
            try:
                # symbol_processor 已经处理了代码格式
                # hk_symbol = self._normalize_hk_symbol(symbol)

                result[0] = ak.stock_hk_hist(
                    symbol=ak_symbol,
                    period="daily",
                    start_date=start_date.replace("-", ""),
                    end_date=end_date.replace("-", ""),
                    adjust="",
                )
            except Exception as e:
                exception[0] = e

        thread = threading.Thread(target=fetch_data, daemon=True)
        thread.start()
        thread.join(timeout=60)

        if thread.is_alive():
            raise TimeoutError(f"获取港股 {symbol} 日线超时（60秒）")
        if exception[0]:
            raise exception[0]

        df = result[0]
        if df is None or df.empty:
            raise DataNotFoundError(
                f"未获取到港股 {symbol} 在 {start_date}~{end_date} 的数据"
            )

        # 标准化列名
        mapping = {
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
        }
        for k, v in mapping.items():
            if k in df.columns:
                df = df.rename(columns={k: v})

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")

        df["symbol"] = ak_symbol
        logger.info(f"✅ 港股数据获取成功: {ak_symbol}, {len(df)}条记录")
        return df

    def get_hk_info(self, symbol: str) -> Dict[str, Any]:
        """
        获取港股基本信息（优化版 - 不使用全市场数据）

        性能优化：移除了全市场数据调用，避免下载2000+只股票数据
        推荐使用 get_stock_basic_info_xq() 和 get_hk_financial_indicator()
        """
        if not self.connected:
            return {
                "symbol": symbol,
                "name": f"港股{symbol}",
                "currency": "HKD",
                "exchange": "HKG",
                "source": "akshare_unavailable",
            }

        try:
            ak_symbol = self.symbol_processor.get_akshare_format(symbol)
            logger.info(f"🇭🇰 获取港股信息: {symbol} -> {ak_symbol}")

            # 优化：直接返回基本信息，不调用全市场数据
            # 详细信息应该通过专用接口获取：
            # - 基本信息: get_stock_basic_info_xq(symbol, "hk")
            # - 财务指标: get_hk_financial_indicator(symbol)
            return {
                "symbol": symbol,
                "name": f"港股{symbol}",
                "currency": "HKD",
                "exchange": "HKG",
                "source": "akshare",
            }

        except Exception as e:
            logger.error(f"❌ 获取港股信息失败: {e}")
            return {
                "symbol": symbol,
                "name": f"港股{symbol}",
                "currency": "HKD",
                "exchange": "HKG",
                "source": "akshare_error",
                "error": str(e),
            }

    # ==================== 美股数据接口 ====================

    def get_us_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取美股日线数据（使用新浪美股历史数据接口）"""
        if not self.connected:
            raise ConnectionError("AKShare未连接")

        ak_symbol = self.symbol_processor.get_akshare_format(symbol)
        logger.info(
            f"🇺🇸 AKShare获取美股数据: {symbol} -> {ak_symbol} ({start_date} ~ {end_date})"
        )

        result = [None]
        exception = [None]

        def fetch_data():
            try:
                # 使用AKShare的新浪美股历史数据接口
                full_data = ak.stock_us_daily(symbol=ak_symbol, adjust="")

                if full_data is None or full_data.empty:
                    logger.warning(f"⚠️ 美股历史数据为空: {symbol}")
                    result[0] = pd.DataFrame()
                    return

                # 过滤日期范围
                if "date" in full_data.columns:
                    full_data["date"] = pd.to_datetime(full_data["date"])
                    start_dt = pd.to_datetime(start_date)
                    end_dt = pd.to_datetime(end_date)

                    filtered_data = full_data[
                        (full_data["date"] >= start_dt) & (full_data["date"] <= end_dt)
                    ].copy()

                    if filtered_data.empty:
                        logger.warning(
                            f"⚠️ 指定日期范围内无美股数据: {symbol} ({start_date} ~ {end_date})"
                        )
                    else:
                        logger.debug(
                            f"✅ 获取美股数据成功: {symbol}, {len(filtered_data)}条"
                        )

                    result[0] = filtered_data
                else:
                    result[0] = full_data

            except Exception as e:
                logger.error(f"❌ 获取美股数据失败: {symbol}, 错误: {e}")
                exception[0] = e

        thread = threading.Thread(target=fetch_data, daemon=True)
        thread.start()
        thread.join(timeout=120)  # 美股数据较大，增加超时时间

        if thread.is_alive():
            raise TimeoutError(f"获取美股 {symbol} 日线超时（120秒）")
        if exception[0]:
            raise exception[0]

        df = result[0]
        if df is None or df.empty:
            raise DataNotFoundError(
                f"未获取到美股 {symbol} 在 {start_date}~{end_date} 的数据"
            )

        # 确保列名正确
        required_columns = ["date", "open", "high", "low", "close", "volume"]
        for col in required_columns:
            if col not in df.columns:
                logger.warning(f"⚠️ 美股数据缺少列 {col}")
                df[col] = 0 if col == "volume" else 0.0

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)

        df["symbol"] = ak_symbol
        logger.info(f"✅ 美股数据处理完成: {ak_symbol}, {len(df)}条记录")
        return df

    def get_us_info(self, symbol: str) -> Dict[str, Any]:
        """
        获取美股基本信息（优化版 - 不使用全市场数据）

        性能优化：移除了全市场数据调用，避免下载3000+只股票数据
        推荐使用 get_stock_basic_info_xq() 和 get_us_financial_indicator()
        """
        if not self.connected:
            return {
                "symbol": symbol,
                "name": f"美股{symbol}",
                "currency": "USD",
                "exchange": "US",
                "source": "akshare_unavailable",
            }

        try:
            ak_symbol = self.symbol_processor.get_akshare_format(symbol)

            # 优化：使用预设名称，不调用全市场数据
            # 详细信息应该通过专用接口获取：
            # - 基本信息: get_stock_basic_info_xq(symbol, "us")
            # - 财务指标: get_us_financial_indicator(symbol)
            stock_name = self._get_us_stock_name(ak_symbol)

            return {
                "symbol": ak_symbol,
                "name": stock_name,
                "currency": "USD",
                "exchange": "US",
                "source": "akshare",
            }

        except Exception as e:
            logger.error(f"❌ 获取美股信息失败: {e}")
            return {
                "symbol": symbol,
                "name": f"美股{symbol}",
                "currency": "USD",
                "exchange": "US",
                "source": "akshare_error",
                "error": str(e),
            }

    def _get_us_stock_name(self, symbol: str) -> str:
        """获取美股名称（使用常见映射）"""
        common_us_stocks = {
            "AAPL": "苹果公司",
            "MSFT": "微软公司",
            "GOOGL": "谷歌A类股",
            "GOOG": "谷歌C类股",
            "AMZN": "亚马逊公司",
            "TSLA": "特斯拉公司",
            "META": "Meta平台",
            "NVDA": "英伟达公司",
            "NFLX": "奈飞公司",
            "AMD": "超威半导体",
            "INTC": "英特尔公司",
            "CRM": "Salesforce",
            "ORCL": "甲骨文公司",
            "ADBE": "Adobe公司",
            "PYPL": "PayPal公司",
            "DIS": "迪士尼公司",
            "BA": "波音公司",
            "JPM": "摩根大通",
            "V": "Visa公司",
            "MA": "万事达卡",
        }

        if symbol in common_us_stocks:
            logger.info(f"✅ 使用预设名称: {symbol} -> {common_us_stocks[symbol]}")
            return common_us_stocks[symbol]
        else:
            logger.info(f"⚠️ 使用默认名称: {symbol}")
            return f"美股{symbol}"

    # ==================== 新闻数据接口 ====================

    def get_stock_news_em(self, symbol: str, max_news: int = 20) -> pd.DataFrame:
        """获取东方财富个股新闻"""
        if not self.connected:
            logger.error("[东方财富新闻] ❌ AKShare未连接")
            return pd.DataFrame()

        start_time = datetime.now()
        ak_symbol = self.symbol_processor.get_akshare_format(symbol)
        logger.info(f"[东方财富新闻] 获取股票 {symbol} -> {ak_symbol} 的新闻数据")

        try:
            result = [None]
            exception = [None]

            def fetch_news():
                try:
                    result[0] = ak.stock_news_em(symbol=ak_symbol)
                except Exception as e:
                    exception[0] = e

            thread = threading.Thread(target=fetch_news)
            thread.daemon = True
            thread.start()
            thread.join(timeout=30)

            if thread.is_alive():
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.warning(
                    f"[东方财富新闻] ⚠️ 获取超时（30秒）: {symbol}, 耗时: {elapsed:.2f}秒"
                )
                raise TimeoutError(f"东方财富新闻获取超时（30秒）: {symbol}")
            if exception[0]:
                raise exception[0]

            news_df = result[0]

            if news_df is not None and not news_df.empty:
                if len(news_df) > max_news:
                    news_df = news_df.head(max_news)

                elapsed = (datetime.now() - start_time).total_seconds()
                logger.info(
                    f"[东方财富新闻] ✅ 获取成功: {ak_symbol}, 共{len(news_df)}条, 耗时: {elapsed:.2f}秒"
                )
                return news_df
            else:
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.warning(
                    f"[东方财富新闻] ⚠️ 数据为空: {symbol}, 耗时: {elapsed:.2f}秒"
                )
                return pd.DataFrame()

        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(
                f"[东方财富新闻] ❌ 获取失败: {symbol}, 错误: {e}, 耗时: {elapsed:.2f}秒"
            )
            return pd.DataFrame()

    # ==================== 全市场数据接口 ====================

    def get_china_market_spot(self) -> pd.DataFrame:
        """
        获取A股全市场实时行情数据
        包含市盈率、市净率等估值指标

        Returns:
            pd.DataFrame: 全市场数据
        """
        if not self.connected:
            raise ConnectionError("AKShare未连接")

        try:
            logger.info("📊 获取A股全市场实时数据...")
            df = ak.stock_zh_a_spot_em()

            if df is not None and not df.empty:
                logger.info(f"✅ 获取A股全市场数据成功: {len(df)} 只股票")
                return df
            else:
                logger.warning("⚠️ A股全市场数据为空")
                return pd.DataFrame()

        except Exception as e:
            logger.error(f"❌ 获取A股全市场数据失败: {e}")
            raise

    def get_hk_market_spot(self) -> pd.DataFrame:
        """
        获取港股全市场实时行情数据

        Returns:
            pd.DataFrame: 全市场数据
        """
        if not self.connected:
            raise ConnectionError("AKShare未连接")

        try:
            logger.info("📊 获取港股全市场实时数据...")
            df = ak.stock_hk_spot_em()

            if df is not None and not df.empty:
                logger.info(f"✅ 获取港股全市场数据成功: {len(df)} 只股票")
                return df
            else:
                logger.warning("⚠️ 港股全市场数据为空")
                return pd.DataFrame()

        except Exception as e:
            logger.error(f"❌ 获取港股全市场数据失败: {e}")
            raise

    def get_us_market_spot(self) -> pd.DataFrame:
        """
        获取美股全市场实时行情数据

        Returns:
            pd.DataFrame: 全市场数据
        """
        if not self.connected:
            raise ConnectionError("AKShare未连接")

        try:
            logger.info("📊 获取美股全市场实时数据...")
            df = ak.stock_us_spot_em()

            if df is not None and not df.empty:
                logger.info(f"✅ 获取美股全市场数据成功: {len(df)} 只股票")
                return df
            else:
                logger.warning("⚠️ 美股全市场数据为空")
                return pd.DataFrame()

        except Exception as e:
            logger.error(f"❌ 获取美股全市场数据失败: {e}")
            raise

    def get_stock_spot_info(
        self, symbol: str, market: str = "china"
    ) -> Optional[Dict[str, Any]]:
        """
        从全市场数据中获取单只股票的实时信息（含市盈率等）

        ⚠️ 性能警告：
        - 会下载整个市场的数据（A股4000+，港股2000+，美股3000+）
        - 首次请求耗时15-30秒
        - 占用大量内存（~50MB）

        ⚠️ 不推荐用于单只股票查询！

        推荐使用场景：
        - 批量查询（超过10只股票）
        - 市场概览
        - 板块分析

        单只股票查询请使用专用接口：
        - A股：get_stock_info() + Tushare财务指标
        - 港股：get_stock_basic_info_xq("symbol", "hk") + get_hk_financial_indicator()
        - 美股：get_stock_basic_info_xq("symbol", "us") + get_us_financial_indicator()

        Args:
            symbol: 股票代码
            market: 市场类型 (china/hk/us)

        Returns:
            Dict: 股票实时信息
        """
        # 添加性能警告
        logger.warning(
            f"⚠️ 正在使用全市场数据接口获取单只股票({symbol})信息，"
            f"这会下载整个{market}市场数据，建议使用专用接口"
        )

        try:
            from ..utils.market_data_cache import get_market_data_cache

            # 使用15分钟缓存
            cache = get_market_data_cache(ttl=900)  # 15分钟缓存

            # 尝试从缓存获取全市场数据
            market_data = cache.get(market, "spot")

            if market_data is None:
                # 缓存未命中，获取新数据
                logger.info(f"📊 缓存未命中，获取{market}全市场数据...")

                if market == "china":
                    market_data = self.get_china_market_spot()
                elif market == "hk":
                    market_data = self.get_hk_market_spot()
                elif market == "us":
                    market_data = self.get_us_market_spot()
                else:
                    logger.error(f"❌ 不支持的市场类型: {market}")
                    return None

                # 写入缓存
                if market_data is not None and not market_data.empty:
                    cache.set(market, market_data, "spot")

            if market_data is None or market_data.empty:
                logger.warning(f"⚠️ {market}全市场数据为空")
                return None

            # 查找指定股票
            ak_symbol = self.symbol_processor.get_akshare_format(symbol)

            # 不同市场的代码列名不同
            code_column = "代码"
            if market == "china":
                # A股: 去掉前缀的纯数字代码
                clean_code = ak_symbol
                stock_row = market_data[market_data[code_column] == clean_code]
            elif market == "hk":
                # 港股: 5位数字代码
                clean_code = ak_symbol.zfill(5)
                stock_row = market_data[market_data[code_column] == clean_code]
            elif market == "us":
                # 美股: 股票代码
                stock_row = market_data[market_data[code_column] == symbol.upper()]
            else:
                return None

            if stock_row.empty:
                logger.warning(f"⚠️ 在{market}全市场数据中未找到 {symbol} ({ak_symbol})")
                return None

            # 转换为字典
            info = stock_row.iloc[0].to_dict()
            logger.info(f"✅ 从全市场数据获取 {symbol} 信息成功")
            return info

        except Exception as e:
            logger.error(f"❌ 获取股票实时信息失败: {symbol}, {e}")
            return None


# ==================== 便捷函数 ====================

_global_service = None


def get_akshare_service() -> AkshareService:
    """获取AKShare服务单例"""
    global _global_service
    if _global_service is None:
        _global_service = AkshareService()
    return _global_service


def get_hk_stock_data_akshare(
    symbol: str, start_date: str = None, end_date: str = None
) -> str:
    """获取港股数据（便捷函数）"""
    try:
        service = get_akshare_service()
        data = service.get_hk_daily(symbol, start_date, end_date)

        if data is not None and not data.empty:
            return _format_hk_stock_data(symbol, data, start_date, end_date)
        else:
            return f"❌ 无法获取港股 {symbol} 的数据"

    except Exception as e:
        return f"❌ AKShare港股数据获取失败: {e}"


def get_us_stock_data_akshare(
    symbol: str, start_date: str = None, end_date: str = None
) -> str:
    """获取美股数据（便捷函数）"""
    try:
        service = get_akshare_service()
        data = service.get_us_daily(symbol, start_date, end_date)

        if data is not None and not data.empty:
            return _format_us_stock_data(symbol, data, start_date, end_date)
        else:
            return f"❌ 无法获取美股 {symbol} 的数据"

    except Exception as e:
        return f"❌ AKShare美股数据获取失败: {e}"


def _format_hk_stock_data(
    symbol: str, data: pd.DataFrame, start_date: str, end_date: str
) -> str:
    """格式化港股数据"""
    try:
        service = get_akshare_service()
        stock_info = service.get_hk_info(symbol)
        stock_name = stock_info.get("name", f"港股{symbol}")

        latest_price = data["close"].iloc[-1]
        first_price = data["close"].iloc[0]
        price_change = latest_price - first_price
        price_change_pct = (price_change / first_price) * 100

        report = f"""
🇭🇰 港股数据报告 (AKShare)
================

股票信息:
- 代码: {symbol}
- 名称: {stock_name}
- 货币: 港币 (HKD)
- 交易所: 香港交易所 (HKG)

价格信息:
- 最新价格: HK${latest_price:.2f}
- 期间涨跌: HK${price_change:+.2f} ({price_change_pct:+.2f}%)
- 期间最高: HK${data['high'].max():.2f}
- 期间最低: HK${data['low'].min():.2f}

交易信息:
- 数据期间: {start_date} 至 {end_date}
- 交易天数: {len(data)}天
- 平均成交量: {data['volume'].mean():,.0f}股

最近5个交易日:
"""
        for _, row in data.tail(5).iterrows():
            date_str = row["date"].strftime("%Y-%m-%d")
            report += f"- {date_str}: 开盘HK${row['open']:.2f}, 收盘HK${row['close']:.2f}, 成交量{row['volume']:,.0f}\n"

        report += "\n数据来源: AKShare (港股)\n"
        return report

    except Exception as e:
        logger.error(f"❌ 格式化港股数据失败: {e}")
        return f"❌ 港股数据格式化失败: {symbol}"


def _format_us_stock_data(
    symbol: str, data: pd.DataFrame, start_date: str, end_date: str
) -> str:
    """格式化美股数据"""
    try:
        service = get_akshare_service()
        stock_info = service.get_us_info(symbol)
        stock_name = stock_info.get("name", f"美股{symbol}")

        latest_price = data["close"].iloc[-1]
        first_price = data["close"].iloc[0]
        price_change = latest_price - first_price
        price_change_pct = (price_change / first_price) * 100

        report = f"""
🇺🇸 美股数据报告 (AKShare)
================

股票信息:
- 代码: {symbol}
- 名称: {stock_name}
- 货币: 美元 (USD)
- 交易所: 美国交易所 (US)

价格信息:
- 最新价格: ${latest_price:.2f}
- 期间涨跌: ${price_change:+.2f} ({price_change_pct:+.2f}%)
- 期间最高: ${data['high'].max():.2f}
- 期间最低: ${data['low'].min():.2f}

交易信息:
- 数据期间: {start_date} 至 {end_date}
- 交易天数: {len(data)}天
- 平均成交量: {data['volume'].mean():,.0f}股

最近5个交易日:
"""
        for _, row in data.tail(5).iterrows():
            date_str = row["date"].strftime("%Y-%m-%d")
            report += f"- {date_str}: 开盘${row['open']:.2f}, 收盘${row['close']:.2f}, 成交量{row['volume']:,.0f}\n"

        report += "\n数据来源: AKShare (美股)\n"
        return report

    except Exception as e:
        logger.error(f"❌ 格式化美股数据失败: {e}")
        return f"❌ 美股数据格式化失败: {symbol}"
