#!/usr/bin/env python3
"""
市场数据服务 - 优化版本
整合优化后的数据源（akshare_optimized, tushare_optimized, tdx_service, yfinance_service）
实现智能降级机制，并能够生成完整的市场技术分析报告
"""
import logging
import warnings
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from ..utils.symbol_processor import get_symbol_processor
from ..utils.data_source_strategy import get_data_source_strategy
from ..exception.exception import DataNotFoundError

logger = logging.getLogger("market_service")
warnings.filterwarnings("ignore")


class MarketDataService:
    """市场数据服务 - 支持多数据源降级和报告生成"""

    def __init__(self):
        """初始化市场数据服务"""
        self.symbol_processor = get_symbol_processor()
        self.strategy = get_data_source_strategy()
        self.services = {}
        self._init_services()

    def _init_services(self):
        """初始化各数据源服务"""
        # 1. Tushare优化服务
        try:
            from .tushare_service import get_tushare_service

            self.services["tushare"] = get_tushare_service()
            logger.info("✅ Tushare优化服务初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ Tushare优化服务初始化失败: {e}")

        # 2. AKShare优化服务
        try:
            from .akshare_service import get_akshare_service

            self.services["akshare"] = get_akshare_service()
            logger.info("✅ AKShare优化服务初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ AKShare优化服务初始化失败: {e}")

        # 3. 通达信服务
        try:
            from .tdx_service import get_tdx_service

            self.services["tdx"] = get_tdx_service()
            logger.info("✅ 通达信服务初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ 通达信服务初始化失败: {e}")

        # 4. YFinance服务
        try:
            from .yfinance_service import YFinanceService

            self.services["yfinance"] = YFinanceService()
            logger.info("✅ YFinance服务初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ YFinance服务初始化失败: {e}")

    def get_data_source_priority(self, symbol: str) -> List[str]:
        """
        根据股票代码获取数据源优先级列表

        Args:
            symbol: 股票代码

        Returns:
            List[str]: 数据源优先级列表
        """
        return self.strategy.get_market_data_sources(symbol)

    def get_stock_daily_data(
        self, symbol: str, start_date: str = None, end_date: str = None
    ) -> pd.DataFrame:
        """
        获取股票日线数据（带智能降级）

        Args:
            symbol: 股票代码
            start_date: 开始日期 'YYYY-MM-DD'
            end_date: 结束日期 'YYYY-MM-DD'

        Returns:
            pd.DataFrame: 标准化的日线数据
        """
        # 设置默认日期
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

        # 获取数据源优先级
        data_sources = self.get_data_source_priority(symbol)

        logger.info(f"📊 获取 {symbol} 的市场数据 ({start_date} 到 {end_date})")
        logger.info(f"🔄 数据源优先级: {data_sources}")

        last_error = None
        for source in data_sources:
            if source not in self.services:
                continue

            try:
                logger.info(f"🔄 尝试从 {source} 获取数据...")
                data = self._get_data_from_source(source, symbol, start_date, end_date)

                if data is not None and not data.empty:
                    logger.info(f"✅ 成功从 {source} 获取 {len(data)} 条数据")
                    return self._standardize_data(data, source)

            except Exception as e:
                last_error = e
                logger.warning(f"⚠️ {source} 获取失败: {e}")
                continue

        # 所有数据源都失败
        raise DataNotFoundError(
            f"无法从任何数据源获取 {symbol} 的数据。最后错误: {last_error}"
        )

    def _get_data_from_source(
        self, source: str, symbol: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """从指定数据源获取数据"""
        service = self.services.get(source)
        if not service:
            return None

        classification = self.symbol_processor.classifier.classify_stock(symbol)

        if source == "tushare":
            # Tushare优化服务
            return service.get_stock_daily(symbol, start_date, end_date)

        elif source == "akshare":
            # AKShare优化服务
            if classification["is_china"]:
                return service.get_stock_daily(symbol, start_date, end_date)
            elif classification["is_hk"]:
                return service.get_hk_daily(symbol, start_date, end_date)
            elif classification["is_us"]:
                return service.get_us_daily(symbol, start_date, end_date)

        elif source == "tdx":
            # 通达信服务（仅支持A股）
            if classification["is_china"]:
                return service.get_stock_daily(symbol, start_date, end_date)

        elif source == "yfinance":
            # YFinance服务
            yf_symbol = self.symbol_processor.get_yfinance_format(symbol)
            return service.get_stock_daily(yf_symbol, start_date, end_date)

        return None

    def _standardize_data(self, data: pd.DataFrame, source: str) -> pd.DataFrame:
        """标准化数据格式"""
        if data.empty:
            return data

        # 确保必要的列存在
        required_columns = ["date", "open", "high", "low", "close", "volume"]

        # 列名映射
        column_mapping = {
            "trade_date": "date",
            "datetime": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "vol": "volume",
            "amount": "turnover",
            "turnover": "turnover",
        }

        # 重命名列
        data = data.rename(columns=column_mapping)

        # 确保日期列是datetime类型
        if "date" in data.columns:
            data["date"] = pd.to_datetime(data["date"])

        # 排序
        if "date" in data.columns:
            data = data.sort_values("date")

        # 添加数据源标识
        data["source"] = source

        return data

    def calculate_technical_indicators(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        计算技术指标

        Args:
            data: 包含OHLCV的DataFrame

        Returns:
            Dict: 技术指标字典
        """
        if data.empty or len(data) < 20:
            return {}

        indicators = {}

        try:
            # 移动平均线
            indicators["MA5"] = (
                float(data["close"].rolling(5).mean().iloc[-1])
                if len(data) >= 5
                else None
            )
            indicators["MA10"] = (
                float(data["close"].rolling(10).mean().iloc[-1])
                if len(data) >= 10
                else None
            )
            indicators["MA20"] = (
                float(data["close"].rolling(20).mean().iloc[-1])
                if len(data) >= 20
                else None
            )
            indicators["MA60"] = (
                float(data["close"].rolling(60).mean().iloc[-1])
                if len(data) >= 60
                else None
            )

            # RSI
            if len(data) >= 14:
                delta = data["close"].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                indicators["RSI"] = float((100 - (100 / (1 + rs))).iloc[-1])

            # MACD
            if len(data) >= 26:
                exp1 = data["close"].ewm(span=12, adjust=False).mean()
                exp2 = data["close"].ewm(span=26, adjust=False).mean()
                macd = exp1 - exp2
                signal = macd.ewm(span=9, adjust=False).mean()
                histogram = macd - signal

                indicators["MACD"] = float(macd.iloc[-1])
                indicators["MACD_Signal"] = float(signal.iloc[-1])
                indicators["MACD_Histogram"] = float(histogram.iloc[-1])

            # 布林带
            if len(data) >= 20:
                sma = data["close"].rolling(20).mean()
                std = data["close"].rolling(20).std()
                indicators["BOLL_Upper"] = float((sma + 2 * std).iloc[-1])
                indicators["BOLL_Middle"] = float(sma.iloc[-1])
                indicators["BOLL_Lower"] = float((sma - 2 * std).iloc[-1])

            # KDJ
            if len(data) >= 9:
                low_min = data["low"].rolling(9).min()
                high_max = data["high"].rolling(9).max()
                rsv = (data["close"] - low_min) / (high_max - low_min) * 100
                k = rsv.ewm(com=2, adjust=False).mean()
                d = k.ewm(com=2, adjust=False).mean()
                j = 3 * k - 2 * d

                indicators["KDJ_K"] = float(k.iloc[-1])
                indicators["KDJ_D"] = float(d.iloc[-1])
                indicators["KDJ_J"] = float(j.iloc[-1])

            # ATR (平均真实波幅)
            if len(data) >= 14:
                high_low = data["high"] - data["low"]
                high_close = np.abs(data["high"] - data["close"].shift())
                low_close = np.abs(data["low"] - data["close"].shift())
                tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                indicators["ATR"] = float(tr.rolling(14).mean().iloc[-1])

        except Exception as e:
            logger.error(f"❌ 计算技术指标失败: {e}")

        return indicators

    def generate_market_report(
        self, symbol: str, start_date: str = None, end_date: str = None
    ) -> str:
        """
        生成完整的市场技术分析报告

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            str: Markdown格式的分析报告
        """
        try:
            # 获取股票数据
            data = self.get_stock_daily_data(symbol, start_date, end_date)

            if data.empty:
                return f"❌ 无法获取 {symbol} 的市场数据"

            # 获取股票分类信息
            classification = self.symbol_processor.classifier.classify_stock(symbol)

            # 计算技术指标
            indicators = self.calculate_technical_indicators(data)

            # 生成报告
            report = self._format_market_report(
                symbol, data, classification, indicators, start_date, end_date
            )

            return report

        except Exception as e:
            logger.error(f"❌ 生成市场报告失败: {e}")
            return f"❌ 生成 {symbol} 的市场报告失败: {str(e)}"

    def _format_market_report(
        self,
        symbol: str,
        data: pd.DataFrame,
        classification: Dict,
        indicators: Dict,
        start_date: str,
        end_date: str,
    ) -> str:
        """格式化市场分析报告"""

        # 基本信息
        latest = data.iloc[-1]
        earliest = data.iloc[0]

        # 计算涨跌幅
        price_change = latest["close"] - earliest["close"]
        price_change_pct = (price_change / earliest["close"]) * 100

        # 计算波动率
        returns = data["close"].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252) * 100  # 年化波动率

        report = f"""
# {symbol} 股票技术分析报告

## 一、基本信息

- **股票代码**: {symbol}
- **市场**: {classification['market_name']}
- **交易所**: {classification['exchange']}
- **板块**: {classification['board']}
- **币种**: {classification['currency']}
- **分析期间**: {start_date} 至 {end_date}
- **数据来源**: {data['source'].iloc[-1]}

---

## 二、价格趋势分析

### 2.1 价格概览
- **最新价格**: {latest['close']:.2f} {classification['currency']}
- **开盘价**: {latest['open']:.2f}
- **最高价**: {latest['high']:.2f}
- **最低价**: {latest['low']:.2f}
- **成交量**: {latest['volume']:,.0f}

### 2.2 期间表现
- **期初价格**: {earliest['close']:.2f}
- **期间最高**: {data['high'].max():.2f}
- **期间最低**: {data['low'].min():.2f}
- **期间涨跌**: {price_change:+.2f} ({price_change_pct:+.2f}%)
- **年化波动率**: {volatility:.2f}%

### 2.3 趋势判断
{self._analyze_trend(data, indicators)}

---

## 三、技术指标分析

### 3.1 移动平均线系统
{self._analyze_moving_averages(indicators, latest['close'])}

### 3.2 动量指标
{self._analyze_momentum_indicators(indicators)}

### 3.3 趋势指标
{self._analyze_trend_indicators(indicators)}

### 3.4 波动性指标
{self._analyze_volatility_indicators(indicators, latest['close'])}

---

## 四、成交量分析

{self._analyze_volume(data)}

---

## 五、支撑与压力位

{self._analyze_support_resistance(data)}

---

## 六、投资建议

{self._generate_trading_advice(data, indicators, classification)}

---

## 七、风险提示

⚠️ **重要声明**:
- 本报告基于历史数据和技术指标分析生成，仅供参考，不构成投资建议
- 技术分析存在滞后性，市场随时可能发生变化
- 投资有风险，入市需谨慎
- 请结合基本面分析和自身风险承受能力做出投资决策

---

*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        return report

    def _analyze_trend(self, data: pd.DataFrame, indicators: Dict) -> str:
        """分析价格趋势"""
        latest_close = data["close"].iloc[-1]

        trend_signals = []

        # MA趋势判断
        if indicators.get("MA5") and indicators.get("MA10") and indicators.get("MA20"):
            ma5 = indicators["MA5"]
            ma10 = indicators["MA10"]
            ma20 = indicators["MA20"]

            if ma5 > ma10 > ma20:
                trend_signals.append("✅ **多头排列**: MA5 > MA10 > MA20，短期趋势向上")
            elif ma5 < ma10 < ma20:
                trend_signals.append("⚠️ **空头排列**: MA5 < MA10 < MA20，短期趋势向下")
            else:
                trend_signals.append("⚡ **均线纠缠**: 均线系统混乱，趋势不明")

        # 价格与均线关系
        if indicators.get("MA20"):
            if latest_close > indicators["MA20"]:
                trend_signals.append(
                    f"📈 价格位于MA20上方 ({latest_close:.2f} > {indicators['MA20']:.2f})，处于相对强势"
                )
            else:
                trend_signals.append(
                    f"📉 价格位于MA20下方 ({latest_close:.2f} < {indicators['MA20']:.2f})，处于相对弱势"
                )

        return "\n".join(trend_signals) if trend_signals else "暂无明确趋势信号"

    def _analyze_moving_averages(self, indicators: Dict, current_price: float) -> str:
        """分析移动平均线"""
        ma_analysis = []

        for period in ["MA5", "MA10", "MA20", "MA60"]:
            if indicators.get(period):
                ma_value = indicators[period]
                diff = current_price - ma_value
                diff_pct = (diff / ma_value) * 100

                ma_analysis.append(
                    f"- **{period}**: {ma_value:.2f} (偏离度: {diff_pct:+.2f}%)"
                )

        return "\n".join(ma_analysis) if ma_analysis else "暂无移动平均线数据"

    def _analyze_momentum_indicators(self, indicators: Dict) -> str:
        """分析动量指标"""
        momentum_analysis = []

        # RSI分析
        if indicators.get("RSI"):
            rsi = indicators["RSI"]
            if rsi > 70:
                momentum_analysis.append(
                    f"- **RSI**: {rsi:.2f} - 🔴 超买区域，可能面临回调压力"
                )
            elif rsi < 30:
                momentum_analysis.append(
                    f"- **RSI**: {rsi:.2f} - 🟢 超卖区域，可能存在反弹机会"
                )
            else:
                momentum_analysis.append(f"- **RSI**: {rsi:.2f} - ⚪ 中性区域")

        # KDJ分析
        if (
            indicators.get("KDJ_K")
            and indicators.get("KDJ_D")
            and indicators.get("KDJ_J")
        ):
            k = indicators["KDJ_K"]
            d = indicators["KDJ_D"]
            j = indicators["KDJ_J"]

            kdj_signal = "中性"
            if k > d and k > 50:
                kdj_signal = "多头信号"
            elif k < d and k < 50:
                kdj_signal = "空头信号"

            momentum_analysis.append(
                f"- **KDJ**: K={k:.2f}, D={d:.2f}, J={j:.2f} - {kdj_signal}"
            )

        return "\n".join(momentum_analysis) if momentum_analysis else "暂无动量指标数据"

    def _analyze_trend_indicators(self, indicators: Dict) -> str:
        """分析趋势指标"""
        trend_analysis = []

        # MACD分析
        if indicators.get("MACD") and indicators.get("MACD_Signal"):
            macd = indicators["MACD"]
            signal = indicators["MACD_Signal"]
            hist = indicators.get("MACD_Histogram", macd - signal)

            if macd > signal and hist > 0:
                trend_analysis.append(
                    f"- **MACD**: 金叉向上 (MACD={macd:.4f}, Signal={signal:.4f})"
                )
            elif macd < signal and hist < 0:
                trend_analysis.append(
                    f"- **MACD**: 死叉向下 (MACD={macd:.4f}, Signal={signal:.4f})"
                )
            else:
                trend_analysis.append(
                    f"- **MACD**: 震荡整理 (MACD={macd:.4f}, Signal={signal:.4f})"
                )

        return "\n".join(trend_analysis) if trend_analysis else "暂无趋势指标数据"

    def _analyze_volatility_indicators(
        self, indicators: Dict, current_price: float
    ) -> str:
        """分析波动性指标"""
        volatility_analysis = []

        # 布林带分析
        if (
            indicators.get("BOLL_Upper")
            and indicators.get("BOLL_Middle")
            and indicators.get("BOLL_Lower")
        ):
            upper = indicators["BOLL_Upper"]
            middle = indicators["BOLL_Middle"]
            lower = indicators["BOLL_Lower"]

            position = "中轨附近"
            if current_price >= upper:
                position = "上轨或上轨上方，超买区域"
            elif current_price <= lower:
                position = "下轨或下轨下方，超卖区域"
            elif current_price > middle:
                position = "中轨上方，相对强势"
            else:
                position = "中轨下方，相对弱势"

            volatility_analysis.append(
                f"- **布林带**: 上轨={upper:.2f}, 中轨={middle:.2f}, 下轨={lower:.2f}"
            )
            volatility_analysis.append(f"  当前价格位于{position}")

        # ATR分析
        if indicators.get("ATR"):
            atr = indicators["ATR"]
            volatility_analysis.append(f"- **ATR (平均真实波幅)**: {atr:.2f}")

        return (
            "\n".join(volatility_analysis)
            if volatility_analysis
            else "暂无波动性指标数据"
        )

    def _analyze_volume(self, data: pd.DataFrame) -> str:
        """分析成交量"""
        recent_volume = data["volume"].iloc[-5:].mean()
        avg_volume = data["volume"].mean()

        volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 0

        volume_analysis = f"""
- **近5日平均成交量**: {recent_volume:,.0f}
- **期间平均成交量**: {avg_volume:,.0f}
- **成交量比率**: {volume_ratio:.2f}倍

"""

        if volume_ratio > 1.5:
            volume_analysis += "📈 **成交量放大**: 近期成交活跃，市场关注度提升"
        elif volume_ratio < 0.7:
            volume_analysis += "📉 **成交量萎缩**: 近期成交清淡，市场观望情绪浓厚"
        else:
            volume_analysis += "⚖️ **成交量正常**: 维持在平均水平"

        return volume_analysis

    def _analyze_support_resistance(self, data: pd.DataFrame) -> str:
        """分析支撑位和阻力位"""
        recent_data = data.tail(20)

        # 计算关键价位
        resistance_levels = []
        support_levels = []

        # 最近高点作为阻力位
        high_max = recent_data["high"].max()
        resistance_levels.append(high_max)

        # 最近低点作为支撑位
        low_min = recent_data["low"].min()
        support_levels.append(low_min)

        # 添加均线作为动态支撑/阻力
        current_price = data["close"].iloc[-1]

        analysis = f"""
### 静态支撑与阻力
- **阻力位1**: {resistance_levels[0]:.2f} (近期高点)
- **支撑位1**: {support_levels[0]:.2f} (近期低点)

### 动态支撑与阻力
- 短期均线(MA5/MA10)可作为动态支撑/阻力参考
- 中期均线(MA20/MA60)可作为趋势判断依据
"""

        return analysis

    def _generate_trading_advice(
        self, data: pd.DataFrame, indicators: Dict, classification: Dict
    ) -> str:
        """生成交易建议"""

        signals = []
        score = 0  # 综合评分 (-100 到 +100)

        # RSI信号
        if indicators.get("RSI"):
            rsi = indicators["RSI"]
            if rsi > 70:
                signals.append("⚠️ RSI超买，注意风险")
                score -= 20
            elif rsi < 30:
                signals.append("✅ RSI超卖，可能存在机会")
                score += 20

        # MACD信号
        if indicators.get("MACD_Histogram"):
            if indicators["MACD_Histogram"] > 0:
                signals.append("✅ MACD多头")
                score += 15
            else:
                signals.append("⚠️ MACD空头")
                score -= 15

        # 均线信号
        current_price = data["close"].iloc[-1]
        if indicators.get("MA20"):
            if current_price > indicators["MA20"]:
                signals.append("✅ 价格位于MA20上方")
                score += 10
            else:
                signals.append("⚠️ 价格位于MA20下方")
                score -= 10

        # 趋势信号
        if indicators.get("MA5") and indicators.get("MA10") and indicators.get("MA20"):
            if indicators["MA5"] > indicators["MA10"] > indicators["MA20"]:
                signals.append("✅ 均线多头排列")
                score += 25
            elif indicators["MA5"] < indicators["MA10"] < indicators["MA20"]:
                signals.append("⚠️ 均线空头排列")
                score -= 25

        # 生成建议
        advice = "\n".join(signals) + "\n\n"

        if score > 30:
            advice += "### 📈 **建议: 积极关注**\n"
            advice += "技术指标整体偏多，短期可能存在上涨机会，但仍需关注市场整体环境和基本面情况。"
        elif score < -30:
            advice += "### 📉 **建议: 谨慎观望**\n"
            advice += "技术指标整体偏空，短期面临调整压力，建议等待更好的入场时机。"
        else:
            advice += "### ⚖️ **建议: 中性观望**\n"
            advice += "技术指标信号混杂，市场方向不明确，建议等待更清晰的信号再做决策。"

        advice += f"\n\n**综合评分**: {score}/100"

        return advice


# ==================== 便捷函数 ====================

_global_service = None


def get_market_service() -> MarketDataService:
    """获取市场数据服务单例"""
    global _global_service
    if _global_service is None:
        _global_service = MarketDataService()
    return _global_service


def get_stock_market_data(
    symbol: str, start_date: str = None, end_date: str = None
) -> pd.DataFrame:
    """获取股票市场数据（便捷函数）"""
    service = get_market_service()
    return service.get_stock_daily_data(symbol, start_date, end_date)


def generate_market_analysis_report(
    symbol: str, start_date: str = None, end_date: str = None
) -> str:
    """生成市场分析报告（便捷函数）"""
    service = get_market_service()
    return service.generate_market_report(symbol, start_date, end_date)
