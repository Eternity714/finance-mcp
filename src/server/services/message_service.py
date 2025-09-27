"""
消息处理服务
处理 JSON-RPC 请求和业务逻辑调用
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from .akshare_service import AkshareService
from .fundamentals_service import FundamentalsAnalysisService
from .news_service import RealtimeNewsAggregator

logger = logging.getLogger(__name__)


class MessageService:
    """消息处理服务"""

    def __init__(self):
        """初始化服务依赖"""
        try:
            self.akshare_service = AkshareService()
            logger.info("✅ AkShare服务已初始化")
        except Exception as e:
            logger.error(f"❌ AkShare服务初始化失败: {e}")
            self.akshare_service = None

        try:
            self.fundamentals_service = FundamentalsAnalysisService()
            logger.info("✅ 基本面服务已初始化")
        except Exception as e:
            logger.error(f"❌ 基本面服务初始化失败: {e}")
            self.fundamentals_service = None

        try:
            from ...config.settings import get_settings

            settings = get_settings()
            self.news_service = RealtimeNewsAggregator(settings)
            logger.info("✅ 新闻服务已初始化")
        except Exception as e:
            logger.error(f"❌ 新闻服务初始化失败: {e}")
            self.news_service = None

    async def handle_jsonrpc_request(
        self, method: str, params: Dict[str, Any], request_id: Optional[str] = None
    ) -> Any:
        """
        处理 JSON-RPC 请求

        Args:
            method: 方法名
            params: 参数
            request_id: 请求ID

        Returns:
            处理结果
        """
        logger.info(f"处理JSON-RPC请求: {method}")

        try:
            # 根据方法名路由到对应的处理函数
            if method == "get_stock_quote":
                return await self._handle_stock_quote(params)
            elif method == "get_stock_analysis":
                return await self._handle_stock_analysis(params)
            elif method == "get_market_overview":
                return await self._handle_market_overview(params)
            elif method == "get_stock_news":
                return await self._handle_stock_news(params)
            elif method == "get_market_sentiment":
                return await self._handle_market_sentiment(params)
            elif method == "refresh_cache":
                return await self._handle_refresh_cache(params)
            elif method == "get_system_status":
                return await self._handle_system_status(params)
            else:
                raise ValueError(f"未知的方法: {method}")

        except Exception as e:
            logger.error(f"处理JSON-RPC请求失败 {method}: {e}")
            raise

    async def _handle_stock_quote(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理股票行情请求"""
        symbol = params.get("symbol")
        if not symbol:
            raise ValueError("缺少股票代码参数")

        if not self.akshare_service:
            raise RuntimeError("AkShare服务不可用")

        # 判断市场类型并获取数据
        if len(symbol) == 6 and symbol.isdigit():
            # A股
            data = self.akshare_service.market_cache.get_china_stock_data(symbol)
            market = "A股"
        elif len(symbol) == 5 and symbol.isdigit():
            # 港股
            data = self.akshare_service.market_cache.get_hk_stock_data(symbol)
            market = "港股"
        else:
            # 美股
            data = self.akshare_service.market_cache.get_us_stock_data(symbol)
            market = "美股"

        if not data:
            raise ValueError(f"未找到股票 {symbol} 的行情数据")

        return {
            "symbol": symbol,
            "market": market,
            "quote": data,
            "timestamp": datetime.now().isoformat(),
        }

    async def _handle_stock_analysis(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理股票分析请求"""
        symbol = params.get("symbol")
        analysis_type = params.get("type", "fundamental")

        if not symbol:
            raise ValueError("缺少股票代码参数")

        result = {}

        if analysis_type in ["fundamental", "all"]:
            if self.fundamentals_service:
                try:
                    fundamental_data = self.fundamentals_service.get_comprehensive_data(
                        symbol
                    )
                    if fundamental_data:
                        result["fundamental"] = {
                            "pe_ratio": fundamental_data.pe_ratio,
                            "pb_ratio": fundamental_data.pb_ratio,
                            "roe": fundamental_data.roe,
                            "market_cap": fundamental_data.market_cap,
                            "eps": fundamental_data.eps,
                            "source": fundamental_data.source,
                        }
                except Exception as e:
                    logger.warning(f"获取基本面数据失败: {e}")
                    result["fundamental"] = {"error": str(e)}

        if analysis_type in ["technical", "all"]:
            # 技术分析可以在这里扩展
            result["technical"] = {"message": "技术分析功能开发中"}

        return {
            "symbol": symbol,
            "analysis_type": analysis_type,
            "analysis": result,
            "timestamp": datetime.now().isoformat(),
        }

    async def _handle_market_overview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理市场概览请求"""
        market = params.get("market", "china")

        if not self.akshare_service:
            raise RuntimeError("AkShare服务不可用")

        if market == "china":
            market_data = self.akshare_service.market_cache.get_china_market_data()
            market_name = "A股"
        elif market == "hk":
            market_data = self.akshare_service.market_cache.get_hk_market_data()
            market_name = "港股"
        elif market == "us":
            market_data = self.akshare_service.market_cache.get_us_market_data()
            market_name = "美股"
        else:
            raise ValueError("不支持的市场类型")

        if market_data is None or market_data.empty:
            raise ValueError(f"无法获取{market_name}市场数据")

        # 计算市场统计
        total_stocks = len(market_data)
        stats = {"total_stocks": total_stocks}

        if "涨跌幅" in market_data.columns:
            rising = len(market_data[market_data["涨跌幅"] > 0])
            falling = len(market_data[market_data["涨跌幅"] < 0])
            unchanged = total_stocks - rising - falling

            stats.update(
                {
                    "rising": rising,
                    "falling": falling,
                    "unchanged": unchanged,
                    "avg_change": float(market_data["涨跌幅"].mean()),
                }
            )

        return {
            "market": market_name,
            "stats": stats,
            "timestamp": datetime.now().isoformat(),
        }

    async def _handle_stock_news(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理股票新闻请求"""
        symbol = params.get("symbol")
        days = params.get("days", 7)

        if not symbol:
            raise ValueError("缺少股票代码参数")

        if not self.news_service:
            raise RuntimeError("新闻服务不可用")

        try:
            news_items = self.news_service.get_realtime_stock_news(symbol, days)

            # 转换为序列化友好的格式
            news_list = []
            for item in news_items[:20]:  # 最多返回20条新闻
                news_list.append(
                    {
                        "title": item.title,
                        "content": (
                            item.content[:200] + "..."
                            if len(item.content) > 200
                            else item.content
                        ),
                        "source": item.source,
                        "published_at": (
                            item.publish_time.isoformat()
                            if hasattr(item, "publish_time")
                            else None
                        ),
                        "url": getattr(item, "url", None),
                    }
                )

            return {
                "symbol": symbol,
                "days": days,
                "news_count": len(news_list),
                "news": news_list,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"获取股票新闻失败: {e}")
            raise RuntimeError(f"获取新闻失败: {str(e)}")

    async def _handle_market_sentiment(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理市场情绪分析请求"""
        symbol = params.get("symbol")

        if not symbol:
            raise ValueError("缺少股票代码参数")

        if not self.news_service:
            raise RuntimeError("新闻服务不可用")

        try:
            # 获取情绪分析（这里可以扩展更复杂的情绪分析逻辑）
            sentiment = {
                "symbol": symbol,
                "overall_sentiment": "neutral",  # 默认中性
                "confidence": 0.6,
                "analysis_time": datetime.now().isoformat(),
                "note": "基础情绪分析，可扩展更多指标",
            }

            return sentiment

        except Exception as e:
            logger.error(f"市场情绪分析失败: {e}")
            raise RuntimeError(f"情绪分析失败: {str(e)}")

    async def _handle_refresh_cache(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理缓存刷新请求"""
        market = params.get("market", "all")

        if not self.akshare_service:
            raise RuntimeError("AkShare服务不可用")

        try:
            if market == "all":
                results = self.akshare_service.market_cache.force_refresh()
                success_count = sum(1 for df in results.values() if df is not None)

                return {
                    "action": "refresh_all_markets",
                    "success_count": success_count,
                    "total_markets": 3,
                    "results": {
                        k: len(v) if v is not None else 0 for k, v in results.items()
                    },
                    "timestamp": datetime.now().isoformat(),
                }
            else:
                results = self.akshare_service.market_cache.force_refresh(market)
                df = results.get(market)

                return {
                    "action": f"refresh_{market}_market",
                    "success": df is not None,
                    "records": len(df) if df is not None else 0,
                    "timestamp": datetime.now().isoformat(),
                }

        except Exception as e:
            logger.error(f"刷新缓存失败: {e}")
            raise RuntimeError(f"缓存刷新失败: {str(e)}")

    async def _handle_system_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理系统状态请求"""
        status = {
            "services": {
                "akshare": self.akshare_service is not None,
                "fundamentals": self.fundamentals_service is not None,
                "news": self.news_service is not None,
            },
            "system_time": datetime.now().isoformat(),
            "uptime": "运行中",
        }

        # 获取缓存状态
        if self.akshare_service:
            try:
                cache_info = self.akshare_service.market_cache.get_cache_info()
                status["cache"] = cache_info
            except Exception as e:
                status["cache"] = {"error": str(e)}

        return status

    # REST API 兼容方法
    async def handle_stock_quote_request(self, symbol: str) -> Dict[str, Any]:
        """处理股票行情请求（REST API兼容）"""
        return await self._handle_stock_quote({"symbol": symbol})

    async def handle_stock_analysis_request(
        self, symbol: str, analysis_type: str = "fundamental"
    ) -> Dict[str, Any]:
        """处理股票分析请求（REST API兼容）"""
        return await self._handle_stock_analysis(
            {"symbol": symbol, "type": analysis_type}
        )

    async def handle_news_search_request(
        self, query: str, days: int = 7
    ) -> Dict[str, Any]:
        """处理新闻搜索请求（REST API兼容）"""
        return await self._handle_stock_news({"symbol": query, "days": days})

    async def get_available_methods(self) -> List[Dict[str, Any]]:
        """获取可用的方法列表"""
        methods = [
            {
                "name": "get_stock_quote",
                "description": "获取股票实时行情",
                "params": {
                    "symbol": {
                        "type": "string",
                        "required": True,
                        "description": "股票代码",
                    }
                },
            },
            {
                "name": "get_stock_analysis",
                "description": "获取股票分析",
                "params": {
                    "symbol": {
                        "type": "string",
                        "required": True,
                        "description": "股票代码",
                    },
                    "type": {
                        "type": "string",
                        "required": False,
                        "description": "分析类型: fundamental/technical/all",
                    },
                },
            },
            {
                "name": "get_market_overview",
                "description": "获取市场概览",
                "params": {
                    "market": {
                        "type": "string",
                        "required": False,
                        "description": "市场类型: china/hk/us",
                    }
                },
            },
            {
                "name": "get_stock_news",
                "description": "获取股票相关新闻",
                "params": {
                    "symbol": {
                        "type": "string",
                        "required": True,
                        "description": "股票代码",
                    },
                    "days": {
                        "type": "integer",
                        "required": False,
                        "description": "天数",
                    },
                },
            },
            {
                "name": "get_market_sentiment",
                "description": "获取市场情绪分析",
                "params": {
                    "symbol": {
                        "type": "string",
                        "required": True,
                        "description": "股票代码",
                    }
                },
            },
            {
                "name": "refresh_cache",
                "description": "刷新数据缓存",
                "params": {
                    "market": {
                        "type": "string",
                        "required": False,
                        "description": "市场类型: china/hk/us/all",
                    }
                },
            },
            {"name": "get_system_status", "description": "获取系统状态", "params": {}},
        ]

        return methods
