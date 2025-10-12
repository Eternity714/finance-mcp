"""
宏观数据同步调度器
负责定时触发数据同步任务
"""

import schedule
import threading
import time
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
import logging

from .incremental_sync import IncrementalSyncEngine

logger = logging.getLogger(__name__)


class MacroDataSyncScheduler:
    """宏观数据同步调度器"""

    def __init__(self):
        """初始化调度器"""
        self.sync_engine = IncrementalSyncEngine()
        self.is_running = False
        self.scheduler_thread: Optional[threading.Thread] = None

        # 同步状态
        self.last_sync_times: Dict[str, datetime] = {}
        self.sync_history: list = []

        # 回调函数
        self.on_sync_complete: Optional[Callable] = None
        self.on_sync_error: Optional[Callable] = None

        logger.info("✅ MacroDataSyncScheduler 初始化成功")

    def setup_schedules(self):
        """设置同步计划"""
        # 清除现有计划
        schedule.clear()

        # GDP数据：每月15日同步（季度数据通常在季度结束后1-2个月发布）
        schedule.every().month.do(self._sync_gdp_job)

        # CPI/PPI：每月10日同步（通常在月初发布上月数据）
        schedule.every().month.do(self._sync_cpi_job)
        schedule.every().month.do(self._sync_ppi_job)

        # PMI：每月1日同步（通常在月初发布）
        schedule.every().month.do(self._sync_pmi_job)

        # 货币供应量：每月15日同步（通常在月中发布）
        schedule.every().month.do(self._sync_money_supply_job)

        # 社会融资：每月15日同步
        schedule.every().month.do(self._sync_social_financing_job)

        # LPR：每月20日同步（LPR报价时间）
        schedule.every().month.do(self._sync_lpr_job)

        # 每日健康检查：检查是否有缺失数据
        schedule.every().day.at("08:00").do(self._daily_health_check)

        # 每周完整同步：周日凌晨2点
        schedule.every().sunday.at("02:00").do(self._weekly_full_sync)

        logger.info("📅 同步计划设置完成")

    def start(self):
        """启动调度器"""
        if self.is_running:
            logger.warning("⚠️ 调度器已在运行")
            return

        self.setup_schedules()
        self.is_running = True

        # 在单独线程中运行调度器
        self.scheduler_thread = threading.Thread(
            target=self._run_scheduler, daemon=True
        )
        self.scheduler_thread.start()

        logger.info("🚀 调度器已启动")

    def stop(self):
        """停止调度器"""
        self.is_running = False
        schedule.clear()

        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)

        logger.info("🛑 调度器已停止")

    def _run_scheduler(self):
        """运行调度器主循环"""
        logger.info("🔄 调度器主循环已启动")

        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
            except Exception as e:
                logger.error(f"❌ 调度器运行错误: {e}")
                if self.on_sync_error:
                    self.on_sync_error(e)

    def _sync_gdp_job(self):
        """GDP同步任务"""
        self._run_sync_job("gdp", "GDP同步任务")

    def _sync_cpi_job(self):
        """CPI同步任务"""
        self._run_sync_job("cpi", "CPI同步任务")

    def _sync_ppi_job(self):
        """PPI同步任务"""
        self._run_sync_job("ppi", "PPI同步任务")

    def _sync_pmi_job(self):
        """PMI同步任务"""
        self._run_sync_job("pmi", "PMI同步任务")

    def _sync_money_supply_job(self):
        """货币供应量同步任务"""
        self._run_sync_job("money_supply", "货币供应量同步任务")

    def _sync_social_financing_job(self):
        """社会融资同步任务"""
        self._run_sync_job("social_financing", "社会融资同步任务")

    def _sync_lpr_job(self):
        """LPR同步任务"""
        self._run_sync_job("lpr", "LPR同步任务")

    def _daily_health_check(self):
        """每日健康检查"""
        try:
            logger.info("🔍 执行每日数据健康检查...")

            # 检查每个指标是否有严重缺失
            indicators = [
                "gdp",
                "cpi",
                "ppi",
                "pmi",
                "money_supply",
                "social_financing",
                "lpr",
            ]
            health_report = {}

            for indicator in indicators:
                missing_periods = self.sync_engine.detect_missing_periods(indicator)
                health_report[indicator] = {
                    "missing_count": len(missing_periods),
                    "status": "healthy" if len(missing_periods) < 3 else "needs_sync",
                }

            # 如果发现需要同步的指标，触发同步
            needs_sync = [
                k for k, v in health_report.items() if v["status"] == "needs_sync"
            ]

            if needs_sync:
                logger.warning(f"⚠️ 发现需要同步的指标: {needs_sync}")
                for indicator in needs_sync:
                    self._run_sync_job(indicator, f"健康检查触发的{indicator}同步")
            else:
                logger.info("✅ 所有指标数据健康")

            # 记录健康检查结果
            self.sync_history.append(
                {
                    "type": "health_check",
                    "timestamp": datetime.now(),
                    "result": health_report,
                }
            )

        except Exception as e:
            logger.error(f"❌ 每日健康检查失败: {e}")

    def _weekly_full_sync(self):
        """每周完整同步"""
        try:
            logger.info("🔄 执行每周完整同步...")

            result = self.sync_engine.sync_all_indicators(force_sync=True)

            # 记录同步结果
            self.sync_history.append(
                {
                    "type": "weekly_full_sync",
                    "timestamp": datetime.now(),
                    "result": result,
                }
            )

            if self.on_sync_complete:
                self.on_sync_complete(result)

            logger.info(
                f"✅ 每周完整同步完成: 同步了 {result.get('total_synced_records', 0)} 条记录"
            )

        except Exception as e:
            logger.error(f"❌ 每周完整同步失败: {e}")
            if self.on_sync_error:
                self.on_sync_error(e)

    def _run_sync_job(self, indicator: str, job_name: str):
        """运行单个同步任务"""
        try:
            logger.info(f"🔄 执行 {job_name}...")

            result = self.sync_engine.sync_indicator(indicator)

            # 更新最后同步时间
            self.last_sync_times[indicator] = datetime.now()

            # 记录同步结果
            self.sync_history.append(
                {
                    "type": "indicator_sync",
                    "indicator": indicator,
                    "job_name": job_name,
                    "timestamp": datetime.now(),
                    "result": result,
                }
            )

            # 保持历史记录在合理范围内
            if len(self.sync_history) > 1000:
                self.sync_history = self.sync_history[-500:]

            if result.get("status") == "completed":
                logger.info(
                    f"✅ {job_name} 完成: 同步了 {result.get('synced_count', 0)} 条记录"
                )
            elif result.get("status") == "skipped":
                logger.info(f"⏩ {job_name} 跳过: {result.get('reason', '未知原因')}")
            elif result.get("status") == "up_to_date":
                logger.info(f"✅ {job_name} 数据已是最新")
            else:
                logger.warning(f"⚠️ {job_name} 部分完成或失败: {result}")

            if self.on_sync_complete:
                self.on_sync_complete(result)

        except Exception as e:
            logger.error(f"❌ {job_name} 失败: {e}")
            if self.on_sync_error:
                self.on_sync_error(e)

    def manual_sync(
        self, indicator: Optional[str] = None, force: bool = False
    ) -> Dict[str, Any]:
        """
        手动触发同步

        Args:
            indicator: 指标名称，None表示同步所有指标
            force: 是否强制同步

        Returns:
            Dict: 同步结果
        """
        try:
            if indicator:
                logger.info(f"📱 手动触发 {indicator} 同步...")
                result = self.sync_engine.sync_indicator(indicator, force_sync=force)
            else:
                logger.info("📱 手动触发全量同步...")
                result = self.sync_engine.sync_all_indicators(force_sync=force)

            # 记录手动同步
            self.sync_history.append(
                {
                    "type": "manual_sync",
                    "indicator": indicator or "all",
                    "timestamp": datetime.now(),
                    "result": result,
                    "force": force,
                }
            )

            if self.on_sync_complete:
                self.on_sync_complete(result)

            return result

        except Exception as e:
            logger.error(f"❌ 手动同步失败: {e}")
            if self.on_sync_error:
                self.on_sync_error(e)
            raise

    def get_sync_status(self) -> Dict[str, Any]:
        """
        获取同步状态

        Returns:
            Dict: 同步状态信息
        """
        return {
            "is_running": self.is_running,
            "last_sync_times": {
                k: v.isoformat() for k, v in self.last_sync_times.items()
            },
            "recent_history": self.sync_history[-10:],  # 最近10次同步记录
            "total_history_count": len(self.sync_history),
            "next_runs": self._get_next_scheduled_runs(),
        }

    def _get_next_scheduled_runs(self) -> Dict[str, str]:
        """获取下次计划运行时间"""
        try:
            next_runs = {}
            for job in schedule.jobs:
                job_name = str(job.job_func.__name__)
                next_run = job.next_run
                if next_run:
                    next_runs[job_name] = next_run.isoformat()
            return next_runs
        except Exception as e:
            logger.error(f"❌ 获取计划运行时间失败: {e}")
            return {}

    def set_callbacks(
        self, on_sync_complete: Callable = None, on_sync_error: Callable = None
    ):
        """
        设置同步回调函数

        Args:
            on_sync_complete: 同步完成回调
            on_sync_error: 同步错误回调
        """
        self.on_sync_complete = on_sync_complete
        self.on_sync_error = on_sync_error
        logger.info("✅ 同步回调函数已设置")

    def get_missing_data_summary(self) -> Dict[str, Any]:
        """
        获取缺失数据汇总

        Returns:
            Dict: 缺失数据汇总
        """
        try:
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
                missing_periods = self.sync_engine.detect_missing_periods(indicator)
                summary[indicator] = {
                    "missing_count": len(missing_periods),
                    "missing_periods": (
                        missing_periods[:5]
                        if len(missing_periods) <= 5
                        else missing_periods[:5] + ["..."]
                    ),
                    "status": (
                        "ok"
                        if len(missing_periods) == 0
                        else ("minor" if len(missing_periods) < 3 else "major")
                    ),
                }

            return summary

        except Exception as e:
            logger.error(f"❌ 获取缺失数据汇总失败: {e}")
            return {}
