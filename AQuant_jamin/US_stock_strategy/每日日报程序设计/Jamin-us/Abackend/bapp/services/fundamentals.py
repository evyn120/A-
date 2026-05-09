"""
基本面因子集合：EPS 预期修正 + 盈利质量 + 估值 + 成长。

参考：
- Zacks："earnings estimate revisions are the most powerful force"
- MSCI Quality：ROE + 低杠杆 + 稳定盈利
- Seeking Alpha Quant：Value / Growth / Profitability / Momentum / EPS Revisions
- AQR：Value + Momentum + Quality 组合

所有因子都归一到 [-1, +1]，正值代表利好。
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from threading import Lock

import yfinance as yf
from iFinDPy import THS_HQ, THS_BD
def _to_ths_symbol(symbol: str) -> str:
    """
    将标准代码转换为 iFinD 代码。
    注意：iFinD 美股通常需要加上 .O (纳斯达克) 或 .N (纽交所)。
    """
    if not symbol:
        return ""
    # 针对基准指数 QQQ 的特殊处理
    if symbol.upper() == "QQQ":
        return "QQQ.O"
    # 默认回退处理：iFinD 美股通常以 .O 或 .N 结尾
    # 如果你的 watchlist 里已经是带后缀的，可以直接返回 symbol
    if "." in symbol:
        return symbol.upper()
    return f"{symbol.upper()}.O"
# ── 缓存设置（可通过环境变量调整） ──
# 分析师修正数据的缓存时间，默认 43200 秒（12 小时）
REVISIONS_CACHE_SECONDS = max(300, int(os.getenv("REVISIONS_CACHE_SECONDS", "43200")))
# 抓取修正数据时的超时时间
REVISIONS_TIMEOUT_SECONDS = max(3, int(os.getenv("REVISIONS_TIMEOUT_SECONDS", "10")))
# 通用信息（如财务指标）的缓存时间，默认 43200 秒（12 小时）
INFO_CACHE_SECONDS = max(300, int(os.getenv("INFO_CACHE_SECONDS", "43200")))


# ── 数据快照类 ──
# 每个类都是一个数据容器，用于保存单个股票的某个因子计算结果
# 都实现了 to_dict() 方法，方便序列化为字典

@dataclass
class RevisionSnapshot:
    """EPS 修正快照"""
    symbol: str
    up_last_30d: int | None      # 过去30天上修次数
    down_last_30d: int | None    # 过去30天下修次数
    up_last_7d: int | None       # 过去7天上修次数
    down_last_7d: int | None     # 过去7天下修次数
    net_score: float | None      # 净修正得分，-1~+1，正值代表分析师整体上修
    status: str                  # ok / missing / error
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class QualitySnapshot:
    """盈利质量快照"""
    symbol: str
    roe: float | None                 # 净资产收益率，例如 0.34 表示 34%
    gross_margin: float | None        # 毛利率，例如 0.68 表示 68%
    debt_to_equity: float | None      # 债务权益比，yfinance 返回的是百分比数，如 31.5 表示 31.5%
    roe_score: float | None           # ROE 得分（-1~+1）
    margin_score: float | None        # 毛利率得分（-1~+1）
    leverage_score: float | None      # 杠杆率得分（-1~+1）
    quality_score: float | None       # 综合质量得分（三者等权平均）
    status: str
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ValueSnapshot:
    """估值快照"""
    symbol: str
    forward_pe: float | None          # 远期市盈率
    peg: float | None                 # PEG = forward_pe / (earningsGrowth * 100)
    value_score: float | None         # 估值得分（-1~+1），便宜为正
    value_note: str                   # 估值说明
    status: str
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class GrowthSnapshot:
    """成长快照"""
    symbol: str
    earnings_growth: float | None     # 盈利同比增长率
    revenue_growth: float | None      # 营收同比增长率
    growth_score: float | None        # 成长得分（-1~+1）
    status: str
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


# ── 全局缓存字典 ──
# 每个缓存字典保存 (时间戳, 数据快照) 的元组
_CACHE: dict[str, tuple[datetime, RevisionSnapshot]] = {}            # EPS 修正缓存
_INFO_CACHE: dict[str, tuple[datetime, dict]] = {}                   # 通用信息缓存（yfinance info）
_QUALITY_CACHE: dict[str, tuple[datetime, QualitySnapshot]] = {}     # 质量因子缓存
_VALUE_CACHE: dict[str, tuple[datetime, ValueSnapshot]] = {}         # 估值因子缓存
_GROWTH_CACHE: dict[str, tuple[datetime, GrowthSnapshot]] = {}       # 成长因子缓存
_LOCK = Lock()  # 线程锁，保证缓存操作的线程安全


# ── 通用工具函数 ──
def _get_info(symbol: str) -> dict:
    """
    通过 iFinD THS_BD 接口拉取并缓存基本面数据。
    """
    now = datetime.now()
    with _LOCK:
        cached = _INFO_CACHE.get(symbol)
        if cached and now - cached[0] < timedelta(seconds=INFO_CACHE_SECONDS):
            return cached[1]

    ths_symbol = _to_ths_symbol(symbol)

    # 注意：以下 iFinD 指标代码（ths_xxx）为美股常见指标示例。
    # 强烈建议你在 iFinD 终端的【数据字典】中核对这几个指标在美股的确切参数名。
    indicators = (
        "ths_roe_us;"  # ROE
        "ths_gross_margin_us;"  # 毛利率
        "ths_debt_to_eqy_us;"  # 债务权益比
        "ths_pe_est_us;"  # Forward PE (预测市盈率)
        "ths_eps_growth_us;"  # 盈利同比增长率
        "ths_rev_growth_us"  # 营收同比增长率
    )

    try:
        res = THS_BD(ths_symbol, indicators, '')
        if res.errorcode == 0 and res.data is not None and not res.data.empty:
            row = res.data.iloc[0]
            info = {
                "returnOnEquity": row.get('ths_roe_us'),
                "grossMargins": row.get('ths_gross_margin_us'),
                "debtToEquity": row.get('ths_debt_to_eqy_us'),
                "forwardPE": row.get('ths_pe_est_us'),
                "earningsGrowth": row.get('ths_eps_growth_us'),
                "revenueGrowth": row.get('ths_rev_growth_us'),
            }
        else:
            info = {}
    except Exception:
        info = {}

    with _LOCK:
        if info:
            _INFO_CACHE[symbol] = (now, info)
    return info

# def _get_info(symbol: str) -> dict:
#     """
#     对 yfinance 的 Ticker.info 做一层缓存，避免多因子重复抓取。
#     返回一个字典，包含当前股票的所有基本信息（财务指标、估值等）。
#     """
#     now = datetime.now()
#     with _LOCK:
#         cached = _INFO_CACHE.get(symbol)
#         # 缓存未过期则直接返回
#         if cached and now - cached[0] < timedelta(seconds=INFO_CACHE_SECONDS):
#             return cached[1]
#
#     try:
#         # 获取 yfinance 的 info 字典
#         info = dict(yf.Ticker(symbol).info or {})
#     except Exception:  # 捕获所有异常，避免因网络问题崩溃
#         info = {}
#
#     with _LOCK:
#         # 成功获取且非空时才更新缓存
#         if info:
#             _INFO_CACHE[symbol] = (now, info)
#     return info


