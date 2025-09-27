# 📈 股票数据 MCP 服务器

一个基于 Model Context Protocol (MCP) 的全功能股票数据服务器，支持多种通信模式，提供实时股票行情、基本面分析、新闻情绪分析等功能。

## ✨ 主要特性

### 🚀 多模式支持
- **STDIO 模式**: 用于本地 MCP 客户端集成
- **SSE 模式**: 基于服务器推送事件的实时通信
- **StreamableHTTP 模式**: 基于 HTTP 的流式传输

### 📊 数据服务
- **实时股票行情**: 支持 A股、港股、美股数据获取
- **基本面分析**: 财务指标、估值分析、盈利能力评估
- **新闻情绪分析**: 多源新闻聚合、情绪评分、影响评估
- **市场概览**: 大盘指数、板块行情、市场热点

### 🔄 数据源集成
- **AKShare**: 中文股票数据主要来源
- **Tushare**: 专业金融数据接口
- **yFinance**: 全球股票数据支持
- **Finnhub**: 实时新闻和基本面数据
- **NewsAPI**: 新闻聚合服务

### 🎯 技术特点
- **多级缓存**: Redis 缓存 + 智能降级机制
- **异步架构**: 高并发处理能力
- **容器化部署**: Docker 支持，生产就绪
- **实时通信**: SSE + WebSocket 双向通信
- **可视化面板**: Web 管理界面

## 🛠️ 技术栈

- **后端框架**: FastAPI + FastMCP
- **数据处理**: Pandas + NumPy
- **缓存系统**: Redis
- **容器化**: Docker + Gunicorn
- **前端**: 原生 JavaScript + SSE
- **数据源**: AKShare, Tushare, yFinance, Finnhub

## 📋 环境要求

- Python 3.11+
- Redis (可选，用于缓存)
- Docker (可选，用于容器化部署)

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone <repository-url>
cd stock-mcp
```

### 2. 环境配置

复制环境配置文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置必要的 API 密钥：

```bash
# 必需配置
TUSHARE_TOKEN="your_tushare_token"
FINNHUB_API_KEY="your_finnhub_api_key"

# 可选配置
ALPHA_VANTAGE_API_KEY="your_alpha_vantage_key"
NEWSAPI_KEY="your_newsapi_key"
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 启动服务

本项目提供一个统一启动脚本 `main.py`，可以并发启动 FastAPI Web 服务和 MCP 服务器（默认 MCP 模式为 `streamable-http`）。日志输出到 stderr（MCP 通信使用 stdout），可通过命令行参数控制端口、MCP 模式和日志级别。

用法：

```bash
python main.py [--mcp-mode {stdio|sse|streamable-http}] [--http-port <port>] [--mcp-port <port>] [--log-level {DEBUG|INFO|WARNING|ERROR}]
```

默认值：
- `--mcp-mode`：`streamable-http`
- `--http-port`：`8000`
- `--mcp-port`：`8001`
- `--log-level`：`INFO`

示例：

```bash
# 仅使用 stdio 模式运行 MCP（适用于本地 MCP 客户端）
python main.py --mcp-mode stdio

# 在 SSE 模式下启动 MCP（MCP 在 8001 端口），同时启动 FastAPI 在 8000
python main.py --mcp-mode sse --mcp-port 8001 --http-port 8000

# 使用 StreamableHTTP 模式（默认）并设置日志级别为 DEBUG
python main.py --mcp-mode streamable-http --mcp-port 8001 --http-port 8000 --log-level DEBUG
```

注意：`main.py` 会同时启动 FastAPI 和 MCP（根据所选模式），如果只想单独启动 FastAPI，可使用 `start_server.py` 或通过 uvicorn 直接运行（参见下方）。

#### 方式二：FastAPI 服务器模式（单独启动）

```bash
# 使用项目自带脚本启动 FastAPI（开发模式）
python start_server.py

# 或者使用 uvicorn 仅启动 FastAPI
uvicorn src.server.app:app --host 127.0.0.1 --port 8000 --reload
```

### 5. 访问服务

- **管理面板**: http://127.0.0.1:8000
- **API 文档**: http://127.0.0.1:8000/docs
- **健康检查**: http://127.0.0.1:8000/health

## 🐳 Docker 部署

### 构建镜像

```bash
docker build -t stock-mcp-server .
```

### 运行容器

```bash
docker run -d \
  --name stock-mcp \
  -p 5005:5005 \
  -e TUSHARE_TOKEN="your_token" \
  -e FINNHUB_API_KEY="your_key" \
  stock-mcp-server
```

### 使用 Docker Compose

```yaml
version: '3.8'
services:
  stock-mcp:
    build: .
    ports:
      - "5005:5005"
    environment:
      - TUSHARE_TOKEN=your_token
      - FINNHUB_API_KEY=your_key
    depends_on:
      - redis
  
  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
```

## 📚 API 文档

### MCP 工具

#### 1. 获取股票价格数据

```python
get_stock_price_data(symbol: str, start_date: str, end_date: str) -> str
```

**参数说明:**
- `symbol`: 股票代码 (如: "000001", "AAPL", "00700")
- `start_date`: 开始日期 (格式: "YYYY-MM-DD")
- `end_date`: 结束日期 (格式: "YYYY-MM-DD")

**返回:** Markdown 格式的股票分析报告

#### 2. 获取基本面分析

```python
get_financial_report(symbol: str) -> str
```

**参数说明:**
- `symbol`: 股票代码

**返回:** 详细的基本面分析报告

#### 3. 获取最新新闻

