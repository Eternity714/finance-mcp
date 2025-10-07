# 🔧 Stock MCP 开发文档

> 架构设计、二次开发和扩展指南

---

## 📐 项目架构

### 整体架构

```
┌──────────────────────────────────────────────────────┐
│                   Client Layer                        │
│  (Claude Desktop / API Client / Web Dashboard)        │
└─────────────────────┬────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        │                           │
        ▼                           ▼
┌───────────────┐          ┌─────────────────┐
│  MCP Server   │          │   FastAPI       │
│  (Port 9999)  │          │  (Port 9998)    │
└───────┬───────┘          └────────┬────────┘
        │                           │
        └─────────────┬─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │     Service Layer          │
        │  ┌──────────────────────┐ │
        │  │ Market Service       │ │
        │  │ Quote Service        │ │
        │  │ News Service         │ │
        │  │ Fundamentals Service │ │
        │  │ Tavily Service       │ │
        │  └──────────────────────┘ │
        └─────────────┬─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │    Data Source Layer       │
        │  ┌──────────────────────┐ │
        │  │ AKShare              │ │
        │  │ Tushare              │ │
        │  │ yFinance             │ │
        │  │ Finnhub              │ │
        │  └──────────────────────┘ │
        └─────────────┬─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │    Redis Cache Layer       │
        └───────────────────────────┘
```

### 目录结构

```
src/
├── server/
│   ├── app.py                 # FastAPI 应用入口
│   ├── mcp_server.py          # MCP 服务器
│   ├── routes/                # API 路由
│   │   ├── api_routes.py      # RESTful 接口
│   │   └── sse_routes.py      # SSE 接口
│   ├── services/              # 业务逻辑层
│   │   ├── market_service.py  # 市场数据
│   │   ├── quote_service.py   # 行情服务
│   │   ├── news_service.py    # 新闻服务
│   │   └── ...
│   └── utils/                 # 工具类
│       ├── redis_cache.py     # 缓存管理
│       ├── symbol_processor.py # 股票代码处理
│       └── ...
└── config/
    └── settings.py            # 配置管理
```

---

## 🛠️ 本地开发

### 开发环境设置

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt
pip install -r requirements-dev.txt  # 开发依赖

# 3. 配置环境变量
cp .env.example .env
vim .env

# 4. 启动 Redis（Docker）
docker run -d -p 6379:6379 redis:alpine

# 5. 启动开发服务器
python main.py --http-port 9998 --mcp-port 9999
```

### 热重载开发

```bash
# 使用 uvicorn 热重载
uvicorn src.server.app:app --reload --port 9998
```

---

## 🔌 添加新数据源

### 1. 创建服务类

```python
# src/server/services/new_data_source_service.py

from typing import Dict, Any, Optional
from ..utils.redis_cache import cache_result

class NewDataSourceService:
    """新数据源服务"""
    
    def __init__(self):
        self.api_key = os.getenv("NEW_API_KEY")
        
    @cache_result(ttl=3600)
    async def get_data(self, symbol: str) -> Dict[str, Any]:
        """获取数据（带缓存）"""
        # 实现数据获取逻辑
        return {
            "symbol": symbol,
            "data": "..."
        }
```

### 2. 注册到路由

```python
# src/server/routes/api_routes.py

from ..services.new_data_source_service import NewDataSourceService

new_service = NewDataSourceService()

@router.get("/api/new-endpoint")
async def get_new_data(symbol: str):
    """新接口"""
    try:
        data = await new_service.get_data(symbol)
        return {"code": 0, "data": data}
    except Exception as e:
        return {"code": 1, "error": str(e)}
```

### 3. 添加 MCP 工具

```python
# src/server/mcp_server.py

@server.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    if name == "new_tool":
        symbol = arguments.get("symbol")
        data = await new_service.get_data(symbol)
        return [TextContent(type="text", text=json.dumps(data))]
```

---

## 🧪 测试

### 单元测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_news_service.py

# 生成覆盖率报告
pytest --cov=src --cov-report=html
```

