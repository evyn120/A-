# 兼容Python低版本的类型注解语法，确保类型提示正常生效
from __future__ import annotations

# 导入自选股服务：用于生成仪表盘基础数据（简报依赖仪表盘数据）
from .watchlist_service import build_dashboard_payload


def _safe_pct_text(value: float | None) -> str:
    """
    【工具函数】安全格式化涨跌幅百分比文本
    作用：处理空值异常，统一涨跌幅展示格式，避免前端报错
    参数：value - 涨跌幅数值（可为None）
    返回：格式化后的字符串，如 "+3.25%" / "-1.50%" / "n/a"
    """
    # 若涨跌幅为None（无数据），返回n/a占位符
    if value is None:
        return "n/a"
    # 格式化：保留2位小数，带正负号，拼接百分号
    return f"{value:+.2f}%"


def build_briefing_payload(dashboard: dict[str, object] | None = None) -> dict[str, object]:
    """
    【核心函数】构建股票市场简报数据
    业务功能：基于仪表盘数据，生成市场总结、信号分类、板块强弱、大盘参考的简报
    参数：dashboard - 可选，仪表盘数据字典；不传则自动生成最新仪表盘数据
    返回：完整的简报数据字典（供前端展示简报、大盘解读、股票分类）
    """
    # 若未传入仪表盘数据，自动调用服务生成最新仪表盘数据
    if dashboard is None:
        dashboard = build_dashboard_payload()

    # 提取仪表盘核心数据：所有监控股票的列表
    items = dashboard["items"]

    # ===================== 按交易信号分类股票（核心业务逻辑） =====================
    # 筛选【强烈试买】信号的股票
    strong_list = [item for item in items if item["signal"]["label"] == "强烈试买"]
    # 筛选【候选试买】信号的股票
    candidates = [item for item in items if item["signal"]["label"] == "候选试买"]
    # 筛选【持有跟踪】信号的股票
    hold_list = [item for item in items if item["signal"]["label"] == "持有跟踪"]
    # 筛选【观望】信号的股票
    watch_list = [item for item in items if item["signal"]["label"] == "观望"]
    # 筛选【风险减仓观察】信号的股票
    risk_list = [item for item in items if item["signal"]["label"] == "风险减仓观察"]

    # 业务定义：优先观察列表 = 强烈试买 + 候选试买（合并为进攻型标的）
    priority_list = strong_list + candidates

    # ===================== 提取板块评分，判断市场主线 =====================
    # 获取AI算力链板块综合评分
    ai_score = dashboard["group_scores"].get("AI 算力链")
    # 获取平台与应用层板块综合评分
    platform_score = dashboard["group_scores"].get("平台与应用层")

    # ===================== 生成简报头条标题（板块强弱判断） =====================
    # 规则1：AI算力链评分 ≥ 平台层评分+5 → AI算力链更强
    if ai_score is not None and platform_score is not None and ai_score >= platform_score + 5:
        headline = "AI 算力链相对更强"
    # 规则2：平台层评分 ≥ AI算力链评分+5 → 平台股更稳
    elif ai_score is not None and platform_score is not None and platform_score >= ai_score + 5:
        headline = "平台股相对更稳"
    # 规则3：差距不足5分 → 市场分化，等待信号确认
    else:
        headline = "整体分化，先看确认"

    # ===================== 拼接市场总结文案（自然语言解读） =====================
    summary_parts = []
    # 1. 优先观察标的总结（最多展示3只）
    if priority_list:
        # 有强烈试买 → 文案：池内排名最前的进攻候选
        # 无强烈试买 → 文案：可优先观察试买信号
        prefix = "池内排名最前的进攻候选：" if strong_list else "可优先观察试买信号的有 "
        summary_parts.append(
            prefix
            + "、".join(item["symbol"] for item in priority_list[:3])  # 取前3只股票代码
            + "。"
        )
    # 2. 观望标的总结（最多展示3只）
    if watch_list:
        summary_parts.append(
            "更适合先观望的有 "
            + "、".join(item["symbol"] for item in watch_list[:3])
            + "。"
        )
    # 3. 风险标的总结（最多展示2只）
    if risk_list:
        summary_parts.append(
            "风险侧更高的有 "
            + "、".join(item["symbol"] for item in risk_list[:2])
            + "。"
        )
    # 4. 无极端信号 → 默认文案
    if not summary_parts:
        summary_parts.append("当前没有特别极端的信号，适合继续跟踪分化。")

    # ===================== 大盘基准数据处理（QQQ:纳斯达克100，SOXX:半导体ETF） =====================
    # 将大盘基准数据转为字典（股票代码为key），方便快速查找
    benchmarks = {item["symbol"]: item for item in dashboard["benchmarks"]}
    # 提取纳斯达克100ETF(QQQ)数据
    qqq = benchmarks.get("QQQ", {})
    # 提取半导体ETF(SOXX)数据
    soxx = benchmarks.get("SOXX", {})

    # ===================== 返回最终简报数据 =====================
    return {
        # 数据生成时间（与仪表盘时间一致）
        "generated_at": dashboard["generated_at"],
        # 简报头条标题（板块强弱结论）
        "headline": headline,
        # 市场总结文案（拼接后的自然语言）
        "summary": " ".join(summary_parts),
        # 大盘环境：两大核心ETF的涨跌幅（格式化后）
        "market_context": {
            "QQQ": _safe_pct_text(qqq.get("change_pct")),
            "SOXX": _safe_pct_text(soxx.get("change_pct")),
        },
        # 股票信号分类列表（仅返回股票代码，供前端分类展示）
        "lists": {
            "strong": [item["symbol"] for item in strong_list],
            "candidates": [item["symbol"] for item in candidates],
            "hold": [item["symbol"] for item in hold_list],
            "watch": [item["symbol"] for item in watch_list],
            "risk": [item["symbol"] for item in risk_list],
        },
    }