# 📘 API 使用示例集

本文档提供各种实际场景下的API使用示例,帮助你快速上手。

## 目录

- [基础查询示例](#基础查询示例)
- [高级查询示例](#高级查询示例)
- [数据分析示例](#数据分析示例)
- [自动化脚本示例](#自动化脚本示例)
- [错误处理示例](#错误处理示例)

---

## 基础查询示例

### 场景1: 查询单只股票实时行情

```bash
# A股 - 贵州茅台
curl "http://localhost:9998/api/stock/news?symbol=600519"

# 美股 - 苹果
curl "http://localhost:9998/api/stock/news?symbol=AAPL"

# 港股 - 腾讯控股
curl "http://localhost:9998/api/stock/news?symbol=00700"
```

### 场景2: 查询历史价格数据

```bash
# 查询最近30天数据
curl "http://localhost:9998/stock/price?symbol=TSLA&start_date=2024-12-01&end_date=2025-01-01"

# 查询全年数据
curl "http://localhost:9998/stock/price?symbol=000001&start_date=2024-01-01&end_date=2024-12-31"
```

### 场景3: 检查今天是否可以交易

```bash
# 检查A股今天是否交易
curl "http://localhost:9998/api/calendar/is-trading-day?symbol=000001&check_date=$(date +%Y-%m-%d)"

# 检查美股今天是否交易
curl "http://localhost:9998/api/calendar/is-trading-day?symbol=AAPL&check_date=$(date +%Y-%m-%d)"
```

---

## 高级查询示例

### 场景4: 批量查询多只股票

```bash
# Python脚本
curl -X POST "http://localhost:9998/api/stock/quotes" \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"]
  }'
```

### 场景5: 获取指定时间范围的新闻

```bash
# 获取过去7天的新闻
curl "http://localhost:9998/api/stock/news/date?symbol=AAPL&target_date=$(date +%Y-%m-%d)&days_before=7"

# 获取过去30天的新闻
curl "http://localhost:9998/api/stock/news/date?symbol=600519&target_date=2025-01-01&days_before=30"
```

### 场景6: 查询财务基本面

```bash
# 查询当前财务数据
curl "http://localhost:9998/api/stock/fundamental?symbol=000008"

# 查询特定日期的财务数据
curl "http://localhost:9998/api/stock/fundamental?symbol=600519&curr_date=2024-12-31"
```

---

## 数据分析示例

### 场景7: 分析股票价格趋势

```python
import requests
import pandas as pd
import matplotlib.pyplot as plt

# 获取历史数据
response = requests.get(
    "http://localhost:9998/stock/price",
    params={
        "symbol": "AAPL",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31"
    }
)

# 解析AI生成的分析报告
analysis = response.json()["data"]
print(analysis)

# 可以进一步解析数据进行可视化
```

### 场景8: 对比多只股票表现

```python
import requests

symbols = ["AAPL", "MSFT", "GOOGL"]
quotes = []

# 批量查询
response = requests.post(
    "http://localhost:9998/api/stock/quotes",
    json={"symbols": symbols}
)

data = response.json()["data"]

# 对比涨跌幅
for stock in data:
    print(f"{stock['symbol']}: {stock['change_percent']}%")
```

### 场景9: 统计交易日数量

```python
import requests
from datetime import datetime, timedelta

# 计算本月交易日数量
today = datetime.now()
first_day = today.replace(day=1)

response = requests.get(
    "http://localhost:9998/api/calendar/trading-days",
    params={
        "symbol": "000001",
        "start_date": first_day.strftime("%Y-%m-%d"),
        "end_date": today.strftime("%Y-%m-%d")
    }
)

trading_days = response.json()["data"]["total_days"]
print(f"本月已有 {trading_days} 个交易日")
```

---

## 自动化脚本示例

### 场景10: 每日盯盘提醒

```bash
#!/bin/bash
# daily_monitor.sh - 每日股票监控脚本

SYMBOLS=("AAPL" "TSLA" "NVDA")
DATE=$(date +%Y-%m-%d)

for symbol in "${SYMBOLS[@]}"; do
  echo "=== $symbol ==="
  
  # 检查是否交易日
  is_trading=$(curl -s "http://localhost:9998/api/calendar/is-trading-day?symbol=$symbol&check_date=$DATE" | jq -r '.data.is_trading_day')
  
  if [ "$is_trading" = "true" ]; then
    # 获取实时行情
    curl -s "http://localhost:9998/api/stock/news?symbol=$symbol" | jq '.data'
  else
    echo "今天休市"
  fi
  echo ""
done
```

### 场景11: 定时抓取新闻

```python
# news_crawler.py
import requests
import schedule
import time
from datetime import datetime

def fetch_news(symbol):
    """抓取股票新闻"""
    response = requests.get(
        f"http://localhost:9998/api/stock/news?symbol={symbol}"
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n[{datetime.now()}] {symbol} 最新新闻:")
        for news in data.get("data", {}).get("news", [])[:3]:
            print(f"  - {news['title']}")

def monitor_stocks():
    """监控多只股票"""
    symbols = ["AAPL", "TSLA", "NVDA"]
    for symbol in symbols:
        fetch_news(symbol)

# 每小时执行一次
schedule.every().hour.do(monitor_stocks)

print("新闻监控已启动...")
while True:
    schedule.run_pending()
    time.sleep(60)
```

### 场景12: 交易日历提醒

```python
# trading_calendar.py
import requests
from datetime import datetime, timedelta

def get_next_trading_days(symbol, days=5):
    """获取未来N个交易日"""
    today = datetime.now()
    end_date = today + timedelta(days=30)  # 查询未来30天
    
    response = requests.get(
        "http://localhost:9998/api/calendar/trading-days",
        params={
            "symbol": symbol,
            "start_date": today.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d")
        }
    )
    
    trading_days = response.json()["data"]["trading_days"]
    return trading_days[:days]

# 查询A股未来5个交易日
next_days = get_next_trading_days("000001", 5)
print("A股未来5个交易日:")
for day in next_days:
    print(f"  - {day}")
```

---

## 错误处理示例

### 场景13: 优雅处理错误

```python
import requests
import time

def fetch_stock_price(symbol, max_retries=3):
    """带重试的股票价格查询"""
    
    for attempt in range(max_retries):
        try:
            response = requests.get(
                "http://localhost:9998/api/stock/news",
                params={"symbol": symbol},
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                # 限流错误,等待后重试
                wait_time = 2 ** attempt
                print(f"请求限流,等待 {wait_time} 秒...")
                time.sleep(wait_time)
            elif response.status_code == 400:
                # 客户端错误,不重试
                print(f"无效的股票代码: {symbol}")
                return None
            else:
                print(f"服务器错误: {response.status_code}")
                
        except requests.Timeout:
            print(f"请求超时 (尝试 {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"未知错误: {e}")
            return None
    
    print(f"达到最大重试次数,查询失败")
    return None

# 使用示例
result = fetch_stock_price("AAPL")
if result:
    print(result["data"])
```

### 场景14: 验证响应数据

```python
def safe_get_quote(symbol):
    """安全获取股票行情"""
    response = requests.get(
        f"http://localhost:9998/api/stock/news?symbol={symbol}"
    )
    
    data = response.json()
    
    # 检查响应状态
    if data.get("status") != "success":
        print(f"错误: {data.get('message')}")
        return None
    
    # 验证数据完整性
    quote_data = data.get("data", {})
    required_fields = ["ticker", "currentPrice", "marketCap"]
    
    for field in required_fields:
        if field not in quote_data:
            print(f"警告: 缺少字段 {field}")
    
    return quote_data

# 使用示例
quote = safe_get_quote("AAPL")
if quote:
    print(f"价格: ${quote['currentPrice']}")
    print(f"市值: ${quote['marketCap']}")
```

---

## 综合应用示例

### 场景15: 构建简单的股票分析工具

```python
# stock_analyzer.py
import requests
from datetime import datetime, timedelta

class StockAnalyzer:
    def __init__(self, base_url="http://localhost:9998"):
        self.base_url = base_url
    
    def get_quote(self, symbol):
        """获取实时行情"""
        response = requests.get(f"{self.base_url}/api/stock/news", params={"symbol": symbol})
        return response.json()["data"]
    
    def get_historical_price(self, symbol, days=30):
        """获取历史价格"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        response = requests.get(
            f"{self.base_url}/stock/price",
            params={
                "symbol": symbol,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d")
            }
        )
        return response.json()["data"]
    
    def get_fundamental(self, symbol):
        """获取基本面数据"""
        response = requests.get(
            f"{self.base_url}/api/stock/fundamental",
            params={"symbol": symbol}
        )
        return response.json()["data"]
    
    def analyze(self, symbol):
        """综合分析"""
        print(f"\n{'='*50}")
        print(f"股票分析报告: {symbol}")
        print(f"{'='*50}\n")
        
        # 1. 实时行情
        quote = self.get_quote(symbol)
        print("📊 实时行情:")
        print(f"  当前价格: ${quote['currentPrice']}")
        print(f"  涨跌幅: {float(quote['dailyChangePercent']):.2f}%")
        print(f"  市盈率: {quote.get('peRatio', 'N/A')}")
        
        # 2. 历史表现
        print("\n📈 历史表现 (30天):")
        historical = self.get_historical_price(symbol, 30)
        print(historical[:500] + "...")  # 显示前500字符
        
        # 3. 基本面
        try:
            fundamental = self.get_fundamental(symbol)
            print("\n💼 基本面数据:")
            print(f"  ROE: {fundamental.get('roe', 'N/A')}")
            print(f"  PE Ratio: {fundamental.get('pe_ratio', 'N/A')}")
        except:
            print("\n💼 基本面数据: 暂无")

# 使用示例
analyzer = StockAnalyzer()
analyzer.analyze("AAPL")
analyzer.analyze("600519")
```

### 场景16: 投资组合监控

```python
# portfolio_monitor.py
import requests
from tabulate import tabulate

class Portfolio:
    def __init__(self):
        self.base_url = "http://localhost:9998"
        self.holdings = {
            "AAPL": {"shares": 10, "cost_basis": 150.00},
            "TSLA": {"shares": 5, "cost_basis": 200.00},
            "600519": {"shares": 100, "cost_basis": 1500.00}
        }
    
    def get_current_prices(self):
        """批量获取当前价格"""
        symbols = list(self.holdings.keys())
        response = requests.post(
            f"{self.base_url}/api/stock/quotes",
            json={"symbols": symbols}
        )
        return {item["symbol"]: float(item["price"]) for item in response.json()["data"]}
    
    def calculate_performance(self):
        """计算投资表现"""
        prices = self.get_current_prices()
        
        portfolio_data = []
        total_cost = 0
        total_value = 0
        
        for symbol, holding in self.holdings.items():
            shares = holding["shares"]
            cost_basis = holding["cost_basis"]
            current_price = prices.get(symbol, 0)
            
            cost = shares * cost_basis
            value = shares * current_price
            profit = value - cost
            profit_pct = (profit / cost * 100) if cost > 0 else 0
            
            total_cost += cost
            total_value += value
            
            portfolio_data.append([
                symbol,
                shares,
                f"${cost_basis:.2f}",
                f"${current_price:.2f}",
                f"${value:.2f}",
                f"${profit:.2f}",
                f"{profit_pct:.2f}%"
            ])
        
        # 显示详细信息
        headers = ["股票", "持仓", "成本", "现价", "市值", "盈亏", "收益率"]
        print("\n投资组合表现:")
        print(tabulate(portfolio_data, headers=headers, tablefmt="grid"))
        
        # 显示汇总
        total_profit = total_value - total_cost
        total_return = (total_profit / total_cost * 100) if total_cost > 0 else 0
        
        print(f"\n总成本: ${total_cost:.2f}")
        print(f"总市值: ${total_value:.2f}")
        print(f"总盈亏: ${total_profit:.2f} ({total_return:.2f}%)")

# 运行监控
portfolio = Portfolio()
portfolio.calculate_performance()
```

---

## 使用技巧

### 💡 提示1: 使用 jq 格式化JSON输出

```bash
curl "http://localhost:9998/api/stock/news?symbol=AAPL" | jq '.'
```

### 💡 提示2: 保存响应到文件

```bash
curl "http://localhost:9998/stock/price?symbol=AAPL&start_date=2024-01-01&end_date=2024-12-31" \
  -o aapl_analysis.json
```

### 💡 提示3: 设置环境变量简化调用

```bash
# .bashrc 或 .zshrc
export STOCK_API="http://localhost:9998"
export STOCK_TOKEN="a7f3518b-2983-4d29-bd1d-15a13e470903"

# 使用
curl "$STOCK_API/api/stock/news?symbol=AAPL" \
  -H "Authorization: $STOCK_TOKEN"
```

---

## 相关文档

- [完整 API 文档](API.md)
- [使用指南](GUIDE.md)
- [OpenAPI 规范](../stock-mcp.openapi.json)

---

<div align="center">

**💡 发现更多用法?** [贡献你的示例](https://github.com/your-repo/pulls)

</div>
