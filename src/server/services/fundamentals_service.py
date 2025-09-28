"""
基本面数据分析服务（Redis缓存优化版本）
整合多数据源的基本面数据，实现降级机制
基于Tushare财务报表API实现完整的基本面分析
集成Redis缓存优化AKShare全市场数据性能
"""

from typing import Dict, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass
import pandas as pd

# from ..utils.exception import DataNotFoundError

# 导入Redis缓存
from ..utils.redis_cache import get_redis_cache

# 导入统一的股票代码处理器
from ..utils.symbol_processor import get_symbol_processor

# 移除MarketDataCache类，改用Redis缓存的AKShareMarketCache


@dataclass
class FundamentalData:
    """基本面数据结构"""

    symbol: str
    company_name: str
    market_cap: float
    pe_ratio: float
    pb_ratio: float
    roe: float
    revenue: float
    net_income: float
    debt_to_equity: float
    current_ratio: float
    source: str
    timestamp: datetime
    # 新增财务指标
    total_assets: float = 0
    total_liabilities: float = 0
    cash_flow_from_operations: float = 0
    gross_profit_margin: float = 0
    operating_profit_margin: float = 0
    roa: float = 0  # 资产收益率
    # 基于fina_indicator接口的新增指标
    eps: float = 0  # 基本每股收益
    dt_eps: float = 0  # 稀释每股收益
    bps: float = 0  # 每股净资产
    ocfps: float = 0  # 每股经营活动现金流
    cfps: float = 0  # 每股现金流量净额
    roe_waa: float = 0  # 加权平均净资产收益率
    roe_dt: float = 0  # 净资产收益率(扣非)
    roic: float = 0  # 投入资本回报率
    netprofit_margin: float = 0  # 销售净利率
    quick_ratio: float = 0  # 速动比率
    assets_to_eqt: float = 0  # 权益乘数
    ebit: float = 0  # 息税前利润
    ebitda: float = 0  # 息税折旧摊销前利润
    fcff: float = 0  # 企业自由现金流
    fcfe: float = 0  # 股权自由现金流
    working_capital: float = 0  # 营运资金
    retained_earnings: float = 0  # 留存收益
    # 增长率指标
    basic_eps_yoy: float = 0  # 每股收益同比增长率
    netprofit_yoy: float = 0  # 净利润同比增长率
    roe_yoy: float = 0  # ROE同比增长率
    tr_yoy: float = 0  # 营业总收入同比增长率
    or_yoy: float = 0  # 营业收入同比增长率
    # 港股专用字段（从复权行情数据获取）
    turnover_ratio: float = 0  # 换手率
    volume: float = 0  # 成交量
    amount: float = 0  # 成交额
    pct_change: float = 0  # 涨跌幅


@dataclass
class TushareFinancialData:
    """Tushare财务数据结构"""

    income_statement: pd.DataFrame
    balance_sheet: pd.DataFrame
    cash_flow: pd.DataFrame
    financial_indicators: pd.DataFrame


