#!/usr/bin/env python3
"""
FastAPI 服务器启动脚本
用于启动 SSE + HTTP POST 双向通信服务器
"""

import sys
from pathlib import Path
import uvicorn

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.server.app import app

if __name__ == "__main__":
    # 启动 FastAPI 服务器
    uvicorn.run(
        "src.server.app:app", host="127.0.0.1", port=8000, reload=True, log_level="info"
    )
