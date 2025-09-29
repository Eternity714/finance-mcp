import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import pandas as pd
from dataclasses import dataclass

# 导入自定义异常
try:
    from ..utils import DataNotFoundError
except ImportError:
    # 当作为独立模块运行时的备用
    class DataNotFoundError(Exception):
        pass


# 导入统一的股票代码处理器
try:
    from ..utils.symbol_processor import get_symbol_processor
except ImportError:
    # 当作为独立模块运行时的备用
    def get_symbol_processor():
        return None


@dataclass
class DataSourceConfig:
    """数据源配置"""

    name: str
    priority: int  # 优先级，数字越小优先级越高
    enabled: bool = True
    timeout: int = 10
    retry_count: int = 3


class MarketDataService:
    """增强市场数据服务，实现完善的降级机制"""

    def __init__(self):
        self.data_sources = []

        # 简单的内存缓存
        self.cache = {}

        # 初始化数据源配置
        self._init_data_sources()

        # 初始化各数据源服务
        self._init_services()

    def _init_data_sources(self):
        """初始化数据源配置"""
        self.data_source_configs = [
            DataSourceConfig("tushare", 2, True),
            DataSourceConfig("akshare", 1, True),
            DataSourceConfig("yfinance", 3, True),
            DataSourceConfig("fallback", 99, True),
        ]

    def _init_services(self):
        """初始化各数据源服务"""
        self.services = {}

        # 1. Tushare服务
        try:
            from .tushare_service import TushareService

            self.services["tushare"] = TushareService()
            print("✅ Tushare数据源已启用")
        except Exception as e:
            print(f"⚠️ Tushare数据源初始化失败: {e}")

        # 2. AKShare服务
        try:
            from .akshare_service import AkshareService

            self.services["akshare"] = AkshareService()
            print("✅ AKShare数据源已启用")
        except Exception as e:
            print(f"⚠️ AKShare数据源初始化失败: {e}")

        # 3. YFinance服务（用于美股）
        try:
            from .yfinance_service import YFinanceService

            self.services["yfinance"] = YFinanceService()
            print("✅ YFinance数据源已启用")
        except Exception as e:
            print(f"⚠️ YFinance数据源初始化失败: {e}")

    def get_stock_data(
        self, symbol: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """
        获取股票数据，实现智能降级

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            pd.DataFrame: 股票数据
        """
        # 使用统一的代码处理器
        processor = get_symbol_processor()
        if processor:
            symbol_info = processor.process_symbol(symbol)
            # 将中文市场名称转换为英文简化名称
            market_cn = symbol_info["market"]
            if symbol_info["is_china"]:
                market = "china"
            elif symbol_info["is_hk"]:
                market = "hk"
            elif symbol_info["is_us"]:
                market = "us"
            else:
                market = "us"  # 默认美股
            data_sources = symbol_info["data_sources"]["market_data"]
        else:
            # 降级到原始方法
            market = self._determine_stock_market(symbol)

        if market == "china":
            data_sources = ["tushare", "akshare", "fallback"]
        elif market == "hk":
            data_sources = ["yfinance", "tushare", "akshare", "fallback"]
        else:  # US market
            data_sources = ["yfinance", "akshare", "fallback"]

        print(f"🔍 检测股票 {symbol} 属于 {market} 市场")

        # 尝试各数据源
        last_error = None
        for source in data_sources:
            try:
                print(f"🔄 尝试从 {source} 获取 {symbol} 数据...")
                data = self._get_data_from_source(
                    source, symbol, start_date, end_date, market
                )

                if data is not None and not data.empty:
                    print(f"✅ 成功从 {source} 获取 {symbol} 数据 ({len(data)} 条记录)")

                    # 标准化数据格式
                    standardized_data = self._standardize_data(data, source)

                    return standardized_data
                else:
                    print(f"⚠️ {source} 未返回数据")

            except Exception as e:
                print(f"❌ {source} 数据获取失败: {e}")
                last_error = e
                continue

        # 所有数据源都失败
        raise DataNotFoundError(
            f"所有数据源都无法获取 {symbol} 的数据。最后错误: {last_error}"
        )

    def _get_data_from_source(
        self, source: str, symbol: str, start_date: str, end_date: str, market: str
    ) -> Optional[pd.DataFrame]:
        """从指定数据源获取数据"""

        if source == "tushare" and "tushare" in self.services:
            # 根据市场类型调用不同的Tushare接口
            return self._get_tushare_data(symbol, start_date, end_date, market)

        elif source == "akshare" and "akshare" in self.services:
            # 根据市场类型调用不同的AKShare接口
            return self._get_akshare_data(symbol, start_date, end_date, market)

        elif source == "yfinance" and "yfinance" in self.services:
            return self._get_yfinance_data(symbol, start_date, end_date)

        elif source == "fallback":
            return self._get_fallback_data(symbol, start_date, end_date, market)

        return None

    def _get_tushare_data(
        self, symbol: str, start_date: str, end_date: str, market: str
    ) -> Optional[pd.DataFrame]:
        """根据市场类型从Tushare获取数据"""
        try:
            # 获取服务和代码处理器
            tushare_service = self.services["tushare"]
            processor = get_symbol_processor()

            # 在调用具体方法前，先将 symbol 标准化为 Tushare 需要的格式
            tushare_symbol = processor.get_tushare_format(symbol)

            if market == "china":
                # 中国A股市场，使用标准接口
                print(f"📈 使用Tushare获取A股数据: {symbol} -> {tushare_symbol}")
                return tushare_service.get_stock_daily(
                    tushare_symbol, start_date, end_date
                )

            elif market == "hk":
                # 港股市场，使用港股接口
                print(f"🇭🇰 使用Tushare获取港股数据: {symbol} -> {tushare_symbol}")
                return tushare_service.get_hk_daily(
                    tushare_symbol, start_date, end_date
                )

            else:
                # 美股市场，Tushare不支持，跳过
                print(f"⚠️ Tushare不支持美股市场，跳过: {symbol} -> {tushare_symbol}")
                return None

        except Exception as e:
            print(f"❌ Tushare获取{market}市场数据失败: {symbol}, 错误: {e}")
            return None

    def _get_akshare_data(
        self, symbol: str, start_date: str, end_date: str, market: str
    ) -> Optional[pd.DataFrame]:
        """从AKShare获取数据，根据市场类型调用不同接口"""
        try:
            # 获取服务和代码处理器
            akshare_service = self.services["akshare"]
            processor = get_symbol_processor()

            # 在调用具体方法前，先将 symbol 标准化为 AKShare 需要的格式
            akshare_symbol = processor.get_akshare_format(symbol)

            if market == "china":
                # 中国A股市场
                print(f"📈 使用AKShare获取A股数据: {symbol} -> {akshare_symbol}")
                return akshare_service.get_stock_daily(
                    akshare_symbol, start_date, end_date
                )

            elif market == "hk":
                # 港股市场
                print(f"🇭🇰 使用AKShare获取港股数据: {symbol} -> {akshare_symbol}")
                return akshare_service.get_hk_daily(
                    akshare_symbol, start_date, end_date
                )

            else:
                # 美股市场，使用AKShare美股接口
                print(f"🇺🇸 使用AKShare获取美股数据: {symbol} -> {akshare_symbol}")
                return akshare_service.get_us_daily(
                    akshare_symbol, start_date, end_date
                )

        except Exception as e:
            print(f"❌ AKShare获取{market}市场数据失败: {symbol}, 错误: {e}")
            return None

    def _get_yfinance_data(
        self, symbol: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """从YFinance获取数据"""
        try:
            # 获取服务和代码处理器
            yfinance_service = self.services["yfinance"]
            processor = get_symbol_processor()

            # 标准化代码为 yfinance 格式
            yfinance_symbol = processor.get_yfinance_format(symbol)
            print(f"🌍 使用YFinance获取数据: {symbol} -> {yfinance_symbol}")

            return yfinance_service.get_stock_daily(
                yfinance_symbol, start_date, end_date
            )
        except Exception as e:
            print(f"❌ YFinance获取数据失败: {e}")
            return None

    def _get_fallback_data(
        self, symbol: str, start_date: str, end_date: str, market: str
    ) -> Optional[pd.DataFrame]:
        """备用数据获取方法"""
        print(f"⚠️ 使用备用方法获取 {symbol} 数据")

        # 这里可以实现备用逻辑，比如：
        # 1. 从本地数据库获取历史数据
        # 2. 使用简单的模拟数据
        # 3. 调用其他免费API

        # 返回空DataFrame表示无法获取
        return pd.DataFrame()

    def _standardize_data(self, data: pd.DataFrame, source: str) -> pd.DataFrame:
        """标准化数据格式"""
        if data.empty:
            return data

        # 确保日期列
        if "date" in data.columns:
            data["date"] = pd.to_datetime(data["date"])
        elif "trade_date" in data.columns:
            data["date"] = pd.to_datetime(data["trade_date"])

        # 确保基本列存在
        required_columns = ["date", "open", "high", "low", "close", "volume"]
        for col in required_columns:
            if col not in data.columns:
                print(f"⚠️ 缺少列 {col}，使用默认值填充")
                if col == "volume":
                    data[col] = 0
                else:
                    data[col] = 0.0

        # 添加数据源标识
        data["source"] = source

        return data.sort_values("date").reset_index(drop=True)

    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """获取股票基本信息"""
        # 检查缓存
        cache_key = f"stock_info_{symbol}"
        cached_info = self._get_from_cache(cache_key)
        if cached_info is not None:
            return cached_info

        market = self._determine_stock_market(symbol)

        # 根据市场选择数据源
        if market == "china":
            sources = ["tushare", "akshare"]
        elif market == "hk":
            sources = ["akshare", "yfinance"]
        else:  # US market
            sources = ["akshare", "yfinance"]

        last_error = None
        for source in sources:
            try:
                if source == "tushare" and "tushare" in self.services:
                    info = self.services["tushare"].get_stock_info(symbol)
                elif source == "akshare" and "akshare" in self.services:
                    info = self._get_akshare_info(symbol, market)
                elif source == "yfinance" and "yfinance" in self.services:
                    info = self._get_yfinance_info(symbol)
                else:
                    continue

                if info:
                    info["source"] = source
                    self._set_cache(cache_key, info)
                    return info

            except Exception as e:
                print(f"❌ {source} 获取股票信息失败: {e}")
                last_error = e
                continue

        raise DataNotFoundError(f"无法获取 {symbol} 的基本信息: {last_error}")

    def _get_akshare_info(self, symbol: str, market: str) -> Dict[str, Any]:
        """从AKShare获取股票信息，根据市场类型调用不同接口"""
        try:
            akshare_service = self.services["akshare"]

            if market == "china":
                # 中国A股市场
                print(f"📈 使用AKShare获取A股信息: {symbol}")
                return akshare_service.get_stock_info(symbol)

            elif market == "hk":
                # 港股市场
                print(f"🇭🇰 使用AKShare获取港股信息: {symbol}")
                return akshare_service.get_hk_info(symbol)

            else:
                # 美股市场，使用AKShare美股接口
                print(f"🇺🇸 使用AKShare获取美股信息: {symbol}")
                return akshare_service.get_us_info(symbol)

        except Exception as e:
            print(f"❌ AKShare获取{market}市场信息失败: {symbol}, 错误: {e}")
            return {}

    def _get_yfinance_info(self, symbol: str) -> Dict[str, Any]:
        """从YFinance获取股票信息"""
        try:
            yfinance_service = self.services["yfinance"]
            processor = get_symbol_processor()
            yfinance_symbol = processor.get_yfinance_format(symbol)

            info = yfinance_service.get_stock_info(yfinance_symbol)
            if info:
                return {
                    "symbol": symbol,
                    "name": info.get("longName", ""),
                    "sector": info.get("sector", ""),
                    "industry": info.get("industry", ""),
                    "market_cap": info.get("marketCap", 0),
                }
            return {}
        except Exception as e:
            print(f"❌ YFinance获取股票信息失败: {e}")
            return {}

    def generate_stock_report(self, symbol: str, start_date: str, end_date: str) -> str:
        """生成股票分析报告"""
        try:
            # 获取股票数据
            data = self.get_stock_data(symbol, start_date, end_date)

            if data.empty:
                return f"❌ 无法获取 {symbol} 的数据"

            # 获取股票基本信息
            try:
                info = self.get_stock_info(symbol)
            except:
                info = {"name": "未知", "source": "未知"}

            # 生成报告
            report = self._generate_markdown_report(
                symbol, data, info, start_date, end_date
            )
            return report

        except Exception as e:
            return f"❌ 生成 {symbol} 报告失败: {e}"

    def _generate_markdown_report(
        self,
        symbol: str,
        data: pd.DataFrame,
        info: Dict,
        start_date: str,
        end_date: str,
    ) -> str:
        """生成Markdown格式的分析报告"""
        # 根据市场确定货币符号
        market = self._determine_stock_market(symbol)
        currency_symbol = "¥"  # 默认为人民币
        if market == "hk":
            currency_symbol = "HK$"
        elif market == "us":
            currency_symbol = "$"

        # 修复中文显示乱码问题
        if "name" in info and isinstance(info["name"], bytes):
            try:
                info["name"] = info["name"].decode("utf-8")
            except:
                info["name"] = "未知"

        if data.empty:
            return f"❌ {symbol} 无可用数据"

        latest = data.iloc[-1]
        first = data.iloc[0]

        # 计算基本统计
        price_change = latest["close"] - first["close"]
        price_change_pct = (price_change / first["close"]) * 100

        high_52w = data["high"].max()
        low_52w = data["low"].min()
        avg_volume = data["volume"].mean()

        report = f"""# {symbol} 股票分析报告

## 📊 基本信息
- **股票名称**: {info.get('name', '未知')}
- **股票代码**: {symbol}
- **分析期间**: {start_date} 至 {end_date}
- **数据来源**: {data['source'].iloc[0] if 'source' in data.columns else '未知'}

## 💰 价格表现
- **当前价格**: {currency_symbol}{latest['close']:.2f}
- **期间涨跌**: {currency_symbol}{price_change:+.2f} ({price_change_pct:+.2f}%)
- **期间最高**: {currency_symbol}{high_52w:.2f}
- **期间最低**: {currency_symbol}{low_52w:.2f}
- **平均成交量**: {avg_volume:,.0f}

## 📈 技术指标
"""

        # 计算简单移动平均
        if len(data) >= 5:
            data["ma5"] = data["close"].rolling(5).mean()
            ma5_current = (
                data["ma5"].iloc[-1] if not pd.isna(data["ma5"].iloc[-1]) else 0
            )
            report += f"- **5日均线**: {currency_symbol}{ma5_current:.2f}\n"

        if len(data) >= 20:
            data["ma20"] = data["close"].rolling(20).mean()
            ma20_current = (
                data["ma20"].iloc[-1] if not pd.isna(data["ma20"].iloc[-1]) else 0
            )
            report += f"- **20日均线**: {currency_symbol}{ma20_current:.2f}\n"

        # 趋势分析
        if len(data) >= 5:
            recent_trend = (
                "上升" if latest["close"] > data["close"].iloc[-5] else "下降"
            )
            report += f"- **近期趋势**: {recent_trend}\n"

        # 添加风险提示
        report += f"""
## ⚠️ 风险提示
本报告仅供参考，不构成投资建议。股市有风险，投资需谨慎。

---
*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""

        return report

    def get_market_status(self) -> Dict[str, Any]:
        """获取各数据源状态"""
        status = {
            "timestamp": datetime.now().isoformat(),
            "sources": {},
            "cache_size": len(self.cache),
        }

        for name, service in self.services.items():
            try:
                # 简单的健康检查
                if name == "tushare" and hasattr(service, "connected"):
                    status["sources"][name] = (
                        "connected" if service.connected else "disconnected"
                    )
                elif name == "yfinance":
                    status["sources"][name] = "available"
                else:
                    status["sources"][name] = "unknown"
            except:
                status["sources"][name] = "error"

        return status

    def _determine_stock_market(self, symbol: str) -> str:
        """判断股票所属市场，使用统一的股票市场分类器"""
        processor = get_symbol_processor()
        if processor:
            return processor.get_market_simple_name(symbol)
        else:
            # 备用逻辑
            from ..utils.stock_market_classifier import classify_stock

            classification = classify_stock(symbol)
            if classification["is_china"]:
                return "china"
            elif classification["is_hk"]:
                return "hk"
            elif classification["is_us"]:
                return "us"
            else:
                return "us"

    def _get_from_cache(self, key: str) -> Optional[Any]:
        """从缓存获取数据"""
        return self.cache.get(key)

    def _set_cache(self, key: str, value: Any) -> None:
        """设置缓存数据"""
        self.cache[key] = value
