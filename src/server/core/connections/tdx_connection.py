"""
通达信(TDX)连接管理器
管理通达信行情接口的连接状态
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

try:
    from pytdx.hq import TdxHq_API
except ImportError:
    TdxHq_API = None

from .base import DataSourceConnection

logger = logging.getLogger("tdx_connection")


class TdxConnection(DataSourceConnection):
    """通达信连接管理器"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._api = None
        self._current_server = None

        # 默认服务器列表
        self._servers = config.get(
            "servers",
            [
                {"ip": "115.238.56.198", "port": 7709},
                {"ip": "115.238.90.165", "port": 7709},
                {"ip": "180.153.18.170", "port": 7709},
                {"ip": "119.147.212.81", "port": 7709},
            ],
        )

    def connect(self) -> bool:
        """建立通达信连接"""
        if TdxHq_API is None:
            logger.error("❌ pytdx 库未安装，请执行: pip install pytdx")
            return False

        try:
            self._api = TdxHq_API()

            # 尝试连接服务器列表
            for server in self._servers:
                try:
                    logger.info(
                        f"🔄 尝试连接通达信服务器: {server['ip']}:{server['port']}"
                    )
                    if self._api.connect(server["ip"], server["port"]):
                        logger.info(
                            f"✅ 通达信服务器连接成功: {server['ip']}:{server['port']}"
                        )
                        self._connected = True
                        self._connection_time = datetime.now()
                        self._current_server = server
                        self._error_count = 0
                        return True
                except Exception as e:
                    logger.warning(
                        f"⚠️ 连接服务器 {server['ip']}:{server['port']} 失败: {e}"
                    )
                    continue

            logger.error("❌ 所有通达信服务器连接失败")
            self._connected = False
            self._error_count += 1
            return False

        except Exception as e:
            logger.error(f"❌ 通达信连接初始化失败: {e}")
            self._connected = False
            self._error_count += 1
            return False

    def disconnect(self) -> bool:
        """断开通达信连接"""
        try:
            if self._api and self._connected:
                self._api.disconnect()
                logger.info("✅ 通达信连接已断开")

            self._connected = False
            self._api = None
            self._current_server = None
            return True
        except Exception as e:
            logger.error(f"❌ 断开通达信连接失败: {e}")
            return False

    def is_healthy(self) -> bool:
        """检查连接健康状态"""
        if not self._connected or not self._api:
            return False

        try:
            # 简单的健康检查：获取服务器信息
            result = self._api.get_security_count(0)  # 获取深市股票数量
            return result is not None and result > 0
        except Exception as e:
            logger.warning(f"⚠️ 通达信健康检查失败: {e}")
            self._error_count += 1
            return False

    def get_client(self):
        """获取通达信API客户端"""
        if not self._connected:
            if not self.connect():
                raise ConnectionError("无法连接到通达信服务器")
        return self._api

    def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        info = super().get_connection_info()
        info.update(
            {"server": self._current_server, "available_servers": len(self._servers)}
        )
        return info
