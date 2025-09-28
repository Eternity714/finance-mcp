# app/api/akshare_service.py
import pandas as pd
from typing import Dict, Optional, Any
import threading
import socket
import requests
import warnings

try:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except Exception:  # 允许在精简环境下缺失
    HTTPAdapter = None  # type: ignore
    Retry = None  # type: ignore

try:
    from ..utils.symbol_processor import get_symbol_processor
except (ImportError, ModuleNotFoundError):
    get_symbol_processor = None

try:
    import akshare as ak
except ImportError:
    ak = None

# 使用标准日志模块
import logging

logger = logging.getLogger("akshare_service")
logging.basicConfig(level=logging.INFO)

warnings.filterwarnings("ignore")


class AkshareService:
    """封装 AKShare 的数据服务（与 TushareService 风格保持一致, 并整合原 akshare_utils 功能）。"""

    def __init__(self):
        """初始化AKShare服务"""
        if ak is None:
            self.connected = False
            logger.error("❌ AKShare未安装")
            raise ImportError("akshare 未安装")

        try:
            # 测试连接
            _ = ak.stock_info_a_code_name()
            self.connected = True

            # 设置更长的超时时间
            self._configure_timeout()

            # 初始化AKShare市场数据缓存管理器
            from ..utils.redis_cache import AKShareMarketCache

            self.market_cache = AKShareMarketCache(cache_duration=86400)  # 24小时缓存

            logger.info("✅ AKShare初始化成功")
        except Exception as e:
            self.connected = False
            logger.error(f"❌ AKShare连接失败: {e}")
            raise ConnectionError(f"AKShare 连接失败: {e}") from e

    # ---------------- 内部：HTTP / 超时配置 ----------------
    def _configure_timeout(self, default_timeout: int = 60):
        """配置AKShare的超时设置"""
        try:
            socket.setdefaulttimeout(default_timeout)

            # 如果AKShare使用requests，设置默认超时
            if HTTPAdapter and Retry:
                # 创建重试策略
                retry_strategy = Retry(
                    total=3,
                    backoff_factor=1,
                    status_forcelist=[429, 500, 502, 503, 504],
                )

                # 设置适配器
                adapter = HTTPAdapter(max_retries=retry_strategy)
                session = requests.Session()
                session.mount("http://", adapter)
                session.mount("https://", adapter)
                self._session = session  # 备用

                logger.info("🔧 AKShare超时配置完成: 60秒超时，3次重试")
        except Exception as e:
            logger.error(f"⚠️ AKShare超时配置失败: {e}")
            logger.info("🔧 使用默认超时设置")

    # ---------------- A股日线 ----------------
    def get_stock_daily(
        self, symbol: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        code = (
            symbol.replace(".SH", "")
            .replace(".SZ", "")
            .replace(".sh", "")
            .replace(".sz", "")
        )
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust="",
        )
        if df is None or df.empty:
            raise ValueError(f"未获取到 {symbol} 在 {start_date}~{end_date} 的日线")
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
        return df

    # ---------------- A股基本信息 ----------------
    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        code = symbol.replace(".SH", "").replace(".SZ", "")
        info_df = ak.stock_info_a_code_name()
        row = info_df[info_df["code"] == code]
        if row.empty:
            raise ValueError(f"未找到 {symbol} 的基本信息")
        return {
            "symbol": symbol,
            "name": row.iloc[0]["name"],
            "source": "akshare",
        }

    # ---------------- 主要财务摘要（旧接口保留） ----------------
    def get_financial_abstract(self, symbol: str) -> pd.DataFrame:
        code = symbol.replace(".SH", "").replace(".SZ", "")
        df = ak.stock_financial_abstract(symbol=code)
        if df is None or df.empty:
            raise ValueError(f"未获取到 {symbol} 财务摘要")
        return df

    # ---------------- 完整财务数据（整合 akshare_utils） ----------------
    def get_financial_data(self, symbol: str) -> Dict[str, Optional[pd.DataFrame]]:
        """
        获取股票财务数据

        Args:
            symbol: 股票代码 (6位数字)

        Returns:
            Dict: 包含主要财务指标的财务数据
        """
        if not self.connected:
            logger.error(f"❌ AKShare未连接，无法获取{symbol}财务数据")
            return {}

        code = symbol.replace(".SH", "").replace(".SZ", "")

        try:
            logger.info(f"🔍 开始获取{symbol}的AKShare财务数据")

            financial_data: Dict[str, Optional[pd.DataFrame]] = {}

            # 1. 优先获取主要财务指标
            try:
                logger.debug(f"📊 尝试获取{symbol}主要财务指标...")
                main_indicators = ak.stock_financial_abstract(symbol=code)
                if main_indicators is not None and not main_indicators.empty:
                    financial_data["main_indicators"] = main_indicators
                    logger.info(
                        f"✅ 成功获取{symbol}主要财务指标: {len(main_indicators)}条记录"
                    )
                    logger.debug(f"主要财务指标列名: {list(main_indicators.columns)}")
                else:
                    logger.warning(f"⚠️ {symbol}主要财务指标为空")
            except Exception as e:
                logger.warning(f"❌ 获取{symbol}主要财务指标失败: {e}")

            # 2. 尝试获取资产负债表
            try:
                logger.debug(f"📊 尝试获取{symbol}资产负债表...")
                if hasattr(ak, "stock_balance_sheet_by_report_em"):
                    balance_sheet = ak.stock_balance_sheet_by_report_em(symbol=code)
                    if balance_sheet is not None and not balance_sheet.empty:
                        financial_data["balance_sheet"] = balance_sheet
                        logger.debug(
                            f"✅ 成功获取{symbol}资产负债表: {len(balance_sheet)}条记录"
                        )
                    else:
                        logger.debug(f"⚠️ {symbol}资产负债表为空")
            except Exception as e:
                logger.debug(f"❌ 获取{symbol}资产负债表失败: {e}")

            # 3. 尝试获取利润表
            try:
                logger.debug(f"📊 尝试获取{symbol}利润表...")
                if hasattr(ak, "stock_profit_sheet_by_report_em"):
                    income_statement = ak.stock_profit_sheet_by_report_em(symbol=code)
                    if income_statement is not None and not income_statement.empty:
                        financial_data["income_statement"] = income_statement
                        logger.debug(
                            f"✅ 成功获取{symbol}利润表: {len(income_statement)}条记录"
                        )
                    else:
                        logger.debug(f"⚠️ {symbol}利润表为空")
            except Exception as e:
                logger.debug(f"❌ 获取{symbol}利润表失败: {e}")

            # 4. 尝试获取现金流量表
            try:
                logger.debug(f"📊 尝试获取{symbol}现金流量表...")
                if hasattr(ak, "stock_cash_flow_sheet_by_report_em"):
                    cash_flow = ak.stock_cash_flow_sheet_by_report_em(symbol=code)
                    if cash_flow is not None and not cash_flow.empty:
                        financial_data["cash_flow"] = cash_flow
                        logger.debug(
                            f"✅ 成功获取{symbol}现金流量表: {len(cash_flow)}条记录"
                        )
                    else:
                        logger.debug(f"⚠️ {symbol}现金流量表为空")
            except Exception as e:
                logger.debug(f"❌ 获取{symbol}现金流量表失败: {e}")

            # 记录最终结果
            if financial_data:
                logger.info(
                    f"✅ AKShare财务数据获取完成: {symbol}, 包含{len(financial_data)}个数据集"
                )
                for key, value in financial_data.items():
                    if hasattr(value, "__len__"):
                        logger.info(f"  - {key}: {len(value)}条记录")
            else:
                logger.warning(f"⚠️ 未能获取{symbol}的任何AKShare财务数据")

            return financial_data

        except Exception as e:
            logger.exception(f"❌ AKShare获取{symbol}财务数据失败: {e}")
            return {}

    def get_us_stock_name_by_symbol(self, symbol: str) -> str:
        """
        根据美股代码获取股票名称（使用简单映射，避免耗时的API调用）

        Args:
            symbol: 美股代码

        Returns:
            str: 股票名称
        """
        # 常见美股的简单映射，避免每次都调用API
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

        processor = get_symbol_processor()
        code = processor.get_akshare_format(symbol)
        if code in common_us_stocks:
            logger.info(f"✅ 使用预设名称: {symbol} -> {common_us_stocks[code]}")
            return common_us_stocks[code]
        else:
            logger.info(f"⚠️ 使用默认名称: {symbol}")
            return f"美股{symbol}"

    def get_hk_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        processor = get_symbol_processor()
        code = processor.get_akshare_format(symbol)

        result = [None]
        exception = [None]

        def task():
            try:
                result[0] = ak.stock_hk_hist(
                    symbol=code,
                    period="daily",
                    start_date=start_date.replace("-", ""),
                    end_date=end_date.replace("-", ""),
                    adjust="",
                )
            except Exception as e:
                exception[0] = e

        t = threading.Thread(target=task, daemon=True)
        t.start()
        t.join(timeout=60)
        if t.is_alive():
            raise TimeoutError(f"获取港股 {symbol} 日线超时")
        if exception[0]:
            raise exception[0] from None
        df = result[0]
        if df is None or df.empty:
            raise ValueError(f"未获取到港股 {symbol} 在 {start_date}~{end_date} 的日线")
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
        df["symbol"] = symbol
        return df

    def get_us_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取美股日线数据（使用新浪美股历史数据接口）"""
        processor = get_symbol_processor()
        code = processor.get_akshare_format(symbol)
        result = [None]
        exception = [None]

        def task():
            try:
                logger.info(f"🇺🇸 使用新浪美股接口获取历史数据: {code}")
                # 使用AKShare的新浪美股历史数据接口
                # adjust="" 返回未复权数据，adjust="qfq" 返回前复权数据
                full_data = ak.stock_us_daily(symbol=code, adjust="")

                if full_data is None or full_data.empty:
                    logger.warning(f"⚠️ 美股历史数据为空: {code}")
                    result[0] = pd.DataFrame()
                    return

                # 过滤日期范围
                if "date" in full_data.columns:
                    full_data["date"] = pd.to_datetime(full_data["date"])
                    start_dt = pd.to_datetime(start_date)
                    end_dt = pd.to_datetime(end_date)

                    # 筛选日期范围内的数据
                    filtered_data = full_data[
                        (full_data["date"] >= start_dt) & (full_data["date"] <= end_dt)
                    ].copy()

                    if filtered_data.empty:
                        logger.warning(
                            f"⚠️ 指定日期范围内无美股数据: {code} ({start_date} ~ {end_date})"
                        )
                    else:
                        logger.info(
                            f"✅ 获取美股历史数据成功: {code}, {len(filtered_data)}条记录"
                        )

                    result[0] = filtered_data
                else:
                    logger.warning(f"⚠️ 美股数据缺少日期列: {code}")
                    result[0] = full_data

            except Exception as e:
                logger.error(f"❌ 获取美股历史数据失败: {code}, 错误: {e}")
                exception[0] = e

        t = threading.Thread(target=task, daemon=True)
        t.start()
        t.join(timeout=120)  # 美股历史数据可能较大，增加超时时间

        if t.is_alive():
            logger.error(f"⚠️ 获取美股日线数据超时: {symbol}")
            raise TimeoutError(f"获取美股 {symbol} 日线超时")
        if exception[0] is not None:
            raise exception[0]

        df = result[0]
        if df is None or df.empty:
            raise ValueError(f"未获取到美股 {symbol} 在 {start_date}~{end_date} 的日线")

        # AKShare美股数据已经是标准格式，只需要确保列名正确
        # 新浪美股接口返回的列名: date, open, high, low, close, volume
        required_columns = ["date", "open", "high", "low", "close", "volume"]
        for col in required_columns:
            if col not in df.columns:
                logger.warning(f"⚠️ 美股数据缺少列 {col}")
                if col == "volume":
                    df[col] = 0
                else:
                    df[col] = 0.0

        # 确保日期格式正确
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)

        # 添加股票代码标识
        df["symbol"] = symbol

        logger.info(f"✅ 美股日线数据处理完成: {symbol}, 最终{len(df)}条记录")
        return df

    def get_hk_info(self, symbol: str) -> Dict[str, Any]:
        """
        获取港股基本信息（使用缓存优化版本）

        Args:
            symbol: 港股代码

        Returns:
            Dict: 港股基本信息
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
            processor = get_symbol_processor()
            code = processor.get_akshare_format(symbol)
            logger.info(f"🇭🇰 获取港股信息: {code}")

            # 1. 优先获取详细的公司资料信息
            company_info = self._get_hk_company_basic_info(code)

            # 2. 获取市场数据（价格等）
            stock_data = self.market_cache.get_hk_stock_data(code)

            # 合并公司信息和市场数据
            result = {
                "symbol": symbol,
                "currency": "HKD",
                "exchange": "HKG",
            }

            # 添加公司基本信息
            if company_info:
                result.update(
                    {
                        "name": company_info.get("company_name", f"港股{symbol}"),
                        "english_name": company_info.get("english_name", ""),
                        "industry": company_info.get("industry", ""),
                        "chairman": company_info.get("chairman", ""),
                        "employees": company_info.get("employees", 0),
                        "office_address": company_info.get("office_address", ""),
                        "website": company_info.get("website", ""),
                        "phone": company_info.get("phone", ""),
                        "source": "akshare_company_profile",
                    }
                )
                logger.info(
                    f"✅ 获取港股公司资料成功: {company_info.get('company_name', symbol)}"
                )
            else:
                result.update(
                    {
                        "name": f"港股{symbol}",
                        "source": "akshare_fallback",
                    }
                )

            # 添加市场数据
            if stock_data:
                result.update(
                    {
                        "latest_price": stock_data.get("最新价", None),
                        "change_amount": stock_data.get("涨跌额", None),
                        "change_percent": stock_data.get("涨跌幅", None),
                        "market_data_source": "akshare_cached",
                    }
                )

            return result

        except Exception as e:
            logger.error(f"❌ AKShare获取港股信息失败: {e}")
            return {
                "symbol": symbol,
                "name": f"港股{symbol}",
                "currency": "HKD",
                "exchange": "HKG",
                "source": "akshare_error",
                "error": str(e),
            }

    def get_us_info(self, symbol: str) -> Dict[str, Any]:
        """
        获取美股基本信息（使用缓存优化版本）

        Args:
            symbol: 美股代码

        Returns:
            Dict: 美股基本信息
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
            processor = get_symbol_processor()
            code = processor.get_akshare_format(symbol)
            logger.info(f"🇺🇸 获取美股信息: {code}")

            # 获取美股名称
            stock_name = self.get_us_stock_name_by_symbol(symbol)

            # 获取市场数据（价格等）
            stock_data = self.market_cache.get_us_stock_data(code)

            # 构建基本信息
            result = {
                "symbol": symbol,
                "currency": "USD",
                "exchange": "US",
                "name": stock_name,
                "source": "akshare_us",
            }

            # 添加市场数据
            if stock_data:
                result.update(
                    {
                        "latest_price": stock_data.get("最新价", None),
                        "change_amount": stock_data.get("涨跌额", None),
                        "change_percent": stock_data.get("涨跌幅", None),
                        "market_cap": stock_data.get("总市值", None),
                        "pe_ratio": stock_data.get("市盈率", None),
                        "market_data_source": "akshare_cached",
                    }
                )
                logger.info(f"✅ 获取美股市场数据成功: {symbol}")
            else:
                logger.warning(f"⚠️ 未能获取美股市场数据: {symbol}")

            return result

        except Exception as e:
            logger.error(f"❌ AKShare获取美股信息失败: {e}")
            return {
                "symbol": symbol,
                "name": f"美股{symbol}",
                "currency": "USD",
                "exchange": "US",
                "source": "akshare_error",
                "error": str(e),
            }

    # ---------------- 港股基本面数据 ----------------
    def get_hk_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        获取港股基本面数据

        Args:
            symbol: 港股代码

        Returns:
            Dict: 港股基本面数据
        """
        if not self.connected:
            logger.error(f"❌ AKShare未连接，无法获取{symbol}港股基本面数据")
            return {}

        try:
            processor = get_symbol_processor()
            code = processor.get_akshare_format(symbol)
            logger.info(f"🇭🇰 AKShare获取港股基本面数据: {code}")

            fundamentals = {}

            # 1. 获取证券资料
            try:
                security_profile = self._get_hk_security_profile(code)
                if security_profile:
                    fundamentals["security_profile"] = security_profile
                    logger.info(f"✅ 获取港股证券资料成功: {symbol}")
            except Exception as e:
                logger.warning(f"⚠️ 获取港股证券资料失败: {e}")

            # 2. 获取公司资料
            try:
                company_profile = self._get_hk_company_profile(code)
                if company_profile:
                    fundamentals["company_profile"] = company_profile
                    logger.info(f"✅ 获取港股公司资料成功: {symbol}")
            except Exception as e:
                logger.warning(f"⚠️ 获取港股公司资料失败: {e}")

            # 3. 获取实时行情（用于市值等计算）
            try:
                market_data = self._get_hk_market_data(code)
                if market_data:
                    fundamentals["market_data"] = market_data
                    logger.info(f"✅ 获取港股市场数据成功: {symbol}")
            except Exception as e:
                logger.warning(f"⚠️ 获取港股市场数据失败: {e}")

            return fundamentals

        except Exception as e:
            logger.error(f"❌ AKShare获取港股基本面数据失败: {symbol}, 错误: {e}")
            return {}

    # ---------------- 美股基本面数据 ----------------
    def get_us_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        获取美股基本面数据

        Args:
            symbol: 美股代码

        Returns:
            Dict: 美股基本面数据
        """
        if not self.connected:
            logger.error(f"❌ AKShare未连接，无法获取{symbol}美股基本面数据")
            return {}

        try:
            processor = get_symbol_processor()
            code = processor.get_akshare_format(symbol)
            logger.info(f"🇺🇸 AKShare获取美股基本面数据: {code}")

            fundamentals = {}

            # 1. 获取实时行情（用于市值等计算）
            try:
                market_data = self._get_us_market_data(code)
                if market_data:
                    fundamentals["market_data"] = market_data
                    logger.info(f"✅ 获取美股市场数据成功: {symbol}")
            except Exception as e:
                logger.warning(f"⚠️ 获取美股市场数据失败: {e}")

            return fundamentals

        except Exception as e:
            logger.error(f"❌ AKShare获取美股基本面数据失败: {symbol}, 错误: {e}")
            return {}

    def _get_us_market_data(self, code: str) -> Dict[str, Any]:
        """获取美股市场数据（使用缓存优化版本）"""
        processor = get_symbol_processor()
        code = processor.get_akshare_format(code)
        try:
            # 优先从缓存获取美股市场数据
            stock_data = self.market_cache.get_us_stock_data(code)

            if stock_data:
                # 从缓存数据提取市场数据
                market_data = {
                    "latest_price": stock_data.get("最新价", 0),
                    "change_amount": stock_data.get("涨跌额", 0),
                    "change_percent": stock_data.get("涨跌幅", 0),
                    "open_price": stock_data.get("开盘价", 0),
                    "high_price": stock_data.get("最高价", 0),
                    "low_price": stock_data.get("最低价", 0),
                    "prev_close": stock_data.get("昨收价", 0),
                    "volume": stock_data.get("成交量", 0),
                    "turnover": stock_data.get("成交额", 0),
                    "market_cap": stock_data.get("总市值", 0),
                    "pe_ratio": stock_data.get("市盈率", 0),
                }
                logger.info(f"📊 从缓存获取美股市场数据: {code}")
                return market_data
            else:
                # 缓存未命中，强制刷新并重新获取
                logger.warning(f"⚠️ 美股缓存未命中，强制刷新: {code}")
                refresh_result = self.market_cache.force_refresh("us")

                if refresh_result.get("us") is not None:
                    # 刷新成功，重新从缓存获取
                    stock_data = self.market_cache.get_us_stock_data(code)
                    if stock_data:
                        market_data = {
                            "latest_price": stock_data.get("最新价", 0),
                            "change_amount": stock_data.get("涨跌额", 0),
                            "change_percent": stock_data.get("涨跌幅", 0),
                            "open_price": stock_data.get("开盘价", 0),
                            "high_price": stock_data.get("最高价", 0),
                            "low_price": stock_data.get("最低价", 0),
                            "prev_close": stock_data.get("昨收价", 0),
                            "volume": stock_data.get("成交量", 0),
                            "turnover": stock_data.get("成交额", 0),
                            "market_cap": stock_data.get("总市值", 0),
                            "pe_ratio": stock_data.get("市盈率", 0),
                        }
                        logger.info(f"📊 刷新后获取美股市场数据: {code}")
                        return market_data

                logger.error(f"❌ 无法获取美股市场数据: {code}")
                return {}

        except Exception as e:
            logger.error(f"❌ 获取美股市场数据失败: {e}")
            return {}

    def _get_hk_security_profile(self, code: str) -> Dict[str, Any]:
        """获取港股证券资料"""
        processor = get_symbol_processor()
        code = processor.get_akshare_format(code)
        result = [None]
        exception = [None]

        def fetch_data():
            try:
                result[0] = ak.stock_hk_security_profile_em(symbol=code)
            except Exception as e:
                exception[0] = e

        thread = threading.Thread(target=fetch_data, daemon=True)
        thread.start()
        thread.join(timeout=30)

        if thread.is_alive():
            raise TimeoutError(f"获取港股证券资料超时: {code}")
        if exception[0]:
            raise exception[0]

        data = result[0]
        if data is None or data.empty:
            return {}

        # 转换为字典格式
        profile = {}
        for _, row in data.iterrows():
            for col in data.columns:
                value = row[col]
                if pd.notna(value):
                    profile[col] = value

        return profile

    def _get_hk_company_profile(self, code: str) -> Dict[str, Any]:
        """获取港股公司资料"""
        processor = get_symbol_processor()
        code = processor.get_akshare_format(code)
        result = [None]
        exception = [None]

        def fetch_data():
            try:
                result[0] = ak.stock_hk_company_profile_em(symbol=code)
            except Exception as e:
                exception[0] = e

        thread = threading.Thread(target=fetch_data, daemon=True)
        thread.start()
        thread.join(timeout=30)

        if thread.is_alive():
            raise TimeoutError(f"获取港股公司资料超时: {code}")
        if exception[0]:
            raise exception[0]

        data = result[0]
        if data is None or data.empty:
            return {}

        # 转换为字典格式
        profile = {}
        for _, row in data.iterrows():
            for col in data.columns:
                value = row[col]
                if pd.notna(value):
                    profile[col] = value

        return profile

    def _get_hk_market_data(self, code: str) -> Dict[str, Any]:
        """获取港股市场数据（使用缓存优化版本）"""
        processor = get_symbol_processor()
        code = processor.get_akshare_format(code)
        try:
            # 优先从缓存获取港股市场数据
            stock_data = self.market_cache.get_hk_stock_data(code)

            if stock_data:
                # 从缓存数据提取市场数据
                market_data = {
                    "latest_price": stock_data.get("最新价", 0),
                    "change_amount": stock_data.get("涨跌额", 0),
                    "change_percent": stock_data.get("涨跌幅", 0),
                    "open_price": stock_data.get("今开", 0),
                    "high_price": stock_data.get("最高", 0),
                    "low_price": stock_data.get("最低", 0),
                    "prev_close": stock_data.get("昨收", 0),
                    "volume": stock_data.get("成交量", 0),
                    "turnover": stock_data.get("成交额", 0),
                }
                logger.info(f"📊 从缓存获取港股市场数据: {code}")
                return market_data
            else:
                # 缓存未命中，强制刷新并重新获取
                logger.warning(f"⚠️ 港股缓存未命中，强制刷新: {code}")
                refresh_result = self.market_cache.force_refresh("hk")

                if refresh_result.get("hk") is not None:
                    # 刷新成功，重新从缓存获取
                    stock_data = self.market_cache.get_hk_stock_data(code)
                    if stock_data:
                        market_data = {
                            "latest_price": stock_data.get("最新价", 0),
                            "change_amount": stock_data.get("涨跌额", 0),
                            "change_percent": stock_data.get("涨跌幅", 0),
                            "open_price": stock_data.get("今开", 0),
                            "high_price": stock_data.get("最高", 0),
                            "low_price": stock_data.get("最低", 0),
                            "prev_close": stock_data.get("昨收", 0),
                            "volume": stock_data.get("成交量", 0),
                            "turnover": stock_data.get("成交额", 0),
                        }
                        logger.info(f"📊 刷新后获取港股市场数据: {code}")
                        return market_data

                logger.error(f"❌ 无法获取港股市场数据: {code}")
                return {}

        except Exception as e:
            logger.error(f"❌ 获取港股市场数据失败: {e}")
            return {}

    def _get_hk_company_basic_info(self, code: str) -> Optional[Dict[str, Any]]:
        """
        获取港股公司基本信息（专门用于公司资料，不包含市场数据）

        Args:
            code: 港股代码（5位数字，如 "03900"）

        Returns:
            Dict: 公司基本信息，如果获取失败返回None
        """
        try:
            processor = get_symbol_processor()
            code = processor.get_akshare_format(code)
            logger.info(f"🏢 获取港股公司资料: {code}")

            # 使用线程超时获取公司资料
            result = [None]
            exception = [None]

            def fetch_company_data():
                try:
                    result[0] = ak.stock_hk_company_profile_em(symbol=code)
                except Exception as e:
                    exception[0] = e

            thread = threading.Thread(target=fetch_company_data, daemon=True)
            thread.start()
            thread.join(timeout=30)

            if thread.is_alive():
                logger.warning(f"⚠️ 获取港股公司资料超时: {code}")
                return None

            if exception[0]:
                logger.warning(f"⚠️ 获取港股公司资料失败: {exception[0]}")
                return None

            data = result[0]
            if data is None or data.empty:
                logger.warning(f"⚠️ 港股公司资料为空: {code}")
                return None

            # 解析公司资料数据
            company_info = {}
            for _, row in data.iterrows():
                # 映射中文字段名到英文字段名
                field_mapping = {
                    "公司名称": "company_name",
                    "英文名称": "english_name",
                    "所属行业": "industry",
                    "董事长": "chairman",
                    "员工人数": "employees",
                    "办公地址": "office_address",
                    "公司网址": "website",
                    "联系电话": "phone",
                    "注册地": "registration_place",
                    "公司成立日期": "establishment_date",
                    "公司秘书": "company_secretary",
                    "年结日": "year_end_date",
                    "E-MAIL": "email",
                    "核数师": "auditor",
                    "传真": "fax",
                    "公司介绍": "company_description",
                }

                for col in data.columns:
                    value = row[col]
                    if pd.notna(value):
                        # 使用映射后的英文字段名
                        field_name = field_mapping.get(col, col)
                        company_info[field_name] = value

                        # 特殊处理员工人数，确保是数字
                        if field_name == "employees" and isinstance(value, str):
                            try:
                                company_info[field_name] = int(value.replace(",", ""))
                            except (ValueError, AttributeError):
                                company_info[field_name] = 0

            logger.info(
                f"✅ 港股公司资料获取成功: {company_info.get('company_name', code)}"
            )
            return company_info

        except Exception as e:
            logger.error(f"❌ 获取港股公司基本信息失败: {e}")
            return None

    # ---------------- 东方财富个股新闻（整合 akshare_utils） ----------------
    def get_stock_news_em(self, symbol: str, max_news: int = 20) -> pd.DataFrame:
        """
        使用AKShare获取东方财富个股新闻

        Args:
            symbol: 股票代码，如 "600000" 或 "300059"
            max_news: 最大新闻数量，默认20条

        Returns:
            pd.DataFrame: 包含新闻标题、内容、日期和链接的DataFrame
        """
        from datetime import datetime

        start_time = datetime.now()
        logger.info(f"[东方财富新闻] 开始获取股票 {symbol} 的东方财富新闻数据")

        if not self.connected:
            logger.error("[东方财富新闻] ❌ AKShare未连接，无法获取东方财富新闻")
            return pd.DataFrame()

        # 清洗股票代码
        code = (
            symbol.replace(".SH", "")
            .replace(".SZ", "")
            .replace(".XSHE", "")
            .replace(".XSHG", "")
        )

        try:
            logger.info(f"[东方财富新闻] 📰 准备调用AKShare API获取个股新闻: {code}")

            # 使用线程超时包装（兼容Windows）
            result = [None]
            exception = [None]

            def fetch_news():
                try:
                    logger.debug(
                        f"[东方财富新闻] 线程开始执行 stock_news_em API调用: {code}"
                    )
                    import time

                    thread_start = time.time()
                    result[0] = ak.stock_news_em(symbol=code)
                    thread_end = time.time()
                    logger.debug(
                        f"[东方财富新闻] 线程执行完成，耗时: {thread_end - thread_start:.2f}秒"
                    )
                except Exception as e:
                    logger.error(f"[东方财富新闻] 线程执行异常: {e}")
                    exception[0] = e

            # 启动线程
            thread = threading.Thread(target=fetch_news)
            thread.daemon = True
            logger.debug("[东方财富新闻] 启动线程获取新闻数据")
            thread.start()

            # 等待30秒
            logger.debug("[东方财富新闻] 等待线程完成，最长等待30秒")
            thread.join(timeout=30)

            if thread.is_alive():
                # 超时了
                elapsed_time = (datetime.now() - start_time).total_seconds()
                logger.warning(
                    f"[东方财富新闻] ⚠️ 获取超时（30秒）: {symbol}，总耗时: {elapsed_time:.2f}秒"
                )
                raise Exception(f"东方财富个股新闻获取超时（30秒）: {symbol}")
            elif exception[0]:
                # 有异常
                elapsed_time = (datetime.now() - start_time).total_seconds()
                logger.error(
                    f"[东方财富新闻] ❌ API调用异常: {exception[0]}，总耗时: {elapsed_time:.2f}秒"
                )
                raise exception[0]
            else:
                # 成功
                news_df = result[0]

            if news_df is not None and not news_df.empty:
                # 限制新闻数量为最新的max_news条
                if len(news_df) > max_news:
                    news_df = news_df.head(max_news)
                    logger.info(
                        f"[东方财富新闻] 📰 新闻数量限制: 从{len(news_df)}条限制为{max_news}条最新新闻"
                    )

                news_count = len(news_df)
                elapsed_time = (datetime.now() - start_time).total_seconds()

                # 记录一些新闻标题示例
                sample_titles = [
                    row.get("标题", "无标题") for _, row in news_df.head(3).iterrows()
                ]
                logger.info(f"[东方财富新闻] 新闻标题示例: {', '.join(sample_titles)}")

                logger.info(
                    f"[东方财富新闻] ✅ 获取成功: {symbol}, 共{news_count}条记录，耗时: {elapsed_time:.2f}秒"
                )
                return news_df
            else:
                elapsed_time = (datetime.now() - start_time).total_seconds()
                logger.warning(
                    f"[东方财富新闻] ⚠️ 数据为空: {symbol}，API返回成功但无数据，耗时: {elapsed_time:.2f}秒"
                )
                return pd.DataFrame()

        except Exception as e:
            elapsed_time = (datetime.now() - start_time).total_seconds()
            logger.error(
                f"[东方财富新闻] ❌ 获取失败: {symbol}, 错误: {e}, 耗时: {elapsed_time:.2f}秒"
            )
            return pd.DataFrame()

    # ---------------- 报告函数 ----------------
    def get_stock_data_report(self, symbol: str, start_date: str, end_date: str) -> str:
        """生成股票数据报告"""
        try:
            info = self.get_stock_info(symbol)
            data = self.get_stock_daily(symbol, start_date, end_date)

            # 根据市场确定货币符号
            from ..utils.stock_market_classifier import classify_stock

            classification = classify_stock(symbol)
            currency_symbol = "¥"  # 默认为人民币
            if classification["is_hk"]:
                currency_symbol = "HK$"
            elif classification["is_us"]:
                currency_symbol = "$"

            name = info.get("name", symbol)
            latest = data.iloc[-1]
            prev_close = data.iloc[-2]["close"] if len(data) > 1 else latest["close"]
            change_pct = (
                ((latest["close"] - prev_close) / prev_close * 100) if prev_close else 0
            )
            volume = latest.get("volume", 0)
            vol_str = f"{volume/10000:.1f}万" if volume > 10000 else f"{volume}"

            report = f"# {symbol} AKShare 日线报告\n\n"
            report += (
                f"## 基本行情\n- 名称: {name}\n- 代码: {symbol}\n"
                f"- 最新收盘: {currency_symbol}{latest['close']:.2f}\n- 涨跌幅: {change_pct:+.2f}%\n"
                f"- 成交量: {vol_str}\n- 数据来源: AKShare\n\n"
            )
            report += (
                f"## 期间概览\n- 区间: {start_date} ~ {end_date}\n- 条数: {len(data)}\n"
                f"- 最高: {currency_symbol}{data['high'].max():.2f}\n"
                f"- 最低: {currency_symbol}{data['low'].min():.2f}\n\n"
            )
            cols = [
                c
                for c in ["date", "open", "high", "low", "close", "volume"]
                if c in data.columns
            ]
            report += "## 最近5日\n" + data[cols].tail(5).to_markdown(index=False)
            return report
        except Exception as e:
            logger.error(f"❌ 生成股票报告失败: {symbol}, 错误: {e}")
            return f"❌ 无法生成 {symbol} 的股票报告: {e}"

    def format_hk_stock_data(
        self, symbol: str, data: pd.DataFrame, start_date: str, end_date: str
    ) -> str:
        """
        格式化AKShare港股数据为文本格式

        Args:
            symbol: 股票代码
            data: 股票数据DataFrame
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            str: 格式化的股票数据文本
        """
        if data is None or data.empty:
            return f"❌ 无法获取港股 {symbol} 的AKShare数据"

        try:
            # 获取股票基本信息（允许失败）
            stock_name = f"港股{symbol}"  # 默认名称
            try:
                stock_info = self.get_hk_info(symbol)
                stock_name = stock_info.get("name", f"港股{symbol}")
                logger.info(f"✅ 港股信息获取成功: {stock_name}")
            except Exception as info_error:
                logger.error(f"⚠️ 港股信息获取失败，使用默认信息: {info_error}")
                # 继续处理，使用默认信息

            # 计算统计信息
            latest_price = (
                data["close"].iloc[-1]
                if "close" in data.columns
                else data["Close"].iloc[-1]
            )
            first_price = (
                data["close"].iloc[0]
                if "close" in data.columns
                else data["Close"].iloc[0]
            )
            price_change = latest_price - first_price
            price_change_pct = (price_change / first_price) * 100

            volume_col = "volume" if "volume" in data.columns else "Volume"
            avg_volume = data[volume_col].mean() if volume_col in data.columns else 0

            high_col = "high" if "high" in data.columns else "High"
            low_col = "low" if "low" in data.columns else "Low"
            max_price = data[high_col].max()
            min_price = data[low_col].min()

            # 格式化输出
            formatted_text = f"""
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
- 期间最高: HK${max_price:.2f}
- 期间最低: HK${min_price:.2f}

