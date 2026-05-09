"""
中期动量因子模块。

学术上 Fama-French Momentum 定义为“过去 12 个月收益（剔除最近 1 个月）”，
实战里大家常用 1M / 3M / 6M 的组合。本模块面向中短期（1~3 月持仓视角），
因此 3M 权重最高，1M/6M 辅助，且每个窗口都使用“相对 QQQ 的超额收益”——
这是 Momentum 真正产生 alpha 的地方，而不是绝对涨跌。
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from threading import Lock
from iFinDPy import THS_HQ, THS_BD
# 假设你在系统入口处已经调用了 THS_iFinDLogin("username", "password")

def _to_ths_symbol(symbol: str) -> str:
    """
    将标准代码转换为 iFinD 代码。
    注意：此处为示例，iFinD 美股通常需要加上 .O (纳斯达克) 或 .N (纽交所)。
    你可能需要查询你的本地股票池数据库来进行准确映射。
    """
    if symbol == "QQQ":
        return "QQQ.O"
    # 简单的默认回退，实际生产中建议查表
    return f"{symbol}.O"

import yfinance as yf


# 动量数据缓存时间（秒），可从环境变量 MOMENTUM_CACHE_SECONDS 读取，默认 4 小时
MOMENTUM_CACHE_SECONDS = max(300, int(os.getenv("MOMENTUM_CACHE_SECONDS", "14400")))
# 用于计算超额收益的基准标的，默认 "QQQ"（纳指ETF）
MOMENTUM_BENCHMARK = os.getenv("MOMENTUM_BENCHMARK", "QQQ")

# 动量窗口定义：(窗口名称, 交易日数量, 权重)
# 合计权重 = 1，突出 3 个月窗口
_WINDOW_WEIGHTS: tuple[tuple[str, int, float], ...] = (
    ("1M", 21, 0.2),
    ("3M", 63, 0.5),
    ("6M", 126, 0.3),
)


@dataclass
class MomentumSnapshot:
    """单只股票的动量快照数据类"""
    symbol: str                         # 股票代码
    return_5d: float | None            # 过去 5 个交易日累计涨幅（%），用于短期反转判断
    return_1m: float | None            # 1 个月收益（%），例如 +3.5 表示 +3.5%
    return_3m: float | None            # 3 个月收益（%）
    return_6m: float | None            # 6 个月收益（%）
    excess_1m: float | None           # 1 个月超额收益（相对基准 %）
    excess_3m: float | None           # 3 个月超额收益（%）
    excess_6m: float | None           # 6 个月超额收益（%）
    composite: float | None           # 加权超额得分（%），根据窗口权重合并
    drawdown_from_52w_high: float | None   # 距 52 周高点的回撤百分比（负值，如 -8.5 表示 -8.5%）
    annualized_vol_60d: float | None       # 过去 60 交易日年化波动率（%，例如 35 表示 35%）
    status: str                        # 状态标识："ok" / "missing" / "error"
    error: str | None = None           # 错误信息

    def to_dict(self) -> dict[str, object]:
        """转换为字典，便于序列化输出"""
        return asdict(self)


# 个股动量缓存：{symbol: (缓存时间戳, MomentumSnapshot)}
_CACHE: dict[str, tuple[datetime, MomentumSnapshot]] = {}
# 基准数据缓存：{benchmark_symbol: (缓存时间戳, 收盘价列表)}
_BENCH_CACHE: dict[str, tuple[datetime, list[float]]] = {}
_LOCK = Lock()  # 线程锁，保护缓存读写


# def _fetch_closes(symbol: str, lookback_days: int = 260) -> list[float]:
#     """
#     拉取最近 lookback_days 个交易日的收盘价数组，最新的在最后。
#
#     默认 260 天可覆盖完整的 52 周窗口（约 252 个交易日），用于计算回撤和波动率。
#     """
#     ticker = yf.Ticker(symbol)
#     # 获取历史日线数据，采用自动除权调整
#     hist = ticker.history(period="14mo", interval="1d", auto_adjust=True)
#     if hist is None or hist.empty or "Close" not in hist.columns:
#         return []
#     # 提取收盘价，过滤掉 None 和 NaN
#     closes = [float(v) for v in hist["Close"].tolist() if v is not None and v == v]  # NaN != NaN
#     # 截取最近 lookback_days 条数据
#     return closes[-lookback_days:]

