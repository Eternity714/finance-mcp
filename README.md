<div align="center">

# 📈 Stock MCP Server

> **基于 Model Context Protocol 的智能股票数据服务**  
> 一站式获取 A股/港股/美股实时数据 + AI 驱动的深度分析

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[快速开始](#-快速开始) • [功能特性](#-核心功能) • [API 文档](http://localhost:9998/docs) • [配置指南](docs/GUIDE.md)

</div>

---

## ✨ 为什么选择 Stock MCP？

- 🌐 **全球市场覆盖** - 一键接入 A股、港股、美股数据
- 🤖 **AI 智能分析** - 新闻情绪分析、深度研究报告、智能搜索
- 🚀 **开箱即用** - Docker 一键部署，5分钟启动服务
- 📊 **多数据源融合** - AKShare、Tushare、yFinance、Finnhub 智能聚合
- 💾 **高性能缓存** - Redis 加速 + 自动降级，稳定可靠

---

## 🚀 快速开始

```bash
# 1. 克隆项目
git clone <your-repo-url> && cd stock-mcp

# 2. 配置环境变量（必需：TUSHARE_TOKEN）
cp .env.example .env && vim .env

# 3. 一键启动
docker-compose up -d

# 4. 访问服务
open http://localhost:9998/docs
```

**🎯 5分钟体验核心功能：**
```bash
# 查询茅台股价
curl "http://localhost:9998/api/quote?symbol=600519"

# 分析特斯拉新闻情绪
curl "http://localhost:9998/api/news/sentiment?symbol=TSLA&days=7"

# AI 研究电动汽车行业
curl -X POST "http://localhost:9998/api/research" \
  -d '{"topic":"电动汽车行业趋势"}'
```

---

## 🎯 核心功能

<table>
<tr>
<td width="50%">

### 📊 数据查询
- ✅ **实时行情** - 分钟级价格/成交量
- ✅ **历史数据** - K线图、复权价格
- ✅ **财务报表** - 资产负债表、现金流
- ✅ **技术指标** - MACD、RSI、布林带
- ✅ **资金流向** - 主力资金、北向资金

</td>
<td width="50%">

### 🤖 AI 增强
- 🔍 **智能搜索** - Tavily 语义搜索
- 📰 **情绪分析** - 多源新闻聚合 + 评分
- 📈 **深度研究** - AI 生成研究报告
- 💡 **决策辅助** - 数据驱动的投资建议
- 🌐 **多语言支持** - 中英文自动识别

</td>
</tr>
</table>

---

## ⚙️ 配置说明

### 核心配置（`.env` 文件）

```bash
# 【必填】A股数据访问（申请地址：https://tushare.pro/）
TUSHARE_TOKEN=your_token_here

# 【可选】代理配置（访问美股数据时推荐）
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890

# 【可选】增强功能
TAVILY_API_KEY=your_key     # AI 搜索和研究
FINNHUB_API_KEY=your_key    # 增强新闻数据
NEWS_API_KEY=your_key       # 新闻聚合
```

<details>
<summary>📖 <b>完整配置说明</b></summary>

| 配置项          | 说明               | 默认值                         |
| --------------- | ------------------ | ------------------------------ |
| `REDIS_HOST`    | Redis 主机         | `redis`（Docker）/ `localhost` |
| `CACHE_ENABLED` | 是否启用缓存       | `true`                         |
| `CACHE_TTL`     | 缓存过期时间（秒） | `3600`                         |

详见：[配置指南](docs/GUIDE.md#配置详解)
</details>

---

## 📡 API 使用

### 核心接口示例

```bash
# 股票行情（支持 A股/美股/港股）
GET /api/quote?symbol=600519&market=CN

# 财务数据
GET /api/financial?symbol=AAPL&report_type=income

# 新闻情绪（返回情绪评分 -1~1）
GET /api/news/sentiment?symbol=TSLA&days=7

# AI 深度研究
POST /api/research
{
  "topic": "新能源汽车行业分析",
  "depth": "comprehensive"
}
```

**📚 完整接口文档**：启动服务后访问 http://localhost:9998/docs

---

## 🐳 Docker 部署

### 服务架构

| 端口   | 服务       | 说明                        |
| ------ | ---------- | --------------------------- |
| `9998` | FastAPI    | RESTful API + Swagger 文档  |
| `9999` | MCP Server | Model Context Protocol 服务 |
| `6379` | Redis      | 内部缓存（不对外暴露）      |

### 常用命令

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f stock-mcp

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 重新构建
docker-compose up -d --build
```

---

## 🛠️ 故障排查

<details>
<summary><b>❌ Redis 连接失败</b></summary>

```bash
# 检查配置
cat .env | grep REDIS_HOST
# 确保 Docker 环境使用: REDIS_HOST=redis

# 检查 Redis 状态
docker-compose ps redis
```
</details>

<details>
<summary><b>❌ yFinance 超时</b></summary>

```bash
# 检查代理配置
cat .env | grep PROXY
# Docker 环境应使用: HTTP_PROXY=http://host.docker.internal:7890
```
</details>

<details>
<summary><b>❌ Tushare 权限错误</b></summary>

确保 Token 有效且已配置到 `.env` 文件：
```bash
grep TUSHARE_TOKEN .env
```
</details>

**更多问题**：[完整故障排查指南](docs/GUIDE.md#故障排查)

---

## 📚 文档

- [📖 完整使用指南](docs/GUIDE.md) - 配置、部署、API 详解
- [🔧 开发文档](docs/DEVELOPMENT.md) - 架构设计、二次开发

---

## 🤝 参与贡献

欢迎提交 Issue 和 Pull Request！

```bash
# 1. Fork 项目
# 2. 创建特性分支
git checkout -b feature/amazing-feature

# 3. 提交代码
git commit -m "Add: amazing feature"

# 4. 推送并创建 PR
git push origin feature/amazing-feature
```

---

## 📄 开源协议

MIT License - 详见 [LICENSE](LICENSE)

---

<div align="center">

### 🙏 致谢

本项目基于以下优秀开源项目构建

[MCP](https://modelcontextprotocol.io/) • [FastAPI](https://fastapi.tiangolo.com/) • [AKShare](https://akshare.akfamily.xyz/) • [Tushare](https://tushare.pro/) • [yFinance](https://github.com/ranaroussi/yfinance) • [Tavily](https://tavily.com/)

---

**⭐️ 如果对你有帮助，请给个 Star ⭐️**

</div>
