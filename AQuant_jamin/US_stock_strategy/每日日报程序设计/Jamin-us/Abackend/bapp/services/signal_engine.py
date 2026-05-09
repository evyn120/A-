from __future__ import annotations

from dataclasses import asdict, dataclass

from .earnings import EarningsSnapshot
from .fundamentals import (
    GrowthSnapshot,
    QualitySnapshot,
    RevisionSnapshot,
    ValueSnapshot,
)
from .industry_rs import IndustryRSSnapshot
from .market_data import QuoteSnapshot
from .momentum import MOMENTUM_BENCHMARK as MOMENTUM_BENCHMARK_LABEL, MomentumSnapshot
from .watchlist_config import StockProfile


LABEL_STYLES = {
    "强烈试买": {"tone": "strong-positive", "color": "#059669"},
    "候选试买": {"tone": "positive", "color": "#1f9d55"},
    "持有跟踪": {"tone": "neutral", "color": "#2563eb"},
    "观望": {"tone": "watch", "color": "#c0841a"},
    "风险减仓观察": {"tone": "risk", "color": "#dc2626"},
}
SCORE_BASE = 50
# 静态 bias 已完全废弃，全部由 Quality / Value / Growth / EPS / Momentum
# 等动态因子决定。手写的 thesis / risk_note 等文本仍在详情页展示，但不参与算分。
BASE_BIAS_WEIGHT = 0
VALUATION_BIAS_WEIGHT = 0
RISK_PENALTY_WEIGHT = 0
# 5 个动态 α 因子等权：每个 ±8 ~ ±10 分量级
EPS_REVISION_WEIGHT = 8
QUALITY_WEIGHT = 8
VALUE_WEIGHT = 8
GROWTH_WEIGHT = 8
# 当日涨跌只作为盘中触发器，权重小
# 当日涨跌：过热反转曲线。+5% 以上反而扣分（盘中冲高最常见的反向信号），
# +1~+3% 是最健康的"温和上涨"区间，权重最大。
# 大跌也不再过度恐慌：-3% 以下只扣 -2，把"恐慌杀跌"机会留出来。
PRICE_MOVE_POSITIVE_BANDS = [(5.0, -3), (3.0, 1), (1.0, 2), (0.3, 1)]
PRICE_MOVE_NEGATIVE_BANDS = [(-3.0, -2), (-1.0, -2), (-0.3, -1)]
# 短期反转（过去 5 日累计涨幅）：> +10% 视为短期过热，扣分。
# 学术依据：Jegadeesh 1990 / AQR Short-Term Reversal —— 1 周大涨平均下周跑输。
SHORT_TERM_REVERSAL_BANDS = [
    (15.0, -8),   # >= +15%：极度过热
    (10.0, -5),   # >= +10%：明显过热
    (7.0, -2),    # >= +7%：略偏热
    (-7.0, 0),    # 中间区间不加不扣
    (-10.0, 2),   # <= -7%：超卖反弹机会
    (-99.0, 4),   # <= -10%：深度超卖
]
# "强烈试买"硬过滤：5 日累计涨幅超过这个阈值，再强也只能给"候选试买"
STRONG_BUY_REVERSAL_THRESHOLD_PCT = 10.0

# 回撤买点（Pullback Buy）：距 52 周高点的回撤作为"逢跌买入"信号。
# 借鉴 IBD/O'Neil 的 Pullback Buy 思路 + Stockscreenr 的"优质股深跌"筛选。
# 仅当 Quality >= 0 时才加分——劣质股深跌更可能是价值陷阱。
PULLBACK_QUALITY_FLOOR = 0.0

# 低波动因子（MSCI Low Volatility / Defensive）：60 日年化波动率。
# 美股蓝筹中位数约 25~30%，TSLA/CRWV 这类常在 60%+。
# 贡献上限 ±5，权重不宜过大——主打"风险修正"，而不是主导排名。
VOL_LOW_THRESHOLD = 22.0   # 低于此视为"低波动"
VOL_HIGH_THRESHOLD = 45.0  # 高于此视为"高波动"
VOL_EXTREME_THRESHOLD = 65.0

# 行业相对强弱（IBD Industry Group Strength）：行业 ETF 3M 相对 QQQ 超额。
# 超额 5% 加 3 分，10% 加 5 分；负向对称扣分。
INDUSTRY_RS_POINTS_PER_PCT = 0.6
INDUSTRY_RS_CAP = 5

# 财报临近：≤ 7 天不发"强烈试买"（财报前夜波动率飙升，追买胜率低）。
# 这个阈值由 earnings.EARNINGS_NEAR_DAYS 控制，这里只作为引用参数。
# 日内相对强弱也是短期执行信号
RELATIVE_STRENGTH_POSITIVE_BANDS = [(2.0, 8), (0.8, 5), (0.2, 2)]
RELATIVE_STRENGTH_NEGATIVE_BANDS = [(-2.0, -8), (-0.8, -5), (-0.2, -2)]
# 真动量（1M/3M/6M 相对 QQQ 超额，权重大）
MOMENTUM_POINTS_PER_EXCESS_PCT = 0.5
MOMENTUM_CAP = 10


