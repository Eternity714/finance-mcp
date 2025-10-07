# 📖 Stock MCP 完整指南

> 快速部署、配置和使用 Stock MCP Server

---

## 📋 目录

- [快速开始](#-快速开始)
- [配置详解](#-配置详解)
- [Docker 部署](#-docker-部署)
- [API 接口](#-api-接口)
- [故障排查](#-故障排查)
- [高级用法](#-高级用法)

---

## 🚀 快速开始

### 前置要求

- Docker & Docker Compose
- Tushare Token（[免费注册](https://tushare.pro/register)）
- （可选）代理服务（访问美股数据）

### 5分钟部署

```bash
# 1. 克隆项目
git clone <your-repo-url>
cd stock-mcp

# 2. 配置环境变量
cp .env.example .env

# 编辑 .env，至少配置 TUSHARE_TOKEN
vim .env

# 3. 启动服务
docker-compose up -d

# 4. 验证服务
curl http://localhost:9998/health
```

### 快速测试

```bash
# 查询贵州茅台股价
curl "http://localhost:9998/api/quote?symbol=600519"

# 查询苹果公司股价
curl "http://localhost:9998/api/quote?symbol=AAPL"
```

---

## ⚙️ 配置详解

### 核心配置项

#### 1. 数据源配置

```bash
# Tushare（必需）- A股数据
TUSHARE_TOKEN=your_token_here

# Finnhub（可选）- 增强美股新闻
FINNHUB_API_KEY=your_key

# NewsAPI（可选）- 新闻聚合
NEWS_API_KEY=your_key

# Tavily（可选）- AI 搜索和研究
TAVILY_API_KEY=your_key
```

#### 2. 代理配置

**本地运行：**
```bash
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```

**Docker 环境：**
```bash
HTTP_PROXY=http://host.docker.internal:7890
HTTPS_PROXY=http://host.docker.internal:7890
```

#### 3. Redis 配置

**本地运行：**
```bash
REDIS_HOST=localhost
REDIS_PORT=6379
```

**Docker 环境：**
```bash
REDIS_HOST=redis
REDIS_PORT=6379
```

#### 4. 缓存配置

```bash
CACHE_ENABLED=true          # 启用缓存
CACHE_TTL=3600             # 缓存过期时间（秒）
CACHE_MAX_RETRIES=3        # 缓存重试次数
```

### 配置文件示例

<details>
<summary><b>点击查看完整 .env 示例</b></summary>

```bash
# ========== 数据源配置 ==========
TUSHARE_TOKEN=your_tushare_token_here
FINNHUB_API_KEY=your_finnhub_key
NEWS_API_KEY=your_newsapi_key
TAVILY_API_KEY=your_tavily_key

# ========== 代理配置 ==========
HTTP_PROXY=http://host.docker.internal:7890
HTTPS_PROXY=http://host.docker.internal:7890

# ========== Redis 配置 ==========
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# ========== 缓存配置 ==========
CACHE_ENABLED=true
CACHE_TTL=3600
CACHE_MAX_RETRIES=3

# ========== 服务配置 ==========
LOG_LEVEL=INFO
MAX_WORKERS=4
```
</details>

---

## 🐳 Docker 部署

### 服务架构

```
┌─────────────────────────────────────┐
│     Client（浏览器/API 客户端）      │
└────────────┬────────────────────────┘
             │
    ┌────────▼─────────┐
    │   Port 9998      │  ← FastAPI (RESTful API)
    │   Port 9999      │  ← MCP Server
    └────────┬─────────┘
             │
    ┌────────▼─────────┐
    │   Redis:6379     │  ← 内部缓存（不对外）
    └──────────────────┘
```

### 常用命令

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f stock-mcp
docker-compose logs -f redis

# 查看服务状态
docker-compose ps

# 停止服务
docker-compose down

# 重启服务
docker-compose restart stock-mcp

# 重新构建
docker-compose up -d --build

# 进入容器
docker-compose exec stock-mcp sh
docker-compose exec redis redis-cli
```

### 多架构支持

本项目自动适配 ARM64（Apple Silicon）和 AMD64（x86）架构：

```bash
# 查看镜像架构
docker inspect stock-mcp:latest | grep Architecture
```

---

## 📡 API 接口

### 股票行情

```bash
# 基本用法
GET /api/quote?symbol=<股票代码>

# 指定市场
GET /api/quote?symbol=600519&market=CN   # A股
GET /api/quote?symbol=AAPL&market=US     # 美股
GET /api/quote?symbol=00700&market=HK    # 港股

# 响应示例
{
  "code": 0,
  "data": {
    "symbol": "600519",
    "name": "贵州茅台",
    "price": 1650.00,
    "change": 25.50,
    "change_percent": 1.57,
    "volume": 1234567,
    "market_cap": "2.07万亿"
  }
}
```

### 财务数据

```bash
# 资产负债表
GET /api/financial?symbol=600519&report_type=balance_sheet

# 利润表
GET /api/financial?symbol=AAPL&report_type=income

# 现金流量表
GET /api/financial?symbol=TSLA&report_type=cashflow
```

### 新闻情绪分析

```bash
# 获取近7天新闻情绪
GET /api/news/sentiment?symbol=TSLA&days=7

# 响应示例
{
  "code": 0,
  "data": {
    "symbol": "TSLA",
    "sentiment_score": 0.65,      # -1（极度负面）到 1（极度正面）
    "sentiment_label": "positive",
    "news_count": 45,
    "sources": ["Reuters", "Bloomberg", "CNBC"],
    "top_keywords": ["electric vehicle", "production", "delivery"]
  }
}
```

### AI 深度研究

```bash
# 行业研究
POST /api/research
Content-Type: application/json

{
  "topic": "新能源汽车行业趋势",
  "depth": "comprehensive"
}

# 响应示例
{
  "code": 0,
  "data": {
    "title": "新能源汽车行业深度研究",
    "summary": "...",
    "key_findings": [...],
    "market_outlook": "...",
    "sources": [...]
  }
}
```

### 完整接口文档

启动服务后访问交互式文档：
- **Swagger UI**: http://localhost:9998/docs
- **ReDoc**: http://localhost:9998/redoc

---

## 🛠️ 故障排查

### Redis 连接问题

**现象**：`ConnectionError: Error connecting to Redis`

**解决方案**：
```bash
# 1. 检查 Redis 服务
docker-compose ps redis

# 2. 检查配置
cat .env | grep REDIS_HOST
# 确保 Docker 环境使用: REDIS_HOST=redis

# 3. 重启服务
docker-compose restart redis
docker-compose restart stock-mcp
```

### yFinance 超时

**现象**：`ReadTimeout: HTTPSConnectionPool`

**解决方案**：
```bash
# 1. 检查代理配置
cat .env | grep PROXY

# 2. Docker 环境确保使用正确格式
HTTP_PROXY=http://host.docker.internal:7890
HTTPS_PROXY=http://host.docker.internal:7890

# 3. 测试代理连通性
docker-compose exec stock-mcp curl -x $HTTP_PROXY https://www.google.com

# 4. 重启服务
docker-compose restart stock-mcp
```

### Tushare 权限错误

**现象**：`No permission to access this API`

**解决方案**：
```bash
# 1. 验证 Token
grep TUSHARE_TOKEN .env

# 2. 检查积分（访问 https://tushare.pro/user/token）
# 某些高级接口需要更高积分

# 3. 重新构建镜像
docker-compose down
docker-compose up -d --build
```

### 端口被占用

**现象**：`Bind for 0.0.0.0:9998 failed: port is already allocated`

**解决方案**：
```bash
# 1. 查找占用进程
lsof -i :9998

# 2. 修改端口（编辑 docker-compose.yml）
ports:
  - "9997:9998"  # 改为其他端口

# 3. 重启服务
docker-compose up -d
```

### 缓存异常

**现象**：数据不更新或返回旧数据

**解决方案**：
```bash
# 1. 清空 Redis 缓存
docker-compose exec redis redis-cli FLUSHALL

# 2. 临时禁用缓存
# 编辑 .env
CACHE_ENABLED=false

# 3. 重启服务
docker-compose restart stock-mcp
```

---

## 🎯 高级用法

### 批量查询

```bash
# 使用脚本批量获取多只股票
symbols=("600519" "000858" "601318")
for symbol in "${symbols[@]}"; do
  curl "http://localhost:9998/api/quote?symbol=$symbol"
done
```

### 定时任务

```bash
# 使用 cron 定时获取数据
# 编辑 crontab -e
0 9,15 * * 1-5 curl "http://localhost:9998/api/quote?symbol=600519" >> /var/log/stock.log
```

### 集成到 MCP 客户端

```json
{
  "mcpServers": {
    "stock": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "--network=host",
        "stock-mcp:latest"
      ]
    }
  }
}
```

### 性能优化

```bash
# 1. 调整缓存时间（高频数据用短 TTL）
CACHE_TTL=300  # 5分钟

# 2. 增加工作进程
MAX_WORKERS=8

# 3. 使用 Redis 持久化
# 编辑 docker-compose.yml
volumes:
  - redis_data:/data

volumes:
  redis_data:
```

---

## 📞 获取支持

- 📖 [GitHub Issues](https://github.com/your-repo/issues)
- 💬 [Discussions](https://github.com/your-repo/discussions)
- 📧 Email: support@example.com

---

## 🔗 相关资源

- [Tushare 文档](https://tushare.pro/document/2)
- [AKShare 文档](https://akshare.akfamily.xyz/)
- [MCP 协议规范](https://modelcontextprotocol.io/docs)
- [FastAPI 文档](https://fastapi.tiangolo.com/)

---

<div align="center">

**📝 文档版本**: v1.0 | **最后更新**: 2025-10-08

</div>
