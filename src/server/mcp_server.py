"""
基于 FastMCP 的股票数据 MCP 服务器
使用 SSE + HTTP POST 双向通信模式
"""

import builtins
import logging
import sys
from functools import partial

# 导入本地服务
from .services.akshare_service import AkshareService
from .services.fundamentals_service import FundamentalsAnalysisService
from .services.market_service import MarketDataService
from .services.new_service import get_news_service
from .services.tavily_service import TavilyService
from .utils.redis_cache import get_redis_cache
from ..config.settings import get_settings

# 配置日志到stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# 重定向print到stderr，避免污染MCP的stdout
_original_print = builtins.print
builtins.print = partial(_original_print, file=sys.stderr)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    logger.error(f"❌ FastMCP未安装: {e}")
    sys.exit(1)


class StockMCPServer:
    """股票数据 MCP 服务器"""

    def __init__(self):
        """初始化服务器和服务"""
        self.settings = get_settings()
        self.redis_cache = get_redis_cache()

        # 初始化服务
        try:
            self.akshare_service = AkshareService()
            logger.info("✅ AkShare服务初始化成功")
        except Exception as e:
            logger.error(f"❌ AkShare服务初始化失败: {e}")
            self.akshare_service = None

        try:
            self.fundamentals_service = FundamentalsAnalysisService()
            logger.info("✅ 基本面服务初始化成功")
        except Exception as e:
            logger.error(f"❌ 基本面服务初始化失败: {e}")
            self.fundamentals_service = None

        try:
            self.market_service = MarketDataService()
            logger.info("✅ 市场数据服务初始化成功")
        except Exception as e:
            logger.error(f"❌ 市场数据服务初始化失败: {e}")
            self.market_service = None

        try:
            self.news_service = get_news_service(use_proxy=False)
            logger.info("✅ 新闻服务初始化成功")
        except Exception as e:
            logger.error(f"❌ 新闻服务初始化失败: {e}")
            self.news_service = None

        try:
            self.tavily_service = TavilyService(self.settings)
            logger.info("✅ Tavily研究服务初始化成功")
        except Exception as e:
            logger.error(f"❌ Tavily研究服务初始化失败: {e}")
            self.tavily_service = None

    def create_mcp_server(self, port: int = None) -> FastMCP:
        """创建并配置 FastMCP 服务器"""
        mcp = FastMCP(
            name="stock-data-server",
            instructions="股票数据分析MCP服务器，提供实时行情、基本面分析、新闻情绪等功能",
            port=port,
            # 设置为无状态模式，允许独立的JSON-RPC请求（如 tools/list）
            stateless_http=True,
        )

        # 注册工具
        self._register_core_tools(mcp)

        logger.info("🚀 MCP服务器创建完成，已注册所有工具")
        return mcp

    def _register_core_tools(self, mcp: FastMCP):
        """注册核心工具"""

        @mcp.tool()
        async def get_stock_price_data(
            symbol: str, start_date: str, end_date: str
        ) -> str:
            """获取股票价格数据和分析报告

            Args:
                symbol: 股票代码，支持A股(如000001)、港股(如00700)、美股(如AAPL)
                start_date: 开始日期，格式YYYY-MM-DD
                end_date: 结束日期，格式YYYY-MM-DD

            Returns:
                包含股票数据分析的详细报告
            """
            try:
                if self.market_service:
                    report = self.market_service.generate_stock_report(
                        symbol, start_date, end_date
                    )
                    return report
                else:
                    return "❌ 市场数据服务当前不可用"

            except Exception as e:
                logger.error(f"获取股票价格数据失败: {e}")
                return f"❌ 获取 {symbol} 股票价格数据失败: {str(e)}"

        @mcp.tool()
        async def get_financial_report(symbol: str) -> str:
            """获取基本面财务报告

            Args:
                symbol: 股票代码

            Returns:
                详细的基本面分析报告，包含估值指标、盈利能力、财务状况等
            """
            try:
                if self.fundamentals_service:
                    report = self.fundamentals_service.generate_fundamentals_report(
                        symbol
                    )
                    return report
                else:
                    return "❌ 基本面分析服务当前不可用"

            except Exception as e:
                logger.error(f"获取基本面分析失败: {e}")
                return f"❌ 获取 {symbol} 基本面分析失败: {str(e)}"

        @mcp.tool()
        async def get_latest_news(symbol: str, days_back: int = 30) -> str:
            """获取股票最新新闻

            Args:
                symbol: 股票代码
                days_back: 获取最近几天的新闻，默认30天

            Returns:
                相关新闻列表和情绪分析报告
            """
            try:
                service = self.news_service
                if not service:
                    return "❌ 新闻服务当前不可用"

                # 获取实时股票新闻
                result = service.get_news_for_date(symbol, None, days_back)

                if not result.get("success", False):
                    error_msg = result.get("error", "获取新闻失败")
                    return f"❌ 获取 {symbol} 新闻失败: {error_msg}"

                # 格式化新闻报告
                news_list = result.get("news", [])
                if not news_list:
                    return f"📰 {symbol} 最近 {days_back} 天没有找到新闻"

                report = f"# {symbol} 实时新闻分析报告\n\n"
                report += f"📅 时间范围: {result['start_date'][:10]}"
                report += f" 到 {result['end_date'][:10]}\n"
                report += f"📊 新闻总数: {result['total_count']}条\n"
                report += f"🌐 市场: {result['market']}\n\n"

                # 数据源统计
                report += "## 📡 数据源统计\n"
                for source, count in result.get("source_stats", {}).items():
                    report += f"- {source}: {count}条\n"
                report += "\n"

                # 显示新闻列表
                report += "## 📰 新闻详情\n\n"
                for i, news in enumerate(news_list[:20], 1):
                    report += f"### {i}. {news['title']}\n"
                    report += f"**来源**: {news['source']} | "
                    report += f"**时间**: {news['publish_time'][:19]}\n"
                    if news.get("content"):
                        content = news["content"][:200]
                        report += f"{content}...\n"
                    if news.get("url"):
                        report += f"🔗 [查看原文]({news['url']})\n"
                    report += "\n"

                if len(news_list) > 20:
                    report += f"\n*还有 {len(news_list) - 20} 条新闻未显示*\n"

                return report

            except Exception as e:
                logger.error(f"获取最新新闻失败: {e}")
                return f"❌ 获取 {symbol} 新闻失败: {str(e)}"

        @mcp.tool()
        async def perform_deep_research(
            topic: str,
            research_type: str = "general",
            symbols: list[str] = None,
        ) -> str:
            """对指定主题或公司进行深入的网络搜索和研究，返回一份总结报告。
            此工具用于探索性分析，与其它获取特定数据的工具形成互补。

            Args:
                topic: 需要研究的核心主题。例如 "半导体行业的最新技术突破" 或 "AI芯片市场前景"。
                research_type: 研究类型。可选值: 'general' (通用), 'company_profile' (公司分析), 'competitor_analysis' (竞品分析), 'industry_analysis' (行业分析)。默认为 'general'。
                symbols: (可选) 相关的股票代码列表。例如 ['NVDA', 'AMD']。当进行公司或竞品分析时，提供此参数可以获得更精确的结果。

            Returns:
                一份Markdown格式的深度研究报告。
            """
            if not self.tavily_service or not self.tavily_service.is_available():
                return "❌ 深度研究服务当前不可用，请检查 TAVILY_API_KEY 配置。"

            try:
                # 1. 构建查询
                query = self._build_query(topic, research_type, symbols)
                logger.info(f"🔬 [深度研究] 类型: {research_type}, 最终查询: '{query}'")

                # 2. 执行搜索
                search_result = self.tavily_service.search(
                    query=query,
                    search_depth="advanced",
                    max_results=7,
                    include_answer=True,
                )

                if not search_result:
                    return f"❌ 未能获取关于 '{query}' 的研究结果。"

                # 3. 格式化报告
                return self._format_research_report(topic, search_result)

            except Exception as e:
                logger.error(f"执行深度研究失败: {e}")
                return f"❌ 执行关于 '{topic}' 的深度研究时发生错误: {str(e)}"

    def _build_query(
        self, topic: str, research_type: str, symbols: list[str] | None
    ) -> str:
        """根据研究类型和参数构建更精确的Tavily查询语句"""
        if not symbols or research_type not in [
            "company_profile",
            "competitor_analysis",
        ]:
            return topic

        # 获取内部基本面数据以丰富查询
        internal_data_summary = []
        if self.fundamentals_service:
            for symbol in symbols:
                try:
                    data = self.fundamentals_service.get_fundamental_data(symbol)
                    summary = (
                        f"{data.company_name}({symbol}): "
                        f"市值 {self.fundamentals_service._format_number(data.market_cap)}元, "
                        f"P/E {data.pe_ratio:.2f}, "
                        f"ROE {data.roe:.2f}%"
                    )
                    internal_data_summary.append(summary)
                except Exception as e:
                    logger.warning(f"获取 {symbol} 内部数据失败: {e}")

        internal_summary_str = "; ".join(internal_data_summary)

        if research_type == "company_profile":
            return (
                f"深入分析公司 {symbols[0]} ({topic}) 的业务模式、核心竞争力、财务状况和未来增长前景。"
                f"已知信息: {internal_summary_str}"
            )
        elif research_type == "competitor_analysis":
            symbol_str = ", ".join(symbols)
            return (
                f"对比分析 {symbol_str} 这几家公司在 '{topic}' 领域的竞争格局、"
                f"各自的优势与劣势、市场份额和未来战略。已知信息: {internal_summary_str}"
            )

        return topic

    def _format_research_report(self, topic: str, search_result: dict) -> str:
        """格式化深度研究报告"""
        report = f"# 深度研究报告: {topic}\n\n"

        if search_result.get("answer"):
            report += f"## 核心摘要 (AI生成)\n\n{search_result['answer']}\n\n"

        if search_result.get("results"):
            report += "## 关键信息来源与摘录\n\n"
            for i, item in enumerate(search_result["results"]):
                report += f"### {i+1}. [{item.get('title', '无标题')}]({item.get('url', '#')})\n"
                report += f"**来源**: {item.get('source', '未知')}\n"
                report += f"> {item.get('content', '无内容')}\n\n---\n\n"

        return report


async def run_mcp_server():
    """运行 MCP 服务器"""
    try:
        server = StockMCPServer()
        mcp = server.create_mcp_server()

        logger.info("🚀 启动股票数据MCP服务器...")
        logger.info(f"服务器名称: {mcp.name}")

        logger.info(
            "✅ 已注册3个核心工具: get_stock_price_data, get_financial_report, get_latest_news"
        )

        # 使用正确的 FastMCP 运行方法 (同步函数)
        mcp.run()

    except Exception as e:
        logger.error(f"❌ MCP服务器运行失败: {e}")
        raise


if __name__ == "__main__":
    # 直接运行同步函数，不使用 asyncio.run()
    server = StockMCPServer()
    mcp = server.create_mcp_server()

    logger.info("🚀 启动股票数据MCP服务器...")
    logger.info(f"服务器名称: {mcp.name}")
    logger.info(
        "✅ 已注册3个核心工具: get_stock_price_data, get_financial_report, get_latest_news"
    )

    mcp.run()
