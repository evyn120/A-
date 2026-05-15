"""
博主/分析师观点爬取服务
从 Gold-Eagle、Seeking Alpha、Financial Post 等来源爬取黄金分析文章
"""
import pandas as pd
import re
import streamlit as st
from config import BLOGGER_SOURCES, POSITIVE_KEYWORDS, NEGATIVE_KEYWORDS

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_SCRAPING = True
except ImportError:
    HAS_SCRAPING = False


def _simple_sentiment(text: str) -> str:
    """基于关键词的简单情感分析"""
    text_lower = text.lower()
    pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw.lower() in text_lower)
    neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw.lower() in text_lower)

    if pos_count > neg_count:
        return "看多"
    elif neg_count > pos_count:
        return "看空"
    else:
        return "中性"


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _scrape_gold_eagle() -> list:
    """爬取 gold-eagle.com 的黄金分析文章"""
    if not HAS_SCRAPING:
        return []

    articles = []
    urls = [
        "https://www.gold-eagle.com/article/gold",
    ]

    for url in urls:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # 新版 gold-eagle 使用 div.view-field-content
            items = soup.select("div.view-field-content")

            for item in items[:10]:
                try:
                    # 标题 & 链接 - 在 item 内找第一个 a
                    title_el = item.find("a")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    if not title:
                        continue

                    href = title_el.get("href", "")
                    if href.startswith("/"):
                        link = "https://www.gold-eagle.com" + href
                    elif href.startswith("http"):
                        link = href
                    else:
                        link = ""

                    # 作者 - 找含 author 的 div
                    author_el = item.select_one(".content_author, .views-field-field-author")
                    author = ""
                    if author_el:
                        author = author_el.get_text(strip=True)
                        author = author.replace("By", "").replace("by", "").strip()
                    if not author:
                        # 尝试第二个链接（通常是作者页）
                        all_links = item.find_all("a")
                        if len(all_links) >= 2:
                            author = all_links[1].get_text(strip=True)

                    # 日期 - 暂无，留空
                    date_str = ""

                    # 摘要 - 用标题
                    summary = title

                    sentiment = _simple_sentiment(title)

                    articles.append({
                        "博主": author or "Gold-Eagle Analyst",
                        "平台": "Gold-Eagle",
                        "观点": summary,
                        "标题": title,
                        "链接": link,
                        "时间": date_str or "-",
                        "方向": sentiment,
                    })
                except Exception:
                    continue

        except Exception:
            continue

    return articles


def _scrape_seeking_alpha() -> list:
    """爬取 Seeking Alpha 的黄金新闻"""
    if not HAS_SCRAPING:
        return []

    articles = []
    url = "https://seekingalpha.com/market-news/gold"

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        items = soup.select("article")

        for item in items[:12]:
            try:
                # 标题
                h3 = item.find("h3")
                if not h3:
                    continue
                title = h3.get_text(strip=True)
                if not title:
                    continue

                # 链接
                link = ""
                a_tag = h3.find("a") or item.find("a")
                if a_tag:
                    href = a_tag.get("href", "")
                    if href.startswith("/"):
                        link = "https://seekingalpha.com" + href.split("#")[0]
                    elif href.startswith("http"):
                        link = href

                # 日期 - 在 article 的文本里找
                date_str = ""
                time_el = item.find("time")
                if time_el:
                    date_str = time_el.get_text(strip=True)
                else:
                    # 寻找类似 "May 08" 的日期文本
                    text_content = item.get_text()
                    date_match = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}", text_content)
                    if date_match:
                        date_str = date_match.group()

                sentiment = _simple_sentiment(title)

                articles.append({
                    "博主": "Seeking Alpha",
                    "平台": "Seeking Alpha",
                    "观点": title,
                    "标题": title,
                    "链接": link,
                    "时间": date_str or "-",
                    "方向": sentiment,
                })
            except Exception:
                continue

    except Exception:
        pass

    return articles


def _scrape_financial_post() -> list:
    """爬取 Financial Post 的黄金新闻"""
    if not HAS_SCRAPING:
        return []

    articles = []
    url = "https://financialpost.com/category/commodities/gold"

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        items = soup.select("article")

        for item in items[:10]:
            try:
                # 标题
                h = item.find(["h2", "h3", "h4"])
                if not h:
                    continue
                title = h.get_text(strip=True)
                if not title:
                    continue

                # 链接
                link = ""
                a_tag = h.find("a")
                if a_tag:
                    href = a_tag.get("href", "")
                    if href.startswith("/"):
                        link = "https://financialpost.com" + href
                    elif href.startswith("http"):
                        link = href

                # 摘要
                summary_el = item.find("p")
                summary = summary_el.get_text(strip=True)[:200] if summary_el else title

                # 日期
                date_str = ""
                time_el = item.find("time")
                if time_el:
                    date_str = time_el.get("datetime", "") or time_el.get_text(strip=True)
                    if len(date_str) > 16:
                        date_str = date_str[:16]

                sentiment = _simple_sentiment(title + " " + summary)

                articles.append({
                    "博主": "Financial Post",
                    "平台": "Financial Post",
                    "观点": summary if summary else title,
                    "标题": title,
                    "链接": link,
                    "时间": date_str or "-",
                    "方向": sentiment,
                })
            except Exception:
                continue

    except Exception:
        pass

    return articles


@st.cache_data(ttl=600, show_spinner="正在爬取博主/分析师观点...")
def get_all_blogger_views() -> pd.DataFrame:
    """
    获取所有博主的最新观点
    """
    all_views = []

    # 爬取 Gold-Eagle
    try:
        gold_eagle_views = _scrape_gold_eagle()
        all_views.extend(gold_eagle_views)
    except Exception:
        pass

    # 爬取 Seeking Alpha
    try:
        sa_views = _scrape_seeking_alpha()
        all_views.extend(sa_views)
    except Exception:
        pass

    # 爬取 Financial Post
    try:
        fp_views = _scrape_financial_post()
        all_views.extend(fp_views)
    except Exception:
        pass

    if not all_views:
        # 返回友好提示
        placeholder = []
        for name, info in BLOGGER_SOURCES.items():
            placeholder.append({
                "博主": name,
                "平台": info["platform"],
                "观点": "暂时无法获取数据，请稍后重试",
                "标题": "-",
                "链接": info.get("url", ""),
                "时间": "-",
                "方向": "待定",
            })
        return pd.DataFrame(placeholder)

    return pd.DataFrame(all_views)


def calculate_blogger_score(views_df: pd.DataFrame) -> dict:
    """
    综合博主观点评分
    """
    if views_df.empty:
        return {"score": 50, "direction": "中性", "confidence": "低"}

    directions = views_df["方向"].tolist()
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

    confidence = "高" if total >= 5 else "中" if total >= 3 else "低"

    return {
        "score": round(score, 1),
        "direction": direction,
        "confidence": confidence,
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
    }