def _to_float(value: object) -> float | None:
    """安全地将值转换为 float，若无法转换或为 NaN 则返回 None。"""
    try:
        if value is None:
            return None
        f = float(value)
        if f != f:  # 检测 NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def _clip(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    """将值限制在 [lo, hi] 区间内。"""
    return max(lo, min(hi, value))


def _safe_int(value: object) -> int | None:
    """安全地将值转换为整数，失败返回 None。"""
    try:
        if value is None:
            return None
        number = int(value)
        return number
    except (TypeError, ValueError):
        return None


# ── 净修正得分计算 ──
def _compute_net_score(up: int | None, down: int | None) -> float | None:
    """
    计算净修正得分： (上修次数 - 下修次数) / 总修正次数
    返回范围 [-1, +1]，表示分析师修正的方向和强度。
    """
    if up is None or down is None:
        return None
    total = up + down
    if total <= 0:
        return 0.0
    return (up - down) / total


# ── EPS 修正抓取 ──
def _fetch_once(symbol: str) -> RevisionSnapshot:
    """
    从 iFinD 抓取 EPS 修正数据。
    """
    ths_symbol = _to_ths_symbol(symbol)

    try:
        # iFinD 中对应的指标可能是预测上调/下调的家数
        # 以下指标代码需根据 iFinD 终端的一致预期数据字典进行精准替换
        indicators = "ths_up_rev_30d_us;ths_down_rev_30d_us;ths_up_rev_7d_us;ths_down_rev_7d_us"
        res = THS_BD(ths_symbol, indicators, '')

        if res.errorcode != 0 or res.data is None or res.data.empty:
            raise ValueError(f"iFinD error or empty data: {res.errmsg}")

        row = res.data.iloc[0]

        up30 = _safe_int(row.get('ths_up_rev_30d_us'))
        down30 = _safe_int(row.get('ths_down_rev_30d_us'))
        up7 = _safe_int(row.get('ths_up_rev_7d_us'))
        down7 = _safe_int(row.get('ths_down_rev_7d_us'))

        # 此处简化了 yfinance 中区分年度/季度的逻辑，如果 iFinD 能区分当年(0y)和下季(+1q)，
        # 你可以在 indicators 中拉取两组数据并在计算 net_score 时维持原有 0.6 / 0.4 的权重。
        net_score = _compute_net_score(up30, down30)

        return RevisionSnapshot(
            symbol=symbol,
            up_last_30d=up30,
            down_last_30d=down30,
            up_last_7d=up7,
            down_last_7d=down7,
            net_score=net_score,
            status="ok" if net_score is not None else "missing",
        )
    except Exception as exc:
        return RevisionSnapshot(
            symbol=symbol, up_last_30d=None, down_last_30d=None,
            up_last_7d=None, down_last_7d=None, net_score=None,
            status="error", error=str(exc),
        )
