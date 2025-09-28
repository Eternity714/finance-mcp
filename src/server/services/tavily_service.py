"""
Tavily 搜索引擎服务
"""

import logging
from typing import List, Dict, Any, Optional

from ...config.settings import Settings

logger = logging.getLogger(__name__)

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None


class TavilyService:
    """封装 Tavily 搜索引擎 API"""

    def __init__(self, settings: Settings):
        """
        初始化 Tavily 服务

        Args:
            settings: 应用配置
        """
        self.api_key = settings.tavily_api_key
        self.client = None

        if TavilyClient is None:
            logger.warning("⚠️ Tavily 客户端库未安装 (pip install tavily-python)")
            return

        if not self.api_key:
            logger.warning("⚠️ TAVILY_API_KEY 未配置，Tavily 服务将不可用")
        else:
            try:
                self.client = TavilyClient(api_key=self.api_key)
                logger.info("✅ Tavily 服务初始化成功")
            except Exception as e:
                logger.error(f"❌ Tavily 客户端初始化失败: {e}")

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.client is not None

    def search(
        self,
        query: str,
        search_depth: str = "basic",
        max_results: int = 5,
        include_answer: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        执行 Tavily 搜索

        Args:
            query: 搜索查询
            search_depth: 搜索深度 ("basic" 或 "advanced")
            max_results: 返回的最大结果数
            include_answer: 是否包含 AI 生成的答案

        Returns:
            搜索结果字典，如果服务不可用或搜索失败则返回 None
        """
        if not self.is_available():
            logger.error("Tavily 服务不可用，无法执行搜索")
            return None

        try:
            logger.info(f"🔍 [Tavily] 正在执行搜索: '{query}' (深度: {search_depth})")
            response = self.client.search(
                query=query,
                search_depth=search_depth,
                max_results=max_results,
                include_answer=include_answer,
            )
            logger.info(
                f"✅ [Tavily] 搜索完成，获取到 {len(response.get('results', []))} 条结果"
            )
            return response
        except Exception as e:
            logger.error(f"❌ [Tavily] 搜索失败: {e}")
            return None