@dataclass
class SignalResult:
    symbol: str
    label: str
    score: int
    confidence: int
    action_hint: str
    relative_strength_pct: float | None
    benchmark_symbol: str
    benchmark_change_pct: float | None
    eps_revision_score: float | None
    eps_revision_contribution: int
    momentum_composite_pct: float | None
    momentum_contribution: int
    quality_score: float | None
    quality_contribution: int
    value_score: float | None
    value_contribution: int
    growth_score: float | None
    growth_contribution: int
    rank: int | None
    rank_total: int | None
    percentile: float | None
    score_breakdown: list[dict[str, object]]
    label_trace: list[dict[str, object]]
    reasons: list[str]
    risks: list[str]
    style: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _band_score(
    value: float | None,
    positive_bands: list[tuple[float, int]],
    negative_bands: list[tuple[float, int]],
) -> int:
    if value is None:
        return 0
    for threshold, score in positive_bands:
        if value >= threshold:
            return score
    for threshold, score in negative_bands:
        if value <= threshold:
            return score
    return 0


def _pick_primary_benchmark(profile: StockProfile, benchmark_quotes: dict[str, QuoteSnapshot]) -> tuple[str, float | None]:
    for symbol in profile.benchmarks:
        quote = benchmark_quotes.get(symbol)
        if quote is not None and quote.change_pct is not None:
            return symbol, quote.change_pct
    first = profile.benchmarks[0] if profile.benchmarks else "QQQ"
    quote = benchmark_quotes.get(first)
    return first, quote.change_pct if quote is not None else None


def _momentum_contribution(composite_pct: float | None) -> int:
    """把加权超额收益（百分比）映射到 -MOMENTUM_CAP ~ +MOMENTUM_CAP 的分数贡献。"""
    if composite_pct is None:
        return 0
    raw = composite_pct * MOMENTUM_POINTS_PER_EXCESS_PCT
    bounded = max(-MOMENTUM_CAP, min(MOMENTUM_CAP, raw))
    return int(round(bounded))


def _volatility_contribution(vol_pct: float | None) -> int:
    """低波动加分、高波动扣分。MSCI Low-Vol 因子的简化版。"""
    if vol_pct is None:
        return 0
    if vol_pct <= VOL_LOW_THRESHOLD:
        return 3
    if vol_pct <= 30.0:
        return 1
    if vol_pct >= VOL_EXTREME_THRESHOLD:
        return -5
    if vol_pct >= VOL_HIGH_THRESHOLD:
        return -3
    return 0


def _vol_detail(vol_pct: float, contribution: int) -> str:
    if vol_pct <= VOL_LOW_THRESHOLD:
        tag = "低波动优势（≤22%）"
    elif vol_pct <= 30.0:
        tag = "温和偏低"
    elif vol_pct >= VOL_EXTREME_THRESHOLD:
        tag = "极端高波动（≥65%）"
    elif vol_pct >= VOL_HIGH_THRESHOLD:
        tag = "高波动"
    else:
        tag = "中性区间"
    return f"60 日年化波动率 {vol_pct:.1f}% → {tag}，贡献 {contribution:+d}"


def _industry_rs_contribution(excess_3m_pct: float | None) -> int:
    if excess_3m_pct is None:
        return 0
    raw = excess_3m_pct * INDUSTRY_RS_POINTS_PER_PCT
    bounded = max(-INDUSTRY_RS_CAP, min(INDUSTRY_RS_CAP, raw))
    return int(round(bounded))


def _industry_rs_detail(etf: str | None, excess_3m: float | None, contribution: int) -> str:
    if etf is None:
        return "未映射到行业 ETF，贡献 0"
    if excess_3m is None:
        return f"行业 ETF {etf} 数据未到齐，贡献 0"
    direction = "跑赢" if excess_3m >= 0 else "跑输"
    return f"行业 {etf} 近 3M {direction} QQQ {excess_3m:+.1f}% → 贡献 {contribution:+d}"


def _pullback_contribution(
    drawdown_pct: float | None,
    quality_score: float | None,
) -> int:
    """距 52 周高点的回撤贡献。

    分段（drawdown 是负数）：
    -  0 ~ -3%：太近，0
    - -3 ~ -8%：健康回调，+2
    - -8 ~ -15%：较深回调，+4
    - -15 ~ -25%：深跌但仍在趋势内，+3
    - -25 ~ -40%：超跌，+1
    - < -40%：可能趋势破坏，0

    Quality < 0 时统一返回 0（防价值陷阱）。
    """
    if drawdown_pct is None or drawdown_pct > 0:
        return 0
    if quality_score is not None and quality_score < PULLBACK_QUALITY_FLOOR:
        return 0
    d = drawdown_pct
    if d > -3.0:
        return 0
    if d > -8.0:
        return 2
    if d > -15.0:
        return 4
    if d > -25.0:
        return 3
    if d > -40.0:
        return 1
    return 0


