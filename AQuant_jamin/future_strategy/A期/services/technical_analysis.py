"""
技术指标计算服务
使用 ta 库计算各类技术指标，并生成具体结论
"""
import pandas as pd
import numpy as np
from ta.trend import SMAIndicator, MACD
from ta.momentum import RSIIndicator, StochasticOscillator
from config import MACD_FAST, MACD_SLOW, MACD_SIGNAL, KDJ_PERIOD, RSI_PERIOD, MA_PERIODS


def calc_ma(df: pd.DataFrame, periods: list = None) -> pd.DataFrame:
    if periods is None:
        periods = MA_PERIODS
    df = df.copy()
    for p in periods:
        df[f"MA{p}"] = df["close"].rolling(window=p).mean()
    return df


def calc_macd(
    df: pd.DataFrame,
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> pd.DataFrame:
    df = df.copy()
    macd_ind = MACD(close=df["close"], window_slow=slow, window_fast=fast, window_sign=signal)
    df["MACD_DIF"] = macd_ind.macd()
    df["MACD_SIGNAL"] = macd_ind.macd_signal()
    df["MACD_HIST"] = macd_ind.macd_diff()
    return df


def calc_kdj(
    df: pd.DataFrame,
    period: int = KDJ_PERIOD,
) -> pd.DataFrame:
    df = df.copy()
    stoch = StochasticOscillator(
        high=df["high"], low=df["low"], close=df["close"],
        window=period, smooth_window=3,
    )
    df["K"] = stoch.stoch()
    df["D"] = stoch.stoch_signal()
    df["J"] = 3 * df["K"] - 2 * df["D"]
    return df


def calc_rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> pd.DataFrame:
    df = df.copy()
    rsi_ind = RSIIndicator(close=df["close"], window=period)
    df["RSI"] = rsi_ind.rsi()
    return df


def calc_volume_ma(df: pd.DataFrame, periods: list = None) -> pd.DataFrame:
    if periods is None:
        periods = [5, 10, 20]
    df = df.copy()
    for p in periods:
        df[f"VOL_MA{p}"] = df["volume"].rolling(window=p).mean()
    return df


def calc_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = calc_ma(df)
    df = calc_macd(df)
    df = calc_kdj(df)
    df = calc_rsi(df)
    df = calc_volume_ma(df)
    return df


# ============================================================
# 具体结论生成函数
# ============================================================

def get_macd_conclusion(df: pd.DataFrame) -> dict:
    """
    生成MACD具体结论
    返回: { "signal": "偏多"/"偏空"/"震荡", "conclusion": "文字描述", "score": 0~100 }
    """
    if df.empty or len(df) < 2 or "MACD_DIF" not in df.columns:
        return {"signal": "未知", "conclusion": "数据不足，无法判断MACD", "score": 50}

    last = df.iloc[-1]
    prev = df.iloc[-2]

    dif = last["MACD_DIF"]
    dea = last["MACD_SIGNAL"]
    hist = last["MACD_HIST"]
    prev_dif = prev["MACD_DIF"]
    prev_dea = prev["MACD_SIGNAL"]
    prev_hist = prev["MACD_HIST"]

    if pd.isna(dif) or pd.isna(dea):
        return {"signal": "未知", "conclusion": "MACD数据不完整", "score": 50}

    # DIF 在零轴上方/下方
    axis_pos = "零轴上方" if dif > 0 else "零轴下方"

    # 金叉/死叉判断
    cross = ""
    if prev_dif <= prev_dea and dif > dea:
        cross = "DIF与DEA金叉"
    elif prev_dif >= prev_dea and dif < dea:
        cross = "DIF与DEA死叉"
    elif dif > dea:
        cross = "DIF在DEA上方运行"
    else:
        cross = "DIF在DEA下方运行"

    # 柱状图变化
    hist_change = ""
    if pd.notna(prev_hist) and pd.notna(hist):
        if prev_hist < 0 and hist > 0:
            hist_change = "柱状图由负转正"
        elif prev_hist > 0 and hist < 0:
            hist_change = "柱状图由正转负"
        elif hist > 0 and hist > prev_hist:
            hist_change = "柱状图持续放大"
        elif hist > 0 and hist < prev_hist:
            hist_change = "柱状图有所收窄"
        elif hist < 0 and hist < prev_hist:
            hist_change = "柱状图持续放大（空头）"
        elif hist < 0 and hist > prev_hist:
            hist_change = "柱状图有所收窄（空头）"

    # 综合判断
    score = 50
    if dif > 0:
        score += 10  # 零轴上方偏多
    else:
        score -= 10

    if dif > dea:
        score += 10
    else:
        score -= 10

    if "金叉" in cross:
        score += 15
    elif "死叉" in cross:
        score -= 15

    if "由负转正" in hist_change:
        score += 10
    elif "由正转负" in hist_change:
        score -= 10

    score = max(0, min(100, score))

    if score >= 60:
        signal = "偏多"
    elif score <= 40:
        signal = "偏空"
    else:
        signal = "震荡"

    direction = "短期偏多" if score >= 55 else "短期偏空" if score <= 45 else "短期震荡"

    conclusion = f"当前DIF在{axis_pos}，{cross}，{hist_change}，{direction}"

    return {"signal": signal, "conclusion": conclusion, "score": score}


def get_kdj_conclusion(df: pd.DataFrame) -> dict:
    """
    生成KDJ具体结论
    """
    if df.empty or len(df) < 2 or "K" not in df.columns:
        return {"signal": "未知", "conclusion": "数据不足，无法判断KDJ", "score": 50}

    last = df.iloc[-1]
    prev = df.iloc[-2]

    k_val = last["K"]
    d_val = last["D"]

    if pd.isna(k_val) or pd.isna(d_val):
        return {"signal": "未知", "conclusion": "KDJ数据不完整", "score": 50}

    # 区域判断
    if k_val > 80 and d_val > 80:
        region = "超买区域"
    elif k_val < 20 and d_val < 20:
        region = "超卖区域"
    else:
        region = "正常区域"

    # 金叉/死叉
    prev_k = prev["K"]
    prev_d = prev["D"]
    cross = ""
    if pd.notna(prev_k) and pd.notna(prev_d):
        if prev_k <= prev_d and k_val > d_val:
            cross = "KD金叉"
        elif prev_k >= prev_d and k_val < d_val:
            cross = "KD死叉"
        else:
            cross = "KD未交叉"

    # 建议
    if region == "超买区域":
        advice = "短期注意回调风险"
    elif region == "超卖区域":
        advice = "短期注意反弹机会"
    else:
        advice = "暂无明显超买超卖信号"

    score = 50
    if region == "超买区域":
        score -= 15
    elif region == "超卖区域":
        score += 15

    if "金叉" in cross:
        score += 15
    elif "死叉" in cross:
        score -= 15

    score = max(0, min(100, score))

    if score >= 60:
        signal = "偏多"
    elif score <= 40:
        signal = "偏空"
    else:
        signal = "震荡"

    conclusion = f"K值{K_val_fmt(k_val)}、D值{K_val_fmt(d_val)}，处于{region}，{cross}，{advice}"

    return {"signal": signal, "conclusion": conclusion, "score": score}


def K_val_fmt(v):
    """格式化KDJ值"""
    if pd.isna(v):
        return "N/A"
    return f"{v:.1f}"


def get_rsi_conclusion(df: pd.DataFrame) -> dict:
    """
    生成RSI具体结论
    """
    if df.empty or "RSI" not in df.columns:
        return {"signal": "未知", "conclusion": "数据不足，无法判断RSI", "score": 50}

    last = df.iloc[-1]
    rsi_val = last["RSI"]

    if pd.isna(rsi_val):
        return {"signal": "未知", "conclusion": "RSI数据不完整", "score": 50}

    if rsi_val > 70:
        region = "超买区间"
        risk = "需注意回调风险"
        score = 30
    elif rsi_val < 30:
        region = "超卖区间"
        risk = "需注意反弹可能"
        score = 70
    else:
        region = "正常区间"
        risk = "暂无风险"
        score = 50

    # 在正常区间内微调
    if 50 <= rsi_val <= 70:
        score = 50 + (rsi_val - 50) * 0.5
    elif 30 <= rsi_val < 50:
        score = 50 - (50 - rsi_val) * 0.5

    score = max(0, min(100, score))

    if score >= 60:
        signal = "偏多"
    elif score <= 40:
        signal = "偏空"
    else:
        signal = "震荡"

    conclusion = f"RSI当前{rsi_val:.1f}，处于{region}，{risk}"

    return {"signal": signal, "conclusion": conclusion, "score": score}


def get_ma_conclusion(df: pd.DataFrame) -> dict:
    """
    生成均线具体结论
    """
    if df.empty or len(df) < 2:
        return {"signal": "未知", "conclusion": "数据不足，无法判断均线", "score": 50}

    last = df.iloc[-1]
    price = last["close"]

    # 判断价格与各均线关系
    ma_relations = []
    key_periods = [5, 20, 60]
    for p in key_periods:
        col = f"MA{p}"
        if col in df.columns and pd.notna(last[col]):
            pos = "上方" if price > last[col] else "下方"
            ma_relations.append((p, pos, last[col]))

    if not ma_relations:
        return {"signal": "未知", "conclusion": "均线数据不完整", "score": 50}

    # 判断均线排列
    ma_vals = {}
    for p in key_periods:
        col = f"MA{p}"
        if col in df.columns and pd.notna(last[col]):
            ma_vals[p] = last[col]

    alignment = "交叉缠绕"
    score = 50
    if len(ma_vals) >= 3:
        ma5, ma20, ma60 = ma_vals.get(5, 0), ma_vals.get(20, 0), ma_vals.get(60, 0)
        if ma5 > ma20 > ma60:
            alignment = "多头排列"
            score = 75
        elif ma5 < ma20 < ma60:
            alignment = "空头排列"
            score = 25

    # 价格与均线关系影响评分
    for p, pos, val in ma_relations:
        if pos == "上方":
            score += 3
        else:
            score -= 3

    score = max(0, min(100, score))

    if score >= 60:
        signal = "偏多"
        trend = "趋势偏多"
    elif score <= 40:
        signal = "偏空"
        trend = "趋势偏空"
    else:
        signal = "震荡"
        trend = "趋势震荡"

    relations_str = "、".join([f"价格在MA{p}{pos}" for p, pos, _ in ma_relations])
    conclusion = f"{relations_str}，均线{alignment}，{trend}"

    return {"signal": signal, "conclusion": conclusion, "score": score}


def get_indicator_signals(df: pd.DataFrame) -> dict:
    """
    根据最新数据生成技术指标信号（简化版，用于信号汇总）
    """
    signals = {}
    if df.empty or len(df) < 2:
        return signals

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # MACD 信号
    if "MACD_DIF" in df.columns and "MACD_SIGNAL" in df.columns:
        if pd.notna(last["MACD_DIF"]) and pd.notna(last["MACD_SIGNAL"]):
            if prev["MACD_DIF"] <= prev["MACD_SIGNAL"] and last["MACD_DIF"] > last["MACD_SIGNAL"]:
                signals["MACD"] = "🟢 金叉（看多）"
            elif prev["MACD_DIF"] >= prev["MACD_SIGNAL"] and last["MACD_DIF"] < last["MACD_SIGNAL"]:
                signals["MACD"] = "🔴 死叉（看空）"
            elif last["MACD_HIST"] > 0:
                signals["MACD"] = "🟢 多头运行"
            else:
                signals["MACD"] = "🔴 空头运行"

    # KDJ 信号
    if "K" in df.columns and "D" in df.columns:
        if pd.notna(last["K"]) and pd.notna(last["D"]):
            if last["K"] > 80 and last["D"] > 80:
                signals["KDJ"] = "🔴 超买区域"
            elif last["K"] < 20 and last["D"] < 20:
                signals["KDJ"] = "🟢 超卖区域"
            elif prev["K"] <= prev["D"] and last["K"] > last["D"]:
                signals["KDJ"] = "🟢 金叉（看多）"
            elif prev["K"] >= prev["D"] and last["K"] < last["D"]:
                signals["KDJ"] = "🔴 死叉（看空）"
            else:
                signals["KDJ"] = "⚪ 震荡"

    # RSI 信号
    if "RSI" in df.columns:
        if pd.notna(last["RSI"]):
            if last["RSI"] > 70:
                signals["RSI"] = "🔴 超买"
            elif last["RSI"] < 30:
                signals["RSI"] = "🟢 超卖"
            else:
                signals["RSI"] = "⚪ 正常区间"

    # 均线信号
    ma_cols = [f"MA{p}" for p in MA_PERIODS if f"MA{p}" in df.columns]
    if ma_cols:
        ma_vals = {col: last[col] for col in ma_cols if pd.notna(last[col])}
        if len(ma_vals) >= 2:
            sorted_mas = sorted(ma_vals.items(), key=lambda x: int(x[0][2:]))
            is_bullish = all(sorted_mas[i][1] > sorted_mas[i + 1][1] for i in range(len(sorted_mas) - 1))
            is_bearish = all(sorted_mas[i][1] < sorted_mas[i + 1][1] for i in range(len(sorted_mas) - 1))
            if is_bullish:
                signals["均线"] = "🟢 多头排列"
            elif is_bearish:
                signals["均线"] = "🔴 空头排列"
            else:
                signals["均线"] = "⚪ 交叉缠绕"

    return signals


def get_all_conclusions(df: pd.DataFrame) -> dict:
    """
    获取所有技术指标的具体结论
    """
    conclusions = {
        "MACD": get_macd_conclusion(df),
        "KDJ": get_kdj_conclusion(df),
        "RSI": get_rsi_conclusion(df),
        "均线": get_ma_conclusion(df),
    }
    return conclusions


def get_overall_technical_verdict(conclusions: dict) -> dict:
    """
    汇总所有技术指标结论，给出整体技术面判断
    返回: { "direction": "偏多"/"偏空"/"震荡", "score": 0~100, "reason": "核心理由" }
    """
    scores = []
    bullish_reasons = []
    bearish_reasons = []

    for name, info in conclusions.items():
        score = info.get("score", 50)
        scores.append(score)
        signal = info.get("signal", "震荡")
        if signal == "偏多":
            bullish_reasons.append(f"{name}偏多")
        elif signal == "偏空":
            bearish_reasons.append(f"{name}偏空")

    avg_score = sum(scores) / len(scores) if scores else 50

    if avg_score >= 58:
        direction = "偏多"
    elif avg_score <= 42:
        direction = "偏空"
    else:
        direction = "震荡"

    # 生成核心理由
    if bullish_reasons and not bearish_reasons:
        reason = f"所有指标均偏多：{'、'.join(bullish_reasons)}"
    elif bearish_reasons and not bullish_reasons:
        reason = f"所有指标均偏空：{'、'.join(bearish_reasons)}"
    elif bullish_reasons and bearish_reasons:
        reason = f"多空分歧：偏多指标有{'、'.join(bullish_reasons)}；偏空指标有{'、'.join(bearish_reasons)}"
    else:
        reason = "多数指标处于震荡区间，方向不明确"

    return {
        "direction": direction,
        "score": round(avg_score, 1),
        "reason": reason,
    }