class FundamentalsAnalysisService:
    """基本面数据分析服务（Redis缓存优化版本）"""

    def __init__(self):
        self.data_sources = []

        # 初始化Redis缓存
        self.redis_cache = get_redis_cache()

        # 初始化AKShare市场数据缓存管理器
        from ..utils.redis_cache import AKShareMarketCache

        self.market_cache = AKShareMarketCache(cache_duration=86400)  # 24小时缓存

        # 初始化数据源
        self._init_data_sources()

    def _init_data_sources(self):
        """初始化基本面数据源"""
        self.services = {}

        # 1. Tushare基本面数据
        try:
            from .tusahre_service import TushareService

            self.services["tushare"] = TushareService()
            print("✅ Tushare基本面数据源已启用")
        except Exception as e:
            print(f"⚠️ Tushare基本面数据源初始化失败: {e}")

        # 2. AKShare基本面数据
        try:
            from .akshare_service import AkshareService

            self.services["akshare"] = AkshareService()
            print("✅ AKShare基本面数据源已启用")
        except Exception as e:
            print(f"⚠️ AKShare基本面数据源初始化失败: {e}")

        # 3. YFinance基本面数据（用于美股）
        try:
            import yfinance as yf

            self.services["yfinance"] = yf
            print("✅ YFinance基本面数据源已启用")
        except Exception as e:
            print(f"⚠️ YFinance基本面数据源初始化失败: {e}")

    def get_fundamental_data(self, symbol: str) -> FundamentalData:
        """
        获取基本面数据，实现多数据源降级

        Args:
            symbol: 股票代码

        Returns:
            FundamentalData: 基本面数据对象
        """
        # 使用统一的代码处理器
        processor = get_symbol_processor()
        symbol_info = processor.process_symbol(symbol)

        market = symbol_info["market"]
        data_sources = symbol_info["data_sources"]["fundamentals"]

        print(f"🔍 检测股票 {symbol} 属于 {market} 市场")
        print(f"📊 数据源策略: {' → '.join(data_sources)}")

        last_error = None
        for source in data_sources:
            try:
                print(f"🔄 尝试从 {source} 获取 {symbol} 基本面数据...")

                if source == "tushare" and source in self.services:
                    data = self._get_tushare_fundamentals(symbol)
                elif source == "akshare" and source in self.services:
                    data = self._get_akshare_fundamentals(symbol)
                elif source == "yfinance" and source in self.services:
                    data = self._get_yfinance_fundamentals(symbol)
                else:
                    continue

                if data:
                    print(f"✅ 成功从 {source} 获取 {symbol} 基本面数据")
                    return data

            except Exception as e:
                print(f"❌ {source} 基本面数据获取失败: {e}")
                last_error = e
                continue

        # 所有数据源都失败，返回默认数据
        print(f"⚠️ 所有数据源都失败，返回 {symbol} 的默认基本面数据")
        return self._get_fallback_fundamentals(symbol, last_error)

    def _get_tushare_fundamentals(self, symbol: str) -> Optional[FundamentalData]:
        """从Tushare获取基本面数据（使用完整财务数据API）"""
        try:
            service = self.services["tushare"]

            # 确定股票市场类型
            market = self._determine_stock_market(symbol)

            # 根据市场类型调用不同的Tushare接口
            if market == "china":
                # A股市场，使用标准接口
                print(f"📈 使用Tushare获取A股基本面数据: {symbol}")
                return self._get_tushare_china_fundamentals(service, symbol)
            elif market == "hk":
                # 港股市场，使用港股接口
                print(f"🇭🇰 使用Tushare获取港股基本面数据: {symbol}")
                return self._get_tushare_hk_fundamentals(service, symbol)
            else:
                # 美股市场，Tushare不支持
                print(f"⚠️ Tushare不支持美股基本面数据，跳过: {symbol}")
                return None

        except Exception as e:
            print(f"Tushare基本面数据获取失败: {e}")
            return None

    def _get_tushare_china_fundamentals(
        self, service, symbol: str
    ) -> Optional[FundamentalData]:
        """获取A股基本面数据"""
        try:

            # 转换股票代码格式
            ts_code = self._convert_to_tushare_code(symbol)

            # 获取基本信息和市场数据
            info = service.get_stock_info(symbol)
            market_data = service.get_market_data(ts_code)

            # 合并基本信息和市场数据
            combined_info = {}
            if info:
                combined_info.update(info)
            if market_data:
                combined_info.update(market_data)

            if not combined_info:
                print(f"未获取到 {symbol} 的基本信息")
                return None

            # 获取完整财务数据
            financial_data = self._get_tushare_financial_data(symbol)
            if not financial_data:
                # 降级到简单方法
                print(f"降级使用简单财务数据获取方式: {symbol}")
                financial = service.get_china_fundamentals(symbol)
                if not financial:
                    return None

                # 从简单财务数据构建FundamentalData
                return self._build_fundamental_data_from_simple(
                    symbol, combined_info, financial
                )

            # 使用新的财务数据计算指标
            return self._build_fundamental_data_from_tushare(
                symbol, combined_info, financial_data
            )

        except Exception as e:
            print(f"Tushare基本面数据获取失败: {e}")
            return None

    def _get_tushare_hk_fundamentals(
        self, service, symbol: str
    ) -> Optional[FundamentalData]:
        """获取港股基本面数据（使用复权行情数据降级处理）"""
        try:
            # 获取港股基本面数据（降级处理）
            hk_fundamentals = service.get_hk_fundamentals(symbol)

            if not hk_fundamentals:
                print(f"未获取到港股 {symbol} 的基本面数据")
                return None

            # 解析基本面数据
            security_profile = hk_fundamentals.get("security_profile", {})
            company_profile = hk_fundamentals.get("company_profile", {})
            market_data = hk_fundamentals.get("market_data", {})

            # 从证券资料获取基本信息
            company_name = security_profile.get(
                "证券简称", company_profile.get("公司名称", f"港股{symbol}")
            )

            # 从市场数据获取关键指标
            latest_price = market_data.get("latest_price", 0)
            total_market_cap = market_data.get("total_market_cap", 0)
            free_market_cap = market_data.get("free_market_cap", 0)
            total_shares = market_data.get("total_shares", 0)
            free_shares = market_data.get("free_shares", 0)
            turnover_ratio = market_data.get("turnover_ratio", 0)
            pct_change = market_data.get("pct_change", 0)
            volume = market_data.get("volume", 0)
            amount = market_data.get("amount", 0)

            # 计算一些基本比率
            pe_ratio = 0  # 港股PE需要从其他数据源获取
            pb_ratio = 0  # 港股PB需要从其他数据源获取

            # 估算每股净资产（BPS）
            bps = 0
            if total_shares > 0 and free_market_cap > 0:
                # 使用流通市值和流通股本粗略估算
                bps = free_market_cap / free_shares if free_shares > 0 else 0

            print(f"✅ 成功解析港股基本面数据: {symbol}")
            print(f"  公司名称: {company_name}")
            print(f"  最新价格: HK${latest_price}")
            print(f"  总市值: {total_market_cap}")
            print(f"  换手率: {turnover_ratio}%")

            return FundamentalData(
                symbol=symbol,
                company_name=company_name,
                market_cap=float(total_market_cap),
                pe_ratio=0,  # 港股PE数据需要从其他接口获取
                pb_ratio=0,  # 港股PB数据需要从其他接口获取
                roe=0,  # 港股ROE数据需要从财务报表获取
                revenue=0,  # 营收数据需要从财务报表获取
                net_income=0,  # 净利润数据需要从财务报表获取
                debt_to_equity=0,  # 资产负债率需要从财务报表获取
                current_ratio=0,  # 流动比率需要从财务报表获取
                total_assets=0,  # 总资产需要从财务报表获取
                total_liabilities=0,  # 总负债需要从财务报表获取
                cash_flow_from_operations=0,  # 经营现金流需要从财务报表获取
                gross_profit_margin=0,  # 毛利率需要从财务报表获取
                operating_profit_margin=0,  # 营业利润率需要从财务报表获取
                roa=0,  # ROA需要从财务报表获取
                eps=0,  # 每股收益需要从财务报表获取
                bps=bps,  # 使用估算的每股净资产
                turnover_ratio=turnover_ratio,  # 添加换手率
                volume=volume,  # 添加成交量
                amount=amount,  # 添加成交额
                pct_change=pct_change,  # 添加涨跌幅
                source="tushare_hk",
                timestamp=datetime.now(),
            )

        except Exception as e:
            print(f"Tushare港股基本面数据获取失败: {e}")
            return None

    def _build_fundamental_data_from_simple(
        self, symbol: str, info: Dict, financial: Dict
    ) -> FundamentalData:
        """从简单财务数据构建基本面数据"""
        balance_sheet = financial.get("balance_sheet", [])
        income_statement = financial.get("income_statement", [])
        cash_flow = financial.get("cash_flow", [])

        # 从资产负债表获取数据
        total_assets = total_liabilities = 0
        if balance_sheet:
            latest_balance = balance_sheet[0]
            total_assets = latest_balance.get("total_assets", 0) or 0
            total_liabilities = latest_balance.get("total_liab", 0) or 0

        # 从利润表获取数据
        revenue = net_income = 0
        if income_statement:
            latest_income = income_statement[0]
            revenue = (
                latest_income.get("total_revenue", 0)
                or latest_income.get("revenue", 0)
                or 0
            )
            net_income = latest_income.get("n_income", 0) or 0

        # 从现金流量表获取数据
        cash_flow_ops = 0
        if cash_flow:
            latest_cf = cash_flow[0]
            cash_flow_ops = latest_cf.get("n_cashflow_act", 0) or 0

        # 获取市值（万元转元）
        market_cap = info.get("total_mv", 0) or 0
        if market_cap:
            market_cap = market_cap * 10000

        # 计算基本比率
        debt_to_equity = 0
        if total_assets > 0:
            debt_to_equity = total_liabilities / total_assets

        return FundamentalData(
            symbol=symbol,
            company_name=info.get("name", ""),
            market_cap=market_cap,
            pe_ratio=info.get("pe", 0) or 0,
            pb_ratio=info.get("pb", 0) or 0,
            roe=0,  # 简单模式下无法获取
            revenue=revenue,
            net_income=net_income,
            debt_to_equity=debt_to_equity,
            current_ratio=0,  # 简单模式下无法获取
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            cash_flow_from_operations=cash_flow_ops,
            source="tushare_simple",
            timestamp=datetime.now(),
        )

    def _get_akshare_fundamentals(self, symbol: str) -> Optional[FundamentalData]:
        """从AKShare获取基本面数据，根据市场类型调用不同接口"""
        try:
            # 判断股票市场类型
            market = self._determine_stock_market(symbol)

            if market == "china":
                return self._get_akshare_china_fundamentals(symbol)
            elif market == "hk":
                return self._get_akshare_hk_fundamentals(symbol)
            else:
                # 美股市场，使用AKShare美股基本面接口
                return self._get_akshare_us_fundamentals(symbol)

        except Exception as e:
            print(f"AKShare基本面数据获取失败: {e}")
            return None

    def _get_akshare_china_fundamentals(self, symbol: str) -> Optional[FundamentalData]:
        """从AKShare获取A股基本面数据（Redis缓存优化版本）"""
        try:
            import akshare as ak  # noqa: F401

            service = self.services["akshare"]

            # 获取基本信息
            info = service.get_stock_info(symbol)

            # 获取财务数据
            financial = service.get_financial_data(symbol)

            if not info:
                return None

            # 初始化默认值
            pe_ratio = pb_ratio = roe = 0
            revenue = net_income = 0
            total_assets = 0
            cash_flow_ops = 0
            debt_to_equity = current_ratio = 0
            eps = bps = 0
            gross_margin = operating_margin = roa = 0
            market_cap = 0

            # 从财务数据中提取关键指标
            main_indicators = financial.get("main_indicators")
            if main_indicators is not None and not main_indicators.empty:
                print(f"🔍 解析AKShare财务指标数据: {len(main_indicators)}条记录")

                # 创建指标查找字典，使用最新季度数据（第一个日期列）
                latest_period = main_indicators.columns[2]  # 跳过'选项'和'指标'列
                print(f"📅 使用最新期间数据: {latest_period}")

                # 优化：使用字典映射提高处理效率
                indicator_mapping = {
                    "净资产收益率(ROE)": "roe",
                    "基本每股收益": "eps",
                    "每股净资产": "bps",
                    "营业总收入": "revenue",
                    "归母净利润": "net_income",
                    "净利润": "net_income_alt",
                    "总资产报酬率(ROA)": "roa",
                    "毛利率": "gross_margin",
                    "销售净利率": "operating_margin",
                    "资产负债率": "debt_to_equity",
                    "流动比率": "current_ratio",
                    "经营现金流量净额": "cash_flow_ops",
                    "股东权益合计(净资产)": "total_assets",
                }

                # 批量处理指标数据
                for _, row in main_indicators.iterrows():
                    indicator_name = row["指标"]
                    if indicator_name in indicator_mapping:
                        indicator_value = row[latest_period]

                        # 跳过NaN值
                        if pd.isna(indicator_value):
                            continue

                        try:
                            value = float(indicator_value)
                            field = indicator_mapping[indicator_name]

                            if field == "roe":
                                roe = value
                            elif field == "eps":
                                eps = value
                            elif field == "bps":
                                bps = value
                            elif field == "revenue":
                                revenue = value
                            elif field in ["net_income", "net_income_alt"]:
                                if net_income == 0:  # 优先使用归母净利润
                                    net_income = value
                            elif field == "roa":
                                roa = value
                            elif field == "gross_margin":
                                gross_margin = value
                            elif field == "operating_margin":
                                operating_margin = value
                            elif field == "debt_to_equity":
                                debt_to_equity = value / 100  # 转换为小数
                            elif field == "current_ratio":
                                current_ratio = value
                            elif field == "cash_flow_ops":
                                cash_flow_ops = value
                            elif field == "total_assets":
                                total_assets = value
                        except (ValueError, TypeError):
                            continue

                print("✅ AKShare关键指标解析完成:")
                print(f"  ROE: {roe}%, 每股收益: {eps}, 每股净资产: {bps}")
                print(f"  营收: {revenue}, 净利润: {net_income}")
                print(f"  资产负债率: {debt_to_equity}, 流动比率: {current_ratio}")

            # 获取市场数据（使用Redis缓存优化）
            code = symbol.replace(".SH", "").replace(".SZ", "")
            market_data = self._get_market_data_cached(code)

            if market_data is not None:
                pe_ratio = market_data.get("市盈率-动态", 0) or 0
                pb_ratio = market_data.get("市净率", 0) or 0
                market_cap = market_data.get("总市值", 0) or 0

                print(
                    f"📊 从缓存获取市场数据: PE={pe_ratio}, PB={pb_ratio}, 市值={market_cap}"
                )
            else:
                print("⚠️ 未能从缓存获取市场数据")

            return FundamentalData(
                symbol=symbol,
                company_name=info.get("name", ""),
                market_cap=float(market_cap),
                pe_ratio=float(pe_ratio),
                pb_ratio=float(pb_ratio),
                roe=roe,
                revenue=revenue,
                net_income=net_income,
                debt_to_equity=debt_to_equity,
                current_ratio=current_ratio,
                total_assets=total_assets,
                total_liabilities=0,  # 需要从资产负债表获取
                cash_flow_from_operations=cash_flow_ops,
                gross_profit_margin=gross_margin,
                operating_profit_margin=operating_margin,
                roa=roa,
                eps=eps,
                bps=bps,
                source="akshare_china",
                timestamp=datetime.now(),
            )

        except Exception as e:
            print(f"AKShare A股基本面数据获取失败: {e}")
            return None

    def _get_akshare_hk_fundamentals(self, symbol: str) -> Optional[FundamentalData]:
        """从AKShare获取港股基本面数据（Redis缓存优化版本）"""
        try:
            service = self.services["akshare"]

            # 获取港股基本面数据
            hk_fundamentals = service.get_hk_fundamentals(symbol)

            if not hk_fundamentals:
                print(f"未获取到港股 {symbol} 的基本面数据")
                return None

            # 解析基本面数据
            security_profile = hk_fundamentals.get("security_profile", {})
            company_profile = hk_fundamentals.get("company_profile", {})
            market_data = hk_fundamentals.get("market_data", {})

            # 从证券资料获取基本信息
            company_name = security_profile.get(
                "证券简称", company_profile.get("公司名称", f"港股{symbol}")
            )

            # 初始化默认值
            pe_ratio = pb_ratio = 0
            latest_price = market_data.get("latest_price", 0)
            market_cap = 0
            volume = turnover = 0

            # 获取市场数据（使用Redis缓存优化）
            code = symbol.replace(".HK", "").replace(".hk", "").zfill(5)
            cached_market_data = self._get_market_data_cached(code)

            if cached_market_data is not None:
                # 从缓存获取港股市场数据 - 使用正确的字段名映射
                latest_price = cached_market_data.get("最新价", 0) or 0
                volume = cached_market_data.get("成交量", 0) or 0
                turnover = cached_market_data.get("成交额", 0) or 0

                # 尝试计算市值 - 港股实时数据中通常没有直接的市值字段
                shares_outstanding = security_profile.get("发行量(股)", 0) or 0
                if shares_outstanding > 0 and latest_price > 0:
                    market_cap = latest_price * shares_outstanding
                    print(
                        f"📊 计算港股市值: 股价={latest_price} × "
                        f"股本={shares_outstanding} = {market_cap}"
                    )

                # 港股实时数据中暂时没有PE/PB比率
                pe_ratio = 0
                pb_ratio = 0

                print(
                    f"📊 从港股缓存获取数据: 价格={latest_price}, "
                    f"成交量={volume}, 成交额={turnover}, 市值={market_cap}"
                )
            else:
                print("⚠️ 未能从缓存获取港股市场数据，强制刷新缓存")

                # 如果缓存没有数据，强制刷新港股缓存
                try:
                    refresh_result = self.market_cache.force_refresh("hk")
                    if refresh_result.get("hk") is not None:
                        # 刷新成功，重新从缓存获取
                        cached_market_data = self._get_market_data_cached(code)
                        if cached_market_data:
                            latest_price = cached_market_data.get("最新价", 0) or 0
                            volume = cached_market_data.get("成交量", 0) or 0
                            turnover = cached_market_data.get("成交额", 0) or 0
                            print(
                                f"📊 刷新后从港股缓存获取数据: 价格={latest_price}, 成交量={volume}"
                            )
                        else:
                            print("⚠️ 刷新后仍无法从缓存获取港股数据")
                    else:
                        print("❌ 港股缓存刷新失败")
                except Exception as e:
                    print(f"❌ 强制刷新港股缓存失败: {e}")

                    # 港股基本面数据有限，直接返回市场数据
            # 不进行任何估算，只使用真实获取到的数据
            print("⚠️ 港股基本面数据获取有限，返回基础市场数据")

            return FundamentalData(
                symbol=symbol,
                company_name=company_name,
                market_cap=0,  # 不估算市值
                pe_ratio=0,  # 不估算PE
                pb_ratio=0,  # 不估算PB
                roe=0,  # 港股ROE数据需要从财务报表接口获取
                revenue=0,  # 不从公司介绍估算营业额
                net_income=0,  # 净利润数据需要从财务报表接口获取
                debt_to_equity=0,  # 资产负债率需要从财务报表接口获取
                current_ratio=0,  # 流动比率需要从财务报表接口获取
                total_assets=0,  # 总资产需要从财务报表接口获取
                total_liabilities=0,  # 总负债需要从财务报表接口获取
                cash_flow_from_operations=0,  # 经营现金流需要从财务报表接口获取
                gross_profit_margin=0,  # 毛利率需要从财务报表接口获取
                operating_profit_margin=0,  # 营业利润率需要从财务报表接口获取
                roa=0,  # ROA需要从财务报表接口获取
                eps=0,  # 每股收益需要从财务报表接口获取
                bps=0,  # 每股净资产需要从财务报表接口获取
                source="akshare_hk",
                timestamp=datetime.now(),
            )

        except Exception as e:
            print(f"AKShare港股基本面数据获取失败: {e}")
            return None

    def _get_akshare_us_fundamentals(self, symbol: str) -> Optional[FundamentalData]:
        """从AKShare获取美股基本面数据（Redis缓存优化版本）"""
        try:
            service = self.services["akshare"]

            # 获取美股基本面数据
            us_fundamentals = service.get_us_fundamentals(symbol)

            if not us_fundamentals:
                print(f"未获取到美股 {symbol} 的基本面数据")
                return None

            # 解析基本面数据
            market_data = us_fundamentals.get("market_data", {})

            # 从AKShare获取美股基本信息
            us_info = service.get_us_info(symbol)
            company_name = us_info.get("name", f"美股{symbol}")

            # 初始化默认值
            pe_ratio = pb_ratio = 0
            latest_price = market_data.get("latest_price", 0)
            market_cap = market_data.get("market_cap", 0)
            volume = turnover = 0

            # 获取市场数据（使用Redis缓存优化）
            code = (
                symbol.upper()
                .replace(".US", "")
                .replace(".NASDAQ", "")
                .replace(".NYSE", "")
            )
            cached_market_data = self._get_market_data_cached(code)

            if cached_market_data is not None:
                # 从缓存获取美股市场数据
                latest_price = cached_market_data.get("最新价", 0) or 0
                volume = cached_market_data.get("成交量", 0) or 0
                turnover = cached_market_data.get("成交额", 0) or 0
                market_cap = cached_market_data.get("总市值", 0) or 0
                pe_ratio = cached_market_data.get("市盈率", 0) or 0

                print(
                    f"📊 从美股缓存获取数据: 价格=${latest_price}, "
                    f"成交量={volume}, 市值=${market_cap}, PE={pe_ratio}"
                )
            else:
                print("⚠️ 未能从缓存获取美股市场数据，强制刷新缓存")

                # 如果缓存没有数据，强制刷新美股缓存
                try:
                    refresh_result = self.market_cache.force_refresh("us")
                    if refresh_result.get("us") is not None:
                        # 刷新成功，重新从缓存获取
                        cached_market_data = self._get_market_data_cached(code)
                        if cached_market_data:
                            latest_price = cached_market_data.get("最新价", 0) or 0
                            volume = cached_market_data.get("成交量", 0) or 0
                            turnover = cached_market_data.get("成交额", 0) or 0
                            market_cap = cached_market_data.get("总市值", 0) or 0
                            pe_ratio = cached_market_data.get("市盈率", 0) or 0
                            print(
                                f"📊 刷新后从美股缓存获取数据: 价格=${latest_price}, 成交量={volume}"
                            )
                        else:
                            print("⚠️ 刷新后仍无法从缓存获取美股数据")
                    else:
                        print("❌ 美股缓存刷新失败")
                except Exception as e:
                    print(f"❌ 强制刷新美股缓存失败: {e}")

            # 美股基本面数据有限，主要返回市场数据
            print("⚠️ 美股基本面数据获取有限，返回基础市场数据")

            return FundamentalData(
                symbol=symbol,
                company_name=company_name,
                market_cap=market_cap or 0,
                pe_ratio=pe_ratio or 0,
                pb_ratio=pb_ratio or 0,  # AKShare美股数据中通常没有PB数据
                roe=0,  # 美股ROE数据需要从财务报表接口获取
                revenue=0,  # 营业收入数据需要从财务报表接口获取
                net_income=0,  # 净利润数据需要从财务报表接口获取
                debt_to_equity=0,  # 资产负债率需要从财务报表接口获取
                current_ratio=0,  # 流动比率需要从财务报表接口获取
                total_assets=0,  # 总资产需要从财务报表接口获取
                total_liabilities=0,  # 总负债需要从财务报表接口获取
                cash_flow_from_operations=0,  # 经营现金流需要从财务报表接口获取
                gross_profit_margin=0,  # 毛利率需要从财务报表接口获取
                operating_profit_margin=0,  # 营业利润率需要从财务报表接口获取
                roa=0,  # ROA需要从财务报表接口获取
                eps=0,  # 每股收益需要从财务报表接口获取
                bps=0,  # 每股净资产需要从财务报表接口获取
                source="akshare_us",
                timestamp=datetime.now(),
            )

        except Exception as e:
            print(f"AKShare美股基本面数据获取失败: {e}")
            return None

    def _get_market_data_cached(self, symbol: str) -> Optional[dict]:
        """
        从AKShare缓存中获取单只股票的市场数据

        Args:
            symbol: 股票代码（可能包含后缀）

        Returns:
            dict: 股票市场数据或None
        """
        try:
            # 使用统一的股票市场分类器判断市场类型
            market = self._determine_stock_market(symbol)

            # 清理股票代码（去除各种后缀）
            clean_symbol = (
                symbol.replace(".SH", "")
                .replace(".SZ", "")
                .replace(".HK", "")
                .replace(".hk", "")
                .replace(".SS", "")
                .replace(".XSHE", "")
                .replace(".XSHG", "")
            )

            # 根据市场类型获取相应的缓存数据
            if market == "china":
                # A股市场
                market_data = self.market_cache.get_china_stock_data(clean_symbol)
                print(f"📊 从A股缓存获取 {clean_symbol} 的市场数据")
            elif market == "hk":
                # 港股市场
                market_data = self.market_cache.get_hk_stock_data(clean_symbol)
                print(f"📊 从港股缓存获取 {clean_symbol} 的市场数据")
            elif market == "us":
                # 美股市场
                market_data = self.market_cache.get_us_stock_data(clean_symbol)
                print(f"📊 从美股缓存获取 {clean_symbol} 的市场数据")
            else:
                # 其他市场，暂不支持缓存
                print(f"⚠️ 市场类型 {market} 暂不支持缓存，股票代码: {symbol}")
                return None

            return market_data
        except Exception as e:
            print(f"从缓存获取市场数据失败: {e}")
            return None

    def _get_yfinance_fundamentals(self, symbol: str) -> Optional[FundamentalData]:
        """从YFinance获取基本面数据"""
        try:
            yf = self.services["yfinance"]
            ticker = yf.Ticker(symbol)
            info = ticker.info

            if not info:
                return None

            return FundamentalData(
                symbol=symbol,
                company_name=info.get("longName", ""),
                market_cap=info.get("marketCap", 0),
                pe_ratio=info.get("forwardPE", 0) or info.get("trailingPE", 0),
                pb_ratio=info.get("priceToBook", 0),
                roe=info.get("returnOnEquity", 0),
                revenue=info.get("totalRevenue", 0),
                net_income=info.get("netIncomeToCommon", 0),
                debt_to_equity=info.get("debtToEquity", 0),
                current_ratio=info.get("currentRatio", 0),
                source="yfinance",
                timestamp=datetime.now(),
            )

        except Exception as e:
            print(f"YFinance基本面数据获取失败: {e}")
            return None

    def _get_fallback_fundamentals(
        self, symbol: str, error: Exception = None
    ) -> FundamentalData:
        """获取备用基本面数据"""
        return FundamentalData(
            symbol=symbol,
            company_name="数据获取失败",
            market_cap=0,
            pe_ratio=0,
            pb_ratio=0,
            roe=0,
            revenue=0,
            net_income=0,
            debt_to_equity=0,
            current_ratio=0,
            source="fallback",
            timestamp=datetime.now(),
        )

    def generate_fundamentals_report(self, symbol: str) -> str:
        """生成基本面分析报告"""
        try:
            data = self.get_fundamental_data(symbol)
            return self._format_fundamentals_report(data)
        except Exception as e:
            return f"❌ 生成 {symbol} 基本面报告失败: {e}"

    def _format_fundamentals_report(self, data: FundamentalData) -> str:
        """格式化基本面分析报告（动态显示有效数据）"""
        # 根据市场确定货币符号
        processor = get_symbol_processor()
        market_simple_name = processor.get_market_simple_name(data.symbol)
        currency_symbol = "¥"  # 默认为人民币
        if market_simple_name == "hk":
            currency_symbol = "HK$"
        elif market_simple_name == "us":
            currency_symbol = "$"

        # 估值分析
        valuation_analysis = self._analyze_valuation(data)

        # 盈利能力分析
        profitability_analysis = self._analyze_profitability(data)

        # 财务健康分析
        financial_health = self._analyze_financial_health(data)

        # 构建基本信息
        basic_info = [
            f"- **公司名称**: {data.company_name}",
            f"- **股票代码**: {data.symbol}",
        ]

        # 只有当市值大于0时才显示
        if data.market_cap > 0:
            basic_info.append(
                f"- **市值**: {self._format_number(data.market_cap)}{currency_symbol.replace('$', '美元')}"
            )

        basic_info.extend(
            [
                f"- **数据来源**: {data.source}",
                f"- **数据时间**: {data.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            ]
        )

        # 构建估值指标
        valuation_metrics = []
        if data.pe_ratio > 0:
            valuation_metrics.append(f"- **市盈率 (P/E)**: {data.pe_ratio:.2f}")
        if data.pb_ratio > 0:
            valuation_metrics.append(f"- **市净率 (P/B)**: {data.pb_ratio:.2f}")

        # 构建盈利能力指标
        profitability_metrics = []
        if data.roe > 0:
            profitability_metrics.append(f"- **净资产收益率 (ROE)**: {data.roe:.2f}%")
        if hasattr(data, "roa") and data.roa > 0:
            profitability_metrics.append(f"- **总资产收益率 (ROA)**: {data.roa:.2f}%")
        if data.revenue > 0:
            profitability_metrics.append(
                f"- **营业收入**: {self._format_number(data.revenue)}{currency_symbol.replace('$', '美元')}"
            )
        if data.net_income > 0:
            profitability_metrics.append(
                f"- **净利润**: {self._format_number(data.net_income)}{currency_symbol.replace('$', '美元')}"
            )
        if hasattr(data, "gross_profit_margin") and data.gross_profit_margin > 0:
            profitability_metrics.append(
                f"- **毛利率**: {data.gross_profit_margin:.2f}%"
            )
        if (
            hasattr(data, "operating_profit_margin")
            and data.operating_profit_margin > 0
        ):
            profitability_metrics.append(
                f"- **营业利润率**: {data.operating_profit_margin:.2f}%"
            )

        # 构建财务健康指标
        financial_health_metrics = []
        if data.debt_to_equity > 0:
            if data.debt_to_equity < 1:
                # 小于1的可能是资产负债率
                financial_health_metrics.append(
                    f"- **资产负债率**: {data.debt_to_equity:.2f}"
                )
            else:
                # 大于1的可能是负债权益比
                financial_health_metrics.append(
                    f"- **负债权益比**: {data.debt_to_equity:.2f}"
                )
        if data.current_ratio > 0:
            financial_health_metrics.append(f"- **流动比率**: {data.current_ratio:.2f}")
        if hasattr(data, "quick_ratio") and data.quick_ratio > 0:
            financial_health_metrics.append(f"- **速动比率**: {data.quick_ratio:.2f}")
        if (
            hasattr(data, "cash_flow_from_operations")
            and data.cash_flow_from_operations != 0
        ):
            financial_health_metrics.append(
                f"- **经营活动现金流**: {self._format_number(data.cash_flow_from_operations)}{currency_symbol.replace('$', '美元')}"
            )

        # 构建每股指标
        per_share_metrics = []
        if hasattr(data, "eps") and data.eps > 0:
            per_share_metrics.append(
                f"- **每股收益 (EPS)**: {data.eps:.2f}{currency_symbol.replace('$', '美元')}"
            )
        if hasattr(data, "bps") and data.bps > 0:
            per_share_metrics.append(
                f"- **每股净资产 (BPS)**: {data.bps:.2f}{currency_symbol.replace('$', '美元')}"
            )

        # 开始构建报告
        report = f"# {data.symbol} 基本面分析报告\n\n"

        # 基本信息
        report += "## 📋 基本信息\n"
        report += "\n".join(basic_info) + "\n\n"

        # 估值指标（只有有数据时才显示整个部分）
        if valuation_metrics:
            report += "## 💰 估值指标\n"
            report += "\n".join(valuation_metrics) + "\n\n"
            report += valuation_analysis + "\n\n"

        # 盈利能力（只有有数据时才显示整个部分）
        if profitability_metrics:
            report += "## 📊 盈利能力\n"
            report += "\n".join(profitability_metrics) + "\n\n"
            report += profitability_analysis + "\n\n"

        # 每股指标（只有有数据时才显示）
        if per_share_metrics:
            report += "## 💎 每股指标\n"
            report += "\n".join(per_share_metrics) + "\n\n"

        # 财务健康（只有有数据时才显示整个部分）
        if financial_health_metrics:
            report += "## 🏦 财务健康\n"
            report += "\n".join(financial_health_metrics) + "\n\n"
            report += financial_health + "\n\n"

        # 免责声明
        report += "---\n"
        report += "*本报告仅供参考，投资有风险，入市需谨慎。*\n\n"
        report += f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"

        return report

    def _analyze_valuation(self, data: FundamentalData) -> str:
        """分析估值水平"""
        analysis = []

        if data.pe_ratio > 0:
            if data.pe_ratio < 15:
                analysis.append("✅ P/E比率较低，可能存在投资价值")
            elif data.pe_ratio < 25:
                analysis.append("🟡 P/E比率适中，估值合理")
            else:
                analysis.append("🔴 P/E比率较高，可能存在估值风险")
        else:
            analysis.append("⚠️ P/E比率数据异常或公司亏损")

        if data.pb_ratio > 0:
            if data.pb_ratio < 1.5:
                analysis.append("✅ P/B比率较低，资产价值低估")
            elif data.pb_ratio < 3:
                analysis.append("🟡 P/B比率适中")
            else:
                analysis.append("🔴 P/B比率较高，可能高估")

        return (
            "\n".join([f"- {item}" for item in analysis])
            if analysis
            else "- 估值数据不足"
        )

    def _analyze_profitability(self, data: FundamentalData) -> str:
        """分析盈利能力"""
        analysis = []

        if data.roe > 0:
            if data.roe > 15:
                analysis.append("✅ ROE优秀，盈利能力强")
            elif data.roe > 10:
                analysis.append("🟡 ROE良好，盈利能力中等")
            else:
                analysis.append("🔴 ROE偏低，盈利能力一般")
        else:
            analysis.append("🔴 ROE为负，公司可能亏损")

        if data.net_income > 0:
            analysis.append("✅ 公司实现盈利")
        elif data.net_income < 0:
            analysis.append("🔴 公司出现亏损")
        else:
            analysis.append("⚠️ 净利润数据缺失")

        return (
            "\n".join([f"- {item}" for item in analysis])
            if analysis
            else "- 盈利数据不足"
        )

    def _analyze_financial_health(self, data: FundamentalData) -> str:
        """分析财务健康状况"""
        analysis = []

        if data.debt_to_equity > 0:
            if data.debt_to_equity < 0.5:
                analysis.append("✅ 负债水平较低，财务风险小")
            elif data.debt_to_equity < 1:
                analysis.append("🟡 负债水平适中")
            else:
                analysis.append("🔴 负债水平较高，需关注财务风险")

        if data.current_ratio > 0:
            if data.current_ratio > 2:
                analysis.append("✅ 流动性充足")
            elif data.current_ratio > 1:
                analysis.append("🟡 流动性良好")
            else:
                analysis.append("🔴 流动性不足，可能面临短期偿债压力")

        return (
            "\n".join([f"- {item}" for item in analysis])
            if analysis
            else "- 财务健康数据不足"
        )

    def _generate_investment_advice(self, data: FundamentalData) -> str:
        """生成投资建议"""
        if data.source == "fallback":
            return "数据获取失败，无法给出投资建议。建议查看其他分析报告或咨询专业投资顾问。"

        positive_factors = []
        negative_factors = []

        # 估值因素
        if 0 < data.pe_ratio < 20:
            positive_factors.append("估值合理 (P/E < 20)")
        elif data.pe_ratio > 30:
            negative_factors.append("估值偏高")

        # 盈利因素
        if data.roe > 12:
            positive_factors.append("盈利能力强")
        elif data.roe < 5:
            negative_factors.append("盈利能力弱 (ROE < 5%)")

        # 财务健康
        if data.debt_to_equity < 0.6:
            positive_factors.append("财务健康")
        elif data.debt_to_equity > 1.2:
            negative_factors.append("负债较重 (负债权益比 > 1.2)")

        advice = ""
        if len(positive_factors) > len(negative_factors):
            advice = f"**建议关注**: {', '.join(positive_factors)}"
            if negative_factors:
                advice += f"\n**风险提示**: {', '.join(negative_factors)}"
        elif len(negative_factors) > len(positive_factors):
            advice = f"**谨慎考虑**: {', '.join(negative_factors)}"
            if positive_factors:
                advice += f"\n**优势因素**: {', '.join(positive_factors)}"
        else:
            advice = "基本面表现中性，建议综合考虑其他因素"

        return advice

    def _format_number(self, number: float) -> str:
        """格式化数字显示"""
        number = float(number)
        if number >= 1e12:
            return f"{number/1e12:.2f}万亿"
        elif number >= 1e8:
            return f"{number/1e8:.2f}亿"
        elif number >= 1e4:
            return f"{number/1e4:.2f}万"
        else:
            return f"{number:,.2f}"

    def compare_stocks(self, symbols: List[str]) -> str:
        """对比多只股票的基本面"""
        if len(symbols) < 2:
            return "❌ 需要至少2只股票进行对比"

        data_list = []
        for symbol in symbols:
            try:
                data = self.get_fundamental_data(symbol)
                data_list.append(data)
            except Exception as e:
                print(f"获取 {symbol} 数据失败: {e}")

        if len(data_list) < 2:
            return "❌ 获取到的有效数据不足，无法进行对比"

        return self._format_comparison_report(data_list)

    def _format_comparison_report(self, data_list: List[FundamentalData]) -> str:
        """格式化股票对比报告"""
        report = "# 股票基本面对比分析\n\n"

        # 创建对比表格
        report += "| 指标 | "
        for data in data_list:
            report += f"{data.symbol} | "
        report += "\n|------|"
        for _ in data_list:
            report += "------|"
        report += "\n"

        # 添加各项指标对比
        metrics = [
            ("公司名称", lambda d: d.company_name),
            ("市值", lambda d: self._format_number(d.market_cap)),
            ("P/E比率", lambda d: f"{d.pe_ratio:.2f}"),
            ("P/B比率", lambda d: f"{d.pb_ratio:.2f}"),
            ("ROE (%)", lambda d: f"{d.roe:.2f}"),
            ("营收", lambda d: self._format_number(d.revenue)),
            ("净利润", lambda d: self._format_number(d.net_income)),
        ]

        for metric_name, value_func in metrics:
            report += f"| {metric_name} | "
            for data in data_list:
                try:
                    value = value_func(data)
                    report += f"{value} | "
                except:
                    report += "N/A | "
            report += "\n"

        report += f"\n*数据获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"

        return report

    def _determine_stock_market(self, symbol: str) -> str:
        """判断股票所属市场，使用统一的股票市场分类器"""
        processor = get_symbol_processor()
        return processor.get_market_simple_name(symbol)

    def _get_tushare_financial_data(
        self, symbol: str
    ) -> Optional[TushareFinancialData]:
        """获取Tushare完整财务数据"""
        try:
            service = self.services["tushare"]

            # 转换股票代码格式（如果需要）
            ts_code = self._convert_to_tushare_code(symbol)

            # 获取最近一年的财务数据
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

            # 调用Tushare财务API
            income_df = service.get_income_statement(ts_code, start_date, end_date)
            balance_df = service.get_balance_sheet(ts_code, start_date, end_date)
            cashflow_df = service.get_cash_flow(ts_code, start_date, end_date)
            indicators_df = service.get_financial_indicators(
                ts_code, start_date, end_date
            )

            # 如果所有数据都为空，返回None
            if (
                income_df.empty
                and balance_df.empty
                and cashflow_df.empty
                and indicators_df.empty
            ):
                print(f"未获取到 {ts_code} 的任何财务数据")
                return None

            return TushareFinancialData(
                income_statement=income_df,
                balance_sheet=balance_df,
                cash_flow=cashflow_df,
                financial_indicators=indicators_df,
            )

        except Exception as e:
            print(f"获取Tushare完整财务数据失败: {e}")
            return None

    def _convert_to_tushare_code(self, symbol: str) -> str:
        """转换为Tushare代码格式"""
        processor = get_symbol_processor()
        return processor.get_tushare_format(symbol)

    def _build_fundamental_data_from_tushare(
        self, symbol: str, info: Dict, financial_data: TushareFinancialData
    ) -> FundamentalData:
        """从Tushare财务数据构建基本面数据"""
        try:
            # 获取最新的财务指标
            indicators = financial_data.financial_indicators
            income = financial_data.income_statement
            balance = financial_data.balance_sheet
            cashflow = financial_data.cash_flow

            # 初始化默认值
            pe_ratio = pb_ratio = roe = 0
            revenue = net_income = 0
            total_assets = total_liabilities = 0
            cash_flow_ops = 0
            debt_to_equity = current_ratio = 0
            roa = gross_margin = operating_margin = 0

            # 从财务指标获取关键数据（fina_indicator接口）
            if indicators is not None and not indicators.empty:
                latest_indicators = indicators.iloc[0]
                # 打印列名以便调试
                print(f"财务指标列名: {list(latest_indicators.index)}")

                # 从fina_indicator接口获取财务比率指标
                roe = (
                    latest_indicators.get("roe", 0)
                    or latest_indicators.get("roe_waa", 0)
                    or 0
                )
                roa = latest_indicators.get("roa", 0) or 0
                current_ratio = latest_indicators.get("current_ratio", 0) or 0
                debt_to_assets = latest_indicators.get("debt_to_assets", 0) or 0
                gross_margin = latest_indicators.get("gross_margin", 0) or 0

            # 从市场数据获取估值指标（daily_basic接口）
            pe_ratio = pb_ratio = 0
            if info:
                print(f"市场数据字段: {list(info.keys())}")
                # pe_ttm和pb_mrq来自daily_basic接口
                pe_ratio = info.get("pe_ttm", 0) or info.get("pe", 0) or 0
                pb_ratio = info.get("pb_mrq", 0) or info.get("pb", 0) or 0

            # 从利润表获取收入和利润数据
            if income is not None and not income.empty:
                latest_income = income.iloc[0]
                # 优先使用total_revenue，如果没有则使用revenue
                revenue = (
                    latest_income.get("total_revenue", 0)
                    or latest_income.get("revenue", 0)
                    or 0
                )
                net_income = latest_income.get("n_income", 0) or 0
                operating_profit = latest_income.get("operate_profit", 0) or 0

                # 计算毛利率和营业利润率
                if revenue > 0:
                    # 由于Tushare利润表可能不直接提供毛利润，使用营业利润率
                    operating_margin = (operating_profit / revenue) * 100

            # 从资产负债表获取资产负债数据
            if balance is not None and not balance.empty:
                latest_balance = balance.iloc[0]
                total_assets = latest_balance.get("total_assets", 0) or 0
                total_liabilities = latest_balance.get("total_liab", 0) or 0

                # 如果没有从财务指标获取到资产负债率，则计算
                if debt_to_assets == 0 and total_assets > 0:
                    debt_to_equity = total_liabilities / total_assets
                else:
                    debt_to_equity = debt_to_assets

            # 从现金流量表获取经营活动现金流
            if cashflow is not None and not cashflow.empty:
                latest_cashflow = cashflow.iloc[0]
                cash_flow_ops = latest_cashflow.get("n_cashflow_act", 0) or 0

            # 获取市值信息
            market_cap = info.get("market_cap", 0)
            # 如果info中没有market_cap，尝试从total_mv获取（万元转元）
            if not market_cap:
                market_cap = (info.get("total_mv", 0) or 0) * 10000

            return FundamentalData(
                symbol=symbol,
                company_name=info.get("name", ""),
                market_cap=market_cap,
                pe_ratio=pe_ratio,
                pb_ratio=pb_ratio,
                roe=roe,
                revenue=revenue,
                net_income=net_income,
                debt_to_equity=debt_to_equity,
                current_ratio=current_ratio,
                total_assets=total_assets,
                total_liabilities=total_liabilities,
                cash_flow_from_operations=cash_flow_ops,
                gross_profit_margin=gross_margin,
                operating_profit_margin=operating_margin,
                roa=roa,
                source="tushare",
                timestamp=datetime.now(),
            )

        except Exception as e:
            print(f"构建Tushare基本面数据失败: {e}")
            # 返回基础数据
            return FundamentalData(
                symbol=symbol,
                company_name=info.get("name", ""),
                market_cap=info.get("market_cap", 0) or info.get("total_mv", 0),
                pe_ratio=0,
                pb_ratio=0,
                roe=0,
                revenue=0,
                net_income=0,
                debt_to_equity=0,
                current_ratio=0,
                source="tushare_basic",
                timestamp=datetime.now(),
            )

    def get_detailed_financial_analysis(self, symbol: str) -> str:
        """获取详细的财务分析报告（使用完整Tushare数据）"""
        try:
            data = self.get_fundamental_data(symbol)

            if data.source.startswith("tushare"):
                # 如果是Tushare数据，生成增强报告
                return self._format_enhanced_financial_report(data)
            else:
                # 否则使用标准报告
                return self._format_fundamentals_report(data)

        except Exception as e:
            return f"❌ 生成 {symbol} 详细财务分析失败: {e}"

    def _format_enhanced_financial_report(self, data: FundamentalData) -> str:
        """格式化增强版财务分析报告（动态显示有效数据）"""

        # 基础分析
        valuation_analysis = self._analyze_valuation(data)
        profitability_analysis = self._analyze_enhanced_profitability(data)
        financial_health = self._analyze_enhanced_financial_health(data)

        # 构建基本信息
        basic_info = [
            f"- **公司名称**: {data.company_name}",
            f"- **股票代码**: {data.symbol}",
        ]

        # 只有当市值大于0时才显示
        if data.market_cap > 0:
            basic_info.append(f"- **市值**: {self._format_number(data.market_cap)}元")

        basic_info.extend(
            [
                f"- **数据来源**: {data.source}",
                f"- **数据时间**: {data.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            ]
        )

        # 构建估值指标
        valuation_metrics = []
        if data.pe_ratio > 0:
            valuation_metrics.append(f"- **市盈率 (P/E)**: {data.pe_ratio:.2f}")
        if data.pb_ratio > 0:
            valuation_metrics.append(f"- **市净率 (P/B)**: {data.pb_ratio:.2f}")

        # 构建盈利能力指标（增强版包含更多指标）
        profitability_metrics = []
        if data.roe > 0:
            profitability_metrics.append(f"- **净资产收益率 (ROE)**: {data.roe:.2f}%")
        if hasattr(data, "roa") and data.roa > 0:
            profitability_metrics.append(f"- **总资产收益率 (ROA)**: {data.roa:.2f}%")
        if data.revenue > 0:
            profitability_metrics.append(
                f"- **营业收入**: {self._format_number(data.revenue)}元"
            )
        if data.net_income > 0:
            profitability_metrics.append(
                f"- **净利润**: {self._format_number(data.net_income)}元"
            )
        if hasattr(data, "gross_profit_margin") and data.gross_profit_margin > 0:
            profitability_metrics.append(
                f"- **毛利率**: {data.gross_profit_margin:.2f}%"
            )
        if (
            hasattr(data, "operating_profit_margin")
            and data.operating_profit_margin > 0
        ):
            profitability_metrics.append(
                f"- **营业利润率**: {data.operating_profit_margin:.2f}%"
            )

        # 构建财务状况指标（增强版包含资产负债数据）
        financial_status_metrics = []
        if hasattr(data, "total_assets") and data.total_assets > 0:
            financial_status_metrics.append(
                f"- **总资产**: {self._format_number(data.total_assets)}元"
            )
        if hasattr(data, "total_liabilities") and data.total_liabilities > 0:
            financial_status_metrics.append(
                f"- **总负债**: {self._format_number(data.total_liabilities)}元"
            )
        if data.debt_to_equity > 0:
            if data.debt_to_equity < 1:
                financial_status_metrics.append(
                    f"- **资产负债率**: {data.debt_to_equity:.2f}"
                )
            else:
                financial_status_metrics.append(
                    f"- **负债权益比**: {data.debt_to_equity:.2f}"
                )
        if data.current_ratio > 0:
            financial_status_metrics.append(f"- **流动比率**: {data.current_ratio:.2f}")
        if hasattr(data, "quick_ratio") and data.quick_ratio > 0:
            financial_status_metrics.append(f"- **速动比率**: {data.quick_ratio:.2f}")
        if (
            hasattr(data, "cash_flow_from_operations")
            and data.cash_flow_from_operations != 0
        ):
            financial_status_metrics.append(
                f"- **经营活动现金流**: {self._format_number(data.cash_flow_from_operations)}元"
            )

        # 构建每股指标（增强版）
        per_share_metrics = []
        if hasattr(data, "eps") and data.eps > 0:
            per_share_metrics.append(f"- **每股收益 (EPS)**: {data.eps:.2f}元")
        if hasattr(data, "bps") and data.bps > 0:
            per_share_metrics.append(f"- **每股净资产 (BPS)**: {data.bps:.2f}元")
        if hasattr(data, "ocfps") and data.ocfps > 0:
            per_share_metrics.append(f"- **每股经营现金流**: {data.ocfps:.2f}元")

        # 构建成长性指标
        growth_metrics = []
        if hasattr(data, "basic_eps_yoy") and data.basic_eps_yoy != 0:
            growth_metrics.append(
                f"- **每股收益同比增长率**: {data.basic_eps_yoy:.2f}%"
            )
        if hasattr(data, "netprofit_yoy") and data.netprofit_yoy != 0:
            growth_metrics.append(f"- **净利润同比增长率**: {data.netprofit_yoy:.2f}%")
        if hasattr(data, "roe_yoy") and data.roe_yoy != 0:
            growth_metrics.append(f"- **ROE同比增长率**: {data.roe_yoy:.2f}%")
        if hasattr(data, "tr_yoy") and data.tr_yoy != 0:
            growth_metrics.append(f"- **营业总收入同比增长率**: {data.tr_yoy:.2f}%")

        # 开始构建报告
        report = f"# {data.symbol} 详细财务分析报告\n\n"

        # 基本信息
        report += "## 📋 基本信息\n"
        report += "\n".join(basic_info) + "\n\n"

        # 估值指标
        if valuation_metrics:
            report += "## 💰 估值指标\n"
            report += "\n".join(valuation_metrics) + "\n\n"
            report += valuation_analysis + "\n\n"

        # 盈利能力分析
        if profitability_metrics:
            report += "## 📊 盈利能力分析\n"
            report += "\n".join(profitability_metrics) + "\n\n"
            report += profitability_analysis + "\n\n"

        # 每股指标
        if per_share_metrics:
            report += "## 💎 每股指标\n"
            report += "\n".join(per_share_metrics) + "\n\n"

        # 财务状况分析
        if financial_status_metrics:
            report += "## 🏦 财务状况分析\n"
            report += "\n".join(financial_status_metrics) + "\n\n"
            report += financial_health + "\n\n"

        # 成长性分析
        if growth_metrics:
            report += "## 📈 成长性分析\n"
            report += "\n".join(growth_metrics) + "\n\n"

        # 免责声明
        report += "---\n"
        report += "*本报告基于专业财务数据生成，仅供参考。*\n\n"
        report += f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"

        return report

    def _analyze_enhanced_profitability(self, data: FundamentalData) -> str:
        """增强版盈利能力分析"""
        analysis = []

        # ROE分析
        if data.roe > 0:
            if data.roe > 15:
                analysis.append("✅ ROE优秀 (>15%)，股东回报高")
            elif data.roe > 10:
                analysis.append("🟡 ROE良好 (10-15%)，盈利能力中等")
            else:
                analysis.append("🔴 ROE偏低 (<10%)，盈利能力待提升")

        # ROA分析
        if data.roa > 0:
            if data.roa > 8:
                analysis.append("✅ ROA优秀，资产使用效率高")
            elif data.roa > 5:
                analysis.append("🟡 ROA良好，资产使用效率中等")
            else:
                analysis.append("🔴 ROA偏低，资产使用效率有待提升")

        # 毛利率分析
        if data.gross_profit_margin > 0:
            if data.gross_profit_margin > 40:
                analysis.append("✅ 毛利率优秀，产品竞争力强")
            elif data.gross_profit_margin > 20:
                analysis.append("🟡 毛利率良好")
            else:
                analysis.append("🔴 毛利率偏低，成本控制需加强")

        # 营业利润率分析
        if data.operating_profit_margin > 0:
            if data.operating_profit_margin > 15:
                analysis.append("✅ 营业利润率优秀，运营效率高")
            elif data.operating_profit_margin > 8:
                analysis.append("🟡 营业利润率良好")
            else:
                analysis.append("🔴 营业利润率偏低，运营效率待提升")

        return (
            "\n".join([f"- {item}" for item in analysis])
            if analysis
            else "- 盈利数据不足"
        )

    def _analyze_enhanced_financial_health(self, data: FundamentalData) -> str:
        """增强版财务健康分析"""
        analysis = []

        # 资产负债分析
        if data.total_assets > 0 and data.total_liabilities > 0:
            debt_ratio = data.total_liabilities / data.total_assets
            if debt_ratio < 0.4:
                analysis.append("✅ 负债率低，财务风险小")
            elif debt_ratio < 0.6:
                analysis.append("🟡 负债率适中")
            else:
                analysis.append("🔴 负债率高，需关注财务风险")

        # 流动性分析
        if data.current_ratio > 0:
            if data.current_ratio > 2:
                analysis.append("✅ 流动性充足，短期偿债能力强")
            elif data.current_ratio > 1:
                analysis.append("🟡 流动性良好")
            else:
                analysis.append("🔴 流动性不足，短期偿债压力大")

        # 现金流分析
        if data.cash_flow_from_operations != 0:
            if data.cash_flow_from_operations > 0:
                if data.net_income > 0:
                    cf_quality = data.cash_flow_from_operations / data.net_income
                    if cf_quality > 1.2:
                        analysis.append("✅ 现金流质量优秀，盈利质量高")
                    elif cf_quality > 0.8:
                        analysis.append("🟡 现金流质量良好")
                    else:
                        analysis.append("🔴 现金流质量一般，需关注应收账款")
                else:
                    analysis.append("✅ 经营活动现金流为正，经营状况良好")
            else:
                analysis.append("🔴 经营活动现金流为负，需关注经营状况")

        return (
            "\n".join([f"- {item}" for item in analysis])
            if analysis
            else "- 财务健康数据不足"
        )

    def _generate_enhanced_investment_advice(self, data: FundamentalData) -> str:
        """生成增强版投资建议"""
        if data.source == "fallback":
            return "数据获取失败，无法给出投资建议。"

        score = 0
        factors = []

        # 估值评分
        if 10 < data.pe_ratio < 25:
            score += 2
            factors.append("估值合理")
        elif data.pe_ratio > 30:
            score -= 1
            factors.append("估值偏高")

        # 盈利能力评分
        if data.roe > 12:
            score += 2
            factors.append("ROE优秀")
        elif data.roe < 5:
            score -= 1
            factors.append("ROE偏低")

        if data.roa > 6:
            score += 1
            factors.append("ROA良好")

        # 利润率评分
        if data.gross_profit_margin > 30:
            score += 1
            factors.append("毛利率高")
        elif data.gross_profit_margin < 15:
            score -= 1
            factors.append("毛利率低")

        # 财务健康评分
        if data.total_assets > 0 and data.total_liabilities > 0:
            debt_ratio = data.total_liabilities / data.total_assets
            if debt_ratio < 0.5:
                score += 1
                factors.append("负债率健康")
            elif debt_ratio > 0.7:
                score -= 1
                factors.append("负债率偏高")

        # 现金流评分
        if data.cash_flow_from_operations > 0 and data.net_income > 0:
            if data.cash_flow_from_operations / data.net_income > 1:
                score += 1
                factors.append("现金流质量好")

        # 生成建议
        if score >= 4:
            return (
                f"**投资建议：买入** ⭐⭐⭐⭐⭐\n\n主要优势：{', '.join(factors[:3])}"
            )
        elif score >= 2:
            return f"**投资建议：关注** ⭐⭐⭐\n\n综合表现：{', '.join(factors[:3])}"
        elif score >= 0:
            return f"**投资建议：观望** ⭐⭐\n\n需要关注：财务指标表现一般"
        else:
            risk_factors = [f for f in factors if "低" in f or "高" in f]
            return f"**投资建议：回避** ⭐\n\n主要风险：{', '.join(risk_factors)}"