def _fetch_closes(symbol: str, lookback_days: int = 260) -> list[float]:
    """
    通过 iFinD 拉取最近 lookback_days 个交易日的前复权收盘价。
    """
    ths_symbol = _to_ths_symbol(symbol)

    # 因为有非交易日，为了确保拿到足够的数据点，时间窗口往回推（1.5倍天数作为缓冲）
    end_date = datetime.now()
    start_date = end_date - timedelta(days=int(lookback_days * 1.5))

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # CPS:1 代表前复权 (等同于 auto_adjust=True)
    # Period:D 代表日线
    res = THS_HQ(ths_symbol, "close", "Fill:Blank,Period:D,CPS:1", start_str, end_str)

    if res.errorcode != 0 or res.data is None or res.data.empty:
        return []

    # iFinD 返回 DataFrame，提取 'close' 列，去除空值并转为 float
    closes = res.data['close'].dropna().astype(float).tolist()

    # 截取最近 lookback_days 条数据
    return closes[-lookback_days:]

def _annualized_vol_pct(closes: list[float], window: int = 60) -> float | None:
    """
    根据最近 window 日的日收益率计算年化波动率（百分比）。

    计算方法：先求日收益率序列的标准差，再乘以 sqrt(252) 进行年化。
    需要至少 window+1 个数据点才能计算 window 个日收益率。
    """
    if len(closes) <= window:
        return None
    series = closes[-(window + 1):]
    rets: list[float] = []
    for i in range(1, len(series)):
        prev = series[i - 1]
        cur = series[i]
        # 跳过无效价格
        if prev is None or prev <= 0 or cur is None:
            continue
        rets.append((cur - prev) / prev)
    if len(rets) < 5:
        return None
    # 计算日收益率的均值与方差
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)  # 样本方差
    std = var ** 0.5
    # 年化收益率标准差，转换为百分比
    return std * (252 ** 0.5) * 100.0


def _window_return_pct(closes: list[float], window: int) -> float | None:
    """计算过去 window 个交易日的累计收益百分比"""
    if len(closes) <= window:
        return None
    start = closes[-(window + 1)]  # 窗口起始价
    end = closes[-1]               # 最新价
    if start is None or start <= 0:
        return None
    return (end - start) / start * 100.0


def _get_benchmark_closes() -> list[float]:
    """
    获取基准标的的收盘价序列，带缓存。

    首先检查缓存，若缓存有效（未超时）则直接返回；否则重新拉取并更新缓存。
    缓存通过 _BENCH_CACHE 字典存储，并以当前时间作为缓存时间戳。
    """
    now = datetime.now()
    with _LOCK:
        cached = _BENCH_CACHE.get(MOMENTUM_BENCHMARK)
        if cached and now - cached[0] < timedelta(seconds=MOMENTUM_CACHE_SECONDS):
            return cached[1]
    closes = _fetch_closes(MOMENTUM_BENCHMARK)
    if closes:
        with _LOCK:
            _BENCH_CACHE[MOMENTUM_BENCHMARK] = (now, closes)
    return closes


def _compute_snapshot(symbol: str, closes: list[float], bench_closes: list[float]) -> MomentumSnapshot:
    """
    根据个股和基准的收盘价序列，计算完整的动量指标。

    若收盘价序列为空（无数据），则返回 status="missing" 的快照。
    否则计算：
    - 各窗口收益和超额收益
    - 加权超额得分（composite），即使部分窗口缺失也会按已有权重归一化
    - 52 周高点回撤
    - 60 日年化波动率
    """
    if not closes or not bench_closes:
        return MomentumSnapshot(
            symbol=symbol,
            return_5d=None,
            return_1m=None, return_3m=None, return_6m=None,
            excess_1m=None, excess_3m=None, excess_6m=None,
            composite=None,
            drawdown_from_52w_high=None,
            annualized_vol_60d=None,
            status="missing",
        )

    # 短期 5 日收益，可用于反转信号
    return_5d = _window_return_pct(closes, 5)

    # 52 周高点回撤（52 周约 252 个交易日）
    window = closes[-252:] if len(closes) >= 252 else closes
    high = max(window)
    last = closes[-1]
    drawdown = (last - high) / high * 100.0 if high > 0 else None

    # 60 日年化波动率
    vol_60d = _annualized_vol_pct(closes, window=60)

    # 遍历窗口权重，计算绝对收益、超额收益，并累计加权得分
    returns: dict[str, float | None] = {}
    excesses: dict[str, float | None] = {}
    weighted_sum = 0.0
    weight_hit = 0.0

    for name, window, weight in _WINDOW_WEIGHTS:
        r = _window_return_pct(closes, window)        # 个股窗口收益
        b = _window_return_pct(bench_closes, window)  # 基准窗口收益
        returns[name] = r
        if r is not None and b is not None:
            excess = r - b            # 超额收益
            excesses[name] = excess
            weighted_sum += excess * weight
            weight_hit += weight
        else:
            excesses[name] = None

    # 归一化加权得分（若所有窗口都缺失，则 composite 为 None）
    composite: float | None
    if weight_hit > 0:
        composite = weighted_sum / weight_hit
    else:
        composite = None

    return MomentumSnapshot(
        symbol=symbol,
        return_5d=return_5d,
        return_1m=returns.get("1M"),
        return_3m=returns.get("3M"),
        return_6m=returns.get("6M"),
        excess_1m=excesses.get("1M"),
        excess_3m=excesses.get("3M"),
        excess_6m=excesses.get("6M"),
        composite=composite,
        drawdown_from_52w_high=drawdown,
        annualized_vol_60d=vol_60d,
        status="ok" if composite is not None else "missing",
    )


