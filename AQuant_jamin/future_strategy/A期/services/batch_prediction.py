"""
批量截面预测服务
对所有配置的期货品种，基于最新日线 OHLCV 数据，
跑技术面 + 资金面 + 缠论 + 波浪理论，得到综合方向与各维度信号，
返回汇总 DataFrame（按偏多/震荡/偏空依次排序）。
"""
import pandas as pd
import streamlit as st

from config import DEFAULT_SYMBOLS, FUTURES_SYMBOLS
from services.market_data import get_kline_data
from services.technical_analysis import (
    calc_all_indicators,
    get_all_conclusions,
    get_overall_technical_verdict,
)
from services.fund_flow import calc_fund_flow_all, get_fund_flow_conclusions
from services.chan_theory import analyze_chan, get_chan_conclusion
from services.elliott_wave import analyze_elliott, get_elliott_conclusion


# 截面预测的子维度权重（消息面/博主观点不参与截面，需重新归一化）
CROSS_SECTION_WEIGHTS = {
    "技术面": 0.45,
    "资金面": 0.30,
    "缠论":   0.15,
    "波浪":   0.10,
}

# 方向排序权重：偏多 > 震荡 > 偏空
DIRECTION_ORDER = {"偏多": 0, "震荡": 1, "中性": 1, "偏空": 2, "未知": 3}


def _score_to_direction(score: float) -> str:
    if score >= 58:
        return "偏多"
    if score <= 42:
        return "偏空"
    return "震荡"


def _predict_one(symbol: str, name: str) -> dict | None:
    """对单个品种执行完整截面分析，失败返回 None"""
    df = get_kline_data(symbol, "日K")
    if df.empty or len(df) < 30:
        return None

    # 技术面
    df = calc_all_indicators(df)
    tech_verdict = get_overall_technical_verdict(get_all_conclusions(df))
    tech_score = tech_verdict["score"]

    # 资金面
    df_fund = calc_fund_flow_all(df.copy())
    fund_overall = get_fund_flow_conclusions(df_fund).get("overall", {})
    fund_score = fund_overall.get("score", 50)

    # 缠论
    chan_res = analyze_chan(df)
    chan_concl = get_chan_conclusion(df, chan_res)
    chan_score = chan_concl.get("score", 50)

    # 波浪
    elliott_res = analyze_elliott(df)
    elliott_concl = get_elliott_conclusion(elliott_res)
    elliott_score = elliott_concl.get("score", 50)

    # 加权综合
    w = CROSS_SECTION_WEIGHTS
    composite = (
        tech_score * w["技术面"]
        + fund_score * w["资金面"]
        + chan_score * w["缠论"]
        + elliott_score * w["波浪"]
    )
    direction = _score_to_direction(composite)

    latest_close = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-2]) if len(df) >= 2 else latest_close
    chg_pct = (latest_close - prev_close) / prev_close * 100 if prev_close else 0

    return {
        "品种":      name,
        "代码":      symbol,
        "最新收盘":   round(latest_close, 2),
        "涨跌幅%":    round(chg_pct, 2),
        "综合预测":   direction,
        "综合评分":   round(composite, 1),
        "技术面":     _score_to_direction(tech_score),
        "技术评分":   round(tech_score, 1),
        "资金面":     _score_to_direction(fund_score),
        "资金评分":   round(fund_score, 1),
        "缠论":       chan_concl.get("signal", "震荡"),
        "缠论评分":   round(chan_score, 1),
        "波浪":       elliott_concl.get("signal", "震荡"),
        "波浪评分":   round(elliott_score, 1),
    }


@st.cache_data(ttl=300, show_spinner="正在对所有品种进行截面预测...")
def batch_predict_all() -> pd.DataFrame:
    """
    遍历所有品种执行截面预测，返回排序后的 DataFrame。
    排序规则：综合预测（偏多→震荡→偏空） + 综合评分（同方向内分数高在前，偏空除外）
    """
    all_symbols = {**DEFAULT_SYMBOLS,**FUTURES_SYMBOLS}
    rows = []
    for name, symbol in all_symbols.items():
        try:
            row = _predict_one(symbol, name)
            if row:
                rows.append(row)
        except Exception as e:
            # 单个品种失败不影响整体
            rows.append({
                "品种": name, "代码": symbol,
                "最新收盘": None, "涨跌幅%": None,
                "综合预测": "未知", "综合评分": None,
                "技术面": "未知", "技术评分": None,
                "资金面": "未知", "资金评分": None,
                "缠论":   "未知", "缠论评分": None,
                "波浪":   "未知", "波浪评分": None,
            })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["_dir_order"] = df["综合预测"].map(DIRECTION_ORDER).fillna(9)
    # 偏多：分数高在前；偏空：分数低在前（最看空在最下）；震荡：按分数远离 50 的距离
    df["_score_order"] = df.apply(
        lambda r: -(r["综合评分"] or 50) if r["综合预测"] == "偏多"
        else (r["综合评分"] or 50) if r["综合预测"] == "偏空"
        else abs((r["综合评分"] or 50) - 50) * -1,  # 震荡时分数更极端的靠前
        axis=1,
    )
    df = df.sort_values(["_dir_order", "_score_order"]).drop(columns=["_dir_order", "_score_order"])
    return df.reset_index(drop=True)
