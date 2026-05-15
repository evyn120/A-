"""
消息面分析视图
新闻聚合、事件日历、情感分析
"""
import streamlit as st
import pandas as pd
from config import DEFAULT_SYMBOLS, ECONOMIC_EVENTS
from services.news_scraper import get_news, get_news_sentiment_score


def render_news():
    """渲染消息面分析页"""
    # 返回首页按钮
    if st.button("← 返回首页", key="back_home_news"):
        st.session_state.page = "home"; st.rerun()

    st.title("📰 消息面分析")
    st.markdown("---")

    # ===== 1. 黄金相关新闻 =====
    st.subheader("📰 黄金相关新闻")

    with st.spinner("正在获取新闻数据，请稍候..."):
        news_df = get_news()

    if news_df.empty:
        st.warning("⚠️ 暂时无法获取新闻数据，请稍后重试。可能原因：网络连接问题或数据源暂时不可用。")
    else:
        # 新闻情感统计
        sentiment_score = get_news_sentiment_score(news_df)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("新闻总数", sentiment_score.get("total", 0))
        with col2:
            st.metric("看多新闻", sentiment_score.get("bullish_count", 0))
        with col3:
            st.metric("看空新闻", sentiment_score.get("bearish_count", 0))

        # 新闻列表
        for idx, row in news_df.iterrows():
            direction = row.get("情感", "中性")
            if direction == "看多":
                tag_class = "tag-bullish"
                tag_text = "🟢 看多"
            elif direction == "看空":
                tag_class = "tag-bearish"
                tag_text = "🔴 看空"
            else:
                tag_class = "tag-neutral"
                tag_text = "⚪ 中性"

            title = row.get("标题", "无标题")
            source = row.get("来源", "未知")
            date = row.get("时间", "")
            link = row.get("链接", "")

            title_html = f"<strong>{title}</strong>"
            if link:
                title_html = f'<a href="{link}" target="_blank" style="color:#4facfe; text-decoration:none;">{title_html}</a>'

            st.markdown(f"""
            <div class="news-item">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>{title_html}</div>
                    <span class="conclusion-tag {tag_class}">{tag_text}</span>
                </div>
                <div style="color:#94a3b8; font-size:0.85em; margin-top:4px;">
                    📌 {source} &nbsp;|&nbsp; 🕐 {date}
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # ===== 2. 消息面情感评分 =====
    st.subheader("📊 消息面情感评分")

    if not news_df.empty:
        score = sentiment_score.get("score", 50)
        direction = sentiment_score.get("direction", "中性")
        confidence = sentiment_score.get("confidence", "低")

        if direction == "偏多":
            tag_class = "tag-bullish"
            tag_text = "🟢 偏多"
        elif direction == "偏空":
            tag_class = "tag-bearish"
            tag_text = "🔴 偏空"
        else:
            tag_class = "tag-neutral"
            tag_text = "⚪ 中性"

        st.markdown(f"""
        <div style="text-align:center; padding: 20px;">
            <span class="conclusion-tag {tag_class}" style="font-size:1.3em; padding: 8px 24px;">
                {tag_text}
            </span>
            <p style="margin-top:12px; font-size:1.1em; color:#1e293b;">
                综合评分：<strong>{score}</strong>/100 &nbsp;|&nbsp; 置信度：<strong>{confidence}</strong>
            </p>
            <p style="color:#64748b; font-size:0.95em;">
                看多占比 {sentiment_score.get('bullish_ratio', 0)}% &nbsp;|&nbsp;
                看空占比 {sentiment_score.get('bearish_ratio', 0)}%
            </p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("暂无足够数据进行情感分析")

    st.markdown("---")

    # ===== 3. 重大经济事件日历 =====
    st.subheader("📅 重大经济事件日历")
    st.caption("以下为近期需关注的关键经济事件")

    for event in ECONOMIC_EVENTS:
        impact = event.get("impact", "中")
        if impact == "极高":
            impact_color = "#dc2626"
            impact_bg = "#fee2e2"
        elif impact == "高":
            impact_color = "#f97316"
            impact_bg = "#fff7ed"
        elif impact == "中":
            impact_color = "#64748b"
            impact_bg = "#f1f5f9"
        else:
            impact_color = "#94a3b8"
            impact_bg = "#f8fafc"

        st.markdown(f"""
        <div class="news-item">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <strong>{event['name']}</strong>
                <span style="background:{impact_bg}; color:{impact_color}; padding:3px 10px;
                             border-radius:12px; font-size:0.8em; font-weight:600;">
                    影响力：{impact}
                </span>
            </div>
            <div style="color:#94a3b8; font-size:0.85em; margin-top:4px;">
                🔄 {event['frequency']}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 底部提示
    st.markdown("---")
    st.caption("⚠️ 新闻数据来源于公开网络，情感分析基于关键词匹配，仅供参考。")