```python
get_latest_news(symbol: str, days_back: int = 30) -> str
```

**参数说明:**
- `symbol`: 股票代码
- `days_back`: 获取最近几天的新闻 (默认: 30天)

**返回:** 新闻列表和情绪分析报告

### REST API 端点

#### 股票数据相关

获取股票价格数据:
```http
GET /api/stock/price?symbol=000001&start_date=2023-01-01&end_date=2023-12-31
```

获取基本面数据:
```http
GET /api/stock/fundamental?symbol=000001
```

获取最新新闻:
```http
GET /api/stock/news?symbol=000001&days_back=30
```

#### SSE 连接

```http
GET /sse/connect
Accept: text/event-stream
```

#### 消息发送

```http
POST /api/message
Content-Type: application/json

{
  "type": "stock_query",
  "symbol": "000001",
  "timestamp": "2023-12-01T10:00:00Z"
}
```

## 🎮 使用示例

### MCP 客户端示例

```python
import asyncio
from mcp_client import MCPClient

async def main():
    client = MCPClient("http://localhost:8000/mcp")
    
    # 获取股票数据
    result = await client.call_tool("get_stock_price_data", {
        "symbol": "000001",
        "start_date": "2023-01-01", 
        "end_date": "2023-12-31"
    })
    
    print(result)

asyncio.run(main())
```

### Web 客户端示例

```javascript
// 连接 SSE
const eventSource = new EventSource('/sse/connect');

eventSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('收到数据:', data);
};

// 发送请求
async function getStockData() {
    const symbol = '000001';
    const startDate = '2023-01-01';
    const endDate = '2023-12-31';
    const url = `/api/stock/price?symbol=${symbol}&start_date=${startDate}&end_date=${endDate}`;

    const response = await fetch(url);
    
    const data = await response.json();
    console.log(data);
}
```

## 🔧 配置说明

### 环境变量

| 变量名                  | 必需 | 默认值      | 说明                   |
| ----------------------- | ---- | ----------- | ---------------------- |
| `HOST`                  | 否   | `127.0.0.1` | 服务器主机地址         |
| `PORT`                  | 否   | `8000`      | 服务器端口             |
| `DEBUG`                 | 否   | `false`     | 调试模式               |
| `TUSHARE_TOKEN`         | 是   | -           | Tushare API 令牌       |
| `FINNHUB_API_KEY`       | 是   | -           | Finnhub API 密钥       |
| `ALPHA_VANTAGE_API_KEY` | 否   | -           | Alpha Vantage API 密钥 |
| `NEWSAPI_KEY`           | 否   | -           | NewsAPI 密钥           |
| `REDIS_HOST`            | 否   | `localhost` | Redis 主机地址         |
| `REDIS_PORT`            | 否   | `6379`      | Redis 端口             |
| `CACHE_TTL`             | 否   | `3600`      | 缓存过期时间 (秒)      |

### Redis 配置

Redis 用于缓存股票数据，提高响应速度：

```bash
# 安装 Redis (macOS)
brew install redis

# 启动 Redis
redis-server

# 或者使用 Docker
docker run -d --name redis -p 6379:6379 redis:alpine
```

## 📊 项目结构

```
stock-mcp/
├── src/
│   ├── server/
│   │   ├── app.py              # FastAPI 主应用
│   │   ├── mcp_server.py       # MCP 服务器实现
│   │   ├── routes/             # API 路由
│   │   ├── services/           # 业务服务层
│   │   └── utils/              # 工具模块
│   ├── client/                 # Web 客户端
│   │   ├── static/             # 静态资源
│   │   └── templates/          # HTML 模板
│   └── config/                 # 配置管理
├── tests/                      # 测试文件
├── main.py                     # MCP 服务器启动脚本
├── start_server.py             # FastAPI 服务器启动脚本
├── requirements.txt            # Python 依赖
├── Dockerfile                  # Docker 配置
└── README.md                   # 项目文档
```

## 🧪 测试

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_api.py

# 测试 MCP 工具
python test_mcp_meta.py
```

### 手动测试

```bash
# 测试健康检查
curl http://localhost:8000/health

# 测试股票价格 API
curl -X GET "http://localhost:8000/api/stock/price?symbol=000001&start_date=2023-01-01&end_date=2023-12-31"
```

## 🔍 监控与日志

### 健康检查

服务提供多个健康检查端点：

- `/health` - 基本健康状态
- `/api/v1/health` - 详细健康报告

### 日志配置

日志输出到 `stderr`，支持多个级别：

```python
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

### 性能监控

使用 Gunicorn 提供生产级性能：

```bash
# 生产环境启动
gunicorn --workers 4 --bind 0.0.0.0:5005 app:app
```

## 🤝 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/new-feature`)
3. 提交更改 (`git commit -am 'Add new feature'`)
4. 推送到分支 (`git push origin feature/new-feature`)
5. 创建 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 🐛 问题反馈

如果您遇到任何问题或有功能建议，请在 [Issues](../../issues) 页面提交。

## 📞 联系方式

- 项目维护者: [胡伟华]
- 邮箱: [2215629678@qq.com]
- 项目主页: [项目链接]

## 🙏 致谢

- [AKShare](https://github.com/akfamily/akshare) - 优秀的中文金融数据接口
- [Tushare](https://tushare.pro/) - 专业的金融数据服务
- [FastMCP](https://github.com/jlowin/fastmcp) - 简洁的 MCP 服务器框架
- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的 Python Web 框架

---

⭐ 如果这个项目对您有帮助，请给个星标支持！
