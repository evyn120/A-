"""
资金面分析服务
量价分析、OBV、MFI、量价背离检测
"""
import pandas as pd
import numpy as np
import streamlit as st

try:
    from ta.volume import OnBalanceVolumeIndicator, MFIIndicator
    HAS_TA = True
except ImportError:
    HAS_TA = False


def calc_obv(df: pd.DataFrame) -> pd.DataFrame:
    """计算OBV（能量潮）指标"""
    df = df.copy()
    if HAS_TA:
        obv_ind = OnBalanceVolumeIndicator(close=df["close"], volume=df["volume"])
        df["OBV"] = obv_ind.on_balance_volume()
    else:
        # 手动计算
        obv = [0]
        for i in range(1, len(df)):
            if df["close"].iloc[i] > df["close"].iloc[i - 1]:
                obv.append(obv[-1] + df["volume"].iloc[i])
            elif df["close"].iloc[i] < df["close"].iloc[i - 1]:
                obv.append(obv[-1] - df["volume"].iloc[i])
            else:
                obv.append(obv[-1])
        df["OBV"] = obv
    return df


def calc_mfi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """计算MFI（资金流量）指标"""
    df = df.copy()
    if HAS_TA:
        try:
            mfi_ind = MFIIndicator(
                high=df["high"], low=df["low"],
                close=df["close"], volume=df["volume"],
                window=period,
            )
            df["MFI"] = mfi_ind.money_flow_index()
        except Exception:
            df["MFI"] = _manual_mfi(df, period)
    else:
        df["MFI"] = _manual_mfi(df, period)
    return df


def _manual_mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """手动计算MFI"""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    money_flow = typical_price * df["volume"]

    positive_flow = pd.Series(
        [money_flow.iloc[i] if typical_price.iloc[i] > typical_price.iloc[i - 1] else 0
         for i in range(len(df))],
        index=df.index,
    )
    negative_flow = pd.Series(
        [money_flow.iloc[i] if typical_price.iloc[i] < typical_price.iloc[i - 1] else 0
         for i in range(len(df))],
        index=df.index,
    )

    positive_mf = positive_flow.rolling(window=period).sum()
    negative_mf = negative_flow.rolling(window=period).sum()

    mfi = 100 - (100 / (1 + positive_mf / negative_mf.replace(0, np.nan)))
    return mfi


def analyze_volume_price(df: pd.DataFrame) -> dict:
    """
    量价分析：计算量增价涨/量缩价涨等关系
    """
    if df.empty or len(df) < 2:
        return {"conclusion": "数据不足", "score": 50, "signal": "未知"}

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price_up = last["close"] > prev["close"]
    vol_up = last["volume"] > prev["volume"]

    # 近5日趋势
    recent = df.tail(5)
    price_trend = recent["close"].iloc[-1] > recent["close"].iloc[0]
    vol_trend = recent["volume"].iloc[-1] > recent["volume"].iloc[0]

    score = 50
    if price_up and vol_up:
        pattern = "量增价涨"
        score += 15
        desc = "量价配合良好，多头力量增强"
    elif price_up and not vol_up:
        pattern = "量缩价涨"
        score += 5
        desc = "价涨但量能不足，上涨持续性存疑"
    elif not price_up and vol_up:
        pattern = "量增价跌"
        score -= 15
        desc = "放量下跌，空头力量增强"
    else:
        pattern = "量缩价跌"
        score -= 5
        desc = "缩量下跌，卖压减弱但仍偏弱"

    # 近期趋势微调
    if price_trend and vol_trend:
        score += 5
    elif not price_trend and vol_trend:
        score -= 5

    score = max(0, min(100, score))
    signal = "偏多" if score >= 58 else "偏空" if score <= 42 else "震荡"

    return {
        "pattern": pattern,
        "conclusion": f"当前{pattern}，{desc}",
        "score": score,
        "signal": signal,
    }


def detect_divergence(df: pd.DataFrame) -> dict:
    """
    量价背离检测
    价格创新高但OBV未创新高 → 顶背离警告
    价格创新低但OBV未创新低 → 底背离信号
    """
    if df.empty or "OBV" not in df.columns or len(df) < 20:
        return {"divergence": "无", "conclusion": "数据不足，无法检测背离", "score": 50}

    recent = df.tail(20)

    price_high_idx = recent["close"].idxmax()
    price_low_idx = recent["close"].idxmin()

    # 顶背离：价格创新高但OBV没有
    divergence = "无"
    score = 50
    conclusion = "暂未检测到明显的量价背离信号"

    if price_high_idx == recent.index[-1] or price_high_idx == recent.index[-2]:
        # 价格接近或创新高
        obv_at_high = recent.loc[price_high_idx, "OBV"]
        obv_max = recent["OBV"].max()
        if obv_at_high < obv_max * 0.95:
            divergence = "顶背离"
            score = 35
            conclusion = "⚠️ 检测到顶背离信号：价格创新高但OBV未能同步创新高，上涨动力可能不足，注意回调风险"

    if price_low_idx == recent.index[-1] or price_low_idx == recent.index[-2]:
        # 价格接近或创新低
        obv_at_low = recent.loc[price_low_idx, "OBV"]
        obv_min = recent["OBV"].min()
        if obv_at_low > obv_min * 1.05:
            divergence = "底背离"
            score = 65
            conclusion = "✅ 检测到底背离信号：价格创新低但OBV未同步创新低，下跌动力可能衰竭，关注反弹机会"

    return {
        "divergence": divergence,
        "conclusion": conclusion,
        "score": score,
    }


