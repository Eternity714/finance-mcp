"""
项目配置设置
"""

import os
from pathlib import Path
from typing import Optional
from functools import lru_cache

try:
    from dotenv import load_dotenv

    # 加载 .env 文件
    env_path = Path(__file__).parent.parent.parent / ".env"
    load_dotenv(env_path)
except ImportError:
    # 如果 python-dotenv 未安装，忽略错误
    pass


class Settings:
    """应用配置"""

    def __init__(self):
        # 应用基本信息
        self.app_name: str = os.getenv("APP_NAME", "Stock SSE-MCP Server")
        self.version: str = os.getenv("VERSION", "1.0.0")
        self.description: str = os.getenv(
            "DESCRIPTION", "基于SSE+HTTP POST的股票数据MCP服务器"
        )

        # 服务器配置
        self.host: str = os.getenv("HOST", "127.0.0.1")
        self.port: int = int(os.getenv("PORT", "8000"))
        self.debug: bool = os.getenv("DEBUG", "false").lower() == "true"

        # MCP 服务器配置
        self.mcp_server_name: str = os.getenv("MCP_SERVER_NAME", "stock-data-server")
        self.mcp_server_version: str = os.getenv("MCP_SERVER_VERSION", "1.0.0")

        # Redis配置
        self.redis_host: str = os.getenv("REDIS_HOST", "localhost")
        self.redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_db: int = int(os.getenv("REDIS_DB", "0"))
        self.redis_password: Optional[str] = os.getenv("REDIS_PASSWORD")

        # AKShare配置
        self.akshare_timeout: int = int(os.getenv("AKSHARE_TIMEOUT", "30"))

        # Tushare配置
        self.TUSHARE_TOKEN: Optional[str] = os.getenv("TUSHARE_TOKEN")

        # 新闻API配置
        self.finnhub_api_key: Optional[str] = os.getenv("FINNHUB_API_KEY")
        self.alpha_vantage_api_key: Optional[str] = os.getenv("ALPHA_VANTAGE_API_KEY")
        self.newsapi_key: Optional[str] = os.getenv("NEWSAPI_KEY")
        self.tavily_api_key: Optional[str] = os.getenv("TAVILY_API_KEY")

        # 缓存配置
        self.cache_ttl: int = int(os.getenv("CACHE_TTL", "3600"))  # 1小时
        self.market_cache_ttl: int = int(
            os.getenv("MARKET_CACHE_TTL", "86400")
        )  # 24小时

        # 日志配置
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.log_format: str = os.getenv(
            "LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )


@lru_cache()
def get_settings() -> Settings:
    """获取配置实例（单例模式）"""
    return Settings()


# MCP 特定配置
class MCPConfig:
    """MCP 服务器配置"""

    def __init__(self):
        self.settings = get_settings()

    @property
    def server_name(self) -> str:
        return self.settings.mcp_server_name

    @property
    def version(self) -> str:
        return self.settings.mcp_server_version

    @property
    def description(self) -> str:
        return self.settings.description

    @property
    def capabilities(self) -> dict:
        """MCP 服务器能力声明"""
        return {
            "tools": True,
            "resources": False,  # 暂不支持资源
            "prompts": False,  # 暂不支持提示
            "sampling": False,  # 暂不支持采样
        }
