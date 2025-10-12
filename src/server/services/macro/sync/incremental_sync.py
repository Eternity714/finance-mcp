"""
简化的增量数据同步器
基于最新日期的简单增量同步策略
"""

import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging
import time

from .tushare_fetcher import TushareMacroFetcher
from ..storage.manager import StorageManager
from ..storage.base import INDICATOR_TIME_FIELD, INDICATOR_FREQUENCY

logger = logging.getLogger(__name__)


class IncrementalSyncEngine:
    """简化的增量同步引擎"""

    def __init__(self):
        """初始化增量同步引擎"""
        self.fetcher = TushareMacroFetcher()
        self.storage_manager = StorageManager()

        # 每个指标的起始时间配置
        self.start_periods = {
            "gdp": "2000Q1",  # GDP从2000年开始
            "cpi": "200001",  # CPI从2000年开始
            "ppi": "200001",  # PPI从2000年开始
            "pmi": "200501",  # PMI从2005年开始有数据
            "money_supply": "200001",  # 货币供应量从2000年开始
            "social_financing": "200201",  # 社融从2002年开始
            "lpr": "20190820",  # LPR从改革开始
        }

        # 数据发布滞后配置
        self.publish_delays = {
            "gdp": {"type": "quarter", "delay": 1},  # 滞后1个季度
            "cpi": {"type": "month", "delay": 1},  # 滞后1个月
            "ppi": {"type": "month", "delay": 1},  # 滞后1个月
            "pmi": {"type": "month", "delay": 1},  # 滞后1个月
            "money_supply": {"type": "month", "delay": 1},  # 滞后1个月
            "social_financing": {"type": "month", "delay": 1},  # 滞后1个月
            "lpr": {"type": "day", "delay": 0},  # 当天发布
        }

        # 每个指标的最小更新间隔（避免过于频繁的同步）
        self.min_sync_interval = {
            "gdp": timedelta(days=30),  # GDP月更新一次
            "cpi": timedelta(days=7),  # CPI周更新一次
            "ppi": timedelta(days=7),  # PPI周更新一次
            "pmi": timedelta(days=7),  # PMI周更新一次
            "money_supply": timedelta(days=7),  # 货币供应量周更新一次
            "social_financing": timedelta(days=7),  # 社融周更新一次
            "lpr": timedelta(days=1),  # LPR可能随时更新
        }

        logger.info("✅ SimplifiedSyncEngine 初始化成功")

    def sync_indicator(
        self, indicator: str, force_sync: bool = False
    ) -> Dict[str, Any]:
        """
        简化的指标同步逻辑

        Args:
            indicator: 指标名称
            force_sync: 是否强制同步（忽略最小更新间隔）

        Returns:
            Dict: 同步结果
        """
        try:
            logger.info(f"🔄 开始同步 {indicator} 数据...")

            # 检查是否需要同步
            if not force_sync and not self._should_sync(indicator):
                return {
                    "indicator": indicator,
                    "status": "skipped",
                    "reason": "未到最小更新间隔",
                    "synced_count": 0,
                }

            # 获取数据库中最新的时间点
            latest_period = self._get_latest_period_from_db(indicator)

            if latest_period is None:
                # 情况1：数据库为空，全量同步
                start_period = self.start_periods.get(indicator)
                end_period = self._get_current_period(indicator)
                logger.info(f"🔄 {indicator} 全量同步: {start_period} → {end_period}")

            else:
                # 情况2：有数据，增量同步
                start_period = self._get_next_period(latest_period, indicator)
                end_period = self._get_current_period(indicator)

                if self._is_period_greater(start_period, end_period, indicator):
                    logger.info(f"✅ {indicator} 已是最新，无需同步")
                    return {
                        "indicator": indicator,
                        "status": "up_to_date",
                        "reason": "数据已是最新",
                        "synced_count": 0,
                    }

                logger.info(f"🔄 {indicator} 增量同步: {start_period} → {end_period}")

            # 获取并保存数据
            data = self._fetch_data(indicator, start_period, end_period)

            if not data.empty:
                storage = self.storage_manager.get_storage()
                storage.save_data(indicator, data)

                # 更新同步时间戳
                self._update_sync_timestamp(indicator)

                logger.info(f"✅ {indicator} 同步成功: {len(data)} 条记录")
                return {
                    "indicator": indicator,
                    "status": "completed",
                    "synced_count": len(data),
                    "start_period": start_period,
                    "end_period": end_period,
                }
            else:
                logger.warning(f"⚠️ {indicator} 未获取到新数据")
                return {
                    "indicator": indicator,
                    "status": "no_data",
                    "reason": "数据源无新数据",
                    "synced_count": 0,
                }

        except Exception as e:
            logger.error(f"❌ {indicator} 同步失败: {e}")
            return {
                "indicator": indicator,
                "status": "failed",
                "error": str(e),
                "synced_count": 0,
            }

    def _get_latest_period_from_db(self, indicator: str) -> Optional[str]:
        """获取数据库中最新的时间点"""
        try:
            storage = self.storage_manager.get_storage()
            latest_data = storage.get_latest_data(indicator, periods=1)

            if latest_data.empty:
                return None

            # 获取时间字段名
            time_field = INDICATOR_TIME_FIELD.get(indicator)
            if not time_field or time_field not in latest_data.columns:
                logger.error(f"❌ {indicator} 缺少时间字段: {time_field}")
                return None

            # 获取最新的时间点
            latest_period = latest_data[time_field].iloc[0]
            logger.info(f"📊 {indicator} 数据库最新时间点: {latest_period}")
            return str(latest_period)

        except Exception as e:
            logger.error(f"❌ 获取 {indicator} 最新时间点失败: {e}")
            return None

    def _get_current_period(self, indicator: str) -> str:
        """获取考虑发布滞后的当前期间"""
        now = datetime.now()
        delay_config = self.publish_delays.get(indicator, {"type": "month", "delay": 1})

        if delay_config["type"] == "quarter":
            # 季度数据处理
            current_quarter = (now.month - 1) // 3 + 1
            target_quarter = current_quarter - delay_config["delay"]

            if target_quarter <= 0:
                target_quarter += 4
                target_year = now.year - 1
            else:
                target_year = now.year

            return f"{target_year}Q{target_quarter}"

        elif delay_config["type"] == "month":
            # 月度数据处理
            target_month = now.month - delay_config["delay"]

            if target_month <= 0:
                target_month += 12
                target_year = now.year - 1
            else:
                target_year = now.year

            return f"{target_year:04d}{target_month:02d}"

        elif delay_config["type"] == "day":
            # 日度数据处理（主要是LPR）
            target_date = now - timedelta(days=delay_config["delay"])
            return target_date.strftime("%Y%m%d")

        return now.strftime("%Y%m")

    def _get_next_period(self, latest_period: str, indicator: str) -> str:
        """计算下一个期间"""
        frequency = INDICATOR_FREQUENCY.get(indicator, "monthly")

        if frequency == "quarterly":
            # GDP: 2024Q2 → 2024Q3
            year, quarter = self._parse_quarter(latest_period)
            if quarter == 4:
                return f"{year + 1}Q1"
            else:
                return f"{year}Q{quarter + 1}"

        elif frequency == "monthly":
            # CPI: 202409 → 202410
            year, month = self._parse_month(latest_period)
            if month == 12:
                return f"{year + 1:04d}01"
            else:
                return f"{year:04d}{month + 1:02d}"

        elif frequency == "irregular":
            # LPR: 特殊处理，从最新日期开始
            return latest_period

        return latest_period

    def _parse_quarter(self, period: str) -> tuple:
        """解析季度字符串: 2024Q2 → (2024, 2)"""
        try:
            year_str, quarter_str = period.split("Q")
            return int(year_str), int(quarter_str)
        except ValueError:
            logger.error(f"❌ 无法解析季度格式: {period}")
            return datetime.now().year, 1

    def _parse_month(self, period: str) -> tuple:
        """解析月份字符串: 202409 → (2024, 9)"""
        try:
            period_str = str(period)
            if len(period_str) == 6:
                year = int(period_str[:4])
                month = int(period_str[4:6])
                return year, month
            else:
                raise ValueError(f"月份格式错误: {period}")
        except ValueError:
            logger.error(f"❌ 无法解析月份格式: {period}")
            return datetime.now().year, datetime.now().month

    def _is_period_greater(self, period1: str, period2: str, indicator: str) -> bool:
        """比较两个时间段的大小"""
        frequency = INDICATOR_FREQUENCY.get(indicator, "monthly")

        if frequency == "quarterly":
            year1, quarter1 = self._parse_quarter(period1)
            year2, quarter2 = self._parse_quarter(period2)
            return (year1, quarter1) > (year2, quarter2)

        elif frequency == "monthly":
            year1, month1 = self._parse_month(period1)
            year2, month2 = self._parse_month(period2)
            return (year1, month1) > (year2, month2)

        elif frequency == "irregular":
            # 日期比较
            try:
                date1 = datetime.strptime(period1, "%Y%m%d")
                date2 = datetime.strptime(period2, "%Y%m%d")
                return date1 > date2
            except ValueError:
                return period1 > period2

        return period1 > period2

    def _fetch_data(
        self, indicator: str, start_period: str, end_period: str
    ) -> pd.DataFrame:
        """获取指定时间范围的数据"""
        try:
            logger.info(f"🔄 获取 {indicator} 数据: {start_period} → {end_period}")

            # 特殊处理LPR的不定期发布
            if indicator == "lpr":
                return self._fetch_lpr_special(start_period, end_period)

            # 根据指标类型调用对应的获取方法
            if indicator == "gdp":
                return self.fetcher.fetch_gdp(start_q=start_period, end_q=end_period)
            elif indicator == "cpi":
                return self.fetcher.fetch_cpi(start_m=start_period, end_m=end_period)
            elif indicator == "ppi":
                return self.fetcher.fetch_ppi(start_m=start_period, end_m=end_period)
            elif indicator == "pmi":
                return self.fetcher.fetch_pmi(start_m=start_period, end_m=end_period)
            elif indicator == "money_supply":
                return self.fetcher.fetch_money_supply(
                    start_m=start_period, end_m=end_period
                )
            elif indicator == "social_financing":
                return self.fetcher.fetch_social_financing(
                    start_m=start_period, end_m=end_period
                )
            else:
                logger.error(f"❌ 未知指标: {indicator}")
                return pd.DataFrame()

        except Exception as e:
            logger.error(f"❌ 获取 {indicator} 数据失败: {e}")
            return pd.DataFrame()

    def _fetch_lpr_special(self, start_period: str, end_period: str) -> pd.DataFrame:
        """LPR的特殊处理：不定期发布"""
        try:
            # LPR不定期发布，获取最近3个月的数据让Tushare自动过滤
            three_months_ago = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
            current_date = datetime.now().strftime("%Y%m%d")

            logger.info(
                f"🔄 LPR特殊处理: 获取最近3个月数据 "
                f"{three_months_ago} → {current_date}"
            )

            all_data = self.fetcher.fetch_lpr(
                start_date=three_months_ago, end_date=current_date
            )

            if all_data.empty:
                return all_data

            # 过滤掉已经存在的数据（比start_period更新的数据）
            if "date" in all_data.columns:
                # 只保留比start_period更新的数据
                all_data = all_data[all_data["date"] >= start_period]

            return all_data

        except Exception as e:
            logger.error(f"❌ LPR特殊处理失败: {e}")
            return pd.DataFrame()

    def _should_sync(self, indicator: str) -> bool:
        """检查是否应该同步指定指标"""
        # 检查最小更新间隔
        last_sync = self._get_last_sync_timestamp(indicator)
        if last_sync:
            min_interval = self.min_sync_interval.get(indicator, timedelta(days=1))
            if datetime.now() - last_sync < min_interval:
                return False
        return True

    def detect_missing_periods(self, indicator: str) -> List[str]:
        """
        检测指定指标的缺失时间段（保留此方法用于兼容性和健康检查）
        注意：这个方法现在主要用于健康检查，核心同步逻辑已简化
        """
        try:
            latest_period = self._get_latest_period_from_db(indicator)
            current_period = self._get_current_period(indicator)

            if latest_period is None:
                start_period = self.start_periods.get(indicator)
                return [f"需要全量同步从 {start_period} 到 {current_period}"]

            if self._is_period_greater(latest_period, current_period, indicator):
                return []  # 无缺失

            next_period = self._get_next_period(latest_period, indicator)
            return [f"需要增量同步从 {next_period} 到 {current_period}"]

        except Exception as e:
            logger.error(f"❌ 检测 {indicator} 缺失时间段失败: {e}")
            return []

    def _get_last_sync_timestamp(self, indicator: str) -> Optional[datetime]:
        """获取指标的最后同步时间戳"""
        # TODO: 实现同步时间戳的持久化存储
        # 暂时返回None，表示总是需要检查
        return None

    def _update_sync_timestamp(self, indicator: str):
        """更新指标的同步时间戳"""
        # TODO: 实现同步时间戳的持久化存储
        pass

    def sync_all_indicators(self, force_sync: bool = False) -> Dict[str, Any]:
        """
        同步所有指标数据

        Args:
            force_sync: 是否强制同步

        Returns:
            Dict: 同步结果汇总
        """
        indicators = [
            "gdp",
            "cpi",
            "ppi",
            "pmi",
            "money_supply",
            "social_financing",
            "lpr",
        ]

        results = {}
        total_synced = 0

        logger.info(f"🚀 开始同步所有宏观数据指标 ({len(indicators)} 个)...")

        for indicator in indicators:
            try:
                result = self.sync_indicator(indicator, force_sync=force_sync)
                results[indicator] = result
                total_synced += result.get("synced_count", 0)

                # 指标间稍作延迟，避免API限制
                time.sleep(1)

            except Exception as e:
                logger.error(f"❌ 同步 {indicator} 时发生错误: {e}")
                results[indicator] = {
                    "status": "failed",
                    "error": str(e),
                    "synced_count": 0,
                }

        # 汇总结果
        summary = {
            "total_indicators": len(indicators),
            "completed": len(
                [r for r in results.values() if r.get("status") == "completed"]
            ),
            "partial": len(
                [r for r in results.values() if r.get("status") == "partial"]
            ),
            "failed": len([r for r in results.values() if r.get("status") == "failed"]),
            "skipped": len(
                [r for r in results.values() if r.get("status") == "skipped"]
            ),
            "up_to_date": len(
                [r for r in results.values() if r.get("status") == "up_to_date"]
            ),
            "total_synced_records": total_synced,
            "results": results,
        }

        logger.info(f"🎯 全量同步完成: {summary}")
        return summary
