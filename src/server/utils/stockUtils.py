# app/utils/stockUtils.py
import pandas as pd
import tushare as ts
from typing import Dict, Optional
from datetime import datetime
from .stock_market_classifier import classify_stock


class StockUtils:
    """
    股票工具类，用于根据股票代码识别市场。
    """

    @staticmethod
    def get_market_info(ticker: str) -> Dict:
        """
        根据股票代码判断市场信息。
        使用统一的股票市场分类器。
        """
        classification = classify_stock(ticker)

        return {
            "market": classification["market"],
            "is_china": classification["is_china"],
            "is_hk": classification["is_hk"],
            "is_us": classification["is_us"],
            "market_name": classification["market_name"],
            "exchange": classification["exchange"],
            "board": classification["board"],
            "currency": classification["currency"],
            "full_symbol": classification["full_symbol"],
        }