交易信息:
- 数据期间: {start_date} 至 {end_date}
- 交易天数: {len(data)}天
- 平均成交量: {avg_volume:,.0f}股

最近5个交易日:
"""

            # 添加最近5天的数据
            recent_data = data.tail(5)
            for _, row in recent_data.iterrows():
                date_col = "date" if "date" in row else "Date"
                date_str = (
                    row[date_col].strftime("%Y-%m-%d")
                    if date_col in row
                    else row.name.strftime("%Y-%m-%d")
                )

                open_price = row.get("open", row.get("Open", 0))
                close_price = row.get("close", row.get("Close", 0))
                volume = row.get("volume", row.get("Volume", 0))

                formatted_text += f"- {date_str}: 开盘HK${open_price:.2f}, 收盘HK${close_price:.2f}, 成交量{volume:,.0f}\n"

            formatted_text += f"\n数据来源: AKShare (港股)\n"

            return formatted_text

        except Exception as e:
            logger.error(f"❌ 格式化AKShare港股数据失败: {e}")
            return f"❌ AKShare港股数据格式化失败: {symbol}"

    def format_us_stock_data(
        self, symbol: str, data: pd.DataFrame, start_date: str, end_date: str
    ) -> str:
        """
        格式化AKShare美股数据为文本格式

        Args:
            symbol: 股票代码
            data: 股票数据DataFrame
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            str: 格式化的股票数据文本
        """
        if data is None or data.empty:
            return f"❌ 无法获取美股 {symbol} 的AKShare数据"

        try:
            # 获取股票基本信息（允许失败）
            stock_name = f"美股{symbol}"  # 默认名称
            try:
                stock_info = self.get_us_info(symbol)
                stock_name = stock_info.get("name", f"美股{symbol}")
                logger.info(f"✅ 美股信息获取成功: {stock_name}")
            except Exception as info_error:
                logger.error(f"⚠️ 美股信息获取失败，使用默认信息: {info_error}")
                # 继续处理，使用默认信息

            # 计算统计信息
            latest_price = (
                data["close"].iloc[-1]
                if "close" in data.columns
                else data["Close"].iloc[-1]
            )
            first_price = (
                data["close"].iloc[0]
                if "close" in data.columns
                else data["Close"].iloc[0]
            )
            price_change = latest_price - first_price
            price_change_pct = (price_change / first_price) * 100

            volume_col = "volume" if "volume" in data.columns else "Volume"
            avg_volume = data[volume_col].mean() if volume_col in data.columns else 0

            high_col = "high" if "high" in data.columns else "High"
            low_col = "low" if "low" in data.columns else "Low"
            max_price = data[high_col].max()
            min_price = data[low_col].min()

            # 格式化输出
            formatted_text = f"""
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
- 期间最高: ${max_price:.2f}
- 期间最低: ${min_price:.2f}

