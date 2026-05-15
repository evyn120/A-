"""
技术分析视图
展示MACD/KDJ/RSI/均线/缠论/波浪理论的具体结论
"""
import streamlit as st
import pandas as pd
from config import DEFAULT_SYMBOLS, FUTURES_SYMBOLS, KLINE_PERIODS
from services.market_data import get_kline_data, resolve_symbol
from services.technical_analysis import (
    calc_all_indicators,
    get_indicator_signals,
    get_all_conclusions,
    get_overall_technical_verdict,
)
from services.chan_theory import analyze_chan, get_chan_conclusion
from services.elliott_wave import analyze_elliott, get_elliott_conclusion
from utils.chart_helper import (
    create_kline_chart,
    create_macd_chart,
    create_kdj_chart,
    create_rsi_chart,
    create_kline_with_chan,
    create_kline_with_elliott,
)


def render_technical():
    """渲染技术分析页"""
    # 返回首页按钮
    if st.button("← 返回首页", key="back_home_tech"):
        st.session_state.page = "home"; st.rerun()

    st.title("📈 技术分析")
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
        key="tech_symbol_select",
    )

    if not selected:
        return

    symbol = all_symbols[selected]

    # K线周期选择
    col1, col2 = st.columns([1, 3])
    with col1:
        period = st.selectbox(
            "K线周期",
            options=list(KLINE_PERIODS.keys()),
            index=0,
            key="tech_period_select",
        )

    # 获取数据
    df = get_kline_data(symbol, period)
    if df.empty:
        st.warning(f"暂无 {selected} 的数据")
        return

    # 计算指标
    df = calc_all_indicators(df)

    # ===== 1. K线图 =====
    st.subheader("📊 K线走势")
    fig_kline = create_kline_chart(df, title=f"{selected} - {period}", show_ma=True, show_volume=True)
    st.plotly_chart(fig_kline, use_container_width=True)

    st.markdown("---")

    # ===== 2. 各指标结论 =====
    st.subheader("📋 技术指标具体结论")

    conclusions = get_all_conclusions(df)

    # MACD
    with st.expander("📉 MACD 结论", expanded=True):
        macd = conclusions.get("MACD", {})
        _render_conclusion_card("MACD", macd)
        fig_macd = create_macd_chart(df)
        st.plotly_chart(fig_macd, use_container_width=True)

    # KDJ
    with st.expander("📊 KDJ 结论", expanded=True):
        kdj = conclusions.get("KDJ", {})
        _render_conclusion_card("KDJ", kdj)
        fig_kdj = create_kdj_chart(df)
        st.plotly_chart(fig_kdj, use_container_width=True)

    # RSI
    with st.expander("📐 RSI 结论", expanded=True):
        rsi = conclusions.get("RSI", {})
        _render_conclusion_card("RSI", rsi)
        fig_rsi = create_rsi_chart(df)
        st.plotly_chart(fig_rsi, use_container_width=True)

    # 均线
    with st.expander("📏 均线 结论", expanded=True):
        ma = conclusions.get("均线", {})
        _render_conclusion_card("均线", ma)

    st.markdown("---")

    # ===== 3. 缠论分析 =====
    st.subheader("🔮 缠论分析")
    chan_result = analyze_chan(df)
    chan_conclusion = get_chan_conclusion(df, chan_result)
    _render_conclusion_card("缠论", chan_conclusion)

    with st.expander("查看缠论K线图"):
        fig_chan = create_kline_with_chan(df, chan_result, title=f"{selected} - 缠论分析")
        st.plotly_chart(fig_chan, use_container_width=True)

    # 显示笔和线段统计
    col1, col2 = st.columns(2)
    with col1:
        st.metric("识别笔数", len(chan_result.get("bi", [])))
    with col2:
        st.metric("识别线段数", len(chan_result.get("duan", [])))

    st.markdown("---")

    # ===== 4. 波浪理论 =====
    st.subheader("🌊 波浪理论分析")
    elliott_result = analyze_elliott(df)
    elliott_conclusion = get_elliott_conclusion(elliott_result)
    _render_conclusion_card("波浪理论", elliott_conclusion)

    with st.expander("查看波浪理论K线图"):
        fig_elliott = create_kline_with_elliott(df, elliott_result, title=f"{selected} - 波浪理论分析")
        st.plotly_chart(fig_elliott, use_container_width=True)

    # 浪型统计
    col1, col2 = st.columns(2)
    with col1:
        st.metric("推动浪数", len(elliott_result.get("impulse_waves", [])))
    with col2:
        st.metric("调整浪数", len(elliott_result.get("corrective_waves", [])))

    # 当前浪型状态
    current_status = elliott_result.get("current_status", {})
    if current_status:
        st.info(f"📍 当前浪型：{current_status.get('current_position', '未知')} — {current_status.get('suggestion', '')}")

    st.markdown("---")

    # ===== 5. 信号汇总 =====
    st.subheader("🎯 信号汇总与整体判断")

    # 简化信号
    signals = get_indicator_signals(df)
    if signals:
        cols = st.columns(len(signals))
        for i, (name, signal) in enumerate(signals.items()):
            with cols[i]:
                st.metric(name, signal)

    # 综合所有结论（包括缠论和波浪）
    all_conclusions = dict(conclusions)
    all_conclusions["缠论"] = chan_conclusion
    all_conclusions["波浪理论"] = elliott_conclusion

    verdict = get_overall_technical_verdict(all_conclusions)

    # 显示整体判断
    st.markdown("### 🔥 整体技术面判断")

    # 方向标签
    direction = verdict["direction"]
    if direction == "偏多":
        tag_class = "tag-bullish"
        tag_text = "🟢 偏多"
    elif direction == "偏空":
        tag_class = "tag-bearish"
        tag_text = "🔴 偏空"
    else:
        tag_class = "tag-neutral"
        tag_text = "⚪ 震荡"

    st.markdown(f"""
    <div style="text-align:center; padding: 20px;">
        <span class="conclusion-tag {tag_class}" style="font-size:1.3em; padding: 8px 24px;">
            {tag_text}
        </span>
        <p style="margin-top:12px; font-size:1.1em; color:#1e293b;">
            综合评分：<strong>{verdict['score']}</strong>/100
        </p>
        <p style="color:#64748b; font-size:0.95em;">{verdict['reason']}</p>
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