def _fetch_once(symbol: str, bench_closes: list[float]) -> MomentumSnapshot:
    """
    单次拉取个股行情并计算动量快照，捕获异常并在出错时返回带错误信息的快照。
    """
    try:
        closes = _fetch_closes(symbol)
        return _compute_snapshot(symbol, closes, bench_closes)
    except Exception as exc:  # noqa: BLE001  # 捕获所有异常，保证函数不抛出
        return MomentumSnapshot(
            symbol=symbol,
            return_5d=None,
            return_1m=None, return_3m=None, return_6m=None,
            excess_1m=None, excess_3m=None, excess_6m=None,
            composite=None,
            drawdown_from_52w_high=None,
            annualized_vol_60d=None,
            status="error",
            error=str(exc),
        )


def get_momentum(symbol: str) -> MomentumSnapshot:
    """
    获取单只股票的动量快照，带缓存。

    若缓存中存在该 symbol 且未超时，直接返回；
    否则重新拉取数据并计算。出错时若缓存中有旧数据，则返回旧缓存数据作为降级。
    """
    now = datetime.now()
    with _LOCK:
        cached = _CACHE.get(symbol)
        if cached is not None and now - cached[0] < timedelta(seconds=MOMENTUM_CACHE_SECONDS):
            return cached[1]

    bench_closes = _get_benchmark_closes()
    snapshot = _fetch_once(symbol, bench_closes)

    with _LOCK:
        # 只有成功（status == "ok"）的快照才会更新缓存；出错时保留旧缓存
        if snapshot.status == "ok":
            _CACHE[symbol] = (now, snapshot)
        else:
            cached = _CACHE.get(symbol)
            if cached is not None:
                return cached[1]  # 降级返回旧缓存
    return snapshot


def get_momentum_batch(symbols: list[str]) -> dict[str, MomentumSnapshot]:
    """
    批量获取多只股票的动量快照。

    先预热基准数据，避免每只股票各自触发基准缓存竞争锁。
    返回以 symbol 为键、MomentumSnapshot 为值的字典。
    """
    _get_benchmark_closes()
    return {symbol: get_momentum(symbol) for symbol in symbols}


def get_market_regime() -> dict[str, object]:
    """
    通过 QQQ 收盘价与 200 日均线的相对位置，判断大盘状态。

    返回字典包含：
    - regime: "bullish"（QQQ > 200D MA 且 20D MA > 200D MA）、
              "bearish"（QQQ < 200D MA 且 20D MA < 200D MA）、
              "neutral"（其他情况，或处于 ±2% 震荡区间）
    - 基准价格、200日均线、20日均线、价格偏离百分比等信息。

    用于 signal_engine 的标签阶段：熊市时提高“强烈试买”的门槛。
    """
    closes = _get_benchmark_closes()
    if not closes or len(closes) < 200:
        return {
            "regime": "unknown",
            "benchmark": MOMENTUM_BENCHMARK,
            "price": None, "ma_200": None, "ma_20": None,
            "price_vs_ma200_pct": None,
        }
    last = closes[-1]
    ma_200 = sum(closes[-200:]) / 200.0
    ma_20 = sum(closes[-20:]) / 20.0
    diff_pct = (last - ma_200) / ma_200 * 100.0

    if diff_pct > 2 and ma_20 > ma_200:
        regime = "bullish"
    elif diff_pct < -2 and ma_20 < ma_200:
        regime = "bearish"
    else:
        regime = "neutral"

    return {
        "regime": regime,
        "benchmark": MOMENTUM_BENCHMARK,
        "price": round(last, 2),
        "ma_200": round(ma_200, 2),
        "ma_20": round(ma_20, 2),
        "price_vs_ma200_pct": round(diff_pct, 2),
    }