"""
缠论分析模块 - 基础笔段划分算法
实现缠论的核心概念：分型、笔、线段
"""
import pandas as pd
import numpy as np
from config import CHAN_MIN_BARS


def find_fractals(df: pd.DataFrame) -> pd.DataFrame:
    """
    识别顶分型和底分型

    缠论定义：
    - 顶分型：第二根K线的高点最高，且三根K线的高点呈"中间高两边低"
    - 底分型：第二根K线的低点最低，且三根K线的低点呈"中间低两边高"
    """
    df = df.copy()
    df["fractal_type"] = 0

    for i in range(1, len(df) - 1):
        # 顶分型判断
        if (df["high"].iloc[i] > df["high"].iloc[i - 1] and
                df["high"].iloc[i] > df["high"].iloc[i + 1] and
                df["low"].iloc[i] > df["low"].iloc[i - 1] and
                df["low"].iloc[i] > df["low"].iloc[i + 1]):
            df.iloc[i, df.columns.get_loc("fractal_type")] = 1

        # 底分型判断
        elif (df["low"].iloc[i] < df["low"].iloc[i - 1] and
              df["low"].iloc[i] < df["low"].iloc[i + 1] and
              df["high"].iloc[i] < df["high"].iloc[i - 1] and
              df["high"].iloc[i] < df["high"].iloc[i + 1]):
            df.iloc[i, df.columns.get_loc("fractal_type")] = -1

    return df


def merge_inclusive_klines(df: pd.DataFrame) -> pd.DataFrame:
    """处理K线包含关系"""
    if len(df) < 2:
        return df

    merged = df.copy()
    to_drop = []

    i = 1
    while i < len(merged):
        prev = merged.iloc[i - 1]
        curr = merged.iloc[i]

        is_inclusive = (
            (curr["high"] <= prev["high"] and curr["low"] >= prev["low"]) or
            (prev["high"] <= curr["high"] and prev["low"] >= curr["low"])
        )

        if is_inclusive:
            if i >= 2:
                prev_prev = merged.iloc[i - 2]
                direction = 1 if prev["high"] > prev_prev["high"] else -1
            else:
                direction = 1 if curr["close"] > prev["close"] else -1

            if direction == 1:
                merged.iloc[i - 1, merged.columns.get_loc("high")] = max(prev["high"], curr["high"])
                merged.iloc[i - 1, merged.columns.get_loc("low")] = max(prev["low"], curr["low"])
            else:
                merged.iloc[i - 1, merged.columns.get_loc("high")] = min(prev["high"], curr["high"])
                merged.iloc[i - 1, merged.columns.get_loc("low")] = min(prev["low"], curr["low"])

            to_drop.append(i)
            i += 1
        else:
            i += 1

    if to_drop:
        merged = merged.drop(merged.index[to_drop]).reset_index(drop=True)

    return merged


def find_bi(df: pd.DataFrame, min_bars: int = CHAN_MIN_BARS) -> list:
    """识别笔"""
    fractals = df[df["fractal_type"] != 0].copy()

    if len(fractals) < 2:
        return []

    bi_list = []
    last_fractal_idx = fractals.index[0]
    last_fractal_type = fractals.iloc[0]["fractal_type"]

    for i in range(1, len(fractals)):
        curr_idx = fractals.index[i]
        curr_type = fractals.iloc[i]["fractal_type"]

        if (curr_type != last_fractal_type and
                curr_idx - last_fractal_idx >= min_bars):
            direction = 1 if last_fractal_type == -1 else -1
            bi_list.append((last_fractal_idx, curr_idx, direction))
            last_fractal_idx = curr_idx
            last_fractal_type = curr_type
        else:
            if last_fractal_type == 1 and curr_type == 1:
                if df["high"].iloc[curr_idx] > df["high"].iloc[last_fractal_idx]:
                    last_fractal_idx = curr_idx
            elif last_fractal_type == -1 and curr_type == -1:
                if df["low"].iloc[curr_idx] < df["low"].iloc[last_fractal_idx]:
                    last_fractal_idx = curr_idx

    return bi_list


def find_duan(df: pd.DataFrame, bi_list: list) -> list:
    """识别线段"""
    if len(bi_list) < 3:
        return []

    duan_list = []
    start_idx = bi_list[0][0]

    for i in range(2, len(bi_list)):
        bi1 = bi_list[i - 2]
        bi2 = bi_list[i - 1]
        bi3 = bi_list[i]

        if bi1[2] == 1:
            if df["low"].iloc[bi3[1]] < df["low"].iloc[bi1[1]]:
                duan_list.append((start_idx, bi2[1]))
                start_idx = bi2[1]
        else:
            if df["high"].iloc[bi3[1]] > df["high"].iloc[bi1[1]]:
                duan_list.append((start_idx, bi2[1]))
                start_idx = bi2[1]

    if start_idx != bi_list[-1][1]:
        duan_list.append((start_idx, bi_list[-1][1]))

    return duan_list


def analyze_chan(df: pd.DataFrame) -> dict:
    """执行完整的缠论分析"""
    if df.empty or len(df) < 5:
        return {"fractals": pd.DataFrame(), "bi": [], "duan": []}

    merged = merge_inclusive_klines(df)
    merged = find_fractals(merged)
    bi_list = find_bi(merged)
    duan_list = find_duan(merged, bi_list)
    df_marked = find_fractals(df)

    return {
        "fractals": df_marked[df_marked["fractal_type"] != 0],
        "bi": bi_list,
        "duan": duan_list,
        "merged_df": merged,
    }


def get_chan_conclusion(df: pd.DataFrame, chan_result: dict) -> dict:
    """
    生成缠论方向性判断
    """
    bi_list = chan_result.get("bi", [])
    duan_list = chan_result.get("duan", [])

    if not bi_list:
        return {"signal": "未知", "conclusion": "缠论数据不足，无法识别笔结构", "score": 50}

    # 看最近一笔的方向
    last_bi = bi_list[-1]
    direction = last_bi[2]  # 1=向上笔, -1=向下笔

    # 统计近期笔的方向
    recent_bi = bi_list[-min(5, len(bi_list)):]
    up_count = sum(1 for b in recent_bi if b[2] == 1)
    down_count = sum(1 for b in recent_bi if b[2] == -1)

    score = 50
    if direction == 1:  # 当前向上笔
        score += 10
        trend_word = "向上笔运行中"
    else:
        score -= 10
        trend_word = "向下笔运行中"

    if up_count > down_count:
        score += 5
        recent_trend = "近期偏多"
    elif down_count > up_count:
        score -= 5
        recent_trend = "近期偏空"
    else:
        recent_trend = "近期震荡"

    # 线段方向
    if duan_list:
        last_duan = duan_list[-1]
        duan_start = df["low"].iloc[last_duan[0]] if last_duan[0] < len(df) else 0
        duan_end = df["low"].iloc[last_duan[1]] if last_duan[1] < len(df) else 0
        if duan_end > duan_start:
            score += 5
            duan_trend = "线段向上"
        else:
            score -= 5
            duan_trend = "线段向下"
    else:
        duan_trend = "线段不明"

    score = max(0, min(100, score))
    signal = "偏多" if score >= 58 else "偏空" if score <= 42 else "震荡"

    conclusion = f"当前{trend_word}，{recent_trend}，{duan_trend}，共识别{len(bi_list)}笔、{len(duan_list)}线段"

    return {"signal": signal, "conclusion": conclusion, "score": score}
