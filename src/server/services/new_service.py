#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新闻服务 - 集成多数据源
支持A股、美股、港股的新闻获取，根据市场类型自动选择最优数据源组合

数据源优先级策略:
- A股: 1. 东方财富(免费) 2. 无备用
- 港股: 1. 东方财富 2. FinnHub
- 美股: 1. FinnHub 2. Alpha Vantage 3. NewsAPI

特点:
- 自动根据市场类型选择数据源
- 支持多数据源并行获取和合并
- 智能去重和优先级排序
- 统一的数据返回格式
"""

import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入配置
from src.config.settings import get_settings

# 导入服务
from src.server.services.akshare_service import AkshareService

# 导入工具
from src.server.utils.symbol_processor import get_symbol_processor

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("new_service")


@dataclass
class NewsArticle:
    """统一的新闻文章数据结构"""

    title: str
    content: str
    source: str  # 数据源名称: FinnHub, AlphaVantage, NewsAPI, EastMoney
    publish_time: str  # ISO格式时间字符串
    url: str
    symbol: str  # 相关股票代码
    relevance_score: float = 0.0  # 相关性评分 0-1
    sentiment: str = "neutral"  # positive, negative, neutral

    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return asdict(self)


class NewsDataSource:
    """新闻数据源基类"""

    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled
        self.settings = get_settings()

    def is_available(self) -> bool:
        """检查数据源是否可用"""
        return self.enabled

    def fetch_news(
        self, symbol: str, start_date: datetime, end_date: datetime
    ) -> List[NewsArticle]:
        """获取新闻数据 - 子类实现"""
        raise NotImplementedError


class FinnHubNewsSource(NewsDataSource):
    """FinnHub 新闻数据源"""

    def __init__(self):
        super().__init__("FinnHub")
        self.api_key = os.getenv("FINNHUB_API_KEY", "")
        self.enabled = bool(self.api_key)

    def is_available(self) -> bool:
        return self.enabled and bool(self.api_key)

    def fetch_news(
        self, symbol: str, start_date: datetime, end_date: datetime
    ) -> List[NewsArticle]:
        """从 FinnHub 获取新闻"""
        if not self.is_available():
            logger.warning(f"[{self.name}] API密钥未配置，跳过")
            return []

        logger.info(
            f"[{self.name}] 获取 {symbol} 的新闻: {start_date.date()} 到 {end_date.date()}"
        )

        url = "https://finnhub.io/api/v1/company-news"
        params = {
            "symbol": symbol,
            "from": start_date.strftime("%Y-%m-%d"),
            "to": end_date.strftime("%Y-%m-%d"),
            "token": self.api_key,
        }

        try:
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if not data:
                    logger.info(f"[{self.name}] 未找到 {symbol} 的新闻数据")
                    return []

                news_list = []
                for item in data:
                    try:
                        news = NewsArticle(
                            title=item.get("headline", ""),
                            content=item.get("summary", ""),
                            source=self.name,
                            publish_time=datetime.fromtimestamp(
                                item.get("datetime", 0)
                            ).isoformat(),
                            url=item.get("url", ""),
                            symbol=symbol,
                            relevance_score=0.8,  # FinnHub数据质量较高
                        )
                        news_list.append(news)
                    except Exception as e:
                        logger.warning(f"[{self.name}] 解析新闻项失败: {e}")
                        continue

                logger.info(f"[{self.name}] ✅ 获取到 {len(news_list)} 条新闻")
                return news_list

            elif response.status_code == 401:
                logger.error(f"[{self.name}] API密钥无效")
                return []
            else:
                logger.error(f"[{self.name}] 请求失败: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"[{self.name}] 请求异常: {e}")
            return []


class AlphaVantageNewsSource(NewsDataSource):
    """Alpha Vantage 新闻数据源"""

    def __init__(self):
        super().__init__("AlphaVantage")
        self.api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "")
        self.enabled = bool(self.api_key)

    def is_available(self) -> bool:
        return self.enabled and bool(self.api_key)

    def fetch_news(
        self, symbol: str, start_date: datetime, end_date: datetime
    ) -> List[NewsArticle]:
        """从 Alpha Vantage 获取新闻"""
        if not self.is_available():
            logger.warning(f"[{self.name}] API密钥未配置，跳过")
            return []

        logger.info(
            f"[{self.name}] 获取 {symbol} 的新闻: {start_date.date()} 到 {end_date.date()}"
        )

        url = "https://www.alphavantage.co/query"
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": symbol,
            "apikey": self.api_key,
            "limit": 100,
        }

        try:
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()

                if "feed" not in data:
                    logger.info(f"[{self.name}] 未找到 {symbol} 的新闻数据")
                    return []

                news_list = []
                for item in data.get("feed", []):
                    try:
                        # 解析时间
                        time_str = item.get("time_published", "")
                        if time_str:
                            pub_time = datetime.strptime(time_str, "%Y%m%dT%H%M%S")
                        else:
                            pub_time = datetime.now()

                        # 过滤时间范围
                        if not (start_date <= pub_time <= end_date):
                            continue

                        # 获取情感分析
                        sentiment_score = item.get("overall_sentiment_score", 0)
                        if sentiment_score > 0.15:
                            sentiment = "positive"
                        elif sentiment_score < -0.15:
                            sentiment = "negative"
                        else:
                            sentiment = "neutral"

                        news = NewsArticle(
                            title=item.get("title", ""),
                            content=item.get("summary", ""),
                            source=self.name,
                            publish_time=pub_time.isoformat(),
                            url=item.get("url", ""),
                            symbol=symbol,
                            relevance_score=abs(sentiment_score),
                            sentiment=sentiment,
                        )
                        news_list.append(news)

                    except Exception as e:
                        logger.warning(f"[{self.name}] 解析新闻项失败: {e}")
                        continue

                logger.info(f"[{self.name}] ✅ 获取到 {len(news_list)} 条新闻")
                return news_list
            else:
                logger.error(f"[{self.name}] 请求失败: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"[{self.name}] 请求异常: {e}")
            return []


class NewsAPISource(NewsDataSource):
    """NewsAPI 新闻数据源"""

    def __init__(self, use_proxy: bool = False):
        super().__init__("NewsAPI")
        self.api_key = os.getenv("NEWSAPI_KEY", "")
        self.enabled = bool(self.api_key)
        self.proxies = None

        if use_proxy:
            self.proxies = {
                "http": "http://127.0.0.1:7890",
                "https": "http://127.0.0.1:7890",
            }

    def is_available(self) -> bool:
        return self.enabled and bool(self.api_key)

    def fetch_news(
        self, symbol: str, start_date: datetime, end_date: datetime
    ) -> List[NewsArticle]:
        """从 NewsAPI 获取新闻"""
        if not self.is_available():
            logger.warning(f"[{self.name}] API密钥未配置，跳过")
            return []

        # NewsAPI 免费版只支持最近30天
        days_diff = (end_date - start_date).days
        if days_diff > 30:
            logger.warning(f"[{self.name}] 免费版仅支持30天内数据，调整查询范围")
            start_date = end_date - timedelta(days=30)

        logger.info(
            f"[{self.name}] 获取 {symbol} 的新闻: {start_date.date()} 到 {end_date.date()}"
        )

        # 构建查询关键词
        query = f"{symbol}"

        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "from": start_date.strftime("%Y-%m-%d"),
            "to": end_date.strftime("%Y-%m-%d"),
            "apiKey": self.api_key,
        }

        try:
            response = requests.get(
                url, params=params, proxies=self.proxies, timeout=10
            )

            if response.status_code == 200:
                data = response.json()

                if data.get("status") != "ok" or not data.get("articles"):
                    logger.info(f"[{self.name}] 未找到 {symbol} 的新闻数据")
                    return []

                news_list = []
                for item in data.get("articles", []):
                    try:
                        pub_time_str = item.get("publishedAt", "")
                        if pub_time_str:
                            pub_time = datetime.fromisoformat(
                                pub_time_str.replace("Z", "+00:00")
                            )
                        else:
                            pub_time = datetime.now()

                        news = NewsArticle(
                            title=item.get("title", ""),
                            content=item.get("description", "")
                            or item.get("content", ""),
                            source=self.name,
                            publish_time=pub_time.isoformat(),
                            url=item.get("url", ""),
                            symbol=symbol,
                            relevance_score=0.7,
                        )
                        news_list.append(news)

                    except Exception as e:
                        logger.warning(f"[{self.name}] 解析新闻项失败: {e}")
                        continue

                logger.info(f"[{self.name}] ✅ 获取到 {len(news_list)} 条新闻")
                return news_list

            elif response.status_code == 426:
                logger.warning(f"[{self.name}] 需要升级订阅以访问历史数据")
                return []
            else:
                logger.error(f"[{self.name}] 请求失败: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"[{self.name}] 请求异常: {e}")
            return []


class EastMoneyNewsSource(NewsDataSource):
    """东方财富(AkShare) 新闻数据源"""

    def __init__(self):
        super().__init__("EastMoney")
        self.akshare_service = AkshareService()
        self.enabled = True  # 免费服务，默认启用

    def is_available(self) -> bool:
        return self.enabled

    def fetch_news(
        self, symbol: str, start_date: datetime, end_date: datetime
    ) -> List[NewsArticle]:
        """从东方财富获取新闻"""
        logger.info(
            f"[{self.name}] 获取 {symbol} 的新闻: {start_date.date()} 到 {end_date.date()}"
        )

        try:
            # 获取新闻数据
            df = self.akshare_service.get_stock_news_em(symbol, max_news=100)

            if df is None or df.empty:
                logger.info(f"[{self.name}] 未找到 {symbol} 的新闻数据")
                return []

            # 查找时间列
            time_column = None
            for col in ["发布时间", "时间", "日期", "date", "publish_time"]:
                if col in df.columns:
                    time_column = col
                    break

            if not time_column:
                logger.warning(
                    f"[{self.name}] 未找到时间列，可用列: {df.columns.tolist()}"
                )
                return []

            # 过滤时间范围
            news_list = []
            for _, row in df.iterrows():
                try:
                    # 解析时间
                    time_str = str(row[time_column])
                    try:
                        pub_time = pd.to_datetime(time_str)
                    except Exception:
                        # 尝试其他格式
                        pub_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")

                    # 时区处理
                    if pub_time.tzinfo is None:
                        pub_time = pub_time.replace(tzinfo=None)
                    else:
                        pub_time = pub_time.replace(tzinfo=None)

                    # 过滤时间范围
                    if not (start_date <= pub_time <= end_date):
                        continue

                    # 提取标题和内容 (使用东方财富的实际列名)
                    title = str(
                        row.get("新闻标题", row.get("标题", row.get("title", "")))
                    )
                    content = str(
                        row.get("新闻内容", row.get("内容", row.get("content", "")))
                    )
                    url = str(row.get("新闻链接", row.get("链接", row.get("url", ""))))

                    news = NewsArticle(
                        title=title,
                        content=content,
                        source=self.name,
                        publish_time=pub_time.isoformat(),
                        url=url,
                        symbol=symbol,
                        relevance_score=0.9,  # 东方财富针对性强
                    )
                    news_list.append(news)

                except Exception as e:
                    logger.warning(f"[{self.name}] 解析新闻项失败: {e}")
                    continue

            logger.info(f"[{self.name}] ✅ 获取到 {len(news_list)} 条新闻")
            return news_list

        except Exception as e:
            logger.error(f"[{self.name}] 请求异常: {e}")
            return []


class MultiSourceNewsService:
    """多数据源新闻服务"""

    def __init__(self, use_proxy_for_newsapi: bool = False):
        """
        初始化多数据源新闻服务

        Args:
            use_proxy_for_newsapi: NewsAPI是否使用代理
        """
        self.symbol_processor = get_symbol_processor()

        # 初始化所有数据源
        self.sources = {
            "finnhub": FinnHubNewsSource(),
            "alphavantage": AlphaVantageNewsSource(),
            "newsapi": NewsAPISource(use_proxy=use_proxy_for_newsapi),
            "eastmoney": EastMoneyNewsSource(),
        }

        # 数据源优先级策略
        self.priority_strategy = {
            "A股": ["eastmoney"],  # 只有东方财富支持
            "港股": ["eastmoney", "finnhub"],  # 东方财富优先，FinnHub备用
            "美股": ["finnhub", "alphavantage", "newsapi"],  # FinnHub最优
        }

        logger.info("✅ 多数据源新闻服务初始化成功")
        self._log_available_sources()

    def _log_available_sources(self):
        """记录可用数据源"""
        available = [
            name for name, source in self.sources.items() if source.is_available()
        ]
        unavailable = [
            name for name, source in self.sources.items() if not source.is_available()
        ]

        if available:
            logger.info(f"✅ 可用数据源: {', '.join(available)}")
        if unavailable:
            logger.warning(f"⚠️ 不可用数据源: {', '.join(unavailable)}")

    def get_news_for_date(
        self, symbol: str, target_date: Optional[str] = None, days_before: int = 30
    ) -> Dict:
        """
        获取指定日期的股票新闻

        Args:
            symbol: 股票代码
            target_date: 目标日期 (YYYY-MM-DD)，默认为当前日期
            days_before: 向前查询的天数，默认30天

        Returns:
            Dict: 包含新闻列表和元数据的字典
        """
        # 处理目标日期
        if target_date:
            try:
                end_date = datetime.strptime(target_date, "%Y-%m-%d")
            except ValueError:
                logger.error(f"日期格式错误: {target_date}，应为 YYYY-MM-DD")
                return {
                    "success": False,
                    "error": "日期格式错误",
                    "symbol": symbol,
                }
        else:
            end_date = datetime.now()

        # 计算开始日期
        start_date = end_date - timedelta(days=days_before)

        return self.get_news(symbol, start_date, end_date)

    def get_news(self, symbol: str, start_date: datetime, end_date: datetime) -> Dict:
        """
        获取指定时间范围的股票新闻

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            Dict: 包含新闻列表和元数据的字典
        """
        # 分析股票代码
        symbol_info = self.symbol_processor.process_symbol(symbol)
        market = symbol_info["market"]

        logger.info("=" * 80)
        logger.info(f"📰 获取新闻: {symbol} ({market})")
        logger.info(f"📅 时间范围: {start_date.date()} 到 {end_date.date()}")
        logger.info("=" * 80)

        # 获取该市场的数据源优先级列表
        source_priority = self.priority_strategy.get(market, [])

        if not source_priority:
            logger.warning(f"⚠️ 市场 {market} 没有配置数据源")
            return {
                "success": False,
                "error": f"不支持的市场: {market}",
                "symbol": symbol,
                "market": market,
            }

        # 根据市场选择合适的股票代码格式
        formatted_symbols = self._get_formatted_symbols(
            symbol, symbol_info, source_priority
        )

        # 并行获取所有数据源的新闻
        all_news = self._fetch_from_multiple_sources(
            source_priority, formatted_symbols, start_date, end_date
        )

        # 去重和排序
        unique_news = self._deduplicate_news(all_news)
        sorted_news = sorted(unique_news, key=lambda x: x.publish_time, reverse=True)

        # 统计信息
        source_stats = {}
        for news in sorted_news:
            source_stats[news.source] = source_stats.get(news.source, 0) + 1

        logger.info("=" * 80)
        logger.info(f"✅ 新闻获取完成: 共 {len(sorted_news)} 条")
        for source, count in source_stats.items():
            logger.info(f"   - {source}: {count} 条")
        logger.info("=" * 80)

        return {
            "success": True,
            "symbol": symbol,
            "market": market,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_count": len(sorted_news),
            "source_stats": source_stats,
            "news": [news.to_dict() for news in sorted_news],
        }

    def _get_formatted_symbols(
        self, original_symbol: str, symbol_info: Dict, source_priority: List[str]
    ) -> Dict[str, str]:
        """
        根据数据源需求格式化股票代码

        Returns:
            Dict: {source_name: formatted_symbol}
        """
        formatted = {}
        formats = symbol_info["formats"]

        for source_name in source_priority:
            if source_name == "finnhub":
                formatted[source_name] = formats[
                    "yfinance"
                ]  # FinnHub使用类似yfinance格式
            elif source_name == "alphavantage":
                formatted[source_name] = formats["yfinance"]
            elif source_name == "newsapi":
                formatted[source_name] = formats["news_api"]
            elif source_name == "eastmoney":
                formatted[source_name] = formats["akshare"]
            else:
                formatted[source_name] = original_symbol

        logger.info(f"📝 代码格式化: {formatted}")
        return formatted

    def _fetch_from_multiple_sources(
        self,
        source_names: List[str],
        formatted_symbols: Dict[str, str],
        start_date: datetime,
        end_date: datetime,
    ) -> List[NewsArticle]:
        """
        并行从多个数据源获取新闻

        Args:
            source_names: 数据源名称列表（按优先级排序）
            formatted_symbols: 格式化后的股票代码字典
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            List[NewsArticle]: 所有数据源的新闻列表
        """
        all_news = []

        # 使用线程池并行获取
        with ThreadPoolExecutor(max_workers=len(source_names)) as executor:
            future_to_source = {}

            for source_name in source_names:
                source = self.sources.get(source_name)
                if not source or not source.is_available():
                    logger.warning(f"⚠️ 数据源 {source_name} 不可用，跳过")
                    continue

                symbol = formatted_symbols.get(source_name, "")
                future = executor.submit(
                    source.fetch_news, symbol, start_date, end_date
                )
                future_to_source[future] = source_name

            # 收集结果
            for future in as_completed(future_to_source):
                source_name = future_to_source[future]
                try:
                    news_list = future.result()
                    all_news.extend(news_list)
                except Exception as e:
                    logger.error(f"❌ 数据源 {source_name} 获取失败: {e}")

        return all_news

    def _deduplicate_news(self, news_list: List[NewsArticle]) -> List[NewsArticle]:
        """
        新闻去重

        策略:
        1. 优先基于URL去重
        2. 其次基于标题+发布时间组合去重
        3. 保留有标题的新闻
        """
        if not news_list:
            return []

        unique_news = []
        seen_urls = set()
        seen_combinations = set()

        for news in news_list:
            # 策略1: URL去重（最可靠）
            if news.url and news.url.strip():
                url_key = news.url.strip().lower()
                if url_key in seen_urls:
                    continue
                seen_urls.add(url_key)

            # 策略2: 标题+时间组合去重
            title_key = news.title.lower().strip()
            time_key = news.publish_time[:10] if news.publish_time else ""
            combination_key = f"{title_key}|{time_key}"

            # 跳过空标题或已见过的组合
            if not title_key or combination_key in seen_combinations:
                continue

            seen_combinations.add(combination_key)
            unique_news.append(news)

        logger.info(f"📊 去重: {len(news_list)} 条 -> {len(unique_news)} 条")
        return unique_news


# ============ 便捷函数 ============


def get_news_service(use_proxy: bool = False) -> MultiSourceNewsService:
    """
    获取新闻服务实例

    Args:
        use_proxy: NewsAPI是否使用代理

    Returns:
        MultiSourceNewsService: 新闻服务实例
    """
    return MultiSourceNewsService(use_proxy_for_newsapi=use_proxy)


def get_stock_news(
    symbol: str,
    target_date: Optional[str] = None,
    days_before: int = 30,
    use_proxy: bool = False,
) -> Dict:
    """
    获取股票新闻的便捷函数

    Args:
        symbol: 股票代码
        target_date: 目标日期 (YYYY-MM-DD)，默认为当前日期
        days_before: 向前查询的天数，默认30天
        use_proxy: NewsAPI是否使用代理

    Returns:
        Dict: 新闻数据
    """
    service = get_news_service(use_proxy=use_proxy)
    return service.get_news_for_date(symbol, target_date, days_before)


def get_stock_news_range(
    symbol: str, start_date: str, end_date: str, use_proxy: bool = False
) -> Dict:
    """
    获取指定时间范围的股票新闻

    Args:
        symbol: 股票代码
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        use_proxy: NewsAPI是否使用代理

    Returns:
        Dict: 新闻数据
    """
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as e:
        logger.error(f"日期格式错误: {e}")
        return {
            "success": False,
            "error": "日期格式错误，应为 YYYY-MM-DD",
        }

    service = get_news_service(use_proxy=use_proxy)
    return service.get_news(symbol, start, end)
