# app/api/news_service.py
import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os
from dataclasses import dataclass

# 从项目配置中导入Settings
from ...config.settings import Settings
from .akshare_service import AkshareService
from .tavily_service import TavilyService

# 导入统一的股票代码处理器
from ..utils.symbol_processor import get_symbol_processor


# --- 1. 定义自定义异常 ---
class NewsNotFoundError(Exception):
    """当API调用成功但未返回任何新闻数据时引发的自定义异常。"""

    pass


@dataclass
class NewsItem:
    """新闻项目数据结构"""

    title: str
    content: str
    source: str
    publish_time: datetime
    url: str
    urgency: str  # high, medium, low
    relevance_score: float


class RealtimeNewsAggregator:
    """实时新闻聚合器"""

    def __init__(self, settings: Settings):
        self.headers = {"User-Agent": "TradingAgents-CN/1.0"}
        # 从配置对象中获取API密钥
        self.finnhub_key = settings.finnhub_api_key
        self.alpha_vantage_key = settings.alpha_vantage_api_key
        self.newsapi_key = settings.newsapi_key

        # 初始化 Tavily 服务
        self.tavily_service = TavilyService(settings)

        print("✅ RealtimeNewsAggregator 初始化成功")
        if not self.finnhub_key:
            print("⚠️ FINNHUB_API_KEY 未配置")
        if not self.tavily_service.is_available():
            print("⚠️ Tavily 服务未配置或初始化失败，将跳过深度研究")

    # --- 2. 修改核心数据获取函数，使其在无数据时抛出异常 ---
    def get_realtime_stock_news(
        self, ticker: str, days_back: int = 30
    ) -> List[NewsItem]:
        """
        聚合所有来源的实时股票新闻。
        如果所有来源都没有数据，则抛出 NewsNotFoundError。
        """
        # 对股票代码进行标准化处理
        processor = get_symbol_processor()
        symbol_info = processor.process_symbol(ticker)

        stock_info = symbol_info  # 保持兼容性
        standardized_ticker = symbol_info["formats"]["news_api"]

        print(f"🔍 [新闻聚合] 原始代码: {ticker} -> 标准化代码: {standardized_ticker}")
        print(
            f"📊 [股票分析] {ticker} -> {symbol_info['market']} | {symbol_info['exchange']} | {symbol_info['board']}"
        )

        all_news = []

        # 1. FinnHub实时新闻 (如果配置了Key)
        if self.finnhub_key:
            try:
                # _get_finnhub_realtime_news 内部不抛出“未找到”异常，仅返回列表
                # 聚合器负责判断最终结果
                all_news.extend(
                    self._get_finnhub_realtime_news(standardized_ticker, days_back)
                )
            except Exception as e:
                # 捕获API连接等其他错误
                print(f"❌ 调用FinnHub新闻源时出错: {e}")

        # 2. Alpha Vantage新闻 (如果配置了Key)
        if self.alpha_vantage_key:
            try:
                all_news.extend(
                    self._get_alpha_vantage_news(standardized_ticker, days_back)
                )
            except Exception as e:
                print(f"❌ 调用Alpha Vantage新闻源时出错: {e}")

        # 3. NewsAPI新闻 (如果配置了Key)
        if self.newsapi_key:
            try:
                all_news.extend(self._get_newsapi_news(standardized_ticker, days_back))
            except Exception as e:
                print(f"❌ 调用NewsAPI新闻源时出错: {e}")

        # 4. 中文财经新闻源 (基于dataflows中的实现)
        try:
            all_news.extend(self._get_chinese_finance_news(ticker, days_back))
        except Exception as e:
            print(f"❌ 调用中文财经新闻源时出错: {e}")

        # 5. Tavily 深度网络搜索 (作为补充)
        if self.tavily_service.is_available():
            try:
                query = f"关于 {symbol_info.get('name', ticker)} ({ticker}) 的最新市场分析、新闻和深度见解"
                tavily_news = self._get_tavily_research_as_news(query)
                all_news.extend(tavily_news)
            except Exception as e:
                print(f"❌ 调用 Tavily 研究时出错: {e}")

        # --- 核心改动 ---
        # 在尝试所有新闻源后，如果列表仍为空，则抛出异常
        if not all_news:
            raise NewsNotFoundError(
                f"未能从任何配置的新闻源获取到关于 {ticker} 的新闻。"
            )

        unique_news = self._deduplicate_news(all_news)
        return sorted(unique_news, key=lambda x: x.publish_time, reverse=True)

    def _get_tavily_research_as_news(self, query: str) -> List[NewsItem]:
        """使用 Tavily 进行深度研究，并将结果转换为 NewsItem 格式"""
        search_result = self.tavily_service.search(
            query, search_depth="basic", max_results=5
        )
        if not search_result or not search_result.get("results"):
            return []

        news_items = []
        # 首先，将 Tavily 的 AI 总结答案作为一个特殊的新闻项
        if search_result.get("answer"):
            news_items.append(
                NewsItem(
                    title="[Tavily AI 总结]",
                    content=search_result["answer"],
                    source="Tavily AI",
                    publish_time=datetime.now(),
                    url="",
                    urgency="high",
                    relevance_score=1.0,
                )
            )

        # 然后，处理具体的搜索结果
        for item in search_result["results"]:
            news_items.append(
                NewsItem(
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    source=item.get("source", "Tavily"),
                    publish_time=datetime.now(),  # Tavily不提供发布时间，使用当前时间
                    url=item.get("url", ""),
                    urgency="medium",
                    relevance_score=item.get("score", 0.8),
                )
            )
        print(f"✅ [Tavily] 获取到 {len(news_items)} 条研究结果")
        return news_items

    def _get_standardized_ticker_for_news(self, ticker: str, stock_info: dict) -> str:
        """
        为新闻API标准化股票代码

        Args:
            ticker: 原始股票代码
            stock_info: 股票分类信息

        Returns:
            str: 标准化后的股票代码
        """
        # 使用统一的代码处理器
        processor = get_symbol_processor()
        return processor.get_news_api_format(ticker)

    def _get_finnhub_realtime_news(self, ticker: str, days_back: int) -> List[NewsItem]:
        """
        从FinnHub获取实时新闻。
        此函数在API调用失败时打印错误并返回空列表，成功但无数据时也返回空列表。
        由上层聚合器决定是否抛出异常。
        """
        if not self.finnhub_key:
            return []

        print(f"🔍 [FinnHub] 正在获取 {ticker} 的新闻...")
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days_back)

            url = "https://finnhub.io/api/v1/company-news"
            params = {
                "symbol": ticker,
                "from": start_time.strftime("%Y-%m-%d"),
                "to": end_time.strftime("%Y-%m-%d"),
                "token": self.finnhub_key,
            }

            response = requests.get(
                url, params=params, headers=self.headers, timeout=10
            )
            response.raise_for_status()  # 如果发生HTTP错误 (如 401, 403, 500), 则会抛出异常

            news_data = response.json()
            # 如果 news_data 是空列表，直接返回空列表，让调用者处理
            if not news_data:
                print(f"ℹ️ [FinnHub] 未找到关于 {ticker} 的新闻。")
                return []

            news_items = []
            for item in news_data:
                publish_time = datetime.fromtimestamp(item.get("datetime", 0))
                if publish_time < start_time:
                    continue

                news_items.append(
                    NewsItem(
                        title=item.get("headline", ""),
                        content=item.get("summary", ""),
                        source="FinnHub",
                        publish_time=publish_time,
                        url=item.get("url", ""),
                        urgency=self._assess_news_urgency(
                            item.get("headline", ""), item.get("summary", "")
                        ),
                        relevance_score=self._calculate_relevance(
                            item.get("headline", ""), ticker
                        ),
                    )
                )
            print(f"✅ [FinnHub] 获取到 {len(news_items)} 条新闻")
            return news_items

        except requests.exceptions.RequestException as e:
            # 捕获网络或HTTP错误
            print(f"❌ [FinnHub] 新闻获取失败 (网络/HTTP错误): {e}")
            return []
        except Exception as e:
            # 捕获其他所有未知错误
            print(f"❌ [FinnHub] 新闻获取时发生未知错误: {e}")
            return []

    def _assess_news_urgency(self, title: str, content: str) -> str:
        """简单评估新闻紧急程度"""
        text = (title + " " + content).lower()
        high_urgency = [
            "breaking",
            "alert",
            "urgent",
            "halt",
            "suspend",
            "investigation",
            "lawsuit",
            "warning",
            "突发",
            "紧急",
            "暂停",
            "重大",
            "调查",
            "诉讼",
            "警告",
            "违规",
        ]
        medium_urgency = [
            "earnings",
            "report",
            "announce",
            "merger",
            "acquisition",
            "partnership",
            "guidance",
            "outlook",
            "new product",
            "launch",
            "财报",
            "发布",
            "宣布",
            "并购",
            "合作",
            "新品",
            "指引",
            "展望",
        ]

        if any(k in text for k in high_urgency):
            return "high"
        if any(k in text for k in medium_urgency):
            return "medium"
        return "low"

    def _calculate_relevance(self, title: str, ticker: str) -> float:
        """简单计算新闻相关性"""
        return 1.0 if ticker.lower() in title.lower() else 0.5

    def _deduplicate_news(self, news_items: List[NewsItem]) -> List[NewsItem]:
        """基于新闻标题进行去重"""
        seen_titles = set()
        unique_news = []
        for item in news_items:
            title_key = item.title.lower().strip()
            if title_key and title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_news.append(item)
        return unique_news

    def _get_alpha_vantage_news(self, ticker: str, days_back: int) -> List[NewsItem]:
        """从Alpha Vantage获取新闻"""
        if not self.alpha_vantage_key:
            return []

        print(f"🔍 [Alpha Vantage] 正在获取 {ticker} 的新闻...")
        try:
            url = "https://www.alphavantage.co/query"
            params = {
                "function": "NEWS_SENTIMENT",
                "tickers": ticker,
                "apikey": self.alpha_vantage_key,
                "limit": 50,
            }

            response = requests.get(
                url, params=params, headers=self.headers, timeout=10
            )
            response.raise_for_status()

            data = response.json()
            news_items = []

            if "feed" in data:
                start_time = datetime.now() - timedelta(days=days_back)

                for item in data["feed"]:
                    # 解析时间
                    time_str = item.get("time_published", "")
                    try:
                        publish_time = datetime.strptime(time_str, "%Y%m%dT%H%M%S")
                    except:
                        continue

                    # 检查时效性
                    if publish_time < start_time:
                        continue

                    news_items.append(
                        NewsItem(
                            title=item.get("title", ""),
                            content=item.get("summary", ""),
                            source="Alpha Vantage",
                            publish_time=publish_time,
                            url=item.get("url", ""),
                            urgency=self._assess_news_urgency(
                                item.get("title", ""), item.get("summary", "")
                            ),
                            relevance_score=self._calculate_relevance(
                                item.get("title", ""), ticker
                            ),
                        )
                    )

            print(f"✅ [Alpha Vantage] 获取到 {len(news_items)} 条新闻")
            return news_items

        except requests.exceptions.RequestException as e:
            print(f"❌ [Alpha Vantage] 新闻获取失败: {e}")
            return []
        except Exception as e:
            print(f"❌ [Alpha Vantage] 新闻获取时发生未知错误: {e}")
            return []

    def _get_newsapi_news(self, ticker: str, days_back: int) -> List[NewsItem]:
        """从NewsAPI获取新闻"""
        if not self.newsapi_key:
            return []

        print(f"🔍 [NewsAPI] 正在获取 {ticker} 的新闻...")
        try:
            # 构建搜索查询
            company_names = {
                "AAPL": "Apple",
                "TSLA": "Tesla",
                "NVDA": "NVIDIA",
                "MSFT": "Microsoft",
                "GOOGL": "Google",
            }

            query = f"{ticker} OR {company_names.get(ticker, ticker)}"

            url = "https://newsapi.org/v2/everything"
            params = {
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "from": (datetime.now() - timedelta(days=days_back)).isoformat(),
                "apiKey": self.newsapi_key,
            }

            response = requests.get(
                url, params=params, headers=self.headers, timeout=10
            )
            response.raise_for_status()

            data = response.json()
            news_items = []

            for item in data.get("articles", []):
                # 解析时间
                time_str = item.get("publishedAt", "")
                try:
                    publish_time = datetime.fromisoformat(
                        time_str.replace("Z", "+00:00")
                    )
                    # 移除时区信息，统一为naive datetime
                    publish_time = publish_time.replace(tzinfo=None)
                except:
                    continue

                news_items.append(
                    NewsItem(
                        title=item.get("title", ""),
                        content=item.get("description", ""),
                        source=item.get("source", {}).get("name", "NewsAPI"),
                        publish_time=publish_time,
                        url=item.get("url", ""),
                        urgency=self._assess_news_urgency(
                            item.get("title", ""), item.get("description", "")
                        ),
                        relevance_score=self._calculate_relevance(
                            item.get("title", ""), ticker
                        ),
                    )
                )

            print(f"✅ [NewsAPI] 获取到 {len(news_items)} 条新闻")
            return news_items

        except requests.exceptions.RequestException as e:
            print(f"❌ [NewsAPI] 新闻获取失败: {e}")
            return []
        except Exception as e:
            print(f"❌ [NewsAPI] 新闻获取时发生未知错误: {e}")
            return []

    def _get_chinese_finance_news(self, ticker: str, days_back: int) -> List[NewsItem]:
        """获取中文财经新闻，基于dataflows中的实现"""
        print(f"🔍 [中文财经] 正在获取 {ticker} 的中文财经新闻...")
        news_items = []

        # 使用统一的股票分类器判断市场类型
        processor = get_symbol_processor()
        symbol_info = processor.process_symbol(ticker)

        stock_info = symbol_info  # 保持兼容性

        print(
            f"📊 [股票分析] {ticker} -> {symbol_info['market']} | {symbol_info['exchange']} | {symbol_info['board']}"
        )

        # 1. 尝试使用东方财富新闻源 (支持A股和部分港股)
        try:
            # A股或港股都可以尝试东方财富
            if stock_info["is_china"] or stock_info["is_hk"]:
                # 处理股票代码格式
                clean_ticker = self._normalize_ticker_for_eastmoney(ticker, stock_info)

                # 使用 AkshareService 获取东方财富个股新闻
                try:
                    ak_service = AkshareService()
                    df = ak_service.get_stock_news_em(clean_ticker, max_news=20)
                    if df is not None and not df.empty:
                        start_time = datetime.now() - timedelta(days=days_back)

                        # 兼容多种列名
                        def _get_val(row, keys, default=""):
                            for k in keys:
                                if k in row and pd.notna(row.get(k)):
                                    return row.get(k)
                            return default

                        # 惰性导入 pandas 用于时间判断（如果可用）
                        try:
                            import pandas as pd  # type: ignore
                            from pandas import Timestamp  # type: ignore
                        except Exception:
                            pd = None  # type: ignore
                            Timestamp = None  # type: ignore

                        for _, row in df.iterrows():
                            # 标题/内容/链接
                            title = _get_val(row, ["标题", "新闻标题", "title"]) or ""
                            content = (
                                _get_val(row, ["内容", "新闻内容", "摘要", "summary"])
                                or ""
                            )
                            url = _get_val(row, ["链接", "新闻链接", "url"]) or ""

                            # 发布时间解析
                            time_raw = _get_val(
                                row,
                                ["时间", "发布时间", "日期", "date", "publish_time"],
                                "",
                            )
                            publish_time = None
                            try:
                                if isinstance(time_raw, datetime):
                                    publish_time = time_raw
                                elif Timestamp is not None and isinstance(time_raw, Timestamp):  # type: ignore
                                    publish_time = time_raw.to_pydatetime()
                                elif isinstance(time_raw, str) and time_raw:
                                    for fmt in (
                                        "%Y-%m-%d %H:%M:%S",
                                        "%Y-%m-%d %H:%M",
                                        "%Y-%m-%d",
                                    ):
                                        try:
                                            publish_time = datetime.strptime(
                                                time_raw, fmt
                                            )
                                            break
                                        except Exception:
                                            continue
                            except Exception:
                                publish_time = None

                            # 无法解析时间则跳过，或不过滤时效
                            if publish_time is not None and publish_time < start_time:
                                continue

                            news_items.append(
                                NewsItem(
                                    title=title,
                                    content=content,
                                    source="东方财富",
                                    publish_time=publish_time or datetime.now(),
                                    url=url,
                                    urgency=self._assess_news_urgency(title, content),
                                    relevance_score=self._calculate_relevance(
                                        title, ticker
                                    ),
                                )
                            )
                        print(f"✅ [中文财经·东方财富] 获取到 {len(news_items)} 条新闻")
                except Exception as e:
                    print(
                        f"❌ [中文财经] 调用 AkshareService 获取东方财富新闻失败: {e}"
                    )

        except Exception as e:
            print(f"❌ [中文财经] 东方财富新闻获取失败: {e}")

        # 2. 财联社等RSS源 (对所有市场都尝试)
        try:
            rss_news = self._get_chinese_rss_news(ticker, days_back)
            news_items.extend(rss_news)
        except Exception as e:
            print(f"❌ [中文财经] RSS新闻获取失败: {e}")

        print(f"✅ [中文财经] 获取到 {len(news_items)} 条中文新闻")
        return news_items

    def _normalize_ticker_for_eastmoney(self, ticker: str, stock_info: dict) -> str:
        """为东方财富API标准化股票代码"""
        if stock_info["is_china"]:
            # A股：移除后缀
            return (
                ticker.replace(".SH", "")
                .replace(".SZ", "")
                .replace(".SS", "")
                .replace(".XSHE", "")
                .replace(".XSHG", "")
            )
        elif stock_info["is_hk"]:
            # 港股：使用5位数字格式
            clean_code = ticker.replace(".HK", "").replace(".hk", "")
            if clean_code.isdigit():
                return clean_code.zfill(5)
            return clean_code
        else:
            # 其他市场：返回原始代码
            return ticker

    def _is_china_stock(self, ticker: str) -> bool:
        """判断是否为中国股票"""
        from ..utils.stock_market_classifier import is_china_stock

        return is_china_stock(ticker)

    def _get_eastmoney_news(self, ticker: str, days_back: int) -> List[NewsItem]:
        """获取东方财富新闻（模拟实现）"""
        # 实际应该集成dataflows中的akshare_utils.get_stock_news_em
        # 这里返回模拟数据
        return []

    def _get_chinese_rss_news(self, ticker: str, days_back: int) -> List[NewsItem]:
        """获取中文RSS新闻源"""
        news_items = []

        # RSS源列表（可以添加更多财经新闻RSS）
        rss_sources = [
            "http://feed.sina.com.cn/finance/roll/index.xml",
            "http://rss.cnstock.com/news/jgsz.xml",
        ]

        for rss_url in rss_sources:
            try:
                items = self._parse_rss_feed(rss_url, ticker, days_back)
                news_items.extend(items)
            except Exception as e:
                print(f"❌ 解析RSS源失败 {rss_url}: {e}")

        return news_items

    def _parse_rss_feed(
        self, rss_url: str, ticker: str, days_back: int
    ) -> List[NewsItem]:
        """解析RSS源"""
        try:
            import feedparser

            feed = feedparser.parse(rss_url)
            news_items = []

            if not feed or not feed.entries:
                return []

            start_time = datetime.now() - timedelta(days=days_back)

            for entry in feed.entries:
                try:
                    # 解析时间
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        import time

                        publish_time = datetime.fromtimestamp(
                            time.mktime(entry.published_parsed)
                        )
                    else:
                        continue

                    # 检查时效性
                    if publish_time < start_time:
                        continue

                    title = entry.title if hasattr(entry, "title") else ""
                    content = entry.description if hasattr(entry, "description") else ""

                    # 检查相关性
                    if (
                        ticker.lower() not in title.lower()
                        and ticker.lower() not in content.lower()
                    ):
                        continue

                    news_items.append(
                        NewsItem(
                            title=title,
                            content=content,
                            source="财经RSS",
                            publish_time=publish_time,
                            url=entry.link if hasattr(entry, "link") else "",
                            urgency=self._assess_news_urgency(title, content),
                            relevance_score=self._calculate_relevance(title, ticker),
                        )
                    )

                except Exception as e:
                    continue

            return news_items

        except ImportError:
            print("⚠️ feedparser库未安装，无法解析RSS源")
            return []
        except Exception as e:
            print(f"❌ RSS解析失败: {e}")
            return []

    # --- 3. 报告生成函数保持不变，它只负责格式化 ---
    def format_news_report(self, news_items: List[NewsItem], ticker: str) -> str:
        """将新闻列表格式化为Markdown报告"""
        if not news_items:
            # 这个判断仍然有用，作为一道防线，或者在不希望抛出异常的场景下直接调用
            return f"❌ 未获取到关于 {ticker} 的实时新闻数据。请检查API密钥或稍后再试。"

        high = [n for n in news_items if n.urgency == "high"]
        medium = [n for n in news_items if n.urgency == "medium"]

        report = f"# {ticker} 实时新闻分析报告\n\n"
        report += f"📅 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"📊 新闻总数 (去重后): {len(news_items)}条\n\n"

        if high:
            report += "## 🚨 紧急新闻\n\n"
            for news in high[:3]:  # 最多3条
                report += f"### {news.title}\n"
                report += f"**来源**: {news.source} | **时间**: {news.publish_time.strftime('%H:%M')}\n"
                report += f"> {news.content}\n\n[阅读原文]({news.url})\n\n"

        if medium:
            report += "## 📢 重要新闻\n\n"
            for news in medium[:5]:  # 最多5条
                report += f"### {news.title}\n"
                report += f"**来源**: {news.source} | **时间**: {news.publish_time.strftime('%H:%M')}\n"
                report += f"> {news.content}\n\n[阅读原文]({news.url})\n\n"

        # 添加低优先级新闻显示
        low = [n for n in news_items if n.urgency == "low"]
        if low and not high and not medium:
            # 如果没有高优先级和中优先级新闻，显示部分低优先级新闻
            report += "## 📰 一般新闻\n\n"
            for news in low[:8]:  # 最多8条
                report += f"### {news.title}\n"
                report += f"**来源**: {news.source} | **时间**: {news.publish_time.strftime('%H:%M')}\n"
                report += f"> {news.content}\n\n[阅读原文]({news.url})\n\n"
        elif low and (high or medium):
            # 如果有高优先级新闻，只显示最新的3条低优先级新闻
            report += "## 📰 其他新闻\n\n"
            for news in low[:3]:
                report += f"### {news.title}\n"
                report += f"**来源**: {news.source} | **时间**: {news.publish_time.strftime('%H:%M')}\n"
                report += f"> {news.content}\n\n[阅读原文]({news.url})\n\n"

        latest_news_time = max(n.publish_time for n in news_items)

        # 处理时区问题：将所有时间转换为naive datetime
        current_time = datetime.now()
        if latest_news_time.tzinfo is not None:
            # 如果新闻时间有时区信息，转换为本地时间并移除时区信息
            latest_news_time = latest_news_time.replace(tzinfo=None)

        time_diff_minutes = (current_time - latest_news_time).total_seconds() / 60

        report += f"\n## ⏰ 数据时效性\n"
        report += f"最新新闻发布于: **{time_diff_minutes:.0f}分钟前**\n"

        if time_diff_minutes < 30:
            report += "🟢 时效性: 优秀\n"
        elif time_diff_minutes < 60:
            report += "🟡 时效性: 良好\n"
        else:
            report += "🔴 时效性: 一般\n"

        return report
