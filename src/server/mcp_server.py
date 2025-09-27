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
from .services.news_service import RealtimeNewsAggregator
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
            self.news_service = RealtimeNewsAggregator(self.settings)
            logger.info("✅ 新闻服务初始化成功")
        except Exception as e:
            logger.error(f"❌ 新闻服务初始化失败: {e}")
            self.news_service = None

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
                agg = self.news_service
                if not agg:
                    return "❌ 新闻服务当前不可用"

                # 获取实时股票新闻
                news_items = agg.get_realtime_stock_news(symbol, days_back)

                # 格式化新闻报告
                report = agg.format_news_report(news_items, symbol)
                return report

            except Exception as e:
                logger.error(f"获取最新新闻失败: {e}")
                return f"❌ 获取 {symbol} 新闻失败: {str(e)}"


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
