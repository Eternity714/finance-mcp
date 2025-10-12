"""
宏观数据服务 - 集成缓存和同步功能
"""

import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging

from .storage import get_macro_storage, INDICATOR_TIME_FIELD, INDICATOR_FREQUENCY
from .cache import MacroDataCache
from .sync.scheduler import MacroDataSyncScheduler
from .sync.incremental_sync import IncrementalSyncEngine
from ...core.connection_registry import get_connection_registry

logger = logging.getLogger(__name__)


class MacroDataService:
    """宏观数据服务 - 集成缓存和同步功能"""

    def __init__(self, enable_cache: bool = True, enable_scheduler: bool = True):
        """
        初始化宏观数据服务

        Args:
            enable_cache: 是否启用缓存
            enable_scheduler: 是否启用同步调度器
        """
        self.storage = get_macro_storage()
        self.connection_registry = get_connection_registry()

        # 初始化缓存
        self.cache = MacroDataCache() if enable_cache else None
        self.cache_enabled = enable_cache and self.cache is not None

        # 初始化同步引擎和调度器
        self.sync_engine = IncrementalSyncEngine()
        self.scheduler = MacroDataSyncScheduler() if enable_scheduler else None

        # 设置同步回调
        if self.scheduler:
            self.scheduler.set_callbacks(
                on_sync_complete=self._on_sync_complete,
                on_sync_error=self._on_sync_error,
            )

        logger.info(
            f"✅ MacroDataService 初始化完成 "
            f"(缓存: {'开启' if self.cache_enabled else '关闭'}, "
            f"调度器: {'开启' if self.scheduler else '关闭'})"
        )

    def _on_sync_complete(self, result: Dict[str, Any]):
        """同步完成回调 - 清除相关缓存"""
        if not self.cache_enabled:
            return

        try:
            # 根据同步结果清除相应的缓存
            if "indicator" in result:
                indicator = result["indicator"]
                if indicator != "all":
                    self.cache.invalidate_indicator(indicator)
                    logger.info(f"🗑️ 已清除 {indicator} 相关缓存")
                else:
                    self.cache.invalidate_all()
                    logger.info("🗑️ 已清除所有宏观数据缓存")

            # 清除同步状态缓存
            if hasattr(self.cache, "redis_client") and self.cache.redis_client:
                sync_status_key = self.cache._make_key("sync_status")
                self.cache.redis_client.delete(sync_status_key)

        except Exception as e:
            logger.error(f"❌ 清除同步完成缓存失败: {e}")

    def _on_sync_error(self, error: Exception):
        """同步错误回调"""
        logger.error(f"❌ 数据同步发生错误: {error}")

    # ==================== 缓存优化的数据获取方法 ====================

    def get_gdp(
        self,
        periods: int = None,
        start_quarter: str = None,
        end_quarter: str = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        获取GDP数据 (支持缓存)

        Args:
            periods: 获取最近N个季度数据
            start_quarter: 开始季度 (如: "2022Q1")
            end_quarter: 结束季度 (如: "2024Q2")
            use_cache: 是否使用缓存

        Returns:
            GDP数据DataFrame
        """
        return self._get_indicator_data(
            "gdp", periods, start_quarter, end_quarter, use_cache
        )

    def get_cpi(
        self,
        periods: int = None,
        start_month: str = None,
        end_month: str = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        获取CPI数据 (支持缓存)

        Args:
            periods: 获取最近N个月数据
            start_month: 开始月份 (如: "202201")
            end_month: 结束月份 (如: "202412")
            use_cache: 是否使用缓存

        Returns:
            CPI数据DataFrame
        """
        return self._get_indicator_data(
            "cpi", periods, start_month, end_month, use_cache
        )

    def get_ppi(
        self,
        periods: int = None,
        start_month: str = None,
        end_month: str = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        获取PPI数据 (支持缓存)

        Args:
            periods: 获取最近N个月数据
            start_month: 开始月份 (如: "202201")
            end_month: 结束月份 (如: "202412")
            use_cache: 是否使用缓存

        Returns:
            PPI数据DataFrame
        """
        return self._get_indicator_data(
            "ppi", periods, start_month, end_month, use_cache
        )

    def get_pmi(
        self,
        periods: int = None,
        start_month: str = None,
        end_month: str = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        获取PMI数据 (支持缓存)

        Args:
            periods: 获取最近N个月数据
            start_month: 开始月份 (如: "202201")
            end_month: 结束月份 (如: "202412")
            use_cache: 是否使用缓存

        Returns:
            PMI数据DataFrame
        """
        return self._get_indicator_data(
            "pmi", periods, start_month, end_month, use_cache
        )

    def get_money_supply(
        self,
        periods: int = None,
        start_month: str = None,
        end_month: str = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        获取货币供应量数据 (支持缓存)

        Args:
            periods: 获取最近N个月数据
            start_month: 开始月份 (如: "202201")
            end_month: 结束月份 (如: "202412")
            use_cache: 是否使用缓存

        Returns:
            货币供应量数据DataFrame
        """
        return self._get_indicator_data(
            "money_supply", periods, start_month, end_month, use_cache
        )

    def get_social_financing(
        self,
        periods: int = None,
        start_month: str = None,
        end_month: str = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        获取社会融资数据 (支持缓存)

        Args:
            periods: 获取最近N个月数据
            start_month: 开始月份 (如: "202201")
            end_month: 结束月份 (如: "202412")
            use_cache: 是否使用缓存

        Returns:
            社会融资数据DataFrame
        """
        return self._get_indicator_data(
            "social_financing", periods, start_month, end_month, use_cache
        )

    def get_lpr(
        self,
        periods: int = None,
        start_date: str = None,
        end_date: str = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        获取LPR数据 (支持缓存)

        Args:
            periods: 获取最近N次数据
            start_date: 开始日期 (如: "20220101")
            end_date: 结束日期 (如: "20241231")
            use_cache: 是否使用缓存

        Returns:
            LPR数据DataFrame
        """
        return self._get_indicator_data("lpr", periods, start_date, end_date, use_cache)

    def _get_indicator_data(
        self,
        indicator: str,
        periods: int = None,
        start_time: str = None,
        end_time: str = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        通用指标数据获取方法 (支持缓存)

        Args:
            indicator: 指标名称
            periods: 期数
            start_time: 开始时间
            end_time: 结束时间
            use_cache: 是否使用缓存

        Returns:
            指标数据DataFrame
        """
        try:
            # 优先从缓存获取
            if use_cache and self.cache_enabled:
                if periods and not start_time and not end_time:
                    # 最新N期数据
                    cached_data = self.cache.get_latest_data(indicator, periods)
                    if cached_data is not None and not cached_data.empty:
                        logger.debug(f"🎯 缓存命中: {indicator} 最新{periods}期")
                        return cached_data

                elif start_time and end_time:
                    # 范围数据
                    cached_data = self.cache.get_range_data(
                        indicator, start_time, end_time
                    )
                    if cached_data is not None and not cached_data.empty:
                        logger.debug(
                            f"🎯 缓存命中: {indicator} {start_time}~{end_time}"
                        )
                        return cached_data

            # 从存储获取数据
            if periods:
                data = self.storage.get_latest_data(indicator, periods)
            else:
                data = self.storage.get_data(indicator, start_time, end_time)

            # 保存到缓存
            if use_cache and self.cache_enabled and not data.empty:
                if periods and not start_time and not end_time:
                    self.cache.set_latest_data(indicator, periods, data)
                elif start_time and end_time:
                    self.cache.set_range_data(indicator, start_time, end_time, data)

            return data

        except Exception as e:
            logger.error(f"❌ 获取{indicator}数据失败: {e}")
            return pd.DataFrame()

    # ==================== 同步管理功能 ====================

    def start_sync_scheduler(self):
        """启动同步调度器"""
        if self.scheduler:
            self.scheduler.start()
            logger.info("🚀 同步调度器已启动")
        else:
            logger.warning("⚠️ 同步调度器未初始化")

    def stop_sync_scheduler(self):
        """停止同步调度器"""
        if self.scheduler:
            self.scheduler.stop()
            logger.info("🛑 同步调度器已停止")

    def manual_sync(
        self, indicator: Optional[str] = None, force: bool = False
    ) -> Dict[str, Any]:
        """
        手动触发同步

        Args:
            indicator: 指标名称，None表示同步所有
            force: 是否强制同步

        Returns:
            同步结果
        """
        if self.scheduler:
            return self.scheduler.manual_sync(indicator, force)
        else:
            # 直接使用同步引擎
            if indicator:
                return self.sync_engine.sync_indicator(indicator, force)
            else:
                return self.sync_engine.sync_all_indicators(force)

    def get_sync_status(self) -> Dict[str, Any]:
        """获取同步状态"""
        # 优先从缓存获取
        if self.cache_enabled:
            try:
                cached_status = self.cache.get_sync_status()
                if cached_status:
                    return cached_status
            except:
                pass

        # 从调度器获取状态
        if self.scheduler:
            status = self.scheduler.get_sync_status()
        else:
            status = {
                "is_running": False,
                "scheduler_enabled": False,
                "last_sync_times": {},
                "recent_history": [],
            }

        # 获取缺失数据汇总
        missing_summary = self.get_missing_data_summary()
        status["missing_data_summary"] = missing_summary

        # 缓存状态信息
        if self.cache_enabled:
            try:
                self.cache.set_sync_status(status)
            except:
                pass

        return status

    def get_missing_data_summary(self) -> Dict[str, Any]:
        """获取缺失数据汇总"""
        if self.scheduler:
            return self.scheduler.get_missing_data_summary()
        else:
            # 直接使用同步引擎检测
            indicators = [
                "gdp",
                "cpi",
                "ppi",
                "pmi",
                "money_supply",
                "social_financing",
                "lpr",
            ]
            summary = {}

            for indicator in indicators:
                try:
                    missing_periods = self.sync_engine.detect_missing_periods(indicator)
                    summary[indicator] = {
                        "missing_count": len(missing_periods),
                        "status": (
                            "ok"
                            if len(missing_periods) == 0
                            else ("minor" if len(missing_periods) < 3 else "major")
                        ),
                    }
                except Exception as e:
                    summary[indicator] = {
                        "missing_count": -1,
                        "status": "error",
                        "error": str(e),
                    }

            return summary

    # ==================== 缓存管理功能 ====================

    def clear_cache(self, indicator: Optional[str] = None):
        """
        清除缓存

        Args:
            indicator: 指标名称，None表示清除所有
        """
        if not self.cache_enabled:
            logger.warning("⚠️ 缓存未启用")
            return

        if indicator:
            self.cache.invalidate_indicator(indicator)
            logger.info(f"🗑️ 已清除 {indicator} 缓存")
        else:
            self.cache.invalidate_all()
            logger.info("🗑️ 已清除所有缓存")

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        if not self.cache_enabled:
            return {"status": "cache_disabled"}

        return self.cache.get_cache_stats()

    # ==================== 批量和概览功能 ====================

    def get_latest_all_indicators(
        self, periods: int = 1, use_cache: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """
        获取所有指标的最新数据

        Args:
            periods: 获取最近N期数据
            use_cache: 是否使用缓存

        Returns:
            各指标数据字典
        """
        indicators = {
            "gdp": self.get_gdp(periods=periods, use_cache=use_cache),
            "cpi": self.get_cpi(periods=periods, use_cache=use_cache),
            "ppi": self.get_ppi(periods=periods, use_cache=use_cache),
            "pmi": self.get_pmi(periods=periods, use_cache=use_cache),
            "money_supply": self.get_money_supply(periods=periods, use_cache=use_cache),
            "social_financing": self.get_social_financing(
                periods=periods, use_cache=use_cache
            ),
            "lpr": self.get_lpr(periods=periods, use_cache=use_cache),
        }

        return indicators

    def get_economic_cycle_data(self, start: str, end: str) -> Dict[str, pd.DataFrame]:
        """
        获取经济周期相关数据（GDP + PMI + CPI）

        Args:
            start: 开始时间
            end: 结束时间

        Returns:
            包含多个指标的字典
        """
        try:
            # 根据时间格式判断类型
            if "Q" in start:  # 季度格式
                gdp_data = self.get_gdp(start_quarter=start, end_quarter=end)
            else:  # 月度格式，获取对应季度
                gdp_data = self.get_gdp(periods=8)  # 最近8个季度

            pmi_data = self.get_pmi(start_month=start, end_month=end)
            cpi_data = self.get_cpi(start_month=start, end_month=end)

            return {"gdp": gdp_data, "pmi": pmi_data, "cpi": cpi_data}
        except Exception as e:
            logger.error(f"❌ 获取经济周期数据失败: {e}")
            return {"gdp": pd.DataFrame(), "pmi": pd.DataFrame(), "cpi": pd.DataFrame()}

    def get_monetary_policy_data(self, start: str, end: str) -> Dict[str, pd.DataFrame]:
        """
        获取货币政策相关数据（货币供应量 + 社融 + LPR）

        Args:
            start: 开始时间
            end: 结束时间

        Returns:
            包含多个指标的字典
        """
        try:
            money_supply_data = self.get_money_supply(start_month=start, end_month=end)
            social_financing_data = self.get_social_financing(
                start_month=start, end_month=end
            )
            lpr_data = self.get_lpr(start_date=start, end_date=end)

            return {
                "money_supply": money_supply_data,
                "social_financing": social_financing_data,
                "lpr": lpr_data,
            }
        except Exception as e:
            logger.error(f"❌ 获取货币政策数据失败: {e}")
            return {
                "money_supply": pd.DataFrame(),
                "social_financing": pd.DataFrame(),
                "lpr": pd.DataFrame(),
            }

    def get_inflation_data(self, start: str, end: str) -> Dict[str, pd.DataFrame]:
        """
        获取通胀相关数据（CPI + PPI）

        Args:
            start: 开始时间 (月份格式: "202201")
            end: 结束时间 (月份格式: "202410")

        Returns:
            包含CPI和PPI的字典
        """
        try:
            cpi_data = self.get_cpi(start_month=start, end_month=end)
            ppi_data = self.get_ppi(start_month=start, end_month=end)

            return {"cpi": cpi_data, "ppi": ppi_data}
        except Exception as e:
            logger.error(f"❌ 获取通胀数据失败: {e}")
            return {"cpi": pd.DataFrame(), "ppi": pd.DataFrame()}

    def get_service_health(self) -> Dict[str, Any]:
        """
        获取服务健康状态

        Returns:
            服务健康状态信息
        """
        health = {
            "service_name": "MacroDataService",
            "timestamp": datetime.now().isoformat(),
            "components": {},
        }

        # 检查存储状态
        try:
            storage_status = self.storage.get_storage_info()
            health["components"]["storage"] = {
                "status": "healthy",
                "details": storage_status,
            }
        except Exception as e:
            health["components"]["storage"] = {"status": "unhealthy", "error": str(e)}

        # 检查缓存状态
        if self.cache_enabled:
            try:
                cache_stats = self.get_cache_stats()
                health["components"]["cache"] = {
                    "status": (
                        "healthy"
                        if cache_stats.get("total_keys", 0) >= 0
                        else "unhealthy"
                    ),
                    "details": cache_stats,
                }
            except Exception as e:
                health["components"]["cache"] = {"status": "unhealthy", "error": str(e)}
        else:
            health["components"]["cache"] = {"status": "disabled"}

        # 检查调度器状态
        if self.scheduler:
            try:
                sync_status = self.get_sync_status()
                health["components"]["scheduler"] = {
                    "status": (
                        "healthy" if sync_status.get("is_running", False) else "stopped"
                    ),
                    "details": sync_status,
                }
            except Exception as e:
                health["components"]["scheduler"] = {
                    "status": "unhealthy",
                    "error": str(e),
                }
        else:
            health["components"]["scheduler"] = {"status": "disabled"}

        # 整体健康状态
        component_statuses = [
            comp.get("status") for comp in health["components"].values()
        ]
        if "unhealthy" in component_statuses:
            health["overall_status"] = "unhealthy"
        elif "stopped" in component_statuses:
            health["overall_status"] = "degraded"
        else:
            health["overall_status"] = "healthy"

        return health

    def get_macro_dashboard_data(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        获取宏观数据仪表板数据 - 智能聚合各指标的合适期数

        为不同指标设置最佳的默认期数：
        - GDP: 最近4个季度 (1年)
        - CPI/PPI: 最近12个月 (1年)
        - PMI: 最近12个月 (1年)
        - 货币供应量: 最近12个月 (1年)
        - 社会融资: 最近12个月 (1年)
        - LPR: 最近12期 (通常月度发布)

        Args:
            use_cache: 是否使用缓存

        Returns:
            包含各指标数据和元数据的字典
        """
        try:
            logger.info("🔄 开始获取宏观数据仪表板数据...")

            # 定义每个指标的最佳期数
            DEFAULT_PERIODS = {
                "gdp": 4,  # 最近4个季度
                "cpi": 12,  # 最近12个月
                "ppi": 12,  # 最近12个月
                "pmi": 12,  # 最近12个月
                "money_supply": 12,  # 最近12个月
                "social_financing": 12,  # 最近12个月
                "lpr": 12,  # 最近12期
            }

            result = {
                "data": {},
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "periods_used": DEFAULT_PERIODS,
                    "description": "宏观经济数据仪表板 - 各指标最近一年数据",
                },
            }

            # 获取各指标数据
            indicators_data = {}

            # GDP数据 (季度)
            try:
                gdp_data = self.get_gdp(
                    periods=DEFAULT_PERIODS["gdp"], use_cache=use_cache
                )
                indicators_data["gdp"] = gdp_data
                logger.info(f"✅ GDP数据获取成功，共{len(gdp_data)}条记录")
            except Exception as e:
                logger.error(f"❌ GDP数据获取失败: {e}")
                indicators_data["gdp"] = pd.DataFrame()

            # CPI数据 (月度)
            try:
                cpi_data = self.get_cpi(
                    periods=DEFAULT_PERIODS["cpi"], use_cache=use_cache
                )
                indicators_data["cpi"] = cpi_data
                logger.info(f"✅ CPI数据获取成功，共{len(cpi_data)}条记录")
            except Exception as e:
                logger.error(f"❌ CPI数据获取失败: {e}")
                indicators_data["cpi"] = pd.DataFrame()

            # PPI数据 (月度)
            try:
                ppi_data = self.get_ppi(
                    periods=DEFAULT_PERIODS["ppi"], use_cache=use_cache
                )
                indicators_data["ppi"] = ppi_data
                logger.info(f"✅ PPI数据获取成功，共{len(ppi_data)}条记录")
            except Exception as e:
                logger.error(f"❌ PPI数据获取失败: {e}")
                indicators_data["ppi"] = pd.DataFrame()

            # PMI数据 (月度)
            try:
                pmi_data = self.get_pmi(
                    periods=DEFAULT_PERIODS["pmi"], use_cache=use_cache
                )
                indicators_data["pmi"] = pmi_data
                logger.info(f"✅ PMI数据获取成功，共{len(pmi_data)}条记录")
            except Exception as e:
                logger.error(f"❌ PMI数据获取失败: {e}")
                indicators_data["pmi"] = pd.DataFrame()

            # 货币供应量数据 (月度)
            try:
                money_supply_data = self.get_money_supply(
                    periods=DEFAULT_PERIODS["money_supply"], use_cache=use_cache
                )
                indicators_data["money_supply"] = money_supply_data
                logger.info(
                    f"✅ 货币供应量数据获取成功，共{len(money_supply_data)}条记录"
                )
            except Exception as e:
                logger.error(f"❌ 货币供应量数据获取失败: {e}")
                indicators_data["money_supply"] = pd.DataFrame()

            # 社会融资数据 (月度)
            try:
                social_financing_data = self.get_social_financing(
                    periods=DEFAULT_PERIODS["social_financing"], use_cache=use_cache
                )
                indicators_data["social_financing"] = social_financing_data
                logger.info(
                    f"✅ 社会融资数据获取成功，共{len(social_financing_data)}条记录"
                )
            except Exception as e:
                logger.error(f"❌ 社会融资数据获取失败: {e}")
                indicators_data["social_financing"] = pd.DataFrame()

            # LPR数据
            try:
                lpr_data = self.get_lpr(
                    periods=DEFAULT_PERIODS["lpr"], use_cache=use_cache
                )
                indicators_data["lpr"] = lpr_data
                logger.info(f"✅ LPR数据获取成功，共{len(lpr_data)}条记录")
            except Exception as e:
                logger.error(f"❌ LPR数据获取失败: {e}")
                indicators_data["lpr"] = pd.DataFrame()

            result["data"] = indicators_data

            # 添加数据统计信息
            result["metadata"]["data_summary"] = {}
            for indicator, df in indicators_data.items():
                result["metadata"]["data_summary"][indicator] = {
                    "records_count": len(df),
                    "has_data": not df.empty,
                    "latest_period": (
                        df.iloc[0][INDICATOR_TIME_FIELD[indicator]]
                        if not df.empty
                        else None
                    ),
                }

            logger.info(
                f"✅ 宏观数据仪表板数据获取完成，共{len(indicators_data)}个指标"
            )
            return result

        except Exception as e:
            logger.error(f"❌ 获取宏观数据仪表板数据失败: {e}")
            return {
                "data": {},
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "error": str(e),
                    "description": "宏观数据仪表板数据获取失败",
                },
            }


# ==================== 便捷函数 ====================

_global_service: Optional[MacroDataService] = None


def get_macro_service() -> MacroDataService:
    """获取宏观数据服务单例"""
    global _global_service
    if _global_service is None:
        _global_service = MacroDataService()
    return _global_service
