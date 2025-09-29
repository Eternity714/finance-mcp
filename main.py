#!/usr/bin/env python3
"""
统一启动脚本: 同时启动 FastAPI Web 服务器和 MCP 服务器
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
import uvicorn

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.server.mcp_server import run_mcp_server
from src.server.app import create_app
from src.server.mcp_server import StockMCPServer


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
        "--mcp-mode",
        choices=["stdio", "sse", "streamable-http"],
        default="streamable-http",
        help="MCP 服务器的通信模式 (默认: streamable-http)",
    )
    parser.add_argument(
        "--http-port",
        type=int,
        default=9998,
        help="FastAPI Web 服务器的端口号 (默认: 8000)",
    )
    parser.add_argument(
        "--mcp-port",
        type=int,
        default=9999,
        help="MCP 服务器在 sse 或 streamable-http 模式下的端口号 (默认: 8001)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="日志级别 (默认: INFO)",
    )

    args = parser.parse_args()

    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    try:
        # --- 启动 FastAPI 服务器 ---
        app = create_app()
        uvicorn_config = uvicorn.Config(
            app, host="0.0.0.0", port=args.http_port, log_level=args.log_level.lower()
        )
        uvicorn_server = uvicorn.Server(uvicorn_config)
        logger.info(f"🚀 FastAPI Web 服务器将在 http://0.0.0.0:{args.http_port} 启动")
        fastapi_task = asyncio.create_task(uvicorn_server.serve())

        # --- 启动 MCP 服务器 ---
        mcp_task = None
        logger.info(f"🚀 启动股票数据 MCP 服务器 (模式: {args.mcp_mode})")
        server = StockMCPServer()

        if args.mcp_mode == "stdio":
            mcp = server.create_mcp_server()
            mcp_task = asyncio.create_task(mcp.run_stdio_async())
        elif args.mcp_mode == "sse":
            mcp = server.create_mcp_server(port=args.mcp_port)
            logger.info(f"📡 MCP (SSE) 服务器将在端口 {args.mcp_port} 启动")
            mcp_task = asyncio.create_task(mcp.run_sse_async())
        elif args.mcp_mode == "streamable-http":
            mcp = server.create_mcp_server(port=args.mcp_port)
            logger.info(f"📡 MCP (StreamableHTTP) 服务器将在端口 {args.mcp_port} 启动")
            mcp_task = asyncio.create_task(mcp.run_streamable_http_async())

        # 并发运行所有任务
        tasks = [task for task in [fastapi_task, mcp_task] if task]
        if tasks:
            await asyncio.gather(*tasks)

    except KeyboardInterrupt:
        logger.info("🛑 收到中断信号，正在关闭服务器...")
    except Exception as e:
        logger.error(f"❌ 服务器运行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
