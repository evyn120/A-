"""下次财报日服务。

数据来自 yfinance 的 Ticker.calendar / earnings_dates。
提供：
- 下次财报日期（UTC + 北京时间字符串）
- 距今天还有多少个自然日
- 是否在"财报临近窗口"（默认 7 天）——交给 signal_engine 做硬过滤

yfinance 的 calendar 字段历史上变化较大，实现里按优先级尝试多种字段。
"""

from __future__ import annotations
from iFinDPy import THS_HQ, THS_BD
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from threading import Lock

import yfinance as yf


EARNINGS_CACHE_SECONDS = max(300, int(os.getenv("EARNINGS_CACHE_SECONDS", "21600")))  # 默认 6 小时
EARNINGS_NEAR_DAYS = max(1, int(os.getenv("EARNINGS_NEAR_DAYS", "7")))

# 北京时间固定 UTC+8
_BEIJING_TZ = timezone(timedelta(hours=8))


@dataclass
class EarningsSnapshot:
    symbol: str
    next_earnings_date_utc: str | None      # "2026-04-23" 或 "2026-04-23 16:30 UTC"
    next_earnings_beijing: str | None       # "2026-04-24 00:30"（北京时间）
    days_until: int | None                  # 距今自然日
    is_near: bool                           # days_until <= EARNINGS_NEAR_DAYS
    status: str                             # ok / missing / error
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_CACHE: dict[str, tuple[datetime, EarningsSnapshot]] = {}
_LOCK = Lock()


def _normalize_to_datetime(raw) -> datetime | None:
    """yfinance 返回的可能是 date / datetime / pd.Timestamp / 字符串，统一为 datetime。"""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, date):
        return datetime(raw.year, raw.month, raw.day)
    try:
        # pandas Timestamp 有 to_pydatetime
        if hasattr(raw, "to_pydatetime"):
            return raw.to_pydatetime()
    except Exception:  # noqa: BLE001
        pass
    try:
        return datetime.fromisoformat(str(raw))
    except Exception:  # noqa: BLE001
        return None


def _extract_next_earnings(symbol: str) -> datetime | None:
    """通过 iFinD 提取下次财报日期"""
    ths_symbol = _to_ths_symbol(symbol)

    # 查找“预计财报披露日”相关的 iFinD 指标
    res = THS_BD(ths_symbol, "ths_next_earn_ann_date_us", "")

    if res.errorcode != 0 or res.data is None or res.data.empty:
        return None

    try:
        # iFinD 通常返回 YYYY-MM-DD 格式的字符串
        raw_date_str = res.data.iloc[0, 1]  # 假设第0列是代码，第1列是值
        if not raw_date_str:
            return None

        dt = datetime.strptime(str(raw_date_str), "%Y-%m-%d")
        # 赋予美东时间（或 UTC）时区以兼容下游北京时间的转化
        # 简单起见，将其设为 UTC 以兼容原有 datetime 处理逻辑
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

# def _extract_next_earnings(ticker: yf.Ticker) -> datetime | None:
#     """优先返回带时区的精确时间；退化时返回仅日期的 naive datetime。"""
#     today_utc = datetime.now(timezone.utc)
#     cutoff = today_utc - timedelta(days=1)
#
#     # 1) Ticker.earnings_dates —— 带时区，精度到分钟，优先使用
#     try:
#         ed = ticker.earnings_dates
#         if ed is not None and hasattr(ed, "empty") and not ed.empty:
#             future: list[datetime] = []
#             for idx in ed.index:
#                 dt = _normalize_to_datetime(idx)
#                 if dt is None:
#                     continue
#                 cmp_dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
#                 if cmp_dt >= cutoff:
#                     future.append(dt)
#             if future:
#                 future.sort(key=lambda d: d if d.tzinfo else d.replace(tzinfo=timezone.utc))
#                 return future[0]
#     except Exception:  # noqa: BLE001
#         pass
#
#     # 2) Ticker.calendar —— 通常只有日期，作为兜底
#     try:
#         cal = ticker.calendar
#         today_naive = datetime.now()
#         if isinstance(cal, dict):
#             raw = cal.get("Earnings Date")
#             if isinstance(raw, (list, tuple)) and raw:
#                 dt = _normalize_to_datetime(raw[0])
#                 if dt and dt >= today_naive - timedelta(days=1):
#                     return dt
#             else:
#                 dt = _normalize_to_datetime(raw)
#                 if dt and dt >= today_naive - timedelta(days=1):
#                     return dt
#         elif cal is not None and hasattr(cal, "empty") and not cal.empty:
#             try:
#                 raw = cal.iloc[0, 0]
#                 dt = _normalize_to_datetime(raw)
#                 if dt and dt >= today_naive - timedelta(days=1):
#                     return dt
#             except Exception:  # noqa: BLE001
#                 pass
#     except Exception:  # noqa: BLE001
#         pass
#
#     return None


def _format_beijing(dt: datetime) -> str:
    # 若 dt 没有时区信息，默认当作 US/Eastern 财报公告时段，这里简化处理：
    # 没有时区则直接视为"美国时区的日期"转北京时间就是 +12 小时左右
    # 但 yfinance 大部分情况给的就是 naive datetime，我们直接按"日期"展示就好。
    if dt.tzinfo is None:
        # 只有日期信息时，北京时间也按同一天展示
        return dt.strftime("%Y-%m-%d") + "（当地交易日）"
    beijing = dt.astimezone(_BEIJING_TZ)
    return beijing.strftime("%Y-%m-%d %H:%M")


def _compute(symbol: str) -> EarningsSnapshot:
    try:
        dt = _extract_next_earnings(symbol)
        if dt is None:
            return EarningsSnapshot(
                symbol=symbol,
                next_earnings_date_utc=None, next_earnings_beijing=None,
                days_until=None, is_near=False, status="missing",
            )

        # 计算 days_until：按"北京时间日期"粒度（带时区时）
        today_bj = datetime.now(_BEIJING_TZ).date()
        if dt.tzinfo is not None:
            target_date = dt.astimezone(_BEIJING_TZ).date()
        else:
            target_date = dt.date()
        days_until = (target_date - today_bj).days

        utc_text = (
            dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            if dt.tzinfo else dt.strftime("%Y-%m-%d")
        )
        beijing_text = _format_beijing(dt)

        return EarningsSnapshot(
            symbol=symbol,
            next_earnings_date_utc=utc_text,
            next_earnings_beijing=beijing_text,
            days_until=days_until,
            is_near=(0 <= days_until <= EARNINGS_NEAR_DAYS),
            status="ok",
        )
    except Exception as exc:  # noqa: BLE001
        return EarningsSnapshot(
            symbol=symbol,
            next_earnings_date_utc=None, next_earnings_beijing=None,
            days_until=None, is_near=False, status="error", error=str(exc),
        )


def get_earnings(symbol: str) -> EarningsSnapshot:
    now = datetime.now()
    with _LOCK:
        cached = _CACHE.get(symbol)
        if cached and now - cached[0] < timedelta(seconds=EARNINGS_CACHE_SECONDS):
            return cached[1]
    snap = _compute(symbol)
    with _LOCK:
        if snap.status == "ok":
            _CACHE[symbol] = (now, snap)
        else:
            cached = _CACHE.get(symbol)
            if cached:
                return cached[1]
    return snap


def get_earnings_batch(symbols: list[str]) -> dict[str, EarningsSnapshot]:
    return {s: get_earnings(s) for s in symbols}