# def _fetch_once(symbol: str) -> RevisionSnapshot:
#     """
#     从 yfinance 抓取单个股票的 EPS 修正数据。
#     使用年度预期（0y）作为主信号，同时融入下一季度（+1q）数据以平滑季节性噪声。
#     """
#     try:
#         ticker = yf.Ticker(symbol)
#         revisions = ticker.eps_revisions
#         if revisions is None or revisions.empty:
#             return RevisionSnapshot(
#                 symbol=symbol,
#                 up_last_30d=None,
#                 down_last_30d=None,
#                 up_last_7d=None,
#                 down_last_7d=None,
#                 net_score=None,
#                 status="missing",
#             )
#
#         # 列名大小写可能不一致，统一转换为小写后查找
#         columns = {col.lower(): col for col in revisions.columns}
#         up30_col = columns.get("uplast30days")
#         down30_col = columns.get("downlast30days")
#         up7_col = columns.get("uplast7days")
#         down7_col = columns.get("downlast7days")
#
#         # 辅助函数：从指定行（period）、指定列取值
#         def row_value(period: str, col: str | None) -> int | None:
#             if col is None or period not in revisions.index:
#                 return None
#             return _safe_int(revisions.loc[period, col])
#
#         # 年度预期行 "0y" 的数据
#         up30_y = row_value("0y", up30_col)
#         down30_y = row_value("0y", down30_col)
#         # 下一季度行 "+1q" 的数据
#         up30_q = row_value("+1q", up30_col)
#         down30_q = row_value("+1q", down30_col)
#
#         net_y = _compute_net_score(up30_y, down30_y)
#         net_q = _compute_net_score(up30_q, down30_q)
#
#         # 综合得分：年度权重0.6，季度权重0.4
#         if net_y is None and net_q is None:
#             net_score = None
#         elif net_y is None:
#             net_score = net_q
#         elif net_q is None:
#             net_score = net_y
#         else:
#             net_score = net_y * 0.6 + net_q * 0.4
#
#         return RevisionSnapshot(
#             symbol=symbol,
#             up_last_30d=up30_y,
#             down_last_30d=down30_y,
#             up_last_7d=row_value("0y", up7_col),
#             down_last_7d=row_value("0y", down7_col),
#             net_score=net_score,
#             status="ok" if net_score is not None else "missing",
#         )
#     except Exception as exc:
#         # 任何异常都返回 error 状态，并记录错误信息
#         return RevisionSnapshot(
#             symbol=symbol,
#             up_last_30d=None,
#             down_last_30d=None,
#             up_last_7d=None,
#             down_last_7d=None,
#             net_score=None,
#             status="error",
#             error=str(exc),
#         )
#

def get_revisions(symbol: str) -> RevisionSnapshot:
    """
    获取单只股票的 EPS 修正快照，带缓存。
    如果本次抓取失败（status 为 error/missing），且缓存中有上次成功数据，则返回缓存数据。
    """
    now = datetime.now()
    with _LOCK:
        cached = _CACHE.get(symbol)
        if cached is not None:
            cached_at, snapshot = cached
            if now - cached_at < timedelta(seconds=REVISIONS_CACHE_SECONDS):
                return snapshot

    snapshot = _fetch_once(symbol)

    with _LOCK:
        # 只有成功抓到数据才更新缓存；失败时允许复用之前的成功结果
        if snapshot.status == "ok":
            _CACHE[symbol] = (now, snapshot)
        else:
            cached = _CACHE.get(symbol)
            if cached is not None:
                return cached[1]
    return snapshot


