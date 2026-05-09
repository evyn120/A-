"""
看盘仪表盘服务模块 (watchlist_service.py)

负责构建看盘所需的完整数据负载 (payload)，包括：
- 合并内置与用户自定义的股票列表
- 批量获取行情、基本面、动量、质量、估值、增长、行业相对强度、盈利等因子数据
- 基于多因子信号引擎 (signal_engine) 计算评分与交易标签
- 提供缓存机制，减少 API 调用并保证数据可用性
- 生成详情页所需数据
"""

from __future__ import annotations

import copy
import os
from datetime import datetime, timedelta

# 导入各因子批量获取函数
from .earnings import get_earnings_batch
from .fundamentals import (
    get_growth_batch,
    get_quality_batch,
    get_revisions_batch,
    get_value_batch,
)
from .industry_rs import get_industry_rs_batch
from .market_data import fetch_quotes
from .momentum import get_market_regime, get_momentum_batch
from .signal_engine import assign_label, build_methodology, build_signal
from .user_watchlist import list_symbols as list_user_symbols
from .watchlist_config import BENCHMARKS, WATCHLIST, WATCHLIST_BY_SYMBOL, build_auto_profile


# ============================================================================
# 常量配置
# ============================================================================

# 默认页面自动刷新间隔，可由环境变量 DASHBOARD_REFRESH_SECONDS 控制，下限 20 秒
DEFAULT_REFRESH_HINT_SECONDS = max(20, int(os.getenv("DASHBOARD_REFRESH_SECONDS", "60")))

# 仪表盘数据缓存有效时长，可由环境变量 DASHBOARD_CACHE_SECONDS 控制，下限 15 秒
DASHBOARD_CACHE_SECONDS = max(15, int(os.getenv("DASHBOARD_CACHE_SECONDS", "55")))

# 获取基准 (benchmark) 行情时，至少需要成功的数量，
# 下限 1，上限为基准列表长度，中间可由环境变量 DASHBOARD_MIN_SUCCESSFUL_BENCHMARKS 设置
MIN_SUCCESSFUL_BENCHMARK_QUOTES = max(1, min(len(BENCHMARKS), int(os.getenv("DASHBOARD_MIN_SUCCESSFUL_BENCHMARKS", "1"))))


# ============================================================================
# 辅助函数
# ============================================================================

def _build_effective_watchlist() -> list:
    """
    构建当前生效的全部股票 profile 列表。

    合并顺序：
    1. 内置 WATCHLIST（包含 Mag7+TSM 等固定标的及其自定义研究笔记）
    2. 用户通过自定义 watchlist 添加的 symbol（若与内置重复则跳过）

    返回：完整的 profile 对象列表。
    """
    profiles = list(WATCHLIST)
    seen = {profile.symbol for profile in profiles}  # 记录已出现的 symbol，避免重复
    for symbol in list_user_symbols():
        if symbol in seen:
            continue
        profiles.append(build_auto_profile(symbol))  # 为用户添加的 symbol 自动构造 profile
        seen.add(symbol)
    return profiles


def _min_successful_watchlist_quotes(total: int) -> int:
    """
    计算看盘列表行情数据至少需要成功获取的只数。

    参数：
        total：当前看盘股票总数

    默认从环境变量 DASHBOARD_MIN_SUCCESSFUL_QUOTES 读取，但不超过总数且至少为 1，
    防止因用户删除所有自选导致系统卡死。
    """
    configured = int(os.getenv("DASHBOARD_MIN_SUCCESSFUL_QUOTES", "6"))
    return max(1, min(total, configured)) if total else 1


def _safe_average(values: list[float | None]) -> float | None:
    """
    安全地计算列表平均值，自动剔除 None 值。
    若列表全部为 None 则返回 None。
    """
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def _pct_text(value: float | None) -> str:
    """
    将百分比数值（例如 0.05 表示 +5%）转换为字符串显示格式，如 "+5.00%"。
    若值为 None 则返回 "n/a"。
    """
    if value is None:
        return "n/a"
    return f"{value:+.2f}%"


# ============================================================================
# 仪表盘缓存
# ============================================================================

# 缓存结构：字典形式，包含过期时间、有效负载、上次成功负载及当前缓存对应的股票池 key
_DASHBOARD_CACHE: dict[str, object] = {
    "expires_at": datetime.min,       # 缓存过期时间，初始为最小时间以保证首次必然刷新
    "payload": None,                  # 当前缓存的有效负载
    "last_good_payload": None,        # 上一次成功构建的负载，用于数据不完整时的降级
    "cache_key": None,                # 反映当前缓存所对应股票池的哈希 key（symbol 元组）
}