交易信息:
- 数据期间: {start_date} 至 {end_date}
- 交易天数: {len(data)}天
- 平均成交量: {avg_volume:,.0f}股

最近5个交易日:
"""

            # 添加最近5天的数据
            recent_data = data.tail(5)
            for _, row in recent_data.iterrows():
                date_col = "date" if "date" in row else "Date"
                date_str = (
                    row[date_col].strftime("%Y-%m-%d")
                    if date_col in row
                    else row.name.strftime("%Y-%m-%d")
                )

                open_price = row.get("open", row.get("Open", 0))
                close_price = row.get("close", row.get("Close", 0))
                volume = row.get("volume", row.get("Volume", 0))

                formatted_text += f"- {date_str}: 开盘${open_price:.2f}, 收盘${close_price:.2f}, 成交量{volume:,.0f}\n"

            formatted_text += f"\n数据来源: AKShare (美股)\n"

            return formatted_text

        except Exception as e:
            logger.error(f"❌ 格式化AKShare美股数据失败: {e}")
            return f"❌ AKShare美股数据格式化失败: {symbol}"


# ---------------- 便捷函数 ----------------
def get_akshare_service() -> AkshareService:
    """获取AKShare服务实例"""
    return AkshareService()


def get_hk_stock_data_akshare(
    symbol: str, start_date: str = None, end_date: str = None
) -> str:
    """
    使用AKShare获取港股数据的便捷函数

    Args:
        symbol: 港股代码
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        str: 格式化的港股数据
    """
    try:
        service = get_akshare_service()
        data = service.get_hk_daily(symbol, start_date, end_date)

        if data is not None and not data.empty:
            return service.format_hk_stock_data(symbol, data, start_date, end_date)
        else:
            return f"❌ 无法获取港股 {symbol} 的AKShare数据"

    except Exception as e:
        return f"❌ AKShare港股数据获取失败: {e}"


def get_hk_stock_info_akshare(symbol: str) -> Dict[str, Any]:
    """
    使用AKShare获取港股信息的便捷函数

    Args:
        symbol: 港股代码

    Returns:
        Dict: 港股信息
    """
    try:
        """
        获取AKShare服务实例
        """
        service = get_akshare_service()
        return service.get_hk_info(symbol)
    except Exception as e:
        return {
            "symbol": symbol,
            "name": f"港股{symbol}",
            "currency": "HKD",
            "exchange": "HKG",
            "source": "akshare_error",
            "error": str(e),
        }


def get_us_stock_data_akshare(
    symbol: str, start_date: str = None, end_date: str = None
) -> str:
    """
    使用AKShare获取美股数据的便捷函数

    Args:
        symbol: 美股代码
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        str: 格式化的美股数据
    """
    try:
        service = get_akshare_service()
        data = service.get_us_daily(symbol, start_date, end_date)

        if data is not None and not data.empty:
            return service.format_us_stock_data(symbol, data, start_date, end_date)
        else:
            return f"❌ 无法获取美股 {symbol} 的AKShare数据"

    except Exception as e:
        return f"❌ AKShare美股数据获取失败: {e}"


def get_us_stock_info_akshare(symbol: str) -> Dict[str, Any]:
    """
    使用AKShare获取美股信息的便捷函数

    Args:
        symbol: 美股代码

    Returns:
        Dict: 美股信息
    """
    try:
        """
        获取AKShare服务实例
        """
        service = get_akshare_service()
        return service.get_us_info(symbol)
    except Exception as e:
        return {
            "symbol": symbol,
            "name": f"美股{symbol}",
            "currency": "USD",
            "exchange": "US",
            "source": "akshare_error",
            "error": str(e),
        }
