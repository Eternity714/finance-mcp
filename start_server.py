#!/usr/bin/env python3
"""
启动 FastAPI 服务器的简单脚本
"""

import os
import sys
from pathlib import Path

# 设置项目根目录
project_root = Path(__file__).parent.absolute()
os.chdir(project_root)
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    import uvicorn

    print("🚀 启动 SSE + HTTP POST 双向通信股票数据服务器")
    print(f"📂 工作目录: {project_root}")
    print("🌐 服务地址: http://127.0.0.1:8000")
    print("📊 管理面板: http://127.0.0.1:8000")
    print("💓 健康检查: http://127.0.0.1:8000/health")

    uvicorn.run(
        "src.server.app:app", host="127.0.0.1", port=8000, reload=True, log_level="info"
    )
