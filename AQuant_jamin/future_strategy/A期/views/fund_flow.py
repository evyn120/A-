"""
资金面分析视图
量价分析、OBV、MFI、量价背离检测
"""
import streamlit as st
import pandas as pd
from config import DEFAULT_SYMBOLS, FUTURES_SYMBOLS, KLINE_PERIODS
from services.market_data import get_kline_data
from services.fund_flow import calc_fund_flow_all, get_fund_flow_conclusions
from utils.chart_helper import (
    create_kline_chart,
    create_obv_chart,
    create_mfi_chart,
)


def render_fund_flow():
    """渲染资金面分析页"""
    # 返回首页按钮
    if st.button("← 返回首页", key="back_home_fund"):
        st.session_state.page = "home"; st.rerun()

    st.title("💰 资金面分析")
    st.markdown("---")

    # 品种选择
    all_symbols = dict(DEFAULT_SYMBOLS)
    all_symbols.update(FUTURES_SYMBOLS)
    if "custom_symbols" in st.session_state and st.session_state.custom_symbols:
        all_symbols.update(st.session_state.custom_symbols)

    selected = st.selectbox(
        "选择品种",
        options=list(all_symbols.keys()),
        format_func=lambda x: f"{x} ({all_symbols[x]})",
        key="fund_symbol_select",
    )

    if not selected:
        return

    symbol = all_symbols[selected]

    # K线周期选择
    period = st.selectbox(
        "K线周期",
        options=list(KLINE_PERIODS.keys()),
        index=0,
        key="fund_period_select",
    )

    # 获取数据
    df = get_kline_data(symbol, period)
    if df.empty:
        st.warning(f"暂无 {selected} 的数据")
        return

    # 计算资金面指标
    df = calc_fund_flow_all(df)

    # ===== 1. 量价分析 =====
    st.subheader("📊 量价分析")

    # K线图（含成交量）
    fig_kline = create_kline_chart(df, title=f"{selected} - {period}", show_ma=True, show_volume=True)
    st.plotly_chart(fig_kline, use_container_width=True)

    st.markdown("---")

    # ===== 2. OBV 能量潮 =====
    st.subheader("📈 OBV 能量潮指标")
    fig_obv = create_obv_chart(df)
    st.plotly_chart(fig_obv, use_container_width=True)

    st.markdown("---")

    # ===== 3. MFI 资金流量 =====
    st.subheader("💸 MFI 资金流量指标")
    fig_mfi = create_mfi_chart(df)
    st.plotly_chart(fig_mfi, use_container_width=True)

    st.markdown("---")

    # ===== 4. 综合结论 =====
    st.subheader("📋 资金面综合结论")

    conclusions = get_fund_flow_conclusions(df)

    # 量价分析结论
    vp = conclusions.get("量价分析", {})
    _render_conclusion_card("量价分析", vp)

    # OBV结论
    obv = conclusions.get("OBV", {})
    _render_conclusion_card("OBV", obv)

    # MFI结论
    mfi = conclusions.get("MFI", {})
    _render_conclusion_card("MFI", mfi)

    # 量价背离
    div = conclusions.get("量价背离", {})
    if div.get("divergence", "无") != "无":
        if div["divergence"] == "顶背离":
            tag_class = "tag-bearish"
            tag_text = "⚠️ 顶背离"
        else:
            tag_class = "tag-bullish"
            tag_text = "✅ 底背离"
        st.markdown(f"""
        <div class="indicator-card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <strong style="font-size:1.1em;">量价背离</strong>
                <span class="conclusion-tag {tag_class}">{tag_text}</span>
            </div>
            <p style="color:#334155; margin:4px 0;">{div.get('conclusion', '')}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("✅ 未检测到明显的量价背离信号")

    st.markdown("---")

    # ===== 5. 整体资金面判断 =====
    st.markdown("### 🔥 整体资金面判断")
    overall = conclusions.get("overall", {})
    direction = overall.get("direction", "中性")
    score = overall.get("score", 50)
    reason = overall.get("reason", "")

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
            综合评分：<strong>{score}</strong>/100
        </p>
        <p style="color:#64748b; font-size:0.95em;">{reason}</p>
    </div>
    """, unsafe_allow_html=True)


def _render_conclusion_card(name: str, info: dict):
    """渲染结论卡片"""
    signal = info.get("signal", "未知")
    conclusion = info.get("conclusion", "无结论")
    score = info.get("score", 50)

    if signal == "偏多":
        tag_class = "tag-bullish"
        tag_text = "🟢 偏多"
    elif signal == "偏空":
        tag_class = "tag-bearish"
        tag_text = "🔴 偏空"
    elif signal == "未知":
        tag_class = "tag-neutral"
        tag_text = "⚪ 未知"
    else:
        tag_class = "tag-neutral"
        tag_text = "⚪ 震荡"

    st.markdown(f"""
    <div class="indicator-card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <strong style="font-size:1.1em;">{name}</strong>
            <span class="conclusion-tag {tag_class}">{tag_text}</span>
        </div>
        <p style="color:#334155; margin:4px 0;">{conclusion}</p>
        <p style="color:#94a3b8; font-size:0.85em;">评分：{score}/100</p>
    </div>
    """, unsafe_allow_html=True)
