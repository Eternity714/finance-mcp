"""
SSE (Server-Sent Events) 服务
管理客户端连接和消息推送
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class SSEConnection:
    """SSE 连接对象"""

    def __init__(self, client_id: str, request):
        self.client_id = client_id
        self.request = request
        self.connected_at = datetime.now()
        self.last_ping = datetime.now()
        self.message_queue = asyncio.Queue()
        self._closed = False

    @property
    def is_closed(self) -> bool:
        return self._closed

    def close(self):
        """关闭连接"""
        self._closed = True

    async def send_message(self, message: Dict[str, Any]) -> bool:
        """发送消息到客户端"""
        if self._closed:
            return False

        try:
            await self.message_queue.put(message)
            return True
        except Exception as e:
            logger.error(f"发送消息到 {self.client_id} 失败: {e}")
            self._closed = True
            return False


class SSEManager:
    """SSE 连接管理器（单例模式）"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.connections: Dict[str, SSEConnection] = {}
            self.client_stats: Dict[str, Dict[str, Any]] = {}
            self._lock = asyncio.Lock()
            self._cleanup_task = None
            SSEManager._initialized = True
            logger.info("🔧 SSE管理器初始化完成")

    async def add_connection(self, client_id: str, request) -> bool:
        """添加新的SSE连接"""
        async with self._lock:
            if client_id in self.connections:
                # 关闭旧连接
                old_conn = self.connections[client_id]
                old_conn.close()
                logger.warning(f"⚠️ 替换已存在的连接: {client_id}")

            # 创建新连接
            connection = SSEConnection(client_id, request)
            self.connections[client_id] = connection

            # 记录客户端统计
            self.client_stats[client_id] = {
                "connected_at": datetime.now(),
                "message_count": 0,
                "last_activity": datetime.now(),
            }

            logger.info(
                f"✅ 添加SSE连接: {client_id} (总连接数: {len(self.connections)})"
            )

            # 启动清理任务
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_connections())

            return True

    async def remove_connection(self, client_id: str) -> bool:
        """移除SSE连接"""
        async with self._lock:
            if client_id in self.connections:
                connection = self.connections[client_id]
                connection.close()
                del self.connections[client_id]

                # 保留统计信息一段时间
                if client_id in self.client_stats:
                    self.client_stats[client_id]["disconnected_at"] = datetime.now()

                logger.info(
                    f"🔌 移除SSE连接: {client_id} (总连接数: {len(self.connections)})"
                )
                return True

            return False

    async def send_message_to_client(
        self, client_id: str, message: Dict[str, Any]
    ) -> bool:
        """向指定客户端发送消息"""
        async with self._lock:
            if client_id not in self.connections:
                logger.warning(f"⚠️ 客户端不存在: {client_id}")
                return False

            connection = self.connections[client_id]
            if connection.is_closed:
                logger.warning(f"⚠️ 连接已关闭: {client_id}")
                return False

            success = await connection.send_message(message)

            if success and client_id in self.client_stats:
                self.client_stats[client_id]["message_count"] += 1
                self.client_stats[client_id]["last_activity"] = datetime.now()

            return success

    async def broadcast_message(self, message: Dict[str, Any]) -> int:
        """向所有连接的客户端广播消息"""
        success_count = 0

        # 获取当前连接列表的副本，避免在迭代时修改
        async with self._lock:
            client_ids = list(self.connections.keys())

        # 并发发送消息
        tasks = []
        for client_id in client_ids:
            task = self.send_message_to_client(client_id, message)
            tasks.append(task)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for result in results if result is True)

        logger.info(
            f"📢 广播消息完成: {success_count}/{len(client_ids)} 客户端接收成功"
        )
        return success_count

    async def get_message_for_client(self, client_id: str) -> Optional[Dict[str, Any]]:
        """获取客户端的待发送消息"""
        async with self._lock:
            if client_id not in self.connections:
                return None

            connection = self.connections[client_id]
            if connection.is_closed:
                return None

        try:
            # 使用超时避免阻塞
            message = await asyncio.wait_for(
                connection.message_queue.get(), timeout=1.0
            )
            return message
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.error(f"获取客户端消息失败 {client_id}: {e}")
            return None

    def get_active_connections(self) -> Dict[str, Dict[str, Any]]:
        """获取活跃连接信息"""
        result = {}
        for client_id, connection in self.connections.items():
            if not connection.is_closed:
                stats = self.client_stats.get(client_id, {})
                result[client_id] = {
                    "connected_at": connection.connected_at.isoformat(),
                    "last_ping": connection.last_ping.isoformat(),
                    "message_count": stats.get("message_count", 0),
                    "last_activity": stats.get(
                        "last_activity", datetime.now()
                    ).isoformat(),
                }
        return result

    async def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        async with self._lock:
            active_count = len(
                [c for c in self.connections.values() if not c.is_closed]
            )
            total_messages = sum(
                stats.get("message_count", 0) for stats in self.client_stats.values()
            )

            return {
                "active_connections": active_count,
                "total_connections": len(self.connections),
                "total_messages_sent": total_messages,
                "connection_details": self.get_active_connections(),
            }

    async def _cleanup_connections(self):
        """清理已断开的连接"""
        while True:
            try:
                await asyncio.sleep(30)  # 每30秒清理一次

                async with self._lock:
                    # 查找需要清理的连接
                    to_remove = []
                    for client_id, connection in self.connections.items():
                        if connection.is_closed:
                            to_remove.append(client_id)

                    # 移除断开的连接
                    for client_id in to_remove:
                        del self.connections[client_id]
                        if client_id in self.client_stats:
                            self.client_stats[client_id][
                                "disconnected_at"
                            ] = datetime.now()

                    if to_remove:
                        logger.info(f"🧹 清理了 {len(to_remove)} 个断开的连接")

            except Exception as e:
                logger.error(f"连接清理任务错误: {e}")

            # 如果没有活跃连接，停止清理任务
            if not self.connections:
                logger.info("📴 没有活跃连接，停止清理任务")
                break

    async def ping_all_clients(self):
        """向所有客户端发送心跳"""
        ping_message = {
            "type": "ping",
            "timestamp": datetime.now().isoformat(),
            "server_status": "healthy",
        }

        success_count = await self.broadcast_message(ping_message)
        logger.debug(f"💓 心跳发送完成: {success_count} 客户端")
        return success_count

    async def shutdown(self):
        """关闭所有连接"""
        logger.info("🛑 关闭SSE管理器...")

        # 发送关闭通知
        shutdown_message = {
            "type": "server_shutdown",
            "timestamp": datetime.now().isoformat(),
            "message": "服务器正在关闭",
        }

        await self.broadcast_message(shutdown_message)

        # 关闭所有连接
        async with self._lock:
            for connection in self.connections.values():
                connection.close()
            self.connections.clear()

        # 取消清理任务
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

        logger.info("✅ SSE管理器已关闭")