### 测试示例

```python
# tests/test_quote_service.py

import pytest
from src.server.services.quote_service import QuoteService

@pytest.mark.asyncio
async def test_get_quote():
    service = QuoteService()
    result = await service.get_quote("600519")
    
    assert result is not None
    assert result["symbol"] == "600519"
    assert "price" in result
```

### API 测试

```bash
# 使用 httpie
http GET localhost:9998/api/quote symbol==600519

# 使用 curl
curl "http://localhost:9998/api/quote?symbol=600519"
```

---

## 📊 性能优化

### 缓存策略

```python
# 不同数据类型使用不同的缓存时间
CACHE_TTL_CONFIG = {
    "realtime_quote": 60,      # 实时行情 1分钟
    "daily_data": 3600,        # 日线数据 1小时
    "financial": 86400,        # 财务数据 1天
    "company_info": 604800,    # 公司信息 1周
}

@cache_result(ttl=CACHE_TTL_CONFIG["realtime_quote"])
async def get_realtime_quote(symbol: str):
    # ...
```

### 并发处理

```python
import asyncio

async def batch_get_quotes(symbols: list):
    """批量获取行情"""
    tasks = [get_quote(symbol) for symbol in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

### 连接池

```python
# 使用 aiohttp 连接池
import aiohttp

session = aiohttp.ClientSession(
    connector=aiohttp.TCPConnector(limit=100),
    timeout=aiohttp.ClientTimeout(total=30)
)
```

---

## 🔒 安全最佳实践

### 环境变量

```python
# ❌ 不要硬编码
API_KEY = "sk-abc123..."

# ✅ 使用环境变量
import os
API_KEY = os.getenv("API_KEY")
```

### API 限流

```python
from fastapi import HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.get("/api/quote")
@limiter.limit("100/minute")
async def get_quote(request: Request, symbol: str):
    # ...
```

### 输入验证

```python
from pydantic import BaseModel, validator

class QuoteRequest(BaseModel):
    symbol: str
    market: str = "CN"
    
    @validator("symbol")
    def validate_symbol(cls, v):
        if not v or len(v) > 10:
            raise ValueError("Invalid symbol")
        return v.upper()
```

---

## 📝 代码风格

### 格式化

```bash
# 使用 black 格式化代码
black src/

# 使用 isort 排序导入
isort src/

# 使用 flake8 检查
flake8 src/
```

### 类型提示

```python
from typing import Dict, List, Optional

def get_quote(symbol: str, market: str = "CN") -> Dict[str, Any]:
    """获取股票行情
    
    Args:
        symbol: 股票代码
        market: 市场代码
        
    Returns:
        包含行情数据的字典
    """
    # ...
```

---

## 🚀 部署

### Docker 构建

```bash
# 构建镜像
docker build -t stock-mcp:latest .

# 多架构构建
docker buildx build --platform linux/amd64,linux/arm64 -t stock-mcp:latest .
```

### 健康检查

```python
@app.get("/health")
async def health_check():
    """健康检查接口"""
    redis_ok = await check_redis()
    return {
        "status": "healthy" if redis_ok else "degraded",
        "redis": redis_ok,
        "timestamp": datetime.now().isoformat()
    }
```

---

## 🐛 调试技巧

### 日志配置

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
logger.debug("Debug message")
```

### 性能分析

```python
import time
from functools import wraps

def timing_decorator(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        result = await func(*args, **kwargs)
        duration = time.time() - start
        logger.info(f"{func.__name__} took {duration:.2f}s")
        return result
    return wrapper

@timing_decorator
async def slow_function():
    # ...
```

---

## 📚 参考资源

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Redis Python 客户端](https://redis-py.readthedocs.io/)
- [AKShare 文档](https://akshare.akfamily.xyz/)

---

<div align="center">

**💡 有疑问？查看 [完整指南](GUIDE.md) 或提交 [Issue](https://github.com/your-repo/issues)**

</div>
