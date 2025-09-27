"""
SSE + HTTP POST 双向通信股票数据服务器
主应用入口文件
"""

import logging
import sys
from contextlib import asynccontextmanager
from typing import Dict, Any
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# 处理相对导入问题
if __name__ == "__main__":
    # 如果直接运行此文件，添加项目根目录到 Python 路径
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    from src.server.routes.sse_routes import router as sse_router
    from src.server.routes.api_routes import router as api_router
    from src.server.services.sse_service import SSEManager
    from src.server.services.message_service import MessageService
    from src.server.utils.event_manager import EventManager
    from src.config.settings import get_settings
else:
    # 正常的相对导入
    from .routes.sse_routes import router as sse_router
    from .routes.api_routes import router as api_router
    from .services.sse_service import SSEManager
    from .services.message_service import MessageService
    from .utils.event_manager import EventManager
    from ..config.settings import get_settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("🚀 启动 SSE + HTTP POST 双向通信服务器")

    # 启动时的初始化
    settings = get_settings()
    logger.info(f"📋 服务配置: {settings.app_name}")

    yield

    # 关闭时的清理
    logger.info("🛑 关闭 SSE + HTTP POST 双向通信服务器")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="SSE + HTTP POST 双向通信股票数据服务",
        version="1.0.0",
        lifespan=lifespan,
    )

    # 配置 CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(sse_router, prefix="/sse", tags=["SSE"])
    app.include_router(api_router, prefix="/api", tags=["API"])

    # 静态文件和模板
    app.mount("/static", StaticFiles(directory="src/client/static"), name="static")
    templates = Jinja2Templates(directory="src/client/templates")

    @app.get("/")
    async def root(request: Request):
        """首页"""
        return templates.TemplateResponse("dashboard.html", {"request": request})

    @app.get("/health")
    async def health_check():
        """健康检查"""
        try:
            sse_manager_instance = SSEManager()
            connections_count = len(sse_manager_instance.get_active_connections())
        except Exception:
            connections_count = 0

        return {
            "status": "healthy",
            "service": "SSE + HTTP POST 双向通信服务",
            "connections": connections_count,
        }

    return app


# 创建应用实例
app = create_app()

if __name__ == "__main__":
    import uvicorn

    logger.info("🚀 直接启动 FastAPI 服务器")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
