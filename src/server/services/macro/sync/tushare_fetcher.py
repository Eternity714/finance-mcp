"""
Tushare 宏观数据拉取器
负责从 Tushare 获取各种宏观经济数据
"""

import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging
import time

from ....core.connection_registry import get_connection_registry
from ..storage.base import INDICATOR_FREQUENCY

logger = logging.getLogger(__name__)


class TushareMacroFetcher:
    """Tushare 宏观数据拉取器"""

    def __init__(self):
        """初始化 Tushare 拉取器"""
        self.connection_registry = get_connection_registry()

        # 验证 Tushare 连接
        try:
            tushare_api = self.connection_registry.get_tushare()
            if tushare_api:
                logger.info("✅ TushareMacroFetcher 初始化成功")
            else:
                logger.warning("⚠️ Tushare 连接不可用")
        except Exception as e:
            logger.error(f"❌ TushareMacroFetcher 初始化失败: {e}")

    @property
    def pro(self):
        """获取 Tushare API 客户端"""
        return self.connection_registry.get_tushare()

    def fetch_gdp(self, start_q: str = None, end_q: str = None) -> pd.DataFrame:
        """
        获取 GDP 数据

        Args:
            start_q: 开始季度，格式如 "2020Q1"
            end_q: 结束季度，格式如 "2024Q4"

        Returns:
            DataFrame: GDP 数据
        """
        if not self.pro:
            raise ConnectionError("Tushare 连接不可用")

        try:
            logger.info(
                f"🔄 从 Tushare 获取 GDP 数据 ({start_q or '全部'} ~ {end_q or '全部'})"
            )

            df = self.pro.cn_gdp(start_q=start_q, end_q=end_q)

            if df is None or df.empty:
                logger.warning("⚠️ Tushare 返回空 GDP 数据")
                return pd.DataFrame()

            # 数据清洗和标准化
            df = self._standardize_gdp_data(df)

            logger.info(f"✅ 成功获取 GDP 数据: {len(df)} 条记录")
            return df

        except Exception as e:
            logger.error(f"❌ 获取 GDP 数据失败: {e}")
            raise

    def fetch_cpi(self, start_m: str = None, end_m: str = None) -> pd.DataFrame:
        """
        获取 CPI 数据

        Args:
            start_m: 开始月份，格式如 "202001"
            end_m: 结束月份，格式如 "202412"

        Returns:
            DataFrame: CPI 数据
        """
        if not self.pro:
            raise ConnectionError("Tushare 连接不可用")

        try:
            logger.info(
                f"🔄 从 Tushare 获取 CPI 数据 ({start_m or '全部'} ~ {end_m or '全部'})"
            )

            df = self.pro.cn_cpi(start_m=start_m, end_m=end_m)

            if df is None or df.empty:
                logger.warning("⚠️ Tushare 返回空 CPI 数据")
                return pd.DataFrame()

            # 数据清洗和标准化
            df = self._standardize_cpi_data(df)

            logger.info(f"✅ 成功获取 CPI 数据: {len(df)} 条记录")
            return df

        except Exception as e:
            logger.error(f"❌ 获取 CPI 数据失败: {e}")
            raise

    def fetch_ppi(self, start_m: str = None, end_m: str = None) -> pd.DataFrame:
        """
        获取 PPI 数据

        Args:
            start_m: 开始月份，格式如 "202001"
            end_m: 结束月份，格式如 "202412"

        Returns:
            DataFrame: PPI 数据
        """
        if not self.pro:
            raise ConnectionError("Tushare 连接不可用")

        try:
            logger.info(
                f"🔄 从 Tushare 获取 PPI 数据 ({start_m or '全部'} ~ {end_m or '全部'})"
            )

            df = self.pro.cn_ppi(start_m=start_m, end_m=end_m)

            if df is None or df.empty:
                logger.warning("⚠️ Tushare 返回空 PPI 数据")
                return pd.DataFrame()

            # 数据清洗和标准化
            df = self._standardize_ppi_data(df)

            logger.info(f"✅ 成功获取 PPI 数据: {len(df)} 条记录")
            return df

        except Exception as e:
            logger.error(f"❌ 获取 PPI 数据失败: {e}")
            raise

    def fetch_money_supply(
        self, start_m: str = None, end_m: str = None
    ) -> pd.DataFrame:
        """
        获取货币供应量数据

        Args:
            start_m: 开始月份，格式如 "202001"
            end_m: 结束月份，格式如 "202412"

        Returns:
            DataFrame: 货币供应量数据
        """
        if not self.pro:
            raise ConnectionError("Tushare 连接不可用")

        try:
            logger.info(
                f"🔄 从 Tushare 获取货币供应量数据 ({start_m or '全部'} ~ {end_m or '全部'})"
            )

            df = self.pro.cn_m(start_m=start_m, end_m=end_m)

            if df is None or df.empty:
                logger.warning("⚠️ Tushare 返回空货币供应量数据")
                return pd.DataFrame()

            # 数据清洗和标准化
            df = self._standardize_money_supply_data(df)

            logger.info(f"✅ 成功获取货币供应量数据: {len(df)} 条记录")
            return df

        except Exception as e:
            logger.error(f"❌ 获取货币供应量数据失败: {e}")
            raise

    def fetch_social_financing(
        self, start_m: str = None, end_m: str = None
    ) -> pd.DataFrame:
        """
        获取社融数据

        Args:
            start_m: 开始月份，格式如 "202001"
            end_m: 结束月份，格式如 "202412"

        Returns:
            DataFrame: 社融数据
        """
        if not self.pro:
            raise ConnectionError("Tushare 连接不可用")

        try:
            logger.info(
                f"🔄 从 Tushare 获取社融数据 ({start_m or '全部'} ~ {end_m or '全部'})"
            )

            df = self.pro.sf_month(start_m=start_m, end_m=end_m)

            if df is None or df.empty:
                logger.warning("⚠️ Tushare 返回空社融数据")
                return pd.DataFrame()

            # 数据清洗和标准化
            df = self._standardize_social_financing_data(df)

            logger.info(f"✅ 成功获取社融数据: {len(df)} 条记录")
            return df

        except Exception as e:
            logger.error(f"❌ 获取社融数据失败: {e}")
            raise

    def fetch_pmi(self, start_m: str = None, end_m: str = None) -> pd.DataFrame:
        """
        获取 PMI 数据

        Args:
            start_m: 开始月份，格式如 "202001"
            end_m: 结束月份，格式如 "202412"

        Returns:
            DataFrame: PMI 数据
        """
        if not self.pro:
            raise ConnectionError("Tushare 连接不可用")

        try:
            logger.info(
                f"🔄 从 Tushare 获取 PMI 数据 ({start_m or '全部'} ~ {end_m or '全部'})"
            )

            # 指定获取主要字段
            fields = "month,pmi010000,pmi010100,pmi010200,pmi010300,pmi010400,pmi020100,pmi030000"
            df = self.pro.cn_pmi(start_m=start_m, end_m=end_m, fields=fields)

            if df is None or df.empty:
                logger.warning("⚠️ Tushare 返回空 PMI 数据")
                return pd.DataFrame()

            # 数据清洗和标准化
            df = self._standardize_pmi_data(df)

            logger.info(f"✅ 成功获取 PMI 数据: {len(df)} 条记录")
            return df

        except Exception as e:
            logger.error(f"❌ 获取 PMI 数据失败: {e}")
            raise

    def fetch_lpr(self, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        获取 LPR 数据

        Args:
            start_date: 开始日期，格式如 "20200101"
            end_date: 结束日期，格式如 "20241231"

        Returns:
            DataFrame: LPR 数据
        """
        if not self.pro:
            raise ConnectionError("Tushare 连接不可用")

        try:
            logger.info(
                f"🔄 从 Tushare 获取 LPR 数据 ({start_date or '全部'} ~ {end_date or '全部'})"
            )

            df = self.pro.shibor_lpr(start_date=start_date, end_date=end_date)

            if df is None or df.empty:
                logger.warning("⚠️ Tushare 返回空 LPR 数据")
                return pd.DataFrame()

            # 数据清洗和标准化
            df = self._standardize_lpr_data(df)

            logger.info(f"✅ 成功获取 LPR 数据: {len(df)} 条记录")
            return df

        except Exception as e:
            logger.error(f"❌ 获取 LPR 数据失败: {e}")
            raise

    # ==================== 数据标准化方法 ====================

    def _standardize_gdp_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化 GDP 数据"""
        try:
            # 按季度排序
            df = df.sort_values("quarter", ascending=True).reset_index(drop=True)

            # 确保数值字段为 float 类型
            numeric_columns = [
                "gdp",
                "gdp_yoy",
                "pi",
                "pi_yoy",
                "si",
                "si_yoy",
                "ti",
                "ti_yoy",
            ]
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            return df

        except Exception as e:
            logger.error(f"❌ GDP 数据标准化失败: {e}")
            return df

    def _standardize_cpi_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化 CPI 数据"""
        try:
            # 按月份排序
            df = df.sort_values("month", ascending=True).reset_index(drop=True)

            # 添加时间字段
            df["time"] = pd.to_datetime(df["month"], format="%Y%m")

            # 确保数值字段为 float 类型
            numeric_columns = [
                "nt_val",
                "nt_yoy",
                "nt_mom",
                "nt_accu",
                "town_val",
                "town_yoy",
                "town_mom",
                "town_accu",
                "cnt_val",
                "cnt_yoy",
                "cnt_mom",
                "cnt_accu",
            ]
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            return df

        except Exception as e:
            logger.error(f"❌ CPI 数据标准化失败: {e}")
            return df

    def _standardize_ppi_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化 PPI 数据"""
        try:
            # 按月份排序
            df = df.sort_values("month", ascending=True).reset_index(drop=True)

            # 添加时间字段
            df["time"] = pd.to_datetime(df["month"], format="%Y%m")

            # 确保数值字段为 float 类型 - PPI 有很多字段，动态处理
            for col in df.columns:
                if col not in ["month", "time"] and df[col].dtype == "object":
                    try:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                    except:
                        pass

            return df

        except Exception as e:
            logger.error(f"❌ PPI 数据标准化失败: {e}")
            return df

    def _standardize_money_supply_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化货币供应量数据"""
        try:
            # 按月份排序
            df = df.sort_values("month", ascending=True).reset_index(drop=True)

            # 添加时间字段
            df["time"] = pd.to_datetime(df["month"], format="%Y%m")

            # 确保数值字段为 float 类型
            numeric_columns = [
                "m0",
                "m0_yoy",
                "m0_mom",
                "m1",
                "m1_yoy",
                "m1_mom",
                "m2",
                "m2_yoy",
                "m2_mom",
            ]
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            return df

        except Exception as e:
            logger.error(f"❌ 货币供应量数据标准化失败: {e}")
            return df

    def _standardize_social_financing_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化社融数据"""
        try:
            # 按月份排序
            df = df.sort_values("month", ascending=True).reset_index(drop=True)

            # 添加时间字段
            df["time"] = pd.to_datetime(df["month"], format="%Y%m")

            # 确保数值字段为 float 类型
            numeric_columns = ["inc_month", "inc_cumval", "stk_endval"]
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            return df

        except Exception as e:
            logger.error(f"❌ 社融数据标准化失败: {e}")
            return df

    def _standardize_pmi_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化 PMI 数据"""
        try:
            # 按月份排序
            df = df.sort_values("month", ascending=True).reset_index(drop=True)

            # 添加时间字段
            df["time"] = pd.to_datetime(df["month"], format="%Y%m")

            # 确保数值字段为 float 类型
            numeric_columns = [
                "pmi010000",
                "pmi010100",
                "pmi010200",
                "pmi010300",
                "pmi010400",
                "pmi020100",
                "pmi030000",
            ]
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            return df

        except Exception as e:
            logger.error(f"❌ PMI 数据标准化失败: {e}")
            return df

    def _standardize_lpr_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化 LPR 数据"""
        try:
            # 按日期排序
            df = df.sort_values("date", ascending=True).reset_index(drop=True)

            # 添加时间字段
            df["time"] = pd.to_datetime(df["date"], format="%Y%m%d")

            # 确保数值字段为 float 类型
            numeric_columns = ["1y", "5y"]
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            return df

        except Exception as e:
            logger.error(f"❌ LPR 数据标准化失败: {e}")
            return df

    def test_connection(self) -> bool:
        """测试 Tushare 连接"""
        try:
            if not self.pro:
                return False

            # 简单的测试查询
            test_df = self.pro.cn_gdp(start_q="2024Q1", end_q="2024Q2")
            return test_df is not None

        except Exception as e:
            logger.error(f"❌ Tushare 连接测试失败: {e}")
            return False
