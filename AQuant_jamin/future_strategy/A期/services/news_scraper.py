"""
新闻爬取服务
从 Google News / finviz 等来源爬取黄金相关新闻
"""
import pandas as pd
import streamlit as st
from config import POSITIVE_KEYWORDS, NEGATIVE_KEYWORDS
from services.sentiment import analyze_sentiment

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_SCRAPING = True
except ImportError:
    HAS_SCRAPING = False


def _scrape_google_news() -> list:
    """爬取 Google News 的黄金相关新闻"""
    if not HAS_SCRAPING:
        return []

    articles = []
    url = "https://news.google.com/search?q=gold+price+forecast+OR+gold+market+analysis&hl=en-US&gl=US&ceid=US:en"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        items = soup.select("article") or soup.select("div.xrnccd")

        for item in items[:15]:
            try:
                # 标题
                title_el = item.select_one("h3 a, h4 a, .JtKRv a")
                title = title_el.get_text(strip=True) if title_el else ""

                # 链接
                link = ""
                if title_el and title_el.get("href"):
                    href = title_el.get("href", "")
                    if href.startswith("./"):
                        link = "https://news.google.com" + href[1:]
                    elif href.startswith("/"):
                        link = "https://news.google.com" + href
                    else:
                        link = href

                # 时间
                time_el = item.select_one("time, .WW6dff")
                date_str = time_el.get("datetime", "") if time_el else ""
                if not date_str and time_el:
                    date_str = time_el.get_text(strip=True)

                # 来源
                source_el = item.select_one(".wEwyrc, .vr1PYe")
                source = source_el.get_text(strip=True) if source_el else "Google News"

                if not title:
                    continue

                sentiment = analyze_sentiment(title)

                articles.append({
                    "标题": title,
                    "来源": source,
                    "链接": link,
                    "时间": date_str,
                    "情感": sentiment["direction"],
                    "得分": sentiment["score"],
                })
            except Exception:
                continue

    except Exception:
        pass

    return articles


def _scrape_finviz() -> list:
    """爬取 finviz 的黄金相关新闻"""
    if not HAS_SCRAPING:
        return []

    articles = []
    url = "https://finviz.com/news.ashx?v=3&t=GC"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # finviz 新闻表格
        news_table = soup.select_one("table.news_table") or soup.select_one("table#news-table")
        if news_table:
            rows = news_table.select("tr")
            current_date = ""
            for row in rows[:20]:
                try:
                    # 日期
                    date_el = row.select_one("td:first-child span")
                    if date_el:
                        date_text = date_el.get_text(strip=True)
                        if date_text:
                            current_date = date_text

                    # 标题和链接
                    link_el = row.select_one("a.tab-link-news, td a")
                    if link_el:
                        title = link_el.get_text(strip=True)
                        link = link_el.get("href", "")

                        # 来源
                        source_el = row.select_one("span.newslink-right, .news-link-left + span")
                        source = source_el.get_text(strip=True) if source_el else "Finviz"

                        if not title:
                            continue

                        sentiment = analyze_sentiment(title)

                        articles.append({
                            "标题": title,
                            "来源": source,
                            "链接": link,
                            "时间": current_date,
                            "情感": sentiment["direction"],
                            "得分": sentiment["score"],
                        })
                except Exception:
                    continue
        else:
            # 尝试备选选择器
            links = soup.select("a.news-link-left, a[href*='news']")
            for link_el in links[:10]:
                try:
                    title = link_el.get_text(strip=True)
                    link = link_el.get("href", "")
                    if not title:
                        continue

                    sentiment = analyze_sentiment(title)
                    articles.append({
                        "标题": title,
                        "来源": "Finviz",
                        "链接": link,
                        "时间": "",
                        "情感": sentiment["direction"],
                        "得分": sentiment["score"],
                    })
                except Exception:
                    continue

    except Exception:
        pass

    return articles


@st.cache_data(ttl=600, show_spinner="正在爬取黄金相关新闻...")
def get_news() -> pd.DataFrame:
    """
    获取黄金相关新闻
    """
    all_news = []

    # 爬取 Google News
    try:
        google_news = _scrape_google_news()
        all_news.extend(google_news)
    except Exception:
        pass

    # 爬取 Finviz
    try:
        finviz_news = _scrape_finviz()
        all_news.extend(finviz_news)
    except Exception:
        pass

    if not all_news:
        # 返回空 DataFrame 而非占位数据
        return pd.DataFrame(columns=["标题", "来源", "链接", "时间", "情感", "得分"])

    return pd.DataFrame(all_news)


def get_news_sentiment_score(news_df: pd.DataFrame) -> dict:
    """
    计算新闻整体情感评分
    """
    if news_df.empty or "情感" not in news_df.columns:
        return {"score": 50, "direction": "中性", "confidence": "低"}

    directions = news_df["情感"].tolist()
    bullish = sum(1 for d in directions if d == "看多")
    bearish = sum(1 for d in directions if d == "看空")
    neutral = sum(1 for d in directions if d == "中性")
    total = len(directions)

    if total == 0:
        return {"score": 50, "direction": "中性", "confidence": "低"}

    score = 50 + (bullish / total - bearish / total) * 50
    score = max(0, min(100, score))

    if score >= 60:
        direction = "偏多"
    elif score <= 40:
        direction = "偏空"
    else:
        direction = "中性"

    confidence = "高" if total >= 8 else "中" if total >= 4 else "低"

    return {
        "score": round(score, 1),
        "direction": direction,
        "confidence": confidence,
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "total": total,
    }
