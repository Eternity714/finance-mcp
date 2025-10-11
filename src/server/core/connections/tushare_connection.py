"""
Tushare 数据源连接管理
"""

from typing import Dict, Any
from datetime import datetime
import logging

try:
    import tushare as ts
except ImportError:
    ts = None

from .base import DataSourceConnection

logger = logging.getLogger(__name__)


class TushareConnection(DataSourceConnection):
    """Tushare 数据源连接"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 Tushare 连接

        Args:
            config: 配置字典，需包含:
                - token: Tushare API token
                - timeout: 超时时间（可选）
                - retry: 重试次数（可选）
        """
        super().__init__(config)
        self.token = config.get("token")

        if not self.token:
            logger.error("❌ Tushare token 未配置")
            raise ValueError("Tushare token 未配置")

        if ts is None:
            logger.error("❌ tushare 库未安装")
            raise ImportError("tushare 库未安装，请执行: pip install tushare")

    def connect(self) -> bool:
        """建立 Tushare 连接"""
        try:
            logger.info("🔄 正在连接 Tushare API...")

            # 设置 token
            ts.set_token(self.token)

            # 创建 pro_api 实例
            self._client = ts.pro_api()

            # 测试连接
            if self.is_healthy():
                self._connected = True
                self._connection_time = datetime.now()
                self.reset_error()
                logger.info("✅ Tushare API 连接成功")
                return True
            else:
                logger.error("❌ Tushare API 健康检查失败")
                return False

        except Exception as e:
            logger.error(f"❌ Tushare 连接失败: {e}")
            self._connected = False
            self.increment_error()
            return False

    def disconnect(self) -> bool:
        """断开 Tushare 连接（Tushare 是无状态的，无需断开）"""
        self._connected = False
        self._client = None
        logger.info("✅ Tushare 连接已断开")
        return True

    def is_healthy(self) -> bool:
        """
        健康检查

        通过查询交易日历测试连接是否正常
        """
        if not self._client:
            return False

        try:
            # 使用轻量级查询测试连接
            # 查询最近的交易日历（只取1条）
            result = self._client.trade_cal(
                exchange="SSE", start_date="20240101", end_date="20240110"
            )

            if result is not None and not result.empty:
                self.reset_error()
                return True
            else:
                logger.warning("⚠️ Tushare 健康检查返回空数据")
                return False

        except Exception as e:
            logger.error(f"❌ Tushare 健康检查失败: {e}")
            self.increment_error()
            return False

    def get_client(self):
        """
        获取 Tushare pro_api 实例

        Returns:
            tushare.pro.client.DataApi: Tushare API 客户端
        """
        return super().get_client()
