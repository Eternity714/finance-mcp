"""
事件管理器
处理系统事件和消息分发
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Callable, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class EventManager:
    """事件管理器"""

    def __init__(self):
        self.listeners: Dict[str, List[Callable]] = defaultdict(list)
        self.event_history: List[Dict[str, Any]] = []
        self.max_history_size = 1000

    def subscribe(self, event_type: str, callback: Callable) -> bool:
        """
        订阅事件

        Args:
            event_type: 事件类型
            callback: 回调函数

        Returns:
            是否订阅成功
        """
        try:
            self.listeners[event_type].append(callback)
            logger.info(f"✅ 订阅事件: {event_type}")
            return True
        except Exception as e:
            logger.error(f"❌ 订阅事件失败 {event_type}: {e}")
            return False

    def unsubscribe(self, event_type: str, callback: Callable) -> bool:
        """
        取消订阅事件

        Args:
            event_type: 事件类型
            callback: 回调函数

        Returns:
            是否取消成功
        """
        try:
            if callback in self.listeners[event_type]:
                self.listeners[event_type].remove(callback)
                logger.info(f"🔕 取消订阅事件: {event_type}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ 取消订阅失败 {event_type}: {e}")
            return False

    async def emit(self, event_type: str, data: Dict[str, Any]) -> int:
        """
        发射事件

        Args:
            event_type: 事件类型
            data: 事件数据

        Returns:
            成功处理的监听器数量
        """
        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat(),
            "event_id": f"{event_type}_{datetime.now().timestamp()}",
        }

        # 记录事件历史
        self._add_to_history(event)

        # 调用监听器
        success_count = 0
        listeners = self.listeners.get(event_type, [])

        if not listeners:
            logger.debug(f"📭 无监听器处理事件: {event_type}")
            return 0

        for callback in listeners:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
                success_count += 1
            except Exception as e:
                logger.error(f"❌ 事件监听器执行失败 {event_type}: {e}")

        logger.debug(f"📡 事件处理完成 {event_type}: {success_count}/{len(listeners)}")
        return success_count

    def _add_to_history(self, event: Dict[str, Any]):
        """添加事件到历史记录"""
        self.event_history.append(event)

        # 保持历史记录大小限制
        if len(self.event_history) > self.max_history_size:
            self.event_history.pop(0)

    def get_event_history(
        self, event_type: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取事件历史

        Args:
            event_type: 事件类型过滤，None表示所有事件
            limit: 返回数量限制

        Returns:
            事件历史列表
        """
        if event_type:
            filtered_events = [e for e in self.event_history if e["type"] == event_type]
        else:
            filtered_events = self.event_history

        return filtered_events[-limit:]

    def get_listener_count(self, event_type: Optional[str] = None) -> Dict[str, int]:
        """获取监听器统计"""
        if event_type:
            return {event_type: len(self.listeners.get(event_type, []))}
        else:
            return {k: len(v) for k, v in self.listeners.items()}

    def clear_history(self):
        """清空事件历史"""
        self.event_history.clear()
        logger.info("🗑️ 事件历史已清空")

    def get_stats(self) -> Dict[str, Any]:
        """获取事件管理器统计信息"""
        return {
            "total_listeners": sum(len(v) for v in self.listeners.values()),
            "event_types": list(self.listeners.keys()),
            "history_size": len(self.event_history),
            "max_history_size": self.max_history_size,
            "listener_details": self.get_listener_count(),
        }


# 全局事件管理器实例
_event_manager = None


def get_event_manager() -> EventManager:
    """获取全局事件管理器实例（单例模式）"""
    global _event_manager
    if _event_manager is None:
        _event_manager = EventManager()
        logger.info("🔧 全局事件管理器已初始化")
    return _event_manager
