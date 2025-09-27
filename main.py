#!/usr/bin/env python3
"""
股票数据 MCP 服务器启动脚本
支持 stdio 和 SSE 两种模式
支持 stdio, sse, 和 streamable-http 三种模式
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.server.mcp_server import run_mcp_server


def setup_logging(level: str = "INFO"):
    """配置日志"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,  # MCP通信使用stdout，日志输出到stderr
    )


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="股票数据 MCP 服务器")
    parser.add_argument(
        "--mode",
        choices=["stdio", "sse", "streamable-http"],
        default="sse",
        help="通信模式: stdio, sse, 或 streamable-http (默认: sse)",
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="SSE模式的端口号 (默认: 8000)"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="日志级别 (默认: INFO)",
    )

    args = parser.parse_args()

    # 配置日志
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"🚀 启动股票数据MCP服务器 (模式: {args.mode})")

        if args.mode == "stdio":
            # stdio 模式 - 用于本地MCP客户端
            from src.server.mcp_server import StockMCPServer

            server = StockMCPServer()
            mcp = server.create_mcp_server()
            await mcp.run_stdio_async()
        elif args.mode == "sse":
            # SSE 模式 - 用于网络通信
            from src.server.mcp_server import StockMCPServer

            server = StockMCPServer()
            # 从 StockMCPServer 创建一个已配置好工具和端口的 mcp 实例
            mcp = server.create_mcp_server(port=args.port)

            logger.info(
                f"📡 SSE 服务器将在端口 {args.port} 启动 (端点: GET /sse, POST /messages/)"
            )
            await mcp.run_sse_async()
        elif args.mode == "streamable-http":
            # Streamable HTTP 模式 - 用于网络通信
            from src.server.mcp_server import StockMCPServer

            server = StockMCPServer()
            # 从 StockMCPServer 创建一个已配置好工具和端口的 mcp 实例
            mcp = server.create_mcp_server(port=args.port)

            logger.info(
                f"📡 StreamableHTTP 服务器将在端口 {args.port} 启动 (端点: POST /mcp)"
            )
            await mcp.run_streamable_http_async()

    except KeyboardInterrupt:
        logger.info("🛑 收到中断信号，正在关闭服务器...")
    except Exception as e:
        logger.error(f"❌ 服务器运行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
