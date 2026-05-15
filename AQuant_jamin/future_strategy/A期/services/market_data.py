"""
行情数据获取服务（akshare 版）
使用 akshare 获取中国国内期货主力连续合约的日/周/月 K 线与实时报价
"""
import akshare as ak
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

from config import DEFAULT_SYMBOLS, FUTURES_SYMBOLS, DATA_DAYS, KLINE_PERIODS


# ---------- 内部工具 ----------
def _resample_kline(df: pd.DataFrame, period_key: str) -> pd.DataFrame:
    """把日 K 线按周/月重采样"""
    if period_key == "日K" or df.empty:
        return df
    rule = "W" if period_key == "周K" else "M"
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    return df.resample(rule).agg(agg).dropna(how="any")


def _standardize(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    """把 akshare 返回的列名统一成 open/high/low/close/volume，索引为日期"""
    if df is None or df.empty:
        return pd.DataFrame()

    rename_map = {
        "日期": "date", "date": "date",
        "开盘价": "open", "open": "open", "Open": "open",
        "最高价": "high", "high": "high", "High": "high",
        "最低价": "low",  "low": "low",  "Low": "low",
        "收盘价": "close","close": "close", "Close": "close",
        "成交量": "volume","volume": "volume", "Volume": "volume",
        "持仓量": "open_interest",
    }
    df = df.rename(columns=rename_map)
    keep = [c for c in ["date", "open", "high", "low", "close", "volume", "open_interest"] if c in df.columns]
    df = df[keep].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    # 强制数值
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"])


# ---------- 主要接口 ----------
@st.cache_data(ttl=300, show_spinner="正在获取行情数据...")
def get_kline_data(symbol: str, period_key: str = "日K") -> pd.DataFrame:
    """
    获取 K 线数据
    Args:
        symbol: akshare 期货主连代码，如 "AU0"（沪金主连）、"CU0"（沪铜主连）
        period_key: "日K" / "周K" / "月K"
    """
    days = DATA_DAYS.get(period_key, 365)
    try:
        # 主路径：新浪期货主力连续日线
        raw = ak.futures_main_sina(symbol=symbol)
        df = _standardize(raw)

        # 回退：东方财富全球期货历史（适合外盘代码）
        if df.empty:
            raw = ak.futures_global_hist_em(symbol=symbol)
            df = _standardize(raw)

        if df.empty:
            return pd.DataFrame()

        # 截取最近 N 天
        cutoff = datetime.now() - timedelta(days=days)
        df = df.loc[df.index >= cutoff]

        # 周/月 K 重采样
        df = _resample_kline(df, period_key)
        df.index.name = "date"
        return df
    except Exception as e:
        st.warning(f"获取 {symbol} 数据失败: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner="正在获取实时报价...")
def get_realtime_price(symbol: str) -> dict:
    """
    获取实时报价（基于最近两根日线计算涨跌幅）
    """
    try:
        df = get_kline_data(symbol, "日K")
        if df.empty:
            return {"symbol": symbol, "price": 0, "change": 0, "change_pct": 0}

        if len(df) >= 2:
            current = df["close"].iloc[-1]
            prev = df["close"].iloc[-2]
            change = current - prev
            change_pct = (change / prev) * 100
        else:
            current = df["close"].iloc[-1]
            change = 0
            change_pct = 0

        return {
            "symbol": symbol,
            "price": round(float(current), 2),
            "change": round(float(change), 2),
            "change_pct": round(float(change_pct), 2),
        }
    except Exception as e:
        return {"symbol": symbol, "price": 0, "change": 0, "change_pct": 0, "error": str(e)}


def get_all_default_prices() -> dict:
    results = {}
    for name, symbol in DEFAULT_SYMBOLS.items():
        results[name] = get_realtime_price(symbol)
    return results


def get_custom_futures_prices(custom_symbols: dict) -> dict:
    results = {}
    for name, symbol in custom_symbols.items():
        results[name] = get_realtime_price(symbol)
    return results


def resolve_symbol(input_code: str) -> str:
    for name, symbol in DEFAULT_SYMBOLS.items():
        if name == input_code or symbol == input_code:
            return symbol
    for name, symbol in FUTURES_SYMBOLS.items():
        if name == input_code or symbol == input_code:
            return symbol
    return input_code