def calc_fund_flow_all(df: pd.DataFrame) -> pd.DataFrame:
    """计算所有资金面指标"""
    if df.empty:
        return df
    df = calc_obv(df)
    df = calc_mfi(df)
    # OBV均线
    df["OBV_MA5"] = df["OBV"].rolling(window=5).mean()
    df["OBV_MA20"] = df["OBV"].rolling(window=20).mean()
    return df


def get_fund_flow_conclusions(df: pd.DataFrame) -> dict:
    """
    生成资金面综合结论
    """
    if df.empty:
        return {
            "量价分析": {"conclusion": "数据不足", "score": 50, "signal": "未知"},
            "OBV": {"conclusion": "数据不足", "score": 50, "signal": "未知"},
            "MFI": {"conclusion": "数据不足", "score": 50, "signal": "未知"},
            "量价背离": {"conclusion": "数据不足", "score": 50},
            "overall": {"score": 50, "direction": "中性", "reason": "数据不足"},
        }

    results = {}

    # 1. 量价分析
    results["量价分析"] = analyze_volume_price(df)

    # 2. OBV结论
    if "OBV" in df.columns and len(df) >= 2:
        last_obv = df["OBV"].iloc[-1]
        prev_obv = df["OBV"].iloc[-2]
        obv_ma5 = df["OBV_MA5"].iloc[-1] if "OBV_MA5" in df.columns and pd.notna(df["OBV_MA5"].iloc[-1]) else None

        obv_score = 50
        obv_trend = ""
        if last_obv > prev_obv:
            obv_trend = "OBV上升，资金流入"
            obv_score += 15
        elif last_obv < prev_obv:
            obv_trend = "OBV下降，资金流出"
            obv_score -= 15
        else:
            obv_trend = "OBV持平"

        if obv_ma5 and last_obv > obv_ma5:
            obv_score += 10
            obv_trend += "，在5日均线上方"

        obv_score = max(0, min(100, obv_score))
        obv_signal = "偏多" if obv_score >= 58 else "偏空" if obv_score <= 42 else "震荡"

        results["OBV"] = {
            "conclusion": f"{obv_trend}",
            "score": obv_score,
            "signal": obv_signal,
        }
    else:
        results["OBV"] = {"conclusion": "OBV数据不完整", "score": 50, "signal": "未知"}

    # 3. MFI结论
    if "MFI" in df.columns:
        last_mfi = df["MFI"].iloc[-1]
        if pd.notna(last_mfi):
            if last_mfi > 80:
                mfi_signal = "偏空"
                mfi_score = 30
                mfi_text = f"MFI={last_mfi:.1f}，超买区域，资金可能即将流出"
            elif last_mfi < 20:
                mfi_signal = "偏多"
                mfi_score = 70
                mfi_text = f"MFI={last_mfi:.1f}，超卖区域，资金可能即将流入"
            elif last_mfi > 60:
                mfi_signal = "偏多"
                mfi_score = 60
                mfi_text = f"MFI={last_mfi:.1f}，偏强区域，资金持续流入"
            elif last_mfi < 40:
                mfi_signal = "偏空"
                mfi_score = 40
                mfi_text = f"MFI={last_mfi:.1f}，偏弱区域，资金持续流出"
            else:
                mfi_signal = "震荡"
                mfi_score = 50
                mfi_text = f"MFI={last_mfi:.1f}，中性区域"

            results["MFI"] = {
                "conclusion": mfi_text,
                "score": mfi_score,
                "signal": mfi_signal,
            }
        else:
            results["MFI"] = {"conclusion": "MFI数据不完整", "score": 50, "signal": "未知"}
    else:
        results["MFI"] = {"conclusion": "MFI数据不可用", "score": 50, "signal": "未知"}

    # 4. 量价背离
    results["量价背离"] = detect_divergence(df)

    # 5. 综合评分
    scores = []
    for key in ["量价分析", "OBV", "MFI"]:
        if key in results:
            scores.append(results[key].get("score", 50))

    # 背离也纳入评分
    div_score = results["量价背离"].get("score", 50)
    scores.append(div_score)

    avg_score = sum(scores) / len(scores) if scores else 50

    direction = "偏多" if avg_score >= 58 else "偏空" if avg_score <= 42 else "中性"

    # 生成理由
    bullish_factors = [k for k, v in results.items() if isinstance(v, dict) and v.get("signal") == "偏多"]
    bearish_factors = [k for k, v in results.items() if isinstance(v, dict) and v.get("signal") == "偏空"]

    if bullish_factors and not bearish_factors:
        reason = f"{'、'.join(bullish_factors)}均显示偏多信号"
    elif bearish_factors and not bullish_factors:
        reason = f"{'、'.join(bearish_factors)}均显示偏空信号"
    elif bullish_factors and bearish_factors:
        reason = f"多空分歧：{'、'.join(bullish_factors)}偏多，{'、'.join(bearish_factors)}偏空"
    else:
        reason = "资金面指标整体中性"

    results["overall"] = {
        "score": round(avg_score, 1),
        "direction": direction,
        "reason": reason,
    }

    return results