def _current_cache_key() -> tuple:
    """
    生成当前有效股票池对应的缓存 key。

    返回有效持仓 profile 列表中的 symbol 组成的元组。
    当用户增删自选导致股票池变化时，key 变化，旧缓存自动失效。
    """
    return tuple(profile.symbol for profile in _build_effective_watchlist())


def invalidate_dashboard_cache() -> None:
    """
    主动使仪表盘缓存失效。通常在数据更新或配置变更后调用。
    """
    _DASHBOARD_CACHE["expires_at"] = datetime.min
    _DASHBOARD_CACHE["cache_key"] = None


# ============================================================================
# 核心数据构建
# ============================================================================

def _compute_dashboard_payload() -> dict[str, object]:
    """
    从底层数据源拉取所有数据，计算每只股票的多因子信号、排名与标签，
    组装成仪表盘所需的完整 payload。

    返回字典包含：
        - generated_at: 生成时间
        - refresh_hint_seconds: 建议刷新间隔
        - market_regime: 市场状态
        - counts: 各标签股票数量统计
        - benchmarks: 基准行情
        - items: 股票列表详情（信号、因子、元数据）
        - group_scores: 各分组的平均得分
        - methodology: 方法论说明
        - data_health: 各数据模块的成功/总数统计
        - is_stale: 是否过期
        - status_message: 状态描述
    """
    # 获取生效的股票 profile 列表
    effective_watchlist = _build_effective_watchlist()
    watchlist_symbols = [profile.symbol for profile in effective_watchlist]

    # 合并看盘标的与基准标的，批量获取行情
    symbols = watchlist_symbols + [profile.symbol for profile in BENCHMARKS]
    quotes = fetch_quotes(symbols)

    # 批量获取各因子数据（只针对看盘标的）
    revisions = get_revisions_batch(watchlist_symbols)
    momentums = get_momentum_batch(watchlist_symbols)
    qualities = get_quality_batch(watchlist_symbols)
    values = get_value_batch(watchlist_symbols)
    growths = get_growth_batch(watchlist_symbols)
    industries = get_industry_rs_batch(watchlist_symbols)
    earnings = get_earnings_batch(watchlist_symbols)

    # 获取整体市场状态（牛/熊/中性等）
    market_regime = get_market_regime()

    # 提取基准行情供信号构建使用
    benchmark_quotes = {profile.symbol: quotes[profile.symbol] for profile in BENCHMARKS}

    # Step 1: 为每个标的构建原始信号（含评分，但尚未分配最终标签）
    signals_by_symbol = {}
    profile_by_symbol = {}
    for profile in effective_watchlist:
        quote = quotes[profile.symbol]
        signal = build_signal(
            profile, quote, benchmark_quotes,
            revision=revisions.get(profile.symbol),
            momentum=momentums.get(profile.symbol),
            quality=qualities.get(profile.symbol),
            value=values.get(profile.symbol),
            growth=growths.get(profile.symbol),
            industry_rs=industries.get(profile.symbol),
        )
        signals_by_symbol[profile.symbol] = signal
        profile_by_symbol[profile.symbol] = profile

    # Step 2: 按得分降序排序，基于排名和额外条件分配交易标签 (方案 A 分位数)
    ranked = sorted(signals_by_symbol.values(), key=lambda s: s.score, reverse=True)
    total = len(ranked)
    regime_str = market_regime.get("regime", "neutral") if isinstance(market_regime, dict) else "neutral"
    for rank, signal in enumerate(ranked, start=1):
        # 提取对应股票的 5 日收益率作为标签分配的辅助参考
        mom = momentums.get(signal.symbol)
        return_5d = mom.return_5d if mom is not None else None
        assign_label(
            signal, rank=rank, total=total,
            return_5d_pct=return_5d,
            earnings=earnings.get(signal.symbol),
            regime=regime_str,
        )

    # 组装每个标的的完整数据
    items: list[dict[str, object]] = []
    # 分组分数累加器，用于计算板块平均分
    group_scores_accumulator: dict[str, list[int]] = {}

    for profile in effective_watchlist:
        signal = signals_by_symbol[profile.symbol]
        quote = quotes[profile.symbol]
        item = {
            "symbol": profile.symbol,
            "name": profile.name,
            "group": profile.group,                 # 所属板块/分组
            "industry_role": profile.industry_role, # 行业角色
            "thesis": profile.thesis,               # 投资论点
            "valuation_note": profile.valuation_note, # 估值笔记
            "risk_note": profile.risk_note,         # 风险要点
            "entry_note": profile.entry_note,       # 入场笔记
            "benchmarks": list(profile.benchmarks), # 对比基准列表
            "chain_links": list(profile.chain_links), # 产业链关联标的
            "catalysts": list(profile.catalysts),   # 催化剂
            "quote": quote.to_dict(),
            "signal": signal.to_dict(),
            "revisions": revisions.get(profile.symbol).to_dict() if revisions.get(profile.symbol) else None,
            "momentum": momentums.get(profile.symbol).to_dict() if momentums.get(profile.symbol) else None,
            "quality": qualities.get(profile.symbol).to_dict() if qualities.get(profile.symbol) else None,
            "value": values.get(profile.symbol).to_dict() if values.get(profile.symbol) else None,
            "growth": growths.get(profile.symbol).to_dict() if growths.get(profile.symbol) else None,
            "industry_rs": industries.get(profile.symbol).to_dict() if industries.get(profile.symbol) else None,
            "earnings": earnings.get(profile.symbol).to_dict() if earnings.get(profile.symbol) else None,
            "is_user_added": profile.is_user_added, # 是否用户自行添加的标的
        }
        items.append(item)
        # 按分组收集信号得分，用于计算板块平均分
        group_scores_accumulator.setdefault(profile.group, []).append(signal.score)

    # 所有标的按信号得分降序排列
    items.sort(key=lambda item: item["signal"]["score"], reverse=True)

    # 统计各标签的股票数量
    counts = {
        label: sum(1 for item in items if item["signal"]["label"] == label)
        for label in ("强烈试买", "候选试买", "持有跟踪", "观望", "风险减仓观察")
    }

    # 计算各分组的平均得分
    group_scores = {
        group: _safe_average(scores) for group, scores in group_scores_accumulator.items()
    }

    # 数据健康度统计：记录各部分数据成功获取的数量与总数
    data_health = {
        "watchlist_ok": sum(1 for item in items if item["quote"]["status"] == "ok"),
        "watchlist_total": len(items),
        "benchmark_ok": sum(1 for quote in benchmark_quotes.values() if quote.status == "ok"),
        "benchmark_total": len(benchmark_quotes),
        "revisions_ok": sum(
            1 for item in items if item["revisions"] and item["revisions"].get("status") == "ok"
        ),
        "revisions_total": len(items),
        "momentum_ok": sum(
            1 for item in items if item["momentum"] and item["momentum"].get("status") == "ok"
        ),
        "momentum_total": len(items),
        "quality_ok": sum(
            1 for item in items if item.get("quality") and item["quality"].get("status") == "ok"
        ),
        "value_ok": sum(
            1 for item in items if item.get("value") and item["value"].get("status") in ("ok", "partial")
        ),
        "growth_ok": sum(
            1 for item in items if item.get("growth") and item["growth"].get("status") == "ok"
        ),
        "fundamentals_total": len(items),
    }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "refresh_hint_seconds": DEFAULT_REFRESH_HINT_SECONDS,
        "market_regime": market_regime,
        "counts": counts,
        "benchmarks": [quote.to_dict() for quote in benchmark_quotes.values()],
        "items": items,
        "group_scores": group_scores,
        "methodology": build_methodology(),
        "data_health": data_health,
        "is_stale": False,
        "status_message": f"实时抓取成功，默认每 {DEFAULT_REFRESH_HINT_SECONDS} 秒刷新一次。",
    }