def _pullback_detail(drawdown: float, contribution: int, quality_ok: bool) -> str:
    if not quality_ok:
        return f"距 52 周高点 {drawdown:+.1f}%，但 Quality < 0（疑似价值陷阱），贡献 0"
    d = drawdown
    if d > -3.0:
        tag = "紧贴高点，无回调机会"
    elif d > -8.0:
        tag = "健康回调（-3% ~ -8%）"
    elif d > -15.0:
        tag = "较深回调（-8% ~ -15%）"
    elif d > -25.0:
        tag = "深跌但仍在趋势内（-15% ~ -25%）"
    elif d > -40.0:
        tag = "超跌机会（-25% ~ -40%）"
    else:
        tag = "回撤 > 40%，趋势可能破坏"
    return f"距 52 周高点 {drawdown:+.1f}% → {tag}，贡献 {contribution:+d}"


def _short_term_reversal_contribution(return_5d_pct: float | None) -> int:
    """把过去 5 日累计涨幅映射到分数贡献。

    阈值表是从大到小写的，第一个匹配的就用：
    - >= +15% → -8（极度过热）
    - >= +10% → -5
    - >= +7%  → -2
    - 中间区间 → 0
    - <= -7%  → +2（超卖反弹机会）
    - <= -10% → +4
    """
    if return_5d_pct is None:
        return 0
    if return_5d_pct >= 15.0:
        return -8
    if return_5d_pct >= 10.0:
        return -5
    if return_5d_pct >= 7.0:
        return -2
    if return_5d_pct <= -10.0:
        return 4
    if return_5d_pct <= -7.0:
        return 2
    return 0


def decide_label(
    score: int,
    rank: int,
    total: int,
    relative_strength: float | None,
    return_5d_pct: float | None = None,
    earnings_near: bool = False,
    earnings_days_until: int | None = None,
    regime: str = "neutral",
) -> tuple[str, str, list[dict[str, object]], float]:
    """方案 A：分位数 + 短期确认 + 绝对分数兜底 的 5 档分级。

    排名规则：rank=1 表示分数最高。
    百分位（percentile）：1.0 表示排名第一，0.0 表示垫底。
    """
    if total <= 0:
        total = 1
    percentile = 1.0 - (rank - 1) / total   # 第 1/N 名 → 1.0，最后 → 接近 0

    rs_confirm = relative_strength is None or relative_strength >= 0  # 短期确认
    rs_text = f"{relative_strength:+.2f}%" if relative_strength is not None else "n/a（视为通过）"

    # 短期过热过滤：过去 5 日涨幅超过阈值 → 不允许"强烈试买"
    not_overheated = (
        return_5d_pct is None or return_5d_pct < STRONG_BUY_REVERSAL_THRESHOLD_PCT
    )
    r5_text = f"{return_5d_pct:+.1f}%" if return_5d_pct is not None else "n/a（视为通过）"

    # 财报临近硬过滤：未来 7 天要发财报 → 不给"强烈试买"
    not_near_earnings = not earnings_near
    if earnings_days_until is not None and 0 <= earnings_days_until:
        earnings_text = f"还有 {earnings_days_until} 天财报"
    else:
        earnings_text = "无临近财报"

    # 大盘 regime：熊市时抬高"强烈试买"分数门槛 + 要求前 5% 而非前 10%
    strong_score_floor = 70 if regime == "bearish" else 65
    strong_percentile_floor = 0.95 if regime == "bearish" else 0.90
    regime_text = {"bullish": "牛市", "bearish": "熊市", "neutral": "震荡", "unknown": "未知"}.get(regime, regime)

    rules = [
        {
            "label": "强烈试买",
            "condition": (
                f"排名前 {int((1-strong_percentile_floor)*100)}% (当前 {rank}/{total}，百分位 {percentile*100:.0f}%) "
                f"且 总分 (={score}) ≥ {strong_score_floor} 且 相对强弱 (={rs_text}) ≥ 0 "
                f"且 5 日涨幅 (={r5_text}) < +{STRONG_BUY_REVERSAL_THRESHOLD_PCT:.0f}%（防追高）"
                f"且 非财报窗口 (={earnings_text}) 且 大盘非熊市 (当前 {regime_text})"
            ),
            "matched": (
                percentile >= strong_percentile_floor
                and score >= strong_score_floor
                and rs_confirm
                and not_overheated
                and not_near_earnings
            ),
            "action_hint": (
                "综合排名靠前且盘面确认，适合优先建立或加仓底仓。"
                if regime != "bearish"
                else "大盘熊市中还能排前 5%，更要控制仓位而非满仓。"
            ),
        },
        {
            "label": "候选试买",
            "condition": (
                f"排名前 30% (百分位 {percentile*100:.0f}%) 且 总分 (={score}) ≥ 55"
            ),
            "matched": percentile >= 0.70 and score >= 55,
            "action_hint": "综合强度居前，可分批试买或纳入核心观察。",
        },
        {
            "label": "持有跟踪",
            "condition": (
                f"排名中段 (百分位 {percentile*100:.0f}%) 或 总分 (={score}) ≥ 45"
            ),
            "matched": (0.30 <= percentile < 0.70) or score >= 45,
            "action_hint": "强度不极端，更适合跟踪而不是主动加仓。",
        },
        {
            "label": "观望",
            "condition": (
                f"排名后 30% (百分位 {percentile*100:.0f}%) 且 总分 (={score}) ≥ 30"
            ),
            "matched": percentile < 0.30 and score >= 30,
            "action_hint": "短期强度不足，等基本面或趋势转好再考虑。",
        },
        {
            "label": "风险减仓观察",
            "condition": (
                f"排名后 10% (百分位 {percentile*100:.0f}%) 或 总分 (={score}) < 30"
            ),
            "matched": percentile < 0.10 or score < 30,
            "action_hint": "综合风险居首，应控制仓位或降低预期。",
        },
    ]

    label: str | None = None
    action_hint: str | None = None
    trace: list[dict[str, object]] = []
    for rule in rules:
        hit = rule["matched"] and label is None
        trace.append({
            "label": rule["label"],
            "condition": rule["condition"],
            "matched": rule["matched"],
            "applied": hit,
        })
        if hit:
            label = rule["label"]
            action_hint = rule["action_hint"]

    if label is None:
        label = "持有跟踪"
        action_hint = "规则均未严格命中，暂以中性标签跟踪。"
        trace.append({
            "label": "持有跟踪（兜底）",
            "condition": "以上规则都未命中，给中性兜底",
            "matched": True,
            "applied": True,
        })

    return label, action_hint, trace, percentile


