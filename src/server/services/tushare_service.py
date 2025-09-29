# app/api/tushare_service.py
import pandas as pd
import tushare as ts
from typing import Dict, Optional
from datetime import datetime, timedelta

# 假设自定义异常在 app/utils/exception.py 中
# 如果不在，请确保从正确的位置导入
try:
    from ..utils import DataNotFoundError
except (ImportError, ModuleNotFoundError):
    # Fallback for local testing or different structure
    class DataNotFoundError(Exception):
        """当API调用成功但未返回任何数据时引发的自定义异常。"""

        pass


# 注意：这里的导入路径可能需要根据你的项目结构调整
from ...config.settings import get_settings
from ..utils.stockUtils import StockUtils


class TushareService:
    """
    封装Tushare API的数据服务。
    所有方法在失败时都会抛出异常。
    """

    def __init__(self):
        settings = get_settings()
        if not settings.TUSHARE_TOKEN:
            raise ValueError("TUSHARE_TOKEN 未在环境变量或 .env 文件中设置")

        try:
            ts.set_token(settings.TUSHARE_TOKEN)
            self.pro = ts.pro_api()
            # Test connection
            self.pro.query("trade_cal", start_date="20240101", end_date="20240101")
            print("✅ Tushare API 连接成功")
        except Exception as e:
            print(f"❌ Tushare API 连接失败: {e}")
            self.pro = None
            # 初始化失败时直接抛出错误
            raise ConnectionError(f"Tushare API 连接失败: {e}") from e

    def _standardize_data(self, data: pd.DataFrame) -> pd.DataFrame:
        if data.empty:
            return data
        try:
            standardized = data.copy()
            column_mapping = {
                "trade_date": "date",
                "ts_code": "code",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "vol": "volume",
                "amount": "amount",
                "pct_chg": "pct_change",
                "change": "change",
            }
            standardized = standardized.rename(columns=column_mapping)
            if "date" in standardized.columns:
                standardized["date"] = pd.to_datetime(standardized["date"])
                standardized = standardized.sort_values("date", ascending=True)
            if "code" in standardized.columns:
                standardized["股票代码"] = standardized["code"].str.replace(
                    r"\.SH|\.SZ|\.BJ", "", regex=True
                )
            if "pct_change" in standardized.columns:
                standardized["涨跌幅"] = standardized["pct_change"]
            return standardized
        except Exception as e:
            print(f"⚠️ 数据标准化失败: {e}")
            return data

    def _standardize_hk_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """标准化港股数据格式"""
        if data.empty:
            return data
        try:
            standardized = data.copy()
            # 港股数据列映射
            column_mapping = {
                "trade_date": "date",
                "ts_code": "code",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "vol": "volume",
                "amount": "amount",
                "pct_chg": "pct_change",
                "change": "change",
                "pre_close": "pre_close",
            }
            standardized = standardized.rename(columns=column_mapping)

            if "date" in standardized.columns:
                standardized["date"] = pd.to_datetime(standardized["date"])
                standardized = standardized.sort_values("date", ascending=True)
            if "code" in standardized.columns:
                standardized["股票代码"] = standardized["code"].str.replace(
                    r"\.HK", "", regex=True
                )
            if "pct_change" in standardized.columns:
                standardized["涨跌幅"] = standardized["pct_change"]

            # 添加数据源标识
            standardized["source"] = "tushare_hk"

            return standardized
        except Exception as e:
            print(f"⚠️ 港股数据标准化失败: {e}")
            return data

    def get_stock_daily(
        self, symbol: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取日线行情。如果无数据或API出错则抛出异常。"""
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            ts_code = symbol  # 直接使用已经标准化的代码
            df = self.pro.daily(
                ts_code=ts_code,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
            )
            if df is None or df.empty:
                raise DataNotFoundError(
                    f"未找到 {ts_code} 在 {start_date} 到 {end_date} 期间的日线数据。"
                )

            df = self._standardize_data(df)
            print(f"✅ 获取并标准化 {ts_code} 数据成功: {len(df)} 条")
            return df
        except Exception as e:
            print(f"❌ 获取 {ts_code} 日线数据时发生错误: {e}")
            # 重新抛出，让上层处理
            raise

    def get_hk_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取港股日线行情数据

        Args:
            symbol: 港股代码 (如: 00700.HK 或 700)
            start_date: 开始日期 (格式: YYYY-MM-DD)
            end_date: 结束日期 (格式: YYYY-MM-DD)

        Returns:
            pd.DataFrame: 港股日线数据
        """
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            ts_code = symbol  # 直接使用已经标准化的代码
            df = self.pro.hk_daily(
                ts_code=ts_code,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
            )
            if df is None or df.empty:
                raise DataNotFoundError(
                    f"未找到 {ts_code} 在 {start_date} 到 {end_date} 期间的港股日线数据。"
                )

            df = self._standardize_hk_data(df)
            print(f"✅ 获取并标准化港股 {ts_code} 数据成功: {len(df)} 条")
            return df
        except Exception as e:
            print(f"❌ 获取港股 {ts_code} 日线数据时发生错误: {e}")
            raise

    def get_hk_rt_daily(self, symbol: str) -> pd.DataFrame:
        """
        获取港股实时日K线数据

        Args:
            symbol: 港股代码 (如: 00700.HK 或 700)

        Returns:
            pd.DataFrame: 港股实时日K线数据
        """
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            ts_code = symbol  # 直接使用已经标准化的代码
            df = self.pro.rt_hk_k(ts_code=ts_code)
            if df is None or df.empty:
                raise DataNotFoundError(f"未找到 {ts_code} 的港股实时日K线数据。")

            print(f"✅ 获取港股实时日K线 {ts_code} 数据成功: {len(df)} 条")
            return df
        except Exception as e:
            print(f"❌ 获取港股实时日K线 {ts_code} 数据时发生错误: {e}")
            raise

    def get_hk_mins(
        self,
        symbol: str,
        freq: str = "1min",
        start_date: str = None,
        end_date: str = None,
    ) -> pd.DataFrame:
        """
        获取港股分钟行情数据

        Args:
            symbol: 港股代码 (如: 00700.HK 或 700)
            freq: 分钟频度 (1min/5min/15min/30min/60min)
            start_date: 开始时间 (格式: YYYY-MM-DD HH:MM:SS)
            end_date: 结束时间 (格式: YYYY-MM-DD HH:MM:SS)

        Returns:
            pd.DataFrame: 港股分钟数据
        """
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            ts_code = symbol  # 直接使用已经标准化的代码
            params = {"ts_code": ts_code, "freq": freq}
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            df = self.pro.hk_mins(**params)
            if df is None or df.empty:
                raise DataNotFoundError(f"未找到 {ts_code} 的港股分钟数据。")

            print(f"✅ 获取港股分钟数据 {ts_code} ({freq}) 成功: {len(df)} 条")
            return df
        except Exception as e:
            print(f"❌ 获取港股分钟数据 {ts_code} 时发生错误: {e}")
            raise

    def get_hk_income(
        self,
        symbol: str,
        period: str = None,
        ind_name: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> pd.DataFrame:
        """
        获取港股利润表数据

        Args:
            symbol: 港股代码 (如: 00700.HK 或 700)
            period: 报告期 (格式: YYYYMMDD)
            ind_name: 指标名 (如: 营业额)
            start_date: 报告期开始日期 (格式: YYYYMMDD)
            end_date: 报告期结束日期 (格式: YYYYMMDD)

        Returns:
            pd.DataFrame: 港股利润表数据
        """
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            ts_code = symbol  # 直接使用已经标准化的代码
            params = {"ts_code": ts_code}
            if period:
                params["period"] = period
            if ind_name:
                params["ind_name"] = ind_name
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            df = self.pro.hk_income(**params)
            if df is None or df.empty:
                raise DataNotFoundError(f"未找到 {ts_code} 的港股利润表数据。")

            print(f"✅ 获取港股利润表 {ts_code} 数据成功: {len(df)} 条")
            return df
        except Exception as e:
            print(f"❌ 获取港股利润表 {ts_code} 数据时发生错误: {e}")
            raise

    def get_hk_balancesheet(
        self,
        symbol: str,
        period: str = None,
        ind_name: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> pd.DataFrame:
        """
        获取港股资产负债表数据

        Args:
            symbol: 港股代码 (如: 00700.HK 或 700)
            period: 报告期 (格式: YYYYMMDD)
            ind_name: 指标名 (如: 应收帐款)
            start_date: 报告期开始日期 (格式: YYYYMMDD)
            end_date: 报告期结束日期 (格式: YYYYMMDD)

        Returns:
            pd.DataFrame: 港股资产负债表数据
        """
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            ts_code = symbol  # 直接使用已经标准化的代码
            params = {"ts_code": ts_code}
            if period:
                params["period"] = period
            if ind_name:
                params["ind_name"] = ind_name
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            df = self.pro.hk_balancesheet(**params)
            if df is None or df.empty:
                raise DataNotFoundError(f"未找到 {ts_code} 的港股资产负债表数据。")

            print(f"✅ 获取港股资产负债表 {ts_code} 数据成功: {len(df)} 条")
            return df
        except Exception as e:
            print(f"❌ 获取港股资产负债表 {ts_code} 数据时发生错误: {e}")
            raise

    def get_hk_cashflow(
        self,
        symbol: str,
        period: str = None,
        ind_name: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> pd.DataFrame:
        """
        获取港股现金流量表数据

        Args:
            symbol: 港股代码 (如: 00700.HK 或 700)
            period: 报告期 (格式: YYYYMMDD)
            ind_name: 指标名 (如: 新增贷款)
            start_date: 报告期开始日期 (格式: YYYYMMDD)
            end_date: 报告期结束日期 (格式: YYYYMMDD)

        Returns:
            pd.DataFrame: 港股现金流量表数据
        """
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            ts_code = symbol  # 直接使用已经标准化的代码
            params = {"ts_code": ts_code}
            if period:
                params["period"] = period
            if ind_name:
                params["ind_name"] = ind_name
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            df = self.pro.hk_cashflow(**params)
            if df is None or df.empty:
                raise DataNotFoundError(f"未找到 {ts_code} 的港股现金流量表数据。")

            print(f"✅ 获取港股现金流量表 {ts_code} 数据成功: {len(df)} 条")
            return df
        except Exception as e:
            print(f"❌ 获取港股现金流量表 {ts_code} 数据时发生错误: {e}")
            raise

    def get_hk_fina_indicator(
        self,
        symbol: str,
        period: str = None,
        report_type: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> pd.DataFrame:
        """
        获取港股财务指标数据

        Args:
            symbol: 港股代码 (如: 00700.HK 或 700)
            period: 报告期 (格式: YYYYMMDD)
            report_type: 报告类型 (Q1/Q2/Q3/Q4)
            start_date: 报告期开始日期 (格式: YYYYMMDD)
            end_date: 报告期结束日期 (格式: YYYYMMDD)

        Returns:
            pd.DataFrame: 港股财务指标数据
        """
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            ts_code = symbol  # 直接使用已经标准化的代码
            params = {"ts_code": ts_code}
            if period:
                params["period"] = period
            if report_type:
                params["report_type"] = report_type
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            df = self.pro.hk_fina_indicator(**params)
            if df is None or df.empty:
                raise DataNotFoundError(f"未找到 {ts_code} 的港股财务指标数据。")

            print(f"✅ 获取港股财务指标 {ts_code} 数据成功: {len(df)} 条")
            return df
        except Exception as e:
            print(f"❌ 获取港股财务指标 {ts_code} 数据时发生错误: {e}")
            raise

    def get_hk_fundamentals(self, symbol: str, period: str = None) -> Dict:
        """
        获取港股核心财务数据（降级处理：使用复权行情数据）

        Args:
            symbol: 港股代码 (如: 00700.HK 或 700)
            period: 报告期 (格式: YYYYMMDD，当前版本暂未使用)

        Returns:
            Dict: 包含基础市值、股本等数据的港股信息
        """
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            ts_code = symbol  # 直接使用已经标准化的代码
            print(f"⚠️ 港股财务报表API不可用，使用复权行情数据降级处理: {ts_code}")

            # 使用复权行情数据作为基本面数据的替代
            basic_data = self.get_hk_basic_fundamentals(symbol)

            if not basic_data:
                raise DataNotFoundError(f"未找到 {ts_code} 的任何港股基础数据")

            # 将复权行情数据转换为基本面数据格式
            return {
                "security_profile": {
                    "证券代码": ts_code,
                    "证券简称": basic_data.get("name", f"港股{symbol}"),
                    "上市日期": basic_data.get("list_date", ""),
                },
                "company_profile": {
                    "公司名称": basic_data.get("name", f"港股{symbol}"),
                    "所属行业": basic_data.get("industry", ""),
                },
                "market_data": {
                    "latest_price": basic_data.get("latest_price", 0),
                    "total_market_cap": basic_data.get("total_market_cap", 0),
                    "free_market_cap": basic_data.get("free_market_cap", 0),
                    "total_shares": basic_data.get("total_shares", 0),
                    "free_shares": basic_data.get("free_shares", 0),
                    "turnover_ratio": basic_data.get("turnover_ratio", 0),
                    "pct_change": basic_data.get("pct_change", 0),
                    "volume": basic_data.get("volume", 0),
                    "amount": basic_data.get("amount", 0),
                },
                # 财务报表数据为空（API不可用）
                "income_statement": [],
                "balance_sheet": [],
                "cash_flow": [],
            }

        except Exception as e:
            print(f"❌ 获取港股 {ts_code} 财务数据时发生错误: {e}")
            raise

    def get_hk_stock_data_report(
        self, symbol: str, start_date: str, end_date: str
    ) -> str:
        """
        生成港股价格行情分析报告

        Args:
            symbol: 港股代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            str: 港股分析报告
        """
        # 获取港股基本信息和日线数据
        data = self.get_hk_daily(symbol, start_date, end_date)

        ts_code = symbol  # 直接使用已经标准化的代码
        # 获取最新数据
        latest_data = data.iloc[-1]
        current_price = f"HK${latest_data['close']:.2f}"

        change_pct_str = "N/A"
        if len(data) > 1:
            change_pct = latest_data.get("pct_change", 0)
            change_pct_str = f"{change_pct:+.2f}%"

        volume = latest_data.get("volume", 0)
        volume_str = (
            f"{volume / 10000:.1f}万股" if volume > 10000 else f"{volume:.0f}股"
        )

        report = f"# {ts_code} 港股数据分析\n\n"
        report += f"## 📊 实时行情\n- 股票代码: {ts_code}\n- 当前价格: {current_price}\n- 涨跌幅: {change_pct_str}\n- 成交量: {volume_str}\n- 数据来源: Tushare港股\n\n"
        report += f"## 📈 历史数据概览\n- 数据期间: {start_date} 至 {end_date}\n- 数据条数: {len(data)}条\n- 期间最高: HK${data['high'].max():.2f}\n- 期间最低: HK${data['low'].min():.2f}\n\n"
        report += "## 📋 最新交易数据 (最近5天)\n"

        display_columns = ["date", "open", "high", "low", "close", "volume", "涨跌幅"]
        existing_columns = [col for col in display_columns if col in data.columns]
        report += data[existing_columns].tail(5).to_markdown(index=False)

        return report

    def get_stock_info(self, symbol: str) -> Dict:
        """获取股票基本信息。如果无数据或API出错则抛出异常。"""
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            ts_code = symbol  # 直接使用已经标准化的代码
            df = self.pro.stock_basic(
                ts_code=ts_code, fields="ts_code,symbol,name,area,industry,market"
            )
            if df is None or df.empty:
                raise DataNotFoundError(f"未找到代码为 {ts_code} 的股票基本信息。")

            return df.iloc[0].to_dict()
        except Exception as e:
            print(f"❌ 获取 {ts_code} 基本信息时发生错误: {e}")
            raise

    def get_china_fundamentals(self, symbol: str, period: str = None) -> Dict:
        """获取A股核心财务数据。如果无数据或API出错则抛出异常。"""
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        if not period:
            period = "20241231"  # 默认最新年报

        try:
            ts_code = symbol  # 直接使用已经标准化的代码
            balance_sheet = self.pro.balancesheet(
                ts_code=ts_code,
                period=period,
                fields="total_assets,total_liab,total_hldr_eqy_exc_min_int",
            )
            income = self.pro.income(
                ts_code=ts_code,
                period=period,
                fields="total_revenue,revenue,n_income,operate_profit",
            )
            cashflow = self.pro.cashflow(
                ts_code=ts_code, period=period, fields="n_cashflow_act"
            )

            if balance_sheet.empty and income.empty and cashflow.empty:
                raise DataNotFoundError(
                    f"未找到 {ts_code} 在报告期 {period} 的任何财务报表数据。"
                )

            return {
                "balance_sheet": (
                    balance_sheet.to_dict("records") if not balance_sheet.empty else []
                ),
                "income_statement": (
                    income.to_dict("records") if not income.empty else []
                ),
                "cash_flow": (
                    cashflow.to_dict("records") if not cashflow.empty else []
                ),
            }
        except Exception as e:
            print(f"❌ 获取 {ts_code} 财务数据时发生错误: {e}")
            raise

    def get_income_statement(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取利润表数据，按公告日期/报告期倒序返回最近记录"""
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            df = self.pro.income(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=(
                    "ts_code,ann_date,end_date,total_revenue,revenue,"
                    "n_income,operate_profit,basic_eps"
                ),
            )
            if df is None:
                return pd.DataFrame()
            sort_cols = [c for c in ["ann_date", "end_date"] if c in df.columns]
            if sort_cols:
                df = df.sort_values(sort_cols, ascending=False)
            return df
        except Exception as e:
            print(f"❌ 获取 {ts_code} 利润表数据失败: {e}")
            return pd.DataFrame()

    def get_balance_sheet(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取资产负债表数据，按公告日期/报告期倒序返回最近记录"""
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            df = self.pro.balancesheet(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=(
                    "ts_code,ann_date,end_date,total_assets,total_liab,"
                    "total_hldr_eqy_exc_min_int"
                ),
            )
            if df is None:
                return pd.DataFrame()
            sort_cols = [c for c in ["ann_date", "end_date"] if c in df.columns]
            if sort_cols:
                df = df.sort_values(sort_cols, ascending=False)
            return df
        except Exception as e:
            print(f"❌ 获取 {ts_code} 资产负债表数据失败: {e}")
            return pd.DataFrame()

    def get_cash_flow(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取现金流量表数据，按公告日期/报告期倒序返回最近记录"""
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            df = self.pro.cashflow(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=(
                    "ts_code,ann_date,end_date,n_cashflow_act,"
                    "c_cash_equ_end_period,free_cashflow"
                ),
            )
            if df is None:
                return pd.DataFrame()
            sort_cols = [c for c in ["ann_date", "end_date"] if c in df.columns]
            if sort_cols:
                df = df.sort_values(sort_cols, ascending=False)
            return df
        except Exception as e:
            print(f"❌ 获取 {ts_code} 现金流量表数据失败: {e}")
            return pd.DataFrame()

    def get_financial_indicators(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取财务指标数据（fina_indicator），按公告日期/报告期倒序返回最近记录"""
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            df = self.pro.fina_indicator(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=(
                    "ts_code,ann_date,end_date,eps,dt_eps,bps,ocfps,cfps,"
                    "roe,roe_waa,roe_dt,roa,netprofit_margin,current_ratio,quick_ratio,"
                    "assets_to_eqt,ebit,ebitda,fcff,fcfe,working_capital,retained_earnings,"
                    "debt_to_assets,basic_eps_yoy,netprofit_yoy,roe_yoy,tr_yoy,or_yoy"
                ),
            )
            if df is None:
                return pd.DataFrame()
            sort_cols = [c for c in ["ann_date", "end_date"] if c in df.columns]
            if sort_cols:
                df = df.sort_values(sort_cols, ascending=False)
            return df
        except Exception as e:
            print(f"❌ 获取 {ts_code} 财务指标数据失败: {e}")
            return pd.DataFrame()

    def get_performance_express(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取业绩快报（express），用于在年报/季报未披露前的快速指标补充"""
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")
        try:
            df = self.pro.express(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=(
                    "ts_code,ann_date,end_date,revenue,operate_profit,total_profit,"
                    "n_income,total_assets,total_hldr_eqy_exc_min_int,diluted_eps,diluted_roe"
                ),
            )
            if df is None:
                return pd.DataFrame()
            sort_cols = [c for c in ["ann_date", "end_date"] if c in df.columns]
            if sort_cols:
                df = df.sort_values(sort_cols, ascending=False)
            return df
        except Exception as e:
            print(f"❌ 获取 {ts_code} 业绩快报失败: {e}")
            return pd.DataFrame()

    def get_market_data(self, ts_code: str) -> Dict:
        """获取市场数据（市值等），带有交易日回退逻辑"""
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            # 获取基本信息
            basic_info = self.pro.stock_basic(
                ts_code=ts_code, fields="ts_code,name,industry,market,list_date"
            )

            # 优先尝试当日
            today = datetime.now().strftime("%Y%m%d")
            print(f"🔍 获取 {ts_code} 的市场数据，日期: {today}")
            is_today = True  # 默认认为是当天数据
            daily_basic = self.pro.daily_basic(
                ts_code=ts_code,
                trade_date=today,
                fields="ts_code,trade_date,total_mv,circ_mv,pe,pb,pe_ttm,pb_mrq",
            )

            # 若当日无数据（非交易日或未更新），回退近10个自然日内最近一条
            if daily_basic is None or daily_basic.empty:
                is_today = False  # 发生回退，标记为非当天数据
                print(f"📅 当日({today})无数据，回退获取最近10天数据")
                start = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
                recent = self.pro.daily_basic(
                    ts_code=ts_code,
                    start_date=start,
                    end_date=today,
                    fields="ts_code,trade_date,total_mv,circ_mv,pe,pb,pe_ttm,pb_mrq",
                )
                if recent is not None and not recent.empty:
                    daily_basic = recent.sort_values(
                        "trade_date", ascending=False
                    ).head(1)
                    print(
                        f"✅ 获取到最近交易日数据：{daily_basic.iloc[0]['trade_date']}"
                    )

            result = {}
            if basic_info is not None and not basic_info.empty:
                result.update(basic_info.iloc[0].to_dict())
            if daily_basic is not None and not daily_basic.empty:
                daily_data = daily_basic.iloc[0].to_dict()
                result.update(daily_data)
                result["is_today"] = is_today  # 在结果中加入是否为当天数据的标识
                print(
                    f"📊 市场数据: PE={daily_data.get('pe_ttm', 'N/A')}, PB={daily_data.get('pb_mrq', 'N/A')}"
                )

            return result
        except Exception as e:
            print(f"❌ 获取 {ts_code} 市场数据失败: {e}")
            return {}

    # --- 报告生成函数 ---
    # 以下函数现在只负责组合数据，任何数据获取失败都会导致它们抛出异常

    def get_stock_data_report(self, symbol: str, start_date: str, end_date: str) -> str:
        """
        生成价格行情分析报告。
        如果任何依赖的数据获取失败，此函数将抛出异常。
        """
        # 这些调用现在会直接抛出异常，无需try-except
        stock_info = self.get_stock_info(symbol)
        data = self.get_stock_daily(symbol, start_date, end_date)

        # 根据市场确定货币符号
        market_info = StockUtils.get_market_info(symbol)
        currency_symbol = "¥"  # 默认为人民币
        if market_info["is_hk"]:
            currency_symbol = "HK$"
        elif market_info["is_us"]:
            currency_symbol = "$"
        # --- 如果代码能执行到这里，说明所有数据都已成功获取 ---
        stock_name = stock_info.get("name", f"股票{symbol}")
        latest_data = data.iloc[-1]

        change_pct_str = "N/A"
        if len(data) > 1:
            prev_close = data.iloc[-2]["close"]
            if prev_close != 0:
                change_pct = (latest_data["close"] - prev_close) / prev_close * 100
                change_pct_str = f"{change_pct:+.2f}%"

        volume = latest_data.get("volume", 0)
        volume_str = (
            f"{volume / 10000:.1f}万手" if volume > 10000 else f"{volume:.0f}手"
        )

        report = f"# {symbol} 股票数据分析\n\n"
        report += f"## 📊 实时行情\n- 股票名称: {stock_name}\n- 股票代码: {symbol}\n- 当前价格: {currency_symbol}{latest_data['close']:.2f}\n- 涨跌幅: {change_pct_str}\n- 成交量: {volume_str}\n- 数据来源: Tushare\n\n"
        report += f"## 📈 历史数据概览\n- 数据期间: {start_date} 至 {end_date}\n- 数据条数: {len(data)}条\n- 期间最高: {currency_symbol}{data['high'].max():.2f}\n- 期间最低: {currency_symbol}{data['low'].min():.2f}\n\n"
        report += "## 📋 最新交易数据 (最近5天)\n"

        display_columns = ["date", "open", "high", "low", "close", "volume", "涨跌幅"]
        existing_columns = [col for col in display_columns if col in data.columns]
        report += data[existing_columns].tail(5).to_markdown(index=False)

        return report

    def get_unified_fundamentals_report(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        curr_date: Optional[str] = None,
    ) -> str:
        """
        生成统一的股票基本面分析报告。
        如果任何依赖的数据获取失败，此函数将抛出异常。
        """
        print(f"📊 [统一基本面工具] 开始分析股票: {ticker}")
        market_info = StockUtils.get_market_info(ticker)

        now = datetime.now()
        curr_date_str = curr_date or now.strftime("%Y-%m-%d")
        end_date_str = end_date or now.strftime("%Y-%m-%d")
        start_date_str = start_date or (now - timedelta(days=30)).strftime("%Y-%m-%d")

        result_parts = []

        if market_info["is_china"]:
            print(f"🇨🇳 [统一基本面工具] 处理A股数据...")

            # 1. 获取价格行情报告。如果失败，会直接抛出异常。
            price_report = self.get_stock_data_report(
                ticker, start_date_str, end_date_str
            )
            result_parts.append(f"## A股价格数据\n{price_report}")

            # 2. 获取财务基本面数据。如果失败，会直接抛出异常。
            period = curr_date_str.replace("-", "")
            fundamentals_data = self.get_china_fundamentals(ticker, period=period)

            # --- 代码执行到此，说明财务数据也已成功获取 ---
            fundamentals_report = ""
            bs_data = fundamentals_data.get("balance_sheet")
            fundamentals_report += "### 资产负债表\n" + (
                pd.DataFrame(bs_data).to_markdown(index=False) + "\n\n"
                if bs_data
                else "无数据。\n\n"
            )

            is_data = fundamentals_data.get("income_statement")
            fundamentals_report += "### 利润表\n" + (
                pd.DataFrame(is_data).to_markdown(index=False) + "\n\n"
                if is_data
                else "无数据。\n\n"
            )

            cf_data = fundamentals_data.get("cash_flow")
            fundamentals_report += "### 现金流量表\n" + (
                pd.DataFrame(cf_data).to_markdown(index=False) + "\n\n"
                if cf_data
                else "无数据。\n\n"
            )

            result_parts.append(
                f"## A股基本面数据 (报告期: {period})\n{fundamentals_report}"
            )

        elif market_info["is_hk"]:
            print(f"🇭🇰 [统一基本面工具] 处理港股数据...")

            # 1. 获取港股价格行情报告
            try:
                price_report = self.get_hk_stock_data_report(
                    ticker, start_date_str, end_date_str
                )
                result_parts.append(f"## 港股价格数据\n{price_report}")
            except Exception as e:
                result_parts.append(f"## 港股价格数据\n❌ 获取价格数据失败: {e}")

            # 2. 获取港股财务基本面数据
            try:
                period = curr_date_str.replace("-", "")
                fundamentals_data = self.get_hk_fundamentals(ticker, period=period)

                fundamentals_report = ""
                is_data = fundamentals_data.get("income_statement")
                fundamentals_report += "### 利润表\n" + (
                    pd.DataFrame(is_data).to_markdown(index=False) + "\n\n"
                    if is_data
                    else "无数据。\n\n"
                )

                bs_data = fundamentals_data.get("balance_sheet")
                fundamentals_report += "### 资产负债表\n" + (
                    pd.DataFrame(bs_data).to_markdown(index=False) + "\n\n"
                    if bs_data
                    else "无数据。\n\n"
                )

                cf_data = fundamentals_data.get("cash_flow")
                fundamentals_report += "### 现金流量表\n" + (
                    pd.DataFrame(cf_data).to_markdown(index=False) + "\n\n"
                    if cf_data
                    else "无数据。\n\n"
                )

                result_parts.append(
                    f"## 港股基本面数据 (报告期: {period})\n{fundamentals_report}"
                )
            except Exception as e:
                result_parts.append(f"## 港股基本面数据\n❌ 获取基本面数据失败: {e}")

        elif market_info["is_us"]:
            result_parts.append(
                f"## 美股数据\n⚠️ {ticker} ({market_info['market_name']}) 的数据获取功能正在开发中。"
            )
        else:
            result_parts.append(
                f"## 未知市场\n❓ 无法识别股票代码 {ticker} 的市场类型。"
            )

        combined_result = f"""# {ticker} 综合分析报告
**股票类型**: {market_info['market_name']}
**分析日期**: {now.strftime('%Y-%m-%d')}

{chr(10).join(result_parts)}
---
*数据来源: Tushare (A股/港股) / 其他 (待定)*
"""
        print(f"📊 [统一基本面工具] 数据获取完成，总长度: {len(combined_result)}")
        return combined_result

    def get_hk_daily_adj(
        self,
        symbol: str,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> pd.DataFrame:
        """
        获取港股复权行情数据（包含市值、股本、换手率等基本面指标）

        Args:
            symbol: 港股代码 (如: 00700.HK 或 700)
            trade_date: 交易日期 (格式: YYYYMMDD)
            start_date: 开始日期 (格式: YYYYMMDD)
            end_date: 结束日期 (格式: YYYYMMDD)

        Returns:
            pd.DataFrame: 港股复权行情数据，包含基本面指标
        """
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            ts_code = symbol  # 直接使用已经标准化的代码
            params = {}
            if ts_code:
                params["ts_code"] = ts_code
            if trade_date:
                params["trade_date"] = trade_date
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            df = self.pro.hk_daily_adj(**params)
            if df is None or df.empty:
                raise DataNotFoundError(f"未找到 {ts_code} 的港股复权行情数据。")

            print(f"✅ 获取港股复权行情 {ts_code} 数据成功: {len(df)} 条")
            return df
        except Exception as e:
            print(f"❌ 获取港股复权行情 {ts_code} 数据时发生错误: {e}")
            raise

    def get_hk_basic_fundamentals(self, symbol: str) -> Dict:
        """
        获取港股基础基本面数据（使用复权行情接口降级处理）

        由于港股财务报表API不可用，使用hk_daily_adj接口获取市值、股本等指标

        Args:
            symbol: 港股代码 (如: 00700.HK 或 700)

        Returns:
            Dict: 港股基础基本面数据
        """
        if not self.pro:
            raise ConnectionError("Tushare服务未初始化或连接失败。")

        try:
            ts_code = symbol  # 直接使用已经标准化的代码
            # 1. 获取港股基本信息
            basic_info = {}
            try:
                df_basic = self.pro.hk_basic(ts_code=ts_code)
                if df_basic is not None and not df_basic.empty:
                    basic_info = df_basic.iloc[0].to_dict()
                    print(f"✅ 获取港股基本信息成功: {ts_code}")
            except Exception as e:
                print(f"⚠️ 获取港股基本信息失败: {e}")

            # 2. 获取最新的复权行情数据（包含基本面指标）
            market_data = {}
            try:
                # 获取最近5个交易日的数据
                end_date = datetime.now().strftime("%Y%m%d")
                start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")

                df_adj = self.get_hk_daily_adj(
                    symbol, start_date=start_date, end_date=end_date
                )
                if not df_adj.empty:
                    # 使用最新交易日的数据
                    latest_data = df_adj.iloc[0]
                    market_data = {
                        "latest_price": latest_data.get("close", 0),
                        "total_market_cap": latest_data.get("total_mv", 0),
                        "free_market_cap": latest_data.get("free_mv", 0),
                        "total_shares": latest_data.get("total_share", 0),
                        "free_shares": latest_data.get("free_share", 0),
                        "turnover_ratio": latest_data.get("turnover_ratio", 0),
                        "trade_date": latest_data.get("trade_date", ""),
                        "pct_change": latest_data.get("pct_change", 0),
                        "volume": latest_data.get("vol", 0),
                        "amount": latest_data.get("amount", 0),
                    }
                    print(f"✅ 获取港股复权行情数据成功: {ts_code}")
            except Exception as e:
                print(f"⚠️ 获取港股复权行情数据失败: {e}")

            # 3. 尝试获取港股日线数据作为补充
            daily_data = {}
            try:
                end_date = datetime.now().strftime("%Y%m%d")
                start_date = (datetime.now() - timedelta(days=5)).strftime("%Y%m%d")

                df_daily = self.get_hk_daily(
                    symbol, start_date.replace("-", ""), end_date.replace("-", "")
                )
                if not df_daily.empty:
                    latest_daily = df_daily.iloc[0]
                    daily_data = {
                        "pre_close": latest_daily.get("pre_close", 0),
                        "change": latest_daily.get("change", 0),
                    }
                    print(f"✅ 获取港股日线补充数据成功: {ts_code}")
            except Exception as e:
                print(f"⚠️ 获取港股日线补充数据失败: {e}")

            # 4. 合并所有数据
            combined_data = {}
            combined_data.update(basic_info)
            combined_data.update(market_data)
            combined_data.update(daily_data)

            if not combined_data:
                raise DataNotFoundError(f"未能获取到 {ts_code} 的任何港股数据")

            return combined_data

        except Exception as e:
            print(f"❌ 获取港股基础基本面数据失败: {e}")
            raise