def get_revisions_batch(symbols: list[str]) -> dict[str, RevisionSnapshot]:
    """批量获取 EPS 修正快照。"""
    return {symbol: get_revisions(symbol) for symbol in symbols}


# ===================== Quality 因子 =====================
#
# 参考 MSCI Quality 指数：ROE（越高越好）、债务权益比（越低越好）、毛利率（越高越好）
# 每个指标通过分段映射到 [-1, +1]，最后等权平均得到综合质量得分

def _score_roe(roe: float | None) -> float | None:
    """ROE 得分映射"""
    if roe is None:
        return None
    if roe >= 0.30: return 1.0
    if roe >= 0.20: return 0.6
    if roe >= 0.12: return 0.2
    if roe >= 0.05: return -0.2
    if roe >= 0.0:  return -0.5
    return -1.0


def _score_margin(margin: float | None) -> float | None:
    """毛利率得分映射"""
    if margin is None:
        return None
    if margin >= 0.60: return 1.0
    if margin >= 0.45: return 0.6
    if margin >= 0.30: return 0.2
    if margin >= 0.15: return -0.2
    if margin >= 0.05: return -0.5
    return -1.0


def _score_leverage(de: float | None) -> float | None:
    """
    杠杆率得分映射（债务权益比）。
    注意 yfinance 的 debtToEquity 是以百分数表示的，如 31.5 表示 31.5%。
    低杠杆（数值越小）得分越高。
    """
    if de is None:
        return None
    if de <= 20:  return 1.0
    if de <= 50:  return 0.4
    if de <= 100: return 0.0
    if de <= 200: return -0.5
    return -1.0


def _compute_quality(symbol: str) -> QualitySnapshot:
    """计算单只股票的质量因子得分。"""
    info = _get_info(symbol)
    if not info:
        return QualitySnapshot(symbol, None, None, None, None, None, None, None, "missing")

    roe = _to_float(info.get("returnOnEquity"))
    margin = _to_float(info.get("grossMargins"))
    de = _to_float(info.get("debtToEquity"))

    roe_s = _score_roe(roe)
    margin_s = _score_margin(margin)
    lev_s = _score_leverage(de)

    # 计算有效子得分的等权平均
    parts = [s for s in (roe_s, margin_s, lev_s) if s is not None]
    if not parts:
        return QualitySnapshot(symbol, roe, margin, de, roe_s, margin_s, lev_s, None, "missing")

    quality_score = _clip(sum(parts) / len(parts))
    return QualitySnapshot(
        symbol=symbol, roe=roe, gross_margin=margin, debt_to_equity=de,
        roe_score=roe_s, margin_score=margin_s, leverage_score=lev_s,
        quality_score=quality_score, status="ok",
    )


def get_quality(symbol: str) -> QualitySnapshot:
    """获取单只股票的质量因子快照，带缓存。"""
    now = datetime.now()
    with _LOCK:
        cached = _QUALITY_CACHE.get(symbol)
        if cached and now - cached[0] < timedelta(seconds=INFO_CACHE_SECONDS):
            return cached[1]
    snap = _compute_quality(symbol)
    with _LOCK:
        if snap.status == "ok":
            _QUALITY_CACHE[symbol] = (now, snap)
        else:
            cached = _QUALITY_CACHE.get(symbol)
            if cached:
                return cached[1]
    return snap


def get_quality_batch(symbols: list[str]) -> dict[str, QualitySnapshot]:
    """批量获取质量因子快照。"""
    return {s: get_quality(s) for s in symbols}


# ===================== Value 因子 =====================
#
# 估值因子：优先使用 PEG（市盈率相对盈利增长比），越低越便宜。
# PEG = Forward PE / (earningsGrowth * 100)
# 当 earningsGrowth 不可用或为负时，则退化为仅使用 forward PE（需要外部百分位评分补充）。
# 当前实现中，若无法计算 PEG，value_score 设为 None，status 为 partial。

def _score_peg(peg: float | None) -> float | None:
    """PEG 得分映射，PEG 越小越便宜，得分越高。"""
    if peg is None or peg <= 0:
        return None
    if peg <= 0.6:  return 1.0
    if peg <= 1.0:  return 0.6
    if peg <= 1.5:  return 0.2
    if peg <= 2.5:  return -0.2
    if peg <= 4.0:  return -0.5
    return -1.0