def _weighted_contribution(score: float | None, weight: int) -> int:
    if score is None:
        return 0
    return int(round(_clip_abs1(score) * weight))


def _clip_abs1(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _quality_detail(q: "QualitySnapshot") -> str:
    parts: list[str] = []
    if q.roe is not None:
        parts.append(f"ROE {q.roe*100:.0f}%")
    if q.gross_margin is not None:
        parts.append(f"毛利 {q.gross_margin*100:.0f}%")
    if q.debt_to_equity is not None:
        parts.append(f"D/E {q.debt_to_equity:.0f}%")
    tail = "、".join(parts) if parts else "数据缺失"
    return f"{tail} → 质量得分 {q.quality_score:+.2f}" if q.quality_score is not None else tail


def _short_reversal_detail(ret_5d_pct: float, contribution: int) -> str:
    if ret_5d_pct >= 15.0:
        tag = "极度过热（≥+15%）"
    elif ret_5d_pct >= 10.0:
        tag = "明显过热（≥+10%）"
    elif ret_5d_pct >= 7.0:
        tag = "略偏热（≥+7%）"
    elif ret_5d_pct <= -10.0:
        tag = "深度超卖（≤-10%）"
    elif ret_5d_pct <= -7.0:
        tag = "超卖反弹机会（≤-7%）"
    else:
        tag = "中性区间"
    return f"过去 5 日 {ret_5d_pct:+.1f}% → {tag}，贡献 {contribution:+d}"


def _growth_detail(g: "GrowthSnapshot") -> str:
    parts: list[str] = []
    if g.earnings_growth is not None:
        parts.append(f"EPS YoY {g.earnings_growth*100:+.0f}%")
    if g.revenue_growth is not None:
        parts.append(f"营收 YoY {g.revenue_growth*100:+.0f}%")
    tail = "、".join(parts) if parts else "数据缺失"
    return f"{tail} → 成长得分 {g.growth_score:+.2f}" if g.growth_score is not None else tail


def _eps_revision_contribution(net_score: float | None) -> int:
    """把 [-1, +1] 的净修正得分映射到分数贡献。

    用简单线性映射：贡献 = round(net_score * EPS_REVISION_WEIGHT)。
    抓不到数据时返回 0，不干扰主流程。
    """
    if net_score is None:
        return 0
    bounded = max(-1.0, min(1.0, net_score))
    return int(round(bounded * EPS_REVISION_WEIGHT))


def build_methodology() -> dict[str, object]:
    return {
        "summary": "当前版本采用规则型评分，而不是黑盒 AI 直接给买卖建议。每只股票先算分，再映射到标签。",
        "formula": [
            {
                "name": "起始分",
                "value": str(SCORE_BASE),
                "description": "每只股票先从 50 分起步，再叠加 Quality / Value / Growth 三大基本面因子，以及 EPS 修正、真动量、当日涨跌和相对强弱。",
            },
            {
                "name": "Quality（MSCI Quality 思路）",
                "value": f"quality_score(∈[-1,+1]) × {QUALITY_WEIGHT}",
                "description": "ROE、毛利率、债务权益比按阈值分段，三者等权。ROE ≥ 30% 或毛利 ≥ 60% 会显著加分。",
            },
            {
                "name": "Value（PEG 为主）",
                "value": f"value_score × {VALUE_WEIGHT}",
                "description": "优先用 PEG = forwardPE / EPS 增速；PEG ≤ 1 加分，≥ 2.5 开始扣分。比纯 PE 更贴近成长股。",
            },
            {
                "name": "Growth（盈利+营收 YoY）",
                "value": f"growth_score × {GROWTH_WEIGHT}",
                "description": "earningsGrowth 占 60%、revenueGrowth 占 40%。≥ 25% 为强增长，负增长会扣分。",
            },
            {
                "name": "当日涨跌贡献（过热反转曲线）",
                "value": "+1~+3% 加分，≥+5% 反而扣分",
                "description": "+1~+3% 是健康的温和上涨，+5% 以上视为盘中冲高反向信号；大跌也只小扣，把恐慌杀跌的机会留出来。",
            },
            {
                "name": "短期反转（过去 5 日涨幅）",
                "value": "≥+10% 扣 5 / ≥+15% 扣 8 / ≤-7% 加 2 / ≤-10% 加 4",
                "description": "Jegadeesh 1990 与 AQR Short-Term Reversal：一周大涨平均下周跑输。用这一项主动回避追高，并捕捉超卖反弹。",
            },
            {
                "name": "回撤买点（距 52 周高点）",
                "value": "-3~-8% 加 2 / -8~-15% 加 4 / -15~-25% 加 3 / -25~-40% 加 1",
                "description": (
                    "IBD/O'Neil Pullback Buy 思路：优质股从高点回调 -3% ~ -15% 是教科书级买点；"
                    "仅对 Quality ≥ 0 的股票生效，防止给低质量股的价值陷阱加分。"
                ),
            },
            {
                "name": "低波动因子（60 日年化）",
                "value": "≤22% 加 3 / ≤30% 加 1 / ≥45% 扣 3 / ≥65% 扣 5",
                "description": "MSCI Low-Volatility / Defensive 因子：长期看低波动组合风险调整收益优于高波动，把 TSLA/CRWV 这类高波动股适度降分。",
            },
            {
                "name": "行业相对强弱（3M vs QQQ）",
                "value": f"行业 ETF 3M 超额 × {INDUSTRY_RS_POINTS_PER_PCT}，上限 ±{INDUSTRY_RS_CAP}",
                "description": "IBD Composite Rating 里的 Industry Group Strength：把股票映射到行业 ETF（SOXX/XLK/XLC/XLY/KWEB），计算板块相对大盘超额。",
            },
            {
                "name": "真动量（1M/3M/6M 超额收益）",
                "value": f"composite × {MOMENTUM_POINTS_PER_EXCESS_PCT}，上限 ±{MOMENTUM_CAP}",
                "description": (
                    "对 1 / 3 / 6 个月相对 QQQ 的超额收益做加权（0.2 / 0.5 / 0.3），"
                    "这是 Fama-French Momentum 因子的实战版本，比只看当日涨跌更能反映真实强弱。"
                ),
            },
            {
                "name": "相对强弱贡献",
                "value": "按相对 QQQ / SOXX 分段加减",
                "description": "如果跑赢基准，就说明资金更愿意买它；如果跑输，则说明强度不够。",
            },
            {
                "name": "分析师 EPS 预期修正",
                "value": f"net_score × {EPS_REVISION_WEIGHT}",
                "description": (
                    "取最近 30 天分析师上修次数 vs 下修次数，算 (up − down) / (up + down) ∈ [−1, +1]，"
                    "年度预期 0y 占 60%，下一季度 +1q 占 40%。Zacks 研究证实这是预测 1–3 月股价最强的单因子。"
                ),
            },
        ],
        "price_move_bands": [
            {"condition": "涨幅 >= +5.0%（过热反转）", "points": "-3"},
            {"condition": "涨幅 >= +3.0%", "points": "+1"},
            {"condition": "涨幅 >= +1.0%（温和上涨最佳区间）", "points": "+2"},
            {"condition": "涨幅 >= +0.3%", "points": "+1"},
            {"condition": "跌幅 <= -0.3%", "points": "-1"},
            {"condition": "跌幅 <= -1.0%", "points": "-2"},
            {"condition": "跌幅 <= -3.0%", "points": "-2"},
        ],
        "short_term_reversal_bands": [
            {"condition": "5 日累计 >= +15%", "points": "-8"},
            {"condition": "5 日累计 >= +10%", "points": "-5"},
            {"condition": "5 日累计 >= +7%", "points": "-2"},
            {"condition": "5 日累计 <= -7%", "points": "+2"},
            {"condition": "5 日累计 <= -10%", "points": "+4"},
        ],
        "relative_strength_bands": [
            {"condition": "相对基准 >= +2.0%", "points": "+10"},
            {"condition": "相对基准 >= +0.8%", "points": "+6"},
            {"condition": "相对基准 >= +0.2%", "points": "+2"},
            {"condition": "相对基准 <= -0.2%", "points": "-2"},
            {"condition": "相对基准 <= -0.8%", "points": "-6"},
            {"condition": "相对基准 <= -2.0%", "points": "-10"},
        ],
        "labels": [
            {
                "label": "强烈试买",
                "color": LABEL_STYLES["强烈试买"]["color"],
                "criteria": [
                    "池内排名前 10%（熊市下收紧到前 5%）",
                    "总分 ≥ 65（熊市下 ≥ 70）",
                    "相对强弱非负",
                    "过去 5 日涨幅 < +10%（防追高）",
                    "未来 7 天无财报",
                ],
                "description": "综合 α 最强的一档，盘面也确认。适合优先建仓或加仓。",
            },
            {
                "label": "候选试买",
                "color": LABEL_STYLES["候选试买"]["color"],
                "criteria": ["池内排名前 30%", "总分 ≥ 55"],
                "description": "综合强度靠前，分批试买或列入核心观察。",
            },
            {
                "label": "持有跟踪",
                "color": LABEL_STYLES["持有跟踪"]["color"],
                "criteria": ["排名中段 (30%~70%)", "或总分 ≥ 45"],
                "description": "没有明显强或弱，继续跟踪而不是主动加仓。",
            },
            {
                "label": "观望",
                "color": LABEL_STYLES["观望"]["color"],
                "criteria": ["排名后 30%", "总分 ≥ 30"],
                "description": "短期强度不足，等趋势或基本面回暖再动手。",
            },
            {
                "label": "风险减仓观察",
                "color": LABEL_STYLES["风险减仓观察"]["color"],
                "criteria": ["排名后 10% 或 总分 < 30"],
                "description": "池内风险最集中，应控制仓位或降低预期。",
            },
        ],
        "rating_scheme": {
            "name": "方案 A：分位数 + 短期确认 + 绝对分数兜底",
            "description": (
                "标签不是只看分数阈值，而是看在当前股票池里的排名百分位："
                "前 10%、前 30%、中段、后 30%、后 10%。强烈试买还需要相对强弱 ≥ 0 做短期确认。"
                "这样即使全池整体弱，最前列仍能拿到进攻标签，避免全部变成观望。"
            ),
        },
        "notes": [
            "当前行情主源是 CNBC 批量接口，默认用常规盘口径来判断涨跌和强弱。",
            "分析师 EPS 预期修正数据来自 yfinance（Yahoo Finance），默认 12 小时缓存一次。",
            "真动量因子使用 yfinance 日线历史（默认 4 小时缓存），统一以 QQQ 为基准计算超额收益。",
            "QQQ 主要用作大盘科技基准，SOXX 主要用作半导体基准。",
            "TSM、NVDA 等 AI 算力链标的会优先参考 SOXX / QQQ 这类基准。",
            "这个模型更适合做研究排序和交易前 briefing，不是自动交易指令。",
        ],
    }


def build_signal(
    profile: StockProfile,
    quote: QuoteSnapshot,
    benchmark_quotes: dict[str, QuoteSnapshot],
    revision: RevisionSnapshot | None = None,
    momentum: MomentumSnapshot | None = None,
    quality: QualitySnapshot | None = None,
    value: ValueSnapshot | None = None,
    growth: GrowthSnapshot | None = None,
    industry_rs: IndustryRSSnapshot | None = None,
) -> SignalResult:
    primary_benchmark, benchmark_change_pct = _pick_primary_benchmark(profile, benchmark_quotes)
    relative_strength = None
    if quote.change_pct is not None and benchmark_change_pct is not None:
        relative_strength = quote.change_pct - benchmark_change_pct

    eps_revision_score = revision.net_score if revision is not None else None
    eps_revision_contribution = _eps_revision_contribution(eps_revision_score)
    momentum_composite_pct = momentum.composite if momentum is not None else None
    momentum_contribution = _momentum_contribution(momentum_composite_pct)

    quality_score = quality.quality_score if quality is not None else None
    quality_contribution = _weighted_contribution(quality_score, QUALITY_WEIGHT)
    value_score = value.value_score if value is not None else None
    value_contribution = _weighted_contribution(value_score, VALUE_WEIGHT)
    growth_score = growth.growth_score if growth is not None else None
    growth_contribution = _weighted_contribution(growth_score, GROWTH_WEIGHT)

    return_5d = momentum.return_5d if momentum is not None else None
    short_reversal_contribution = _short_term_reversal_contribution(return_5d)

    drawdown_pct = momentum.drawdown_from_52w_high if momentum is not None else None
    pullback_contribution = _pullback_contribution(drawdown_pct, quality_score)
    pullback_quality_ok = (
        quality_score is None or quality_score >= PULLBACK_QUALITY_FLOOR
    )

    vol_pct = momentum.annualized_vol_60d if momentum is not None else None
    volatility_contribution = _volatility_contribution(vol_pct)

    industry_excess_3m = industry_rs.excess_3m if industry_rs is not None else None
    industry_rs_contribution = _industry_rs_contribution(industry_excess_3m)

    price_move_contribution = _band_score(
        quote.change_pct,
        positive_bands=PRICE_MOVE_POSITIVE_BANDS,
        negative_bands=PRICE_MOVE_NEGATIVE_BANDS,
    )
    relative_strength_contribution = _band_score(
        relative_strength,
        positive_bands=RELATIVE_STRENGTH_POSITIVE_BANDS,
        negative_bands=RELATIVE_STRENGTH_NEGATIVE_BANDS,
    )

    base_bias_contribution = profile.base_bias * BASE_BIAS_WEIGHT
    valuation_bias_contribution = profile.valuation_bias * VALUATION_BIAS_WEIGHT
    risk_penalty_contribution = -(profile.risk_penalty * RISK_PENALTY_WEIGHT)

    raw_score = (
        SCORE_BASE
        + base_bias_contribution
        + valuation_bias_contribution
        + risk_penalty_contribution
        + price_move_contribution
        + relative_strength_contribution
        + eps_revision_contribution
        + momentum_contribution
        + quality_contribution
        + value_contribution
        + growth_contribution
        + short_reversal_contribution
        + pullback_contribution
        + volatility_contribution
        + industry_rs_contribution
    )
    score = max(0, min(100, raw_score))

    score_breakdown: list[dict[str, object]] = [
        {
            "name": "起始分",
            "detail": f"所有股票统一起点 {SCORE_BASE}",
            "raw": None,
            "contribution": SCORE_BASE,
            "is_base": True,
        },
        {
            "name": "Quality（ROE+毛利+杠杆）",
            "detail": (
                _quality_detail(quality)
                if quality is not None
                else "数据未到齐，贡献 0"
            ),
            "raw": quality_score,
            "contribution": quality_contribution,
        },
        {
            "name": "Value（PEG 估值）",
            "detail": (
                value.value_note if value is not None and value.value_note else "估值数据未到齐，贡献 0"
            ),
            "raw": value_score,
            "contribution": value_contribution,
        },
        {
            "name": "Growth（EPS+营收 YoY）",
            "detail": (
                _growth_detail(growth)
                if growth is not None
                else "增长数据未到齐，贡献 0"
            ),
            "raw": growth_score,
            "contribution": growth_contribution,
        },
        {
            "name": "当日涨跌",
            "detail": (
                f"当前 {quote.change_pct:+.2f}% 落在分段：{price_move_contribution:+d} 分"
                if quote.change_pct is not None
                else "缺少当日涨跌数据，贡献 0"
            ),
            "raw": quote.change_pct,
            "contribution": price_move_contribution,
        },
        {
            "name": f"相对 {primary_benchmark} 强弱",
            "detail": (
                f"超额 {relative_strength:+.2f}% 落在分段：{relative_strength_contribution:+d} 分"
                if relative_strength is not None
                else "缺少基准对比数据，贡献 0"
            ),
            "raw": relative_strength,
            "contribution": relative_strength_contribution,
        },
        {
            "name": "短反转（过去 5 日涨幅）",
            "detail": (
                _short_reversal_detail(return_5d, short_reversal_contribution)
                if return_5d is not None
                else "5 日涨跌数据未到齐，贡献 0"
            ),
            "raw": return_5d,
            "contribution": short_reversal_contribution,
        },
        {
            "name": "回撤买点（距 52 周高点）",
            "detail": (
                _pullback_detail(drawdown_pct, pullback_contribution, pullback_quality_ok)
                if drawdown_pct is not None
                else "历史价格未到齐，贡献 0"
            ),
            "raw": drawdown_pct,
            "contribution": pullback_contribution,
        },
        {
            "name": "低波动（60 日年化）",
            "detail": (
                _vol_detail(vol_pct, volatility_contribution)
                if vol_pct is not None
                else "波动率数据未到齐，贡献 0"
            ),
            "raw": vol_pct,
            "contribution": volatility_contribution,
        },
        {
            "name": "行业相对强弱（3M vs QQQ）",
            "detail": _industry_rs_detail(
                industry_rs.industry_etf if industry_rs else None,
                industry_excess_3m,
                industry_rs_contribution,
            ),
            "raw": industry_excess_3m,
            "contribution": industry_rs_contribution,
        },
        {
            "name": "真动量（1M/3M/6M 超额）",
            "detail": (
                f"加权超额 {momentum_composite_pct:+.1f}% × {MOMENTUM_POINTS_PER_EXCESS_PCT}"
                f"（上限 ±{MOMENTUM_CAP}）"
                if momentum_composite_pct is not None
                else "动量数据未到齐，贡献 0"
            ),
            "raw": momentum_composite_pct,
            "contribution": momentum_contribution,
        },
        {
            "name": "分析师 EPS 预期修正",
            "detail": (
                f"净修正得分 {eps_revision_score:+.2f} × {EPS_REVISION_WEIGHT}"
                if eps_revision_score is not None
                else "EPS 修正数据未到齐，贡献 0"
            ),
            "raw": eps_revision_score,
            "contribution": eps_revision_contribution,
        },
    ]

    if raw_score != score:
        score_breakdown.append({
            "name": "封顶修正",
            "detail": f"原始累计 {raw_score} 分被截断到 [0, 100] 区间",
            "raw": raw_score,
            "contribution": score - raw_score,
            "is_clamp": True,
        })

    # 分级依赖"全池排名"，由 watchlist_service 稍后通过 assign_label 填入。
    label = ""
    action_hint = ""
    label_trace: list[dict[str, object]] = []

    reasons = [
        profile.thesis,
        f"{profile.name} 当前相对 {primary_benchmark} 的强弱为 "
        f"{relative_strength:+.2f}%" if relative_strength is not None else f"{profile.name} 当前缺少完整基准数据，先看方向不看力度。",
        profile.entry_note,
    ]

    if momentum is not None and momentum.composite is not None:
        def _fmt(value: float | None) -> str:
            return f"{value:+.1f}%" if value is not None else "n/a"
        direction_m = (
            "中期趋势跑赢大盘" if momentum.composite > 1.0 else (
                "中期趋势跑输大盘" if momentum.composite < -1.0 else "中期走势与大盘接近"
            )
        )
        reasons.append(
            f"真动量：1M/3M/6M 相对 {MOMENTUM_BENCHMARK_LABEL} 超额 "
            f"{_fmt(momentum.excess_1m)} / {_fmt(momentum.excess_3m)} / {_fmt(momentum.excess_6m)}，"
            f"加权 {momentum.composite:+.1f}%，{direction_m}，贡献 {momentum_contribution:+d} 分。"
        )

    if quality is not None and quality.quality_score is not None:
        reasons.append(f"Quality：{_quality_detail(quality)}，贡献 {quality_contribution:+d} 分。")
    if value is not None and value.value_score is not None:
        reasons.append(f"Value：{value.value_note}，贡献 {value_contribution:+d} 分。")
    if growth is not None and growth.growth_score is not None:
        reasons.append(f"Growth：{_growth_detail(growth)}，贡献 {growth_contribution:+d} 分。")
    if pullback_contribution != 0 and drawdown_pct is not None:
        reasons.append(
            f"回撤买点：{_pullback_detail(drawdown_pct, pullback_contribution, pullback_quality_ok)}。"
        )

    if revision is not None and revision.net_score is not None:
        up = revision.up_last_30d if revision.up_last_30d is not None else 0
        down = revision.down_last_30d if revision.down_last_30d is not None else 0
        direction = "整体上修" if revision.net_score > 0.1 else (
            "整体下修" if revision.net_score < -0.1 else "方向中性"
        )
        reasons.append(
            f"分析师最近 30 天 EPS 预期{direction}（上修 {up} 次 / 下修 {down} 次，"
            f"净得分 {revision.net_score:+.2f}，贡献 {eps_revision_contribution:+d} 分）。"
        )

    risks = [profile.valuation_note, profile.risk_note]

    confidence = 55 + abs(score - 50)
    confidence = max(50, min(95, confidence))

    return SignalResult(
        symbol=profile.symbol,
        label=label,
        score=score,
        confidence=confidence,
        action_hint=action_hint,
        relative_strength_pct=relative_strength,
        benchmark_symbol=primary_benchmark,
        benchmark_change_pct=benchmark_change_pct,
        eps_revision_score=eps_revision_score,
        eps_revision_contribution=eps_revision_contribution,
        momentum_composite_pct=momentum_composite_pct,
        momentum_contribution=momentum_contribution,
        quality_score=quality_score,
        quality_contribution=quality_contribution,
        value_score=value_score,
        value_contribution=value_contribution,
        growth_score=growth_score,
        growth_contribution=growth_contribution,
        rank=None,
        rank_total=None,
        percentile=None,
        score_breakdown=score_breakdown,
        label_trace=label_trace,
        reasons=reasons,
        risks=risks,
        style={"tone": "neutral", "color": "#2563eb"},
    )


def assign_label(
    result: SignalResult,
    rank: int,
    total: int,
    return_5d_pct: float | None = None,
    earnings: EarningsSnapshot | None = None,
    regime: str = "neutral",
) -> SignalResult:
    """池内排名已知后，给 SignalResult 填上 label / style / action_hint / trace。"""
    label, action_hint, trace, percentile = decide_label(
        result.score, rank, total, result.relative_strength_pct,
        return_5d_pct=return_5d_pct,
        earnings_near=bool(earnings and earnings.is_near),
        earnings_days_until=(earnings.days_until if earnings else None),
        regime=regime,
    )
    result.label = label
    result.action_hint = action_hint
    result.label_trace = trace
    result.style = LABEL_STYLES[label]
    result.rank = rank
    result.rank_total = total
    result.percentile = percentile
    return result
