"""
情感分析服务
基于关键词匹配的文本情感分析
"""
import pandas as pd
from config import POSITIVE_KEYWORDS, NEGATIVE_KEYWORDS


def analyze_sentiment(text: str) -> dict:
    """
    对文本进行情感分析（关键词匹配法）

    Args:
        text: 待分析文本

    Returns:
        情感分析结果字典
    """
    if not text:
        return {
            "text": text,
            "sentiment": "neutral",
            "direction": "中性",
            "score": 0.0,
            "confidence": 0.0,
        }

    text_lower = text.lower()
    pos_matches = [kw for kw in POSITIVE_KEYWORDS if kw.lower() in text_lower]
    neg_matches = [kw for kw in NEGATIVE_KEYWORDS if kw.lower() in text_lower]

    pos_count = len(pos_matches)
    neg_count = len(neg_matches)

    # 计算情感得分 (-1 到 1)
    total = pos_count + neg_count
    if total == 0:
        score = 0.0
        sentiment = "neutral"
        direction = "中性"
        confidence = 0.0
    else:
        score = (pos_count - neg_count) / total
        confidence = min(total / 5, 1.0)  # 匹配越多置信度越高

        if score > 0.2:
            sentiment = "positive"
            direction = "看多"
        elif score < -0.2:
            sentiment = "negative"
            direction = "看空"
        else:
            sentiment = "neutral"
            direction = "中性"

    return {
        "text": text[:100],
        "sentiment": sentiment,
        "direction": direction,
        "score": round(score, 2),
        "confidence": round(confidence, 2),
        "pos_keywords": pos_matches[:3],
        "neg_keywords": neg_matches[:3],
    }


def batch_sentiment(texts: list) -> pd.DataFrame:
    """
    批量情感分析

    Args:
        texts: 待分析文本列表

    Returns:
        情感分析结果 DataFrame
    """
    results = [analyze_sentiment(t) for t in texts]
    return pd.DataFrame(results)


def get_overall_sentiment_score(results_df: pd.DataFrame) -> dict:
    """
    计算整体情感评分

    Returns:
        {"score": 0-100, "direction": "偏多/偏空/中性", "confidence": "高/中/低"}
    """
    if results_df.empty:
        return {"score": 50, "direction": "中性", "confidence": "低"}

    scores = results_df["score"].tolist()
    avg_score = sum(scores) / len(scores)

    # 映射到 0-100
    mapped_score = 50 + avg_score * 50
    mapped_score = max(0, min(100, mapped_score))

    directions = results_df["direction"].tolist()
    bullish = sum(1 for d in directions if d == "看多")
    bearish = sum(1 for d in directions if d == "看空")
    total = len(directions)

    if mapped_score >= 60:
        direction = "偏多"
    elif mapped_score <= 40:
        direction = "偏空"
    else:
        direction = "中性"

    confidence = "高" if total >= 5 else "中" if total >= 3 else "低"

    return {
        "score": round(mapped_score, 1),
        "direction": direction,
        "confidence": confidence,
        "bullish_ratio": round(bullish / total * 100, 1) if total > 0 else 0,
        "bearish_ratio": round(bearish / total * 100, 1) if total > 0 else 0,
    }