def _compute_value(symbol: str) -> ValueSnapshot:
    """计算单只股票的估值因子得分。"""
    info = _get_info(symbol)
    if not info:
        return ValueSnapshot(symbol, None, None, None, "数据缺失", "missing")

    fpe = _to_float(info.get("forwardPE"))
    eg = _to_float(info.get("earningsGrowth"))

    peg: float | None = None
    if fpe is not None and eg is not None and eg > 0:
        peg = fpe / (eg * 100.0)

    value_score = _score_peg(peg)
    if value_score is not None:
        note = f"PEG={peg:.2f}（forwardPE {fpe:.1f} ÷ 盈利增速 {eg*100:.1f}%）"
        status = "ok"
    elif fpe is not None:
        note = f"盈利增速不适用，仅供参考 forwardPE={fpe:.1f}"
        status = "partial"
    else:
        note = "估值数据缺失"
        status = "missing"

    return ValueSnapshot(
        symbol=symbol, forward_pe=fpe, peg=peg,
        value_score=value_score, value_note=note, status=status,
    )


def get_value(symbol: str) -> ValueSnapshot:
    """获取单只股票的估值因子快照，带缓存。"""
    now = datetime.now()
    with _LOCK:
        cached = _VALUE_CACHE.get(symbol)
        if cached and now - cached[0] < timedelta(seconds=INFO_CACHE_SECONDS):
            return cached[1]
    snap = _compute_value(symbol)
    with _LOCK:
        if snap.status in ("ok", "partial"):
            _VALUE_CACHE[symbol] = (now, snap)
        else:
            cached = _VALUE_CACHE.get(symbol)
            if cached:
                return cached[1]
    return snap


def get_value_batch(symbols: list[str]) -> dict[str, ValueSnapshot]:
    """批量获取估值因子快照。"""
    return {s: get_value(s) for s in symbols}


# ===================== Growth 因子 =====================
#
# 成长因子：使用盈利同比增长率（earningsGrowth）和营收同比增长率（revenueGrowth）。
# 盈利增速权重 0.6，营收增速权重 0.4，因为 EPS 增长更直接与股价相关。

def _score_growth_metric(g: float | None) -> float | None:
    """增长指标得分映射（适用于 EPS 增长和营收增长）。"""
    if g is None:
        return None
    if g >= 0.50:  return 1.0
    if g >= 0.25:  return 0.6
    if g >= 0.10:  return 0.2
    if g >= 0.0:   return -0.2
    if g >= -0.10: return -0.5
    return -1.0


def _compute_growth(symbol: str) -> GrowthSnapshot:
    """计算单只股票的成长因子得分。"""
    info = _get_info(symbol)
    if not info:
        return GrowthSnapshot(symbol, None, None, None, "missing")

    eg = _to_float(info.get("earningsGrowth"))
    rg = _to_float(info.get("revenueGrowth"))

    eg_s = _score_growth_metric(eg)
    rg_s = _score_growth_metric(rg)
    parts = [s for s in (eg_s, rg_s) if s is not None]
    if not parts:
        return GrowthSnapshot(symbol, eg, rg, None, "missing")

    # 加权综合：如果两个指标都有，EPS 增长权重 0.6，营收增长 0.4；否则等权平均
    if eg_s is not None and rg_s is not None:
        growth_score = _clip(eg_s * 0.6 + rg_s * 0.4)
    else:
        growth_score = _clip(sum(parts) / len(parts))

    return GrowthSnapshot(symbol, eg, rg, growth_score, "ok")


def get_growth(symbol: str) -> GrowthSnapshot:
    """获取单只股票的成长因子快照，带缓存。"""
    now = datetime.now()
    with _LOCK:
        cached = _GROWTH_CACHE.get(symbol)
        if cached and now - cached[0] < timedelta(seconds=INFO_CACHE_SECONDS):
            return cached[1]
    snap = _compute_growth(symbol)
    with _LOCK:
        if snap.status == "ok":
            _GROWTH_CACHE[symbol] = (now, snap)
        else:
            cached = _GROWTH_CACHE.get(symbol)
            if cached:
                return cached[1]
    return snap


def get_growth_batch(symbols: list[str]) -> dict[str, GrowthSnapshot]:
    """批量获取成长因子快照。"""
    return {s: get_growth(s) for s in symbols}