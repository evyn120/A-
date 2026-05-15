"""
全品种截面预测视图
基于最新日线 OHLCV 数据，对全部品种执行多维度预测，汇总为可排序表格
"""
import streamlit as st
import pandas as pd

from services.batch_prediction import batch_predict_all, CROSS_SECTION_WEIGHTS


def _color_direction(val):
    if val == "偏多":
        return "background-color:#dcfce7; color:#16a34a; font-weight:bold;"
    if val == "偏空":
        return "background-color:#fee2e2; color:#dc2626; font-weight:bold;"
    if val == "震荡":
        return "background-color:#f1f5f9; color:#64748b;"
    return ""


def render_batch_prediction():
    if st.button("← 返回首页", key="back_home_batch"):
        st.session_state.page = "home"; st.rerun()

    st.title("🧮 全品种截面预测")
    st.caption("基于各期货品种最新收盘量价数据，遍历全部品种执行多维度规则预测，结果按 偏多 → 震荡 → 偏空 依次排序")

    with st.expander("ℹ️ 评分维度与权重说明", expanded=False):
        st.markdown(
            "\n".join([f"- **​{k}​**：权重 {v*100:.0f}%" for k, v in CROSS_SECTION_WEIGHTS.items()])
            + "\n\n方向阈值：综合评分 ≥ 58 → **偏多**；≤ 42 → **偏空**；其余 → **震荡**。"
        )

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 重新计算", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    df = batch_predict_all()
    if df.empty:
        st.warning("没有获取到任何品种的有效数据，请检查 akshare 网络连接或品种代码配置。")
        return

    # 统计概览
    bull = (df["综合预测"] == "偏多").sum()
    bear = (df["综合预测"] == "偏空").sum()
    osc  = (df["综合预测"] == "震荡").sum()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("品种总数", len(df))
    m2.metric("偏多", int(bull))
    m3.metric("震荡", int(osc))
    m4.metric("偏空", int(bear))

    st.markdown("---")

    # 表格展示
    styled = (
        df.style
        .map(_color_direction, subset=["综合预测", "技术面", "资金面", "缠论", "波浪"])
        .format({
            "最新收盘": "{:.2f}",
            "涨跌幅%":  "{:+.2f}%",
            "综合评分": "{:.1f}",
            "技术评分": "{:.1f}",
            "资金评分": "{:.1f}",
            "缠论评分": "{:.1f}",
            "波浪评分": "{:.1f}",
        }, na_rep="—")
    )
    st.dataframe(styled, use_container_width=True, hide_index=True, height=600)

    # 下载
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 下载为 CSV", data=csv, file_name="batch_prediction.csv", mime="text/csv")

    st.caption("⚠️ 截面预测仅基于量价规则与技术指标，未纳入消息面/博主观点，请结合具体行情综合判断。")
