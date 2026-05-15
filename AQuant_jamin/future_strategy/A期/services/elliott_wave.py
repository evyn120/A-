"""
波浪理论分析模块 - Elliott Wave 基础实现
识别推动浪（5浪）和调整浪（3浪）的基本结构
"""
import pandas as pd
import numpy as np
from config import WAVE_MIN_SIZE


def find_swing_points(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """识别摆动高低点（Swing Points）"""
    df = df.copy()
    df["swing_type"] = 0

    for i in range(window, len(df) - window):
        is_high = True
        for j in range(1, window + 1):
            if df["high"].iloc[i] <= df["high"].iloc[i - j] or \
               df["high"].iloc[i] <= df["high"].iloc[i + j]:
                is_high = False
                break
        if is_high:
            df.iloc[i, df.columns.get_loc("swing_type")] = 1
            continue

        is_low = True
        for j in range(1, window + 1):
            if df["low"].iloc[i] >= df["low"].iloc[i - j] or \
               df["low"].iloc[i] >= df["low"].iloc[i + j]:
                is_low = False
                break
        if is_low:
            df.iloc[i, df.columns.get_loc("swing_type")] = -1

    return df


def identify_impulse_wave(swing_points: list, min_size: float = WAVE_MIN_SIZE) -> list:
    """识别推动浪（Impulse Wave）"""
    if len(swing_points) < 6:
        return []

    waves = []
    for start in range(len(swing_points) - 5):
        points = swing_points[start:start + 6]

        valid_alternation = True
        for i in range(1, len(points)):
            if points[i][2] == points[i - 1][2]:
                valid_alternation = False
                break
        if not valid_alternation:
            continue

        prices = [p[1] for p in points]
        is_bullish = points[0][2] == -1

        if is_bullish:
            w1 = prices[1] - prices[0]
            w2 = prices[1] - prices[2]
            w3 = prices[3] - prices[2]
            w4 = prices[3] - prices[4]
            w5 = prices[5] - prices[4]
            if w1 <= 0 or w3 <= 0 or w5 <= 0:
                continue
            if w2 <= 0 or w4 <= 0:
                continue
        else:
            w1 = prices[0] - prices[1]
            w2 = prices[2] - prices[1]
            w3 = prices[2] - prices[3]
            w4 = prices[4] - prices[3]
            w5 = prices[4] - prices[5]
            if w1 <= 0 or w3 <= 0 or w5 <= 0:
                continue
            if w2 <= 0 or w4 <= 0:
                continue

        if w2 / w1 > 1.0:
            continue
        if w3 < w1 and w3 < w5:
            continue
        if is_bullish:
            if prices[4] < prices[1]:
                continue
        else:
            if prices[4] > prices[1]:
                continue

        total_range = abs(prices[-1] - prices[0])
        if total_range / prices[0] < min_size:
            continue

        wave_info = {
            "type": "Impulse" if is_bullish else "Impulse (Down)",
            "direction": "上升" if is_bullish else "下降",
            "start_idx": points[0][0],
            "end_idx": points[-1][0],
            "points": points,
            "wave_sizes": {
                "W1": round(w1, 2),
                "W2": round(w2, 2),
                "W3": round(w3, 2),
                "W4": round(w4, 2),
                "W5": round(w5, 2),
            },
            "retracement": {
                "W2/W1": round(w2 / w1 * 100, 1),
                "W4/W3": round(w4 / w3 * 100, 1),
            },
        }
        waves.append(wave_info)

    return waves


def identify_corrective_wave(swing_points: list, min_size: float = WAVE_MIN_SIZE) -> list:
    """识别调整浪（Corrective Wave）"""
    if len(swing_points) < 4:
        return []

    waves = []
    for start in range(len(swing_points) - 3):
        points = swing_points[start:start + 4]
        prices = [p[1] for p in points]

        valid = True
        for i in range(1, len(points)):
            if points[i][2] == points[i - 1][2]:
                valid = False
                break
        if not valid:
            continue

        is_zigzag = points[0][2] == 1

        if is_zigzag:
            wa = prices[0] - prices[1]
            wb = prices[2] - prices[1]
            wc = prices[2] - prices[3]
            if wa <= 0 or wc <= 0 or wb <= 0:
                continue
        else:
            wa = prices[1] - prices[0]
            wb = prices[1] - prices[2]
            wc = prices[3] - prices[2]
            if wa <= 0 or wc <= 0 or wb <= 0:
                continue

        b_retracement = wb / wa
        if b_retracement < 0.236 or b_retracement > 1.0:
            continue

        total_range = abs(prices[-1] - prices[0])
        if total_range / prices[0] < min_size:
            continue

        wave_info = {
            "type": "Zigzag" if is_zigzag else "Zigzag (Up)",
            "direction": "之字形调整" if is_zigzag else "倒之字形调整",
            "start_idx": points[0][0],
            "end_idx": points[-1][0],
            "points": points,
            "wave_sizes": {
                "A": round(wa, 2),
                "B": round(wb, 2),
                "C": round(wc, 2),
            },
            "b_retracement": round(b_retracement * 100, 1),
        }
        waves.append(wave_info)

    return waves


def analyze_elliott(df: pd.DataFrame, swing_window: int = 5) -> dict:
    """执行完整的波浪理论分析"""
    if df.empty or len(df) < swing_window * 2 + 1:
        return {"impulse_waves": [], "corrective_waves": [], "swing_df": pd.DataFrame()}

    swing_df = find_swing_points(df, window=swing_window)

    swing_points = []
    for idx, row in swing_df[swing_df["swing_type"] != 0].iterrows():
        if row["swing_type"] == 1:
            swing_points.append((idx, row["high"], 1))
        else:
            swing_points.append((idx, row["low"], -1))

    impulse_waves = identify_impulse_wave(swing_points)
    corrective_waves = identify_corrective_wave(swing_points)
    current_wave_status = _get_current_wave_status(impulse_waves, corrective_waves)

    return {
        "impulse_waves": impulse_waves,
        "corrective_waves": corrective_waves,
        "swing_df": swing_df,
        "current_status": current_wave_status,
    }


def _get_current_wave_status(impulse_waves: list, corrective_waves: list) -> dict:
    """判断当前可能所处的浪型"""
    status = {
        "latest_impulse": None,
        "latest_corrective": None,
        "current_position": "未知",
        "suggestion": "数据不足，无法判断",
    }

    if impulse_waves:
        latest = impulse_waves[-1]
        status["latest_impulse"] = latest
        status["current_position"] = f"推动浪中（{latest['direction']}方向）"
        sizes = latest["wave_sizes"]
        if "W5" in sizes:
            status["suggestion"] = "推动浪5浪可能完成，关注调整浪开始"

    if corrective_waves:
        latest = corrective_waves[-1]
        status["latest_corrective"] = latest
        if not impulse_waves:
            status["current_position"] = f"调整浪中（{latest['direction']}）"
            status["suggestion"] = "调整浪进行中，等待完成信号"

    return status


def get_elliott_conclusion(elliott_result: dict) -> dict:
    """
    生成波浪理论方向性判断
    """
    impulse_waves = elliott_result.get("impulse_waves", [])
    corrective_waves = elliott_result.get("corrective_waves", [])
    current_status = elliott_result.get("current_status", {})

    if not impulse_waves and not corrective_waves:
        return {"signal": "未知", "conclusion": "波浪理论数据不足，无法识别浪型结构", "score": 50}

    score = 50
    position = current_status.get("current_position", "未知")
    suggestion = current_status.get("suggestion", "")

    # 基于最新推动浪方向
    if impulse_waves:
        latest_impulse = impulse_waves[-1]
        if latest_impulse["direction"] == "上升":
            score += 10
            direction_word = "识别到上升推动浪"
        else:
            score -= 10
            direction_word = "识别到下降推动浪"
    else:
        direction_word = "未识别到推动浪"

    # 基于调整浪
    if corrective_waves:
        latest_corrective = corrective_waves[-1]
        if "之字形调整" in latest_corrective["direction"]:
            score -= 5
            corr_word = "当前处于之字形调整"
        else:
            score += 5
            corr_word = "当前处于倒之字形调整"
    else:
        corr_word = "未识别到调整浪"

    score = max(0, min(100, score))
    signal = "偏多" if score >= 58 else "偏空" if score <= 42 else "震荡"

    conclusion = f"{direction_word}，{corr_word}。当前浪型：{position}。{suggestion}"

    return {"signal": signal, "conclusion": conclusion, "score": score}