def _payload_is_usable(payload: dict[str, object]) -> bool:
    """
    判断 payload 是否达到可用标准：看盘股票行情成功数不低于最低要求，
    且基准行情成功数不低于配置的最低基准数。
    """
    data_health = payload["data_health"]
    total = data_health["watchlist_total"]
    return (
        data_health["watchlist_ok"] >= _min_successful_watchlist_quotes(total)
        and data_health["benchmark_ok"] >= MIN_SUCCESSFUL_BENCHMARK_QUOTES
    )


# ============================================================================
# 公开接口：构建仪表盘负载
# ============================================================================

def build_dashboard_payload(force_refresh: bool = False) -> dict[str, object]:
    """
    获取仪表盘数据的主入口。优先返回缓存，缓存无效或强制刷新时重新构建。
    当构建数据不满足可用条件时，使用上次成功数据降级，并标记为 stale；
    若连降级数据都没有，则返回当前不完整数据并缩短缓存时间以便重试。
    """
    now = datetime.now()
    current_key = _current_cache_key()
    cached_payload = _DASHBOARD_CACHE["payload"]
    expires_at = _DASHBOARD_CACHE["expires_at"]
    cache_key = _DASHBOARD_CACHE.get("cache_key")

    # 条件满足则直接返回缓存深拷贝
    if (
        not force_refresh
        and cached_payload is not None
        and now < expires_at
        and cache_key == current_key
    ):
        return copy.deepcopy(cached_payload)

    # 重新计算 payload
    payload = _compute_dashboard_payload()

    # 数据可用：更新缓存并返回
    if _payload_is_usable(payload):
        _DASHBOARD_CACHE["payload"] = payload
        _DASHBOARD_CACHE["last_good_payload"] = payload
        _DASHBOARD_CACHE["expires_at"] = now + timedelta(seconds=DASHBOARD_CACHE_SECONDS)
        _DASHBOARD_CACHE["cache_key"] = current_key
        return copy.deepcopy(payload)

    # 数据不可用但有之前成功的数据：使用降级数据，标记为 stale，并提示用户
    last_good_payload = _DASHBOARD_CACHE["last_good_payload"]
    if last_good_payload is not None:
        stale_payload = copy.deepcopy(last_good_payload)
        stale_payload["is_stale"] = True
        stale_payload["refresh_hint_seconds"] = DEFAULT_REFRESH_HINT_SECONDS
        stale_payload["status_message"] = (
            "本轮抓取不完整，暂时沿用上一次成功数据，避免页面整体变成 n/a。"
        )
        stale_payload["last_attempted_at"] = now.isoformat(timespec="seconds")
        # 用较短的缓存时间以便下次尽早重试
        _DASHBOARD_CACHE["payload"] = stale_payload
        _DASHBOARD_CACHE["expires_at"] = now + timedelta(seconds=DEFAULT_REFRESH_HINT_SECONDS)
        return copy.deepcopy(stale_payload)

    # 连降级数据都没有：将当前不完整数据返回，并设置更短的缓存时间
    payload["status_message"] = (
        "当前数据抓取不完整，可能是行情源波动或限流；稍后会按较低频率重试。"
    )
    _DASHBOARD_CACHE["payload"] = payload
    _DASHBOARD_CACHE["expires_at"] = now + timedelta(seconds=max(15, DEFAULT_REFRESH_HINT_SECONDS // 2))
    return copy.deepcopy(payload)


def build_detail_payload(symbol: str) -> dict[str, object]:
    """
    为指定 symbol 构建详情页所需的负载。

    包含：
    - 该股票在当前仪表盘数据中的完整条目
    - 产业链关联标的列表
    - 根据盘面、研究笔记等生成的描述性文字段落

    如果 symbol 不在当前仪表盘数据中，抛出 KeyError。
    """
    # 复用仪表盘数据，确保前端一致性
    dashboard = build_dashboard_payload()
    item = next((stock for stock in dashboard["items"] if stock["symbol"] == symbol), None)
    if item is None:
        raise KeyError(symbol)

    # 查找标的关联的产业链股票（chain_links 中的 symbol）
    linked = [
        stock
        for stock in dashboard["items"]
        if stock["symbol"] in item["chain_links"]
    ]

    quote = item["quote"]
    signal = item["signal"]
    benchmark_text = _pct_text(signal["benchmark_change_pct"])
    relative_text = _pct_text(signal["relative_strength_pct"])

    # 组合详情展示段落
    detail_sections = [
        {
            "title": "当前结论",
            "content": f"{item['name']} 当前标签为 {signal['label']}，分数 {signal['score']} / 100。{signal['action_hint']}",
        },
        {
            "title": "盘面解读",
            "content": (
                f"{item['name']} 当前 {quote['session_label']} 涨跌幅 {_pct_text(quote['change_pct'])}，"
                f"对比 {signal['benchmark_symbol']} 的基准涨跌 {benchmark_text}，"
                f"相对强弱 {relative_text}。"
            ),
        },
    ]
    # 如果有投资论点或风险要点，追加研究视角段落
    if item["thesis"] or item["risk_note"]:
        parts: list[str] = []
        if item["thesis"]:
            parts.append(item["thesis"])
        if item["risk_note"]:
            parts.append(f"风险侧重点：{item['risk_note']}")
        detail_sections.append({"title": "研究视角", "content": " ".join(parts)})

    return {
        "generated_at": dashboard["generated_at"],
        "item": item,
        "linked_items": linked,
        "detail_sections": detail_sections,
    }