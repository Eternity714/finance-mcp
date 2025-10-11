"""
Tushare 数据服务 - 优化版本
基于参考文件 cankao/tushare_utils.py 的经过验证的API实现
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
import logging
import warnings

try:
    import tushare as ts
except ImportError:
    ts = None

from ..utils.symbol_processor import get_symbol_processor
from ..exception.exception import DataNotFoundError
from ..core.connection_registry import get_connection_registry

logger = logging.getLogger("tushare_service")
warnings.filterwarnings("ignore")


class TushareService:
    """封装Tushare API的数据服务（使用统一连接管理）"""

    def __init__(self):
        """初始化Tushare服务"""
        self.connection_registry = get_connection_registry()
        self.symbol_processor = get_symbol_processor()

        # 验证 Tushare 连接是否可用（不强制要求）
        try:
            tushare_conn = self.connection_registry.get_connection("tushare")
            if tushare_conn and not tushare_conn.is_healthy():
                logger.warning("⚠️ Tushare连接不健康，尝试重连...")
                tushare_conn.reconnect()
            if tushare_conn:
                logger.info("✅ TushareService 初始化成功")
            else:
                logger.warning("⚠️ Tushare 未配置或初始化失败")
        except Exception as e:
            logger.warning(f"⚠️ TushareService 初始化失败: {e}")

    @property
    def pro(self):
        """延迟获取 Tushare API 客户端"""
        try:
            return self.connection_registry.get_tushare()
        except ConnectionError:
            return None

    # ==================== A股数据接口 ====================

    def get_stock_daily(
        self, symbol: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取A股日线行情（带前复权价格计算）"""
        if not self.pro:
            raise ConnectionError("Tushare未连接")

        try:
            # 标准化股票代码
            ts_code = self.symbol_processor.get_tushare_format(symbol)

            # 设置默认日期
            if end_date is None:
                end_date = datetime.now().strftime("%Y%m%d")
            else:
                end_date = end_date.replace("-", "")

            if start_date is None:
                start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
            else:
                start_date = start_date.replace("-", "")

            logger.info(f"🔄 Tushare获取{ts_code}数据 ({start_date} 到 {end_date})")

            # 获取日线数据
            data = self.pro.daily(
                ts_code=ts_code, start_date=start_date, end_date=end_date
            )

            if data is None or data.empty:
                logger.warning(f"⚠️ Tushare返回空数据: {ts_code}")
                raise DataNotFoundError(f"未获取到 {ts_code} 的日线数据")

            # 数据预处理
            data = data.sort_values("trade_date")
            data["trade_date"] = pd.to_datetime(data["trade_date"])

            # 计算前复权价格（基于pct_chg重新计算连续价格）
            data = self._calculate_forward_adjusted_prices(data)

            # 标准化数据格式
            data = self._standardize_data(data)

            logger.info(f"✅ 获取{ts_code}数据成功: {len(data)}条")
            return data

        except Exception as e:
            logger.error(f"❌ 获取{symbol}数据失败: {e}")
            raise

    def _calculate_forward_adjusted_prices(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        基于pct_chg计算前复权价格

        Tushare的daily接口返回除权价格，在除权日会出现价格跳跃。
        使用pct_chg（涨跌幅）重新计算连续的前复权价格，确保价格序列的连续性。
        """
        if data.empty or "pct_chg" not in data.columns:
            logger.warning("⚠️ 数据为空或缺少pct_chg列，无法计算前复权价格")
            return data

        try:
            # 复制数据避免修改原始数据
            adjusted_data = data.copy()
            adjusted_data = adjusted_data.sort_values("trade_date").reset_index(
                drop=True
            )

            # 保存原始价格列
            adjusted_data["close_raw"] = adjusted_data["close"].copy()
            adjusted_data["open_raw"] = adjusted_data["open"].copy()
            adjusted_data["high_raw"] = adjusted_data["high"].copy()
            adjusted_data["low_raw"] = adjusted_data["low"].copy()

            # 从最新的收盘价开始，向前计算前复权价格
            latest_close = float(adjusted_data.iloc[-1]["close"])

            # 计算前复权收盘价
            adjusted_closes = [latest_close]

            # 从倒数第二天开始向前计算
            for i in range(len(adjusted_data) - 2, -1, -1):
                pct_change = float(adjusted_data.iloc[i + 1]["pct_chg"]) / 100.0

                # 前一天的前复权收盘价 = 今天的前复权收盘价 / (1 + 今天的涨跌幅)
                prev_close = adjusted_closes[0] / (1 + pct_change)
                adjusted_closes.insert(0, prev_close)

            # 更新收盘价
            adjusted_data["close"] = adjusted_closes

            # 计算其他价格的调整比例
            for i in range(len(adjusted_data)):
                if adjusted_data.iloc[i]["close_raw"] != 0:
                    # 计算调整比例
                    adjustment_ratio = (
                        adjusted_data.iloc[i]["close"]
                        / adjusted_data.iloc[i]["close_raw"]
                    )

                    # 应用调整比例到其他价格
                    adjusted_data.iloc[i, adjusted_data.columns.get_loc("open")] = (
                        adjusted_data.iloc[i]["open_raw"] * adjustment_ratio
                    )
                    adjusted_data.iloc[i, adjusted_data.columns.get_loc("high")] = (
                        adjusted_data.iloc[i]["high_raw"] * adjustment_ratio
                    )
                    adjusted_data.iloc[i, adjusted_data.columns.get_loc("low")] = (
                        adjusted_data.iloc[i]["low_raw"] * adjustment_ratio
                    )

            # 添加标记
            adjusted_data["price_type"] = "forward_adjusted"

            logger.info(f"✅ 前复权价格计算完成，数据条数: {len(adjusted_data)}")
            return adjusted_data

        except Exception as e:
            logger.error(f"❌ 前复权价格计算失败: {e}")
            return data

    def _standardize_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """标准化A股数据格式"""
        if data.empty:
            return data

        try:
            # 重命名列
            column_mapping = {
                "trade_date": "date",
                "ts_code": "code",
                "vol": "volume",
                "amount": "turnover",
            }

            for old_col, new_col in column_mapping.items():
                if old_col in data.columns:
                    data = data.rename(columns={old_col: new_col})

            # 确保日期格式
            if "date" in data.columns:
                data["date"] = pd.to_datetime(data["date"])

            # 计算涨跌幅（如果没有）
            if "pct_chg" not in data.columns and "close" in data.columns:
                data = data.sort_values("date")
                data["pct_chg"] = data["close"].pct_change() * 100

            return data

        except Exception as e:
            logger.error(f"❌ 标准化数据失败: {e}")
            return data

    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """获取股票基本信息"""
        if not self.pro:
            raise ConnectionError("Tushare未连接")

        try:
            ts_code = self.symbol_processor.get_tushare_format(symbol)

            basic_info = self.pro.stock_basic(
                ts_code=ts_code,
                fields="ts_code,symbol,name,area,industry,market,list_date",
            )

            if basic_info is None or basic_info.empty:
                raise DataNotFoundError(f"未找到 {ts_code} 的股票信息")

            info = basic_info.iloc[0]
            return {
                "symbol": symbol,
                "ts_code": info["ts_code"],
                "name": info["name"],
                "area": info.get("area", ""),
                "industry": info.get("industry", ""),
                "market": info.get("market", ""),
                "list_date": info.get("list_date", ""),
                "source": "tushare",
            }

        except Exception as e:
            logger.error(f"❌ 获取{symbol}股票信息失败: {e}")
            raise

    # ==================== 港股数据接口 ====================

    def get_hk_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取港股日线行情"""
        if not self.pro:
            raise ConnectionError("Tushare未连接")

        try:
            # 标准化港股代码
            ts_code = self.symbol_processor.get_tushare_format(symbol)

            # 格式化日期
            start_date_formatted = start_date.replace("-", "") if start_date else None
            end_date_formatted = end_date.replace("-", "") if end_date else None

            logger.info(
                f"🇭🇰 Tushare获取港股数据: {ts_code} ({start_date} ~ {end_date})"
            )

            # 获取港股日线数据
            data = self.pro.hk_daily(
                ts_code=ts_code,
                start_date=start_date_formatted,
                end_date=end_date_formatted,
            )

            if data is None or data.empty:
                logger.warning(f"⚠️ Tushare返回空港股数据: {ts_code}")
                raise DataNotFoundError(f"未获取到港股 {ts_code} 的日线数据")

            # 标准化数据
            data = self._standardize_hk_data(data)

            logger.info(f"✅ 获取港股{ts_code}数据成功: {len(data)}条")
            return data

        except Exception as e:
            logger.error(f"❌ 获取港股{symbol}数据失败: {e}")
            raise

    def _standardize_hk_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """标准化港股数据格式"""
        if data.empty:
            return data

        try:
            # 重命名列
            column_mapping = {
                "trade_date": "date",
                "ts_code": "code",
                "vol": "volume",
                "amount": "turnover",
            }

            for old_col, new_col in column_mapping.items():
                if old_col in data.columns:
                    data = data.rename(columns={old_col: new_col})

            # 确保日期格式
            if "date" in data.columns:
                data["date"] = pd.to_datetime(data["date"])

            return data

        except Exception as e:
            logger.error(f"❌ 标准化港股数据失败: {e}")
            return data

    # ==================== 财务数据接口 ====================

    def get_china_fundamentals(self, symbol: str, period: str = None) -> Dict[str, Any]:
        """
        获取A股核心财务数据

        Args:
            symbol: 股票代码
            period: 报告期(YYYYMMDD格式,如20231231表示年报,20230630半年报,20230930三季报)

        Returns:
            Dict包含:
            - basic_info: 股票基本信息
            - balance_sheet: 资产负债表
            - income_statement: 利润表
            - cash_flow: 现金流量表
            - fina_indicator: 财务指标
            - financial_data: 整合后的核心财务数据
        """
        if not self.pro:
            raise ConnectionError("Tushare未连接")

        if not period:
            # 默认使用最近已发布的报告期
            # 财报通常有延迟：年报4月底，一季报4月底，半年报8月底，三季报10月底
            # 注意：这里使用2024年作为基准年
            now = datetime.now()
            year = 2024  # 当前基准年
            month = now.month

            # 根据当前月份判断最近可获取的报告期
            if month <= 4:
                # 1-4月：上一年年报
                period = f"{year - 1}1231"
            elif month <= 8:
                # 5-8月：当年一季报
                period = f"{year}0331"
            elif month <= 10:
                # 9-10月：当年半年报
                period = f"{year}0630"
            else:
                # 11-12月：当年三季报
                period = f"{year}0930"

            logger.info(f"📅 自动选择报告期: {period}")

        try:
            ts_code = self.symbol_processor.get_tushare_format(symbol)
            logger.info(f"📊 获取{ts_code}财务数据，报告期: {period}")

            fundamentals = {
                "symbol": symbol,
                "ts_code": ts_code,
                "period": period,
                "source": "tushare",
            }

            # 获取基本信息
            try:
                basic_info = self.get_stock_info(symbol)
                fundamentals["basic_info"] = basic_info
            except Exception as e:
                logger.warning(f"⚠️ 获取股票基本信息失败: {e}")
                fundamentals["basic_info"] = {}

            # 获取资产负债表 (balancesheet)
            try:
                balance_sheet = self.pro.balancesheet(
                    ts_code=ts_code,
                    period=period,
                    fields="ts_code,ann_date,f_ann_date,end_date,report_type,"
                    "total_assets,total_liab,total_hldr_eqy_exc_min_int,"
                    "money_cap,accounts_receiv,inventories,fix_assets,"
                    "lt_borr,st_borr,notes_payable,acct_payable,"
                    "cap_rese,surplus_rese,undistr_porfit",
                )
                if balance_sheet is not None and not balance_sheet.empty:
                    fundamentals["balance_sheet"] = balance_sheet.iloc[0].to_dict()
                    logger.info(f"✅ 获取资产负债表成功")
                else:
                    logger.warning(f"⚠️ 资产负债表数据为空")
                    fundamentals["balance_sheet"] = {}
            except Exception as e:
                logger.warning(f"⚠️ 获取资产负债表失败: {e}")
                fundamentals["balance_sheet"] = {}

            # 获取利润表 (income)
            try:
                income_statement = self.pro.income(
                    ts_code=ts_code,
                    period=period,
                    fields="ts_code,ann_date,f_ann_date,end_date,report_type,"
                    "total_revenue,revenue,operate_profit,total_profit,"
                    "n_income,n_income_attr_p,basic_eps,diluted_eps,"
                    "total_cogs,sell_exp,admin_exp,fin_exp,"
                    "oper_cost,rd_exp,ebit,ebitda",
                )
                if income_statement is not None and not income_statement.empty:
                    fundamentals["income_statement"] = income_statement.iloc[
                        0
                    ].to_dict()
                    logger.info(f"✅ 获取利润表成功")
                else:
                    logger.warning(f"⚠️ 利润表数据为空")
                    fundamentals["income_statement"] = {}
            except Exception as e:
                logger.warning(f"⚠️ 获取利润表失败: {e}")
                fundamentals["income_statement"] = {}

            # 获取现金流量表 (cashflow)
            try:
                cash_flow = self.pro.cashflow(
                    ts_code=ts_code,
                    period=period,
                    fields="ts_code,ann_date,f_ann_date,end_date,report_type,"
                    "n_cashflow_act,n_cashflow_inv_act,"
                    "n_cash_flows_fnc_act,c_fr_sale_sg,c_paid_goods_s,"
                    "c_paid_to_for_empl,c_paid_for_taxes,net_profit,"
                    "finan_exp,im_n_incr_cash_equ,free_cashflow",
                )
                if cash_flow is not None and not cash_flow.empty:
                    fundamentals["cash_flow"] = cash_flow.iloc[0].to_dict()
                    logger.info(f"✅ 获取现金流量表成功")
                else:
                    logger.warning(f"⚠️ 现金流量表数据为空")
                    fundamentals["cash_flow"] = {}
            except Exception as e:
                logger.warning(f"⚠️ 获取现金流量表失败: {e}")
                fundamentals["cash_flow"] = {}

            # 获取财务指标 (fina_indicator)
            try:
                fina_indicator = self.pro.fina_indicator(
                    ts_code=ts_code,
                    period=period,
                    fields="ts_code,ann_date,f_ann_date,end_date,"
                    "eps,dt_eps,roe,roe_waa,roe_dt,roa,bps,ocfps,"
                    "gross_margin,current_ratio,quick_ratio,"
                    "debt_to_assets,assets_to_eqt,debt_to_eqt,"
                    "netprofit_margin,grossprofit_margin,"
                    "profit_to_gr,or_yoy,q_sales_yoy,netprofit_yoy",
                )
                if fina_indicator is not None and not fina_indicator.empty:
                    fundamentals["fina_indicator"] = fina_indicator.iloc[0].to_dict()
                    logger.info(f"✅ 获取财务指标成功")
                else:
                    logger.warning(f"⚠️ 财务指标数据为空")
                    fundamentals["fina_indicator"] = {}
            except Exception as e:
                logger.warning(f"⚠️ 获取财务指标失败: {e}")
                fundamentals["fina_indicator"] = {}

            # 整合核心财务数据到 financial_data 字段
            financial_data = {}

            # 从资产负债表提取数据
            bs = fundamentals.get("balance_sheet", {})
            if bs:
                financial_data.update(
                    {
                        "total_assets": bs.get("total_assets"),
                        "total_liabilities": bs.get("total_liab"),
                        "total_equity": bs.get("total_hldr_eqy_exc_min_int"),
                        "cash": bs.get("money_cap"),
                        "accounts_receivable": bs.get("accounts_receiv"),
                        "inventory": bs.get("inventories"),
                        "fixed_assets": bs.get("fix_assets"),
                        "long_term_debt": bs.get("lt_borr"),
                        "short_term_debt": bs.get("st_borr"),
                    }
                )

            # 从利润表提取数据
            income = fundamentals.get("income_statement", {})
            if income:
                financial_data.update(
                    {
                        "total_revenue": income.get("total_revenue"),
                        "operating_revenue": income.get("revenue"),
                        "operating_profit": income.get("operate_profit"),
                        "total_profit": income.get("total_profit"),
                        "net_income": income.get("n_income"),
                        "net_income_parent": income.get("n_income_attr_p"),
                        "eps": income.get("basic_eps"),
                        "diluted_eps": income.get("diluted_eps"),
                        "operating_cost": income.get("oper_cost"),
                        "selling_expense": income.get("sell_exp"),
                        "admin_expense": income.get("admin_exp"),
                        "financial_expense": income.get("fin_exp"),
                        "rd_expense": income.get("rd_exp"),
                        "ebit": income.get("ebit"),
                        "ebitda": income.get("ebitda"),
                    }
                )

            # 从现金流量表提取数据
            cf = fundamentals.get("cash_flow", {})
            if cf:
                financial_data.update(
                    {
                        "operating_cash_flow": cf.get("n_cashflow_act"),
                        "investing_cash_flow": cf.get("n_cashflow_inv_act"),
                        "financing_cash_flow": cf.get("n_cash_flows_fnc_act"),
                        "free_cash_flow": cf.get("free_cashflow"),
                    }
                )

            # 从财务指标提取数据
            fi = fundamentals.get("fina_indicator", {})
            if fi:
                financial_data.update(
                    {
                        "roe": fi.get("roe"),
                        "roe_weighted": fi.get("roe_waa"),
                        "roa": fi.get("roa"),
                        "bps": fi.get("bps"),
                        "ocfps": fi.get("ocfps"),
                        "gross_margin": fi.get(
                            "grossprofit_margin"
                        ),  # 使用grossprofit_margin而不是gross_margin
                        "net_margin": fi.get("netprofit_margin"),
                        "current_ratio": fi.get("current_ratio"),
                        "quick_ratio": fi.get("quick_ratio"),
                        "debt_to_assets": fi.get("debt_to_assets"),
                        "debt_to_equity": fi.get("debt_to_eqt"),
                        "revenue_growth_yoy": fi.get("or_yoy"),
                        "profit_growth_yoy": fi.get("netprofit_yoy"),
                    }
                )

            fundamentals["financial_data"] = financial_data

            # 检查是否成功获取任何数据
            has_data = any(
                [
                    fundamentals.get("balance_sheet"),
                    fundamentals.get("income_statement"),
                    fundamentals.get("cash_flow"),
                    fundamentals.get("fina_indicator"),
                ]
            )

            if not has_data:
                logger.warning(f"⚠️ 未获取到{symbol}的任何财务数据")
            else:
                logger.info(f"✅ 成功获取{symbol}财务数据")

            return fundamentals

        except Exception as e:
            logger.error(f"❌ 获取{symbol}财务数据失败: {e}")
            raise

    # ==================== 报告生成函数 ====================

    def get_stock_data_report(self, symbol: str, start_date: str, end_date: str) -> str:
        """生成股票数据分析报告"""
        try:
            # 获取股票信息和日线数据
            info = self.get_stock_info(symbol)
            data = self.get_stock_daily(symbol, start_date, end_date)

            ts_code = info.get("ts_code", symbol)
            name = info.get("name", symbol)

            # 计算统计数据
            latest_data = data.iloc[-1]
            current_price = f"¥{latest_data['close']:.2f}"

            # 计算涨跌幅
            change_pct_str = "N/A"
            if len(data) > 1:
                prev_close = data.iloc[-2]["close"]
                change_pct = (latest_data["close"] - prev_close) / prev_close * 100
                change_pct_str = f"{change_pct:+.2f}%"

            volume = latest_data.get("volume", 0)
            volume_str = (
                f"{volume / 10000:.1f}万手" if volume > 10000 else f"{volume:.0f}手"
            )

            # 生成报告
            report = f"# {name}（{ts_code}）股票数据分析\n\n"
            report += f"## 📊 实时行情\n"
            report += f"- 股票代码: {ts_code}\n"
            report += f"- 股票名称: {name}\n"
            report += f"- 当前价格: {current_price}\n"
            report += f"- 涨跌幅: {change_pct_str}\n"
            report += f"- 成交量: {volume_str}\n"
            report += f"- 数据来源: Tushare\n\n"

            report += f"## 📈 历史数据概览\n"
            report += f"- 数据期间: {start_date} 至 {end_date}\n"
            report += f"- 数据条数: {len(data)}条\n"
            report += f"- 期间最高: ¥{data['high'].max():.2f}\n"
            report += f"- 期间最低: ¥{data['low'].min():.2f}\n\n"

            report += "## 📋 最新交易数据 (最近5天)\n"
            display_columns = [
                c
                for c in ["date", "open", "high", "low", "close", "volume"]
                if c in data.columns
            ]
            report += data[display_columns].tail(5).to_markdown(index=False)

            return report

        except Exception as e:
            logger.error(f"❌ 生成股票报告失败: {symbol}, 错误: {e}")
            return f"❌ 无法生成 {symbol} 的股票报告: {e}"


# ==================== 便捷函数 ====================

_global_service = None


def get_tushare_service() -> TushareService:
    """获取Tushare服务单例"""
    global _global_service
    if _global_service is None:
        _global_service = TushareService()
    return _global_service


def get_china_stock_data_tushare(
    symbol: str, start_date: str = None, end_date: str = None
) -> pd.DataFrame:
    """获取中国股票数据（便捷函数）"""
    service = get_tushare_service()
    return service.get_stock_daily(symbol, start_date, end_date)


def get_china_stock_info_tushare(symbol: str) -> Dict[str, Any]:
    """获取中国股票信息（便捷函数）"""
    service = get_tushare_service()
    return service.get_stock_info(symbol)
