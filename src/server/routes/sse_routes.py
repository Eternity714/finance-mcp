"""
SSE (Server-Sent Events) 路由
用于服务器向客户端推送消息
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from sse_starlette import EventSourceResponse

from ..services.sse_service import SSEManager

logger = logging.getLogger(__name__)
router = APIRouter()

# 全局 SSE 管理器
sse_manager = SSEManager()


@router.get("/connect")
async def sse_connect(request: Request):
    """建立 SSE 连接"""

    async def event_stream():
        """事件流生成器"""
        client_id = f"client_{datetime.now().timestamp()}"

        try:
            # 添加客户端连接
            await sse_manager.add_connection(client_id, request)
            logger.info(f"✅ 新客户端连接: {client_id}")

            # 发送连接确认消息
            init_message = {
                "type": "connection_established",
                "client_id": client_id,
                "timestamp": datetime.now().isoformat(),
                "message": "SSE 连接建立成功",
                "post_endpoint": "/api/message",  # 告诉客户端POST端点
            }

            yield {
                "event": "connection",
                "data": json.dumps(init_message, ensure_ascii=False),
            }

            # 保持连接活跃，监听消息队列
            while True:
                try:
                    # 检查是否有待发送的消息
                    message = await sse_manager.get_message_for_client(client_id)
                    if message:
                        yield {
                            "event": message.get("event", "message"),
                            "data": json.dumps(message, ensure_ascii=False),
                        }

                    # 定期发送心跳
                    await asyncio.sleep(1)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"SSE流错误: {e}")
                    break

        except Exception as e:
            logger.error(f"SSE连接错误: {e}")
        finally:
            # 清理连接
            await sse_manager.remove_connection(client_id)
            logger.info(f"🔌 客户端断开: {client_id}")

    return EventSourceResponse(
        event_stream(),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/status")
async def sse_status():
    """获取 SSE 服务状态"""
    connections = sse_manager.get_active_connections()

    return {
        "status": "active",
        "active_connections": len(connections),
        "connection_ids": list(connections.keys()),
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/broadcast")
async def broadcast_message(message_data: Dict[str, Any]):
    """向所有连接的客户端广播消息"""
    try:
        # 添加时间戳
        message_data["timestamp"] = datetime.now().isoformat()
        message_data["type"] = "broadcast"

        # 广播消息
        success_count = await sse_manager.broadcast_message(message_data)

        return {
            "status": "success",
            "message": "消息广播成功",
            "recipients": success_count,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"广播消息失败: {e}")
        return {
            "status": "error",
            "message": f"广播失败: {str(e)}",
            "timestamp": datetime.now().isoformat(),
        }


@router.post("/send/{client_id}")
async def send_to_client(client_id: str, message_data: Dict[str, Any]):
    """向指定客户端发送消息"""
    try:
        # 添加时间戳
        message_data["timestamp"] = datetime.now().isoformat()
        message_data["type"] = "direct_message"

        # 发送消息
        success = await sse_manager.send_message_to_client(client_id, message_data)

        if success:
            return {
                "status": "success",
                "message": f"消息已发送到客户端 {client_id}",
                "timestamp": datetime.now().isoformat(),
            }
        else:
            return {
                "status": "error",
                "message": f"客户端 {client_id} 不存在或连接已断开",
                "timestamp": datetime.now().isoformat(),
            }

    except Exception as e:
        logger.error(f"发送消息失败: {e}")
        return {
            "status": "error",
            "message": f"发送失败: {str(e)}",
            "timestamp": datetime.now().isoformat(),
        }
