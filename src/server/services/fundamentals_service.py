"""
基本面数据服务 - 优化版本
整合优化后的数据源（tushare, akshare, yfinance_service）
实现智能降级机制，并能够生成完整的基本面分析报告
"""

from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
import pandas as pd
import logging
import warnings

from ..utils.symbol_processor import get_symbol_processor
from ..utils.data_source_strategy import get_data_source_strategy
from ..exception.exception import DataNotFoundError

logger = logging.getLogger("fundamentals_service")
warnings.filterwarnings("ignore")


class FundamentalsService:
    """基本面数据服务 - 支持多数据源降级和报告生成"""

    def __init__(self):
        """初始化基本面数据服务"""
        self.symbol_processor = get_symbol_processor()
        self.strategy = get_data_source_strategy()
        self.services = {}
        self._init_services()

    def _init_services(self):
        """初始化各数据源服务"""
        # 1. Tushare服务
        try:
            from .tushare_service import get_tushare_service

            self.services["tushare"] = get_tushare_service()
            logger.info("✅ Tushare基本面服务初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ Tushare基本面服务初始化失败: {e}")

        # 2. AKShare服务
        try:
            from .akshare_service import get_akshare_service

            self.services["akshare"] = get_akshare_service()
            logger.info("✅ AKShare基本面服务初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ AKShare基本面服务初始化失败: {e}")

        # 3. YFinance服务
        try:
            from .yfinance_service import YFinanceService

            self.services["yfinance"] = YFinanceService()
            logger.info("✅ YFinance服务初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ YFinance服务初始化失败: {e}")

    def get_fundamental_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取股票基本面数据（带智能降级）

        Args:
            symbol: 股票代码

        Returns:
            Dict[str, Any]: 基本面数据字典
        """
        # 获取数据源优先级
        data_sources = self.strategy.get_fundamental_data_sources(symbol)
        classification = self.symbol_processor.classifier.classify_stock(symbol)

        logger.info(f"📊 获取 {symbol} 的基本面数据")
        logger.info(f"🔄 数据源优先级: {data_sources}")

        last_error = None
        for source in data_sources:
            if source not in self.services:
                continue

            try:
                logger.info(f"🔄 尝试从 {source} 获取基本面数据...")
                data = self._get_data_from_source(source, symbol, classification)

                if data is not None:
                    logger.info(f"✅ 成功从 {source} 获取基本面数据")
                    data["source"] = source
                    data["symbol"] = symbol
                    data["timestamp"] = datetime.now().isoformat()
                    return data

            except Exception as e:
                last_error = e
                logger.warning(f"⚠️ {source} 获取失败: {e}")
                continue

        # 所有数据源都失败
        raise DataNotFoundError(
            f"无法从任何数据源获取 {symbol} 的基本面数据。最后错误: {last_error}"
        )

    def _get_data_from_source(
        self, source: str, symbol: str, classification: Dict
    ) -> Optional[Dict[str, Any]]:
        """从指定数据源获取基本面数据"""
        service = self.services.get(source)
        if not service:
            return None

        if source == "tushare":
            # Tushare优化服务
            if classification["is_china"]:
                # A股：获取完整财务数据
                return self._get_tushare_china_fundamentals(service, symbol)
            elif classification["is_hk"]:
                # 港股：Tushare港股数据有限
                info = service.get_hk_info(symbol)
                if info:
                    return {"basic_info": info, "data_type": "limited"}
                return None
            else:
                return None

        elif source == "akshare":
            # AKShare优化服务
            if classification["is_china"]:
                return self._get_akshare_china_fundamentals(service, symbol)
            elif classification["is_hk"]:
                return self._get_akshare_hk_fundamentals(service, symbol)
            elif classification["is_us"]:
                return self._get_akshare_us_fundamentals(service, symbol)
            return None

        elif source == "yfinance":
            # YFinance服务（主要用于美股和港股）
            return self._get_yfinance_fundamentals(service, symbol, classification)

        return None

    def _get_tushare_china_fundamentals(
        self, service, symbol: str
    ) -> Optional[Dict[str, Any]]:
        """获取Tushare A股基本面数据"""
        try:
            # 获取财务数据（包含基本信息和财务数据）
            fundamentals = service.get_china_fundamentals(symbol)

            if not fundamentals:
                return None

            # Tushare返回的数据已经是完整格式，直接返回
            # 包含: basic_info, balance_sheet, income_statement, cash_flow,
            #      fina_indicator, financial_data
            fundamentals["data_type"] = "complete"
            fundamentals["source"] = "tushare"

            return fundamentals

        except Exception as e:
            logger.error(f"❌ Tushare A股基本面数据获取失败: {e}")
            return None

    def _get_akshare_china_fundamentals(
        self, service, symbol: str
    ) -> Optional[Dict[str, Any]]:
        """获取AKShare A股基本面数据"""
        try:
            # 1. 获取基本信息
            info = service.get_stock_info(symbol)
            if not info:
                logger.warning(f"⚠️ 未获取到{symbol}基本信息")
                info = {}

            # 性能优化：移除了全市场数据调用
            # 如需PE、PB等指标，请使用Tushare的财务指标接口

            # 2. 获取财务数据
            financial_data = service.get_financial_data(symbol)

            result = {
                "basic_info": info,
                "financial_data": financial_data if financial_data else {},
                "data_type": "complete" if info else "limited",
            }

            return result

        except Exception as e:
            logger.error(f"❌ AKShare A股基本面数据获取失败: {e}")
            return None

    def _get_akshare_hk_fundamentals(
        self, service, symbol: str
    ) -> Optional[Dict[str, Any]]:
        """获取AKShare 港股基本面数据（增强版）"""
        try:
            # 1. 获取基本信息（雪球数据源）
            info = {}
            try:
                xq_info = service.get_stock_basic_info_xq(symbol, market="hk")
                if xq_info:
                    info.update(xq_info)
                    logger.info(f"✅ 从雪球获取港股{symbol}基本信息成功")
            except Exception as e:
                logger.warning(f"⚠️ 从雪球获取港股基本信息失败: {e}")

            # 2. 获取全市场实时数据
            try:
                spot_info = service.get_stock_spot_info(symbol, market="hk")
                if spot_info:
                    info.update(spot_info)
                    logger.info(f"✅ 从全市场数据获取港股{symbol}实时信息")
            except Exception as e:
                logger.warning(f"⚠️ 获取港股全市场数据失败: {e}")

            # 3. 获取财务报表（年度数据）
            financial_data = {}

            # 资产负债表
            try:
                balance_sheet = service.get_hk_financial_report(
                    symbol, report_type="资产负债表", indicator="年度"
                )
                if balance_sheet is not None and not balance_sheet.empty:
                    financial_data["balance_sheet"] = balance_sheet
                    logger.info(f"✅ 获取港股{symbol}资产负债表成功")
            except Exception as e:
                logger.warning(f"⚠️ 获取港股资产负债表失败: {e}")

            # 利润表
            try:
                income_statement = service.get_hk_financial_report(
                    symbol, report_type="利润表", indicator="年度"
                )
                if income_statement is not None and not income_statement.empty:
                    financial_data["income_statement"] = income_statement
                    logger.info(f"✅ 获取港股{symbol}利润表成功")
            except Exception as e:
                logger.warning(f"⚠️ 获取港股利润表失败: {e}")

            # 现金流量表
            try:
                cash_flow = service.get_hk_financial_report(
                    symbol, report_type="现金流量表", indicator="年度"
                )
                if cash_flow is not None and not cash_flow.empty:
                    financial_data["cash_flow"] = cash_flow
                    logger.info(f"✅ 获取港股{symbol}现金流量表成功")
            except Exception as e:
                logger.warning(f"⚠️ 获取港股现金流量表失败: {e}")

            # 4. 获取主要财务指标
            fina_indicator_df = None
            try:
                fina_indicator_df = service.get_hk_financial_indicator(
                    symbol, indicator="年度"
                )
                if fina_indicator_df is not None and not fina_indicator_df.empty:
                    financial_data["fina_indicator"] = fina_indicator_df
                    logger.info(f"✅ 获取港股{symbol}财务指标成功")
            except Exception as e:
                logger.warning(f"⚠️ 获取港股财务指标失败: {e}")

            result = {
                "basic_info": info,
                "financial_data": financial_data,
                "fina_indicator": fina_indicator_df,  # 提取到顶层
                "data_type": "complete" if financial_data else "basic",
            }

            return result

        except Exception as e:
            logger.error(f"❌ AKShare 港股基本面数据获取失败: {e}")
            return None

    def _get_akshare_us_fundamentals(
        self, service, symbol: str
    ) -> Optional[Dict[str, Any]]:
        """获取AKShare 美股基本面数据（增强版）"""
        try:
            # 1. 获取基本信息（雪球数据源）
            info = {}
            try:
                xq_info = service.get_stock_basic_info_xq(symbol, market="us")
                if xq_info:
                    info.update(xq_info)
                    logger.info(f"✅ 从雪球获取美股{symbol}基本信息成功")
            except Exception as e:
                logger.warning(f"⚠️ 从雪球获取美股基本信息失败: {e}")

            # 2. 获取全市场实时数据
            try:
                spot_info = service.get_stock_spot_info(symbol, market="us")
                if spot_info:
                    info.update(spot_info)
                    logger.info(f"✅ 从全市场数据获取美股{symbol}实时信息")
            except Exception as e:
                logger.warning(f"⚠️ 获取美股全市场数据失败: {e}")

            # 3. 获取财务报表（年报数据）
            financial_data = {}

            # 资产负债表
            try:
                balance_sheet = service.get_us_financial_report(
                    symbol, report_type="资产负债表", indicator="年报"
                )
                if balance_sheet is not None and not balance_sheet.empty:
                    financial_data["balance_sheet"] = balance_sheet
                    logger.info(f"✅ 获取美股{symbol}资产负债表成功")
            except Exception as e:
                logger.warning(f"⚠️ 获取美股资产负债表失败: {e}")

            # 综合损益表
            try:
                income_statement = service.get_us_financial_report(
                    symbol, report_type="综合损益表", indicator="年报"
                )
                if income_statement is not None and not income_statement.empty:
                    financial_data["income_statement"] = income_statement
                    logger.info(f"✅ 获取美股{symbol}综合损益表成功")
            except Exception as e:
                logger.warning(f"⚠️ 获取美股综合损益表失败: {e}")

            # 现金流量表
            try:
                cash_flow = service.get_us_financial_report(
                    symbol, report_type="现金流量表", indicator="年报"
                )
                if cash_flow is not None and not cash_flow.empty:
                    financial_data["cash_flow"] = cash_flow
                    logger.info(f"✅ 获取美股{symbol}现金流量表成功")
            except Exception as e:
                logger.warning(f"⚠️ 获取美股现金流量表失败: {e}")

            # 4. 获取主要财务指标
            fina_indicator_df = None
            try:
                fina_indicator_df = service.get_us_financial_indicator(
                    symbol, indicator="年报"
                )
                if fina_indicator_df is not None and not fina_indicator_df.empty:
                    financial_data["fina_indicator"] = fina_indicator_df
                    logger.info(f"✅ 获取美股{symbol}财务指标成功")
            except Exception as e:
                logger.warning(f"⚠️ 获取美股财务指标失败: {e}")

            result = {
                "basic_info": info,
                "financial_data": financial_data,
                "fina_indicator": fina_indicator_df,  # 提取到顶层
                "data_type": "complete" if financial_data else "basic",
            }

            return result

        except Exception as e:
            logger.error(f"❌ AKShare 美股基本面数据获取失败: {e}")
            return None

    def _get_yfinance_fundamentals(
        self, service, symbol: str, classification: Dict
    ) -> Optional[Dict[str, Any]]:
        """获取YFinance基本面数据"""
        try:
            # 转换为YFinance格式
            yf_symbol = self.symbol_processor.get_yfinance_format(
                symbol, classification
            )

            # 获取基本信息
            info = service.get_fundamentals(yf_symbol)
            if not info:
                return None

            # 获取财务报表
            financial_data = {}
            try:
                financial_data["income_statement"] = service.get_income_statement(
                    yf_symbol
                )
            except:
                pass

            try:
                financial_data["balance_sheet"] = service.get_balance_sheet(yf_symbol)
            except:
                pass

            try:
                financial_data["cash_flow"] = service.get_cash_flow(yf_symbol)
            except:
                pass

            result = {
                "basic_info": info,
                "financial_data": financial_data,
                "data_type": "complete",
            }

            return result

        except Exception as e:
            logger.error(f"❌ YFinance 基本面数据获取失败: {e}")
            return None

    def calculate_financial_ratios(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算财务比率

        Args:
            data: 基本面数据

        Returns:
            Dict: 财务比率字典
        """
        ratios = {}

        try:
            basic_info = data.get("basic_info", {})
            financial_data = data.get("financial_data", {})
            fina_indicator = data.get("fina_indicator", {})

            # 如果fina_indicator是DataFrame，取最新一期数据
            if isinstance(fina_indicator, pd.DataFrame) and not fina_indicator.empty:
                fina_indicator = fina_indicator.iloc[0].to_dict()

            # 优先从financial_data获取数据（Tushare整合数据）
            # 估值指标
            ratios["pe_ratio"] = basic_info.get("pe_ratio") or basic_info.get(
                "trailingPE"
            )
            ratios["pb_ratio"] = basic_info.get("pb_ratio") or basic_info.get(
                "priceToBook"
            )
            ratios["ps_ratio"] = basic_info.get("ps_ratio") or basic_info.get(
                "priceToSalesTrailing12Months"
            )

            # 盈利能力指标 - 支持A股(Tushare)和港股/美股(AKShare)
            ratios["roe"] = (
                financial_data.get("roe")
                or fina_indicator.get("roe")
                or fina_indicator.get("ROE_AVG")  # 港股/美股
                or fina_indicator.get("ROE_YEARLY")  # 港股/美股
                or basic_info.get("roe")
                or basic_info.get("returnOnEquity")
            )
            ratios["roa"] = (
                financial_data.get("roa")
                or fina_indicator.get("roa")
                or fina_indicator.get("ROA")  # 港股/美股（大写）
                or basic_info.get("roa")
                or basic_info.get("returnOnAssets")
            )
            ratios["gross_margin"] = (
                financial_data.get("gross_margin")
                or fina_indicator.get("grossprofit_margin")
                or fina_indicator.get("GROSS_PROFIT_RATIO")  # 港股/美股
                or basic_info.get("gross_margin")
                or basic_info.get("grossMargins")
            )
            ratios["profit_margin"] = (
                financial_data.get("net_margin")
                or fina_indicator.get("netprofit_margin")
                or fina_indicator.get("NET_PROFIT_RATIO")  # 港股/美股
                or basic_info.get("profit_margin")
                or basic_info.get("profitMargins")
            )

            # 偿债能力指标
            ratios["debt_to_equity"] = (
                financial_data.get("debt_to_equity")
                or fina_indicator.get("debt_to_eqt")
                or basic_info.get("debt_to_equity")
                or basic_info.get("debtToEquity")
            )
            ratios["debt_to_assets"] = (
                financial_data.get("debt_to_assets")
                or fina_indicator.get("debt_to_assets")
                or fina_indicator.get("DEBT_ASSET_RATIO")  # 港股/美股
                or basic_info.get("debt_to_assets")
            )
            ratios["current_ratio"] = (
                financial_data.get("current_ratio")
                or fina_indicator.get("current_ratio")
                or fina_indicator.get("CURRENT_RATIO")  # 港股/美股（大写）
                or basic_info.get("current_ratio")
                or basic_info.get("currentRatio")
            )
            ratios["quick_ratio"] = (
                financial_data.get("quick_ratio")
                or fina_indicator.get("quick_ratio")
                or fina_indicator.get("QUICK_RATIO")  # 港股/美股（大写）
                or basic_info.get("quick_ratio")
                or basic_info.get("quickRatio")
            )

            # 增长指标
            ratios["revenue_growth"] = (
                financial_data.get("revenue_growth_yoy")
                or fina_indicator.get("or_yoy")
                or fina_indicator.get("OPERATE_INCOME_YOY")  # 港股/美股
                or basic_info.get("revenue_growth")
                or basic_info.get("revenueGrowth")
            )
            ratios["earnings_growth"] = (
                financial_data.get("profit_growth_yoy")
                or fina_indicator.get("netprofit_yoy")
                or fina_indicator.get("HOLDER_PROFIT_YOY")  # 港股/美股
                or basic_info.get("earnings_growth")
                or basic_info.get("earningsGrowth")
            )

            # 每股指标
            ratios["eps"] = (
                financial_data.get("eps")
                or fina_indicator.get("eps")
                or fina_indicator.get("BASIC_EPS")  # 港股/美股（基本每股收益）
                or fina_indicator.get("DILUTED_EPS")  # 港股/美股（稀释每股收益）
                or basic_info.get("eps")
            )
            ratios["bps"] = (
                financial_data.get("bps")
                or fina_indicator.get("bps")
                or fina_indicator.get("BPS")  # 港股/美股（大写）
                or basic_info.get("bps")
            )

        except Exception as e:
            logger.error(f"❌ 计算财务比率失败: {e}")

        return ratios

    def generate_fundamental_report(self, symbol: str) -> str:
        """
        生成完整的基本面分析报告

        Args:
            symbol: 股票代码

        Returns:
            str: Markdown格式的分析报告
        """
        try:
            # 获取基本面数据
            data = self.get_fundamental_data(symbol)
            classification = self.symbol_processor.classifier.classify_stock(symbol)

            # 计算财务比率
            ratios = self.calculate_financial_ratios(data)

            # 调试日志
            logger.info(f"📊 计算的财务比率: {ratios}")

            # 生成报告
            report = self._format_fundamental_report(
                symbol, data, classification, ratios
            )

            return report

        except Exception as e:
            import traceback

            error_msg = f"# 基本面分析报告生成失败\n\n**股票代码**: {symbol}\n\n**错误信息**: {str(e)}\n\n**详细堆栈**:\n```\n{traceback.format_exc()}\n```\n"
            logger.error(f"❌ 生成基本面报告失败: {e}")
            logger.error(f"详细堆栈: {traceback.format_exc()}")
            return error_msg

    def _format_fundamental_report(
        self, symbol: str, data: Dict, classification: Dict, ratios: Dict
    ) -> str:
        """格式化基本面分析报告"""
        basic_info = data.get("basic_info", {})
        financial_data = data.get("financial_data", {})
        source = data.get("source", "未知")

        # 获取公司名称
        company_name = (
            basic_info.get("name")
            or basic_info.get("longName")
            or basic_info.get("shortName")
            or symbol
        )

        report = f"""# {company_name} ({symbol}) 基本面分析报告

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**数据来源**: {source}
**市场**: {classification['market_name']}
**交易所**: {classification['exchange']}

---

## 一、公司基本信息

"""

        # 公司基本信息
        if basic_info:
            report += self._format_basic_info(basic_info, classification)

        # 估值指标
        report += "\n## 二、估值指标\n\n"
        report += self._format_valuation_metrics(ratios, basic_info)

        # 盈利能力
        report += "\n## 三、盈利能力分析\n\n"
        report += self._format_profitability_metrics(ratios, financial_data)

        # 偿债能力
        report += "\n## 四、偿债能力分析\n\n"
        report += self._format_solvency_metrics(ratios, financial_data)

        # 成长性分析
        report += "\n## 五、成长性分析\n\n"
        report += self._format_growth_metrics(ratios, financial_data)

        # 财务报表摘要（如果有）
        if financial_data:
            report += "\n## 六、财务报表摘要\n\n"
            report += self._format_financial_statements(financial_data)

        # 投资建议
        report += "\n## 七、投资建议\n\n"
        report += self._generate_investment_advice(data, ratios, classification)

        report += (
            "\n---\n\n*本报告仅供参考，不构成投资建议。投资有风险，入市需谨慎。*\n"
        )

        return report

    def _format_basic_info(self, info: Dict, classification: Dict) -> str:
        """格式化基本信息"""
        text = ""

        # 行业信息
        industry = info.get("industry") or info.get("industry_name")
        sector = info.get("sector") or info.get("sector_name")

        if industry:
            text += f"- **所属行业**: {industry}\n"
        if sector and sector != industry:
            text += f"- **所属板块**: {sector}\n"

        # 市值
        market_cap = (
            info.get("market_cap")
            or info.get("marketCap")
            or info.get("total_mv")
            or info.get("circ_mv")
        )
        if market_cap:
            if isinstance(market_cap, (int, float)) and market_cap > 1e8:
                text += f"- **总市值**: {market_cap / 1e8:.2f} 亿\n"
            else:
                text += f"- **总市值**: {market_cap}\n"

        # 上市日期
        list_date = info.get("list_date") or info.get("listDate")
        if list_date:
            text += f"- **上市日期**: {list_date}\n"

        # 员工人数
        employees = info.get("fullTimeEmployees") or info.get("employees")
        if employees:
            text += f"- **员工人数**: {employees:,}\n"

        # 公司网站
        website = info.get("website")
        if website:
            text += f"- **公司网站**: {website}\n"

        # 公司简介
        business = (
            info.get("business_summary")
            or info.get("longBusinessSummary")
            or info.get("introduction")
        )
        if business:
            text += f"\n**公司简介**:\n\n{business[:500]}{'...' if len(str(business)) > 500 else ''}\n"

        return text if text else "暂无公司基本信息\n"

    def _format_valuation_metrics(self, ratios: Dict, info: Dict) -> str:
        """格式化估值指标"""
        metrics = []

        pe = ratios.get("pe_ratio")
        if pe:
            metrics.append(f"- **市盈率 (P/E)**: {pe:.2f}")

        pb = ratios.get("pb_ratio")
        if pb:
            metrics.append(f"- **市净率 (P/B)**: {pb:.2f}")

        ps = ratios.get("ps_ratio")
        if ps:
            metrics.append(f"- **市销率 (P/S)**: {ps:.2f}")

        # 股息率
        dividend_yield = info.get("dividendYield") or info.get("dividend_yield")
        if dividend_yield:
            dividend_pct = (
                dividend_yield * 100 if dividend_yield < 1 else dividend_yield
            )
            metrics.append(f"- **股息率**: {dividend_pct:.2f}%")

        if not metrics:
            return "暂无估值指标数据\n"

        return "\n".join(metrics) + "\n"

    def _format_profitability_metrics(self, ratios: Dict, financial_data: Dict) -> str:
        """格式化盈利能力指标"""
        metrics = []

        roe = ratios.get("roe")
        if roe:
            roe_pct = roe * 100 if roe < 1 else roe
            metrics.append(f"- **净资产收益率 (ROE)**: {roe_pct:.2f}%")

        roa = ratios.get("roa")
        if roa:
            roa_pct = roa * 100 if roa < 1 else roa
            metrics.append(f"- **总资产收益率 (ROA)**: {roa_pct:.2f}%")

        gross_margin = ratios.get("gross_margin")
        if gross_margin:
            margin_pct = gross_margin * 100 if gross_margin < 1 else gross_margin
            metrics.append(f"- **毛利率**: {margin_pct:.2f}%")

        profit_margin = ratios.get("profit_margin")
        if profit_margin:
            margin_pct = profit_margin * 100 if profit_margin < 1 else profit_margin
            metrics.append(f"- **净利率**: {margin_pct:.2f}%")

        if not metrics:
            return "暂无盈利能力数据\n"

        return "\n".join(metrics) + "\n"

    def _format_solvency_metrics(self, ratios: Dict, financial_data: Dict) -> str:
        """格式化偿债能力指标"""
        metrics = []

        debt_to_equity = ratios.get("debt_to_equity")
        if debt_to_equity:
            metrics.append(f"- **资产负债率**: {debt_to_equity:.2f}")

        current_ratio = ratios.get("current_ratio")
        if current_ratio:
            metrics.append(f"- **流动比率**: {current_ratio:.2f}")

        quick_ratio = ratios.get("quick_ratio")
        if quick_ratio:
            metrics.append(f"- **速动比率**: {quick_ratio:.2f}")

        if not metrics:
            return "暂无偿债能力数据\n"

        return "\n".join(metrics) + "\n"

    def _format_growth_metrics(self, ratios: Dict, financial_data: Dict) -> str:
        """格式化成长性指标"""
        metrics = []

        revenue_growth = ratios.get("revenue_growth")
        if revenue_growth:
            growth_pct = revenue_growth * 100 if revenue_growth < 1 else revenue_growth
            metrics.append(f"- **营收增长率**: {growth_pct:.2f}%")

        earnings_growth = ratios.get("earnings_growth")
        if earnings_growth:
            growth_pct = (
                earnings_growth * 100 if earnings_growth < 1 else earnings_growth
            )
            metrics.append(f"- **利润增长率**: {growth_pct:.2f}%")

        if not metrics:
            return "暂无成长性数据\n"

        return "\n".join(metrics) + "\n"

    def _format_financial_statements(self, financial_data: Dict) -> str:
        """格式化财务报表摘要"""
        text = ""

        # 利润表
        income = financial_data.get("income_statement")
        if income is None:
            income = financial_data.get("income")

        if isinstance(income, pd.DataFrame) and not income.empty:
            text += "### 利润表摘要\n\n"
            text += f"最近 {len(income.columns)} 个报告期的数据\n\n"
        elif income is not None and not isinstance(income, pd.DataFrame):
            text += "### 利润表摘要\n\n"
            text += "数据已获取\n\n"

        # 资产负债表
        balance = financial_data.get("balance_sheet")
        if balance is None:
            balance = financial_data.get("balance")

        if isinstance(balance, pd.DataFrame) and not balance.empty:
            text += "### 资产负债表摘要\n\n"
            text += f"最近 {len(balance.columns)} 个报告期的数据\n\n"
        elif balance is not None and not isinstance(balance, pd.DataFrame):
            text += "### 资产负债表摘要\n\n"
            text += "数据已获取\n\n"

        # 现金流量表
        cashflow = financial_data.get("cash_flow")
        if cashflow is None:
            cashflow = financial_data.get("cashflow")

        if isinstance(cashflow, pd.DataFrame) and not cashflow.empty:
            text += "### 现金流量表摘要\n\n"
            text += f"最近 {len(cashflow.columns)} 个报告期的数据\n\n"
        elif cashflow is not None and not isinstance(cashflow, pd.DataFrame):
            text += "### 现金流量表摘要\n\n"
            text += "数据已获取\n\n"

        return text if text else "暂无财务报表数据\n"

    def _generate_investment_advice(
        self, data: Dict, ratios: Dict, classification: Dict
    ) -> str:
        """生成投资建议"""
        advice = []

        # 估值评估
        pe = ratios.get("pe_ratio")
        if pe:
            if pe < 15:
                advice.append("✅ **估值**: 市盈率较低，可能被低估")
            elif pe > 30:
                advice.append("⚠️ **估值**: 市盈率较高，估值偏贵")
            else:
                advice.append("📊 **估值**: 市盈率处于合理区间")

        # 盈利能力评估
        roe = ratios.get("roe")
        if roe:
            roe_val = roe * 100 if roe < 1 else roe
            if roe_val > 15:
                advice.append("✅ **盈利能力**: ROE优秀，盈利能力强")
            elif roe_val > 10:
                advice.append("📊 **盈利能力**: ROE良好")
            else:
                advice.append("⚠️ **盈利能力**: ROE偏低，需关注")

        # 成长性评估
        revenue_growth = ratios.get("revenue_growth")
        if revenue_growth:
            growth_val = revenue_growth * 100 if revenue_growth < 1 else revenue_growth
            if growth_val > 20:
                advice.append("✅ **成长性**: 营收增长强劲")
            elif growth_val > 0:
                advice.append("📊 **成长性**: 营收保持增长")
            else:
                advice.append("⚠️ **成长性**: 营收出现下滑")

        # 偿债能力评估
        current_ratio = ratios.get("current_ratio")
        if current_ratio:
            if current_ratio > 2:
                advice.append("✅ **偿债能力**: 流动比率健康")
            elif current_ratio > 1:
                advice.append("📊 **偿债能力**: 流动比率合理")
            else:
                advice.append("⚠️ **偿债能力**: 流动比率偏低，需关注财务风险")

        if not advice:
            advice.append("数据不足，暂无具体投资建议")

        advice.append(
            "\n**风险提示**: 以上分析基于历史数据，市场情况随时变化，请结合实际情况谨慎决策。"
        )

        return "\n".join(advice) + "\n"


# ==================== 便捷函数 ====================

_global_service = None


def get_fundamentals_service() -> FundamentalsService:
    """获取基本面数据服务单例"""
    global _global_service
    if _global_service is None:
        _global_service = FundamentalsService()
    return _global_service


def get_stock_fundamental_data(symbol: str) -> Dict[str, Any]:
    """获取股票基本面数据（便捷函数）"""
    service = get_fundamentals_service()
    return service.get_fundamental_data(symbol)


def generate_fundamental_analysis_report(symbol: str) -> str:
    """生成基本面分析报告（便捷函数）"""
    service = get_fundamentals_service()
    return service.generate_fundamental_report(symbol)
