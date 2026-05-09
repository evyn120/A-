"""
market_data.py

通过 CNBC 接口获取市场报价快照，并封装为统一的 QuoteSnapshot 数据结构。
主要提供 fetch_quotes() 函数用于批量拉取报价。
"""

from __future__ import annotations  # 允许在类型注解中使用类本身等前向引用

import os
from dataclasses import asdict, dataclass  # 用于定义简洁的数据类，asdict 将数据类转为字典

import requests

from .watchlist_config import ALL_SYMBOLS_BY_SYMBOL  # 从配置中导入全部交易品种的详细信息映射

# CNBC 实时报价接口地址
CNBC_QUOTE_URL = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
# 接口超时时间（秒），可从环境变量 CNBC_TIMEOUT_SECONDS 读取，默认 8 秒，且不低于 3 秒
CNBC_TIMEOUT_SECONDS = max(3, int(os.getenv("CNBC_TIMEOUT_SECONDS", "8")))
# 默认的 HTTP 请求头，伪装成常见浏览器，避免被屏蔽
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    )
}

# 将 CNBC 返回的市场状态码映射为中文标签
SESSION_LABELS = {
    "REG_MKT": "常规",  # 常规交易时段
    "PRE_MKT": "盘前",  # 盘前交易
    "POST_MKT": "盘后",  # 盘后交易
}

# 创建全局的 requests.Session，可复用 TCP 连接，提高请求效率
_SESSION = requests.Session()
_SESSION.headers.update(DEFAULT_HEADERS)


@dataclass
class QuoteSnapshot:
    """单只股票/交易品种的报价快照数据类"""
    symbol: str  # 交易代码
    name: str  # 显示名称（公司名或简称）
    source_symbol: str  # 数据源中使用的原始代码
    session_label: str  # 当前交易时段的中文标签（常规/盘前/盘后/未知）
    price: float | None  # 最新价
    change: float | None  # 涨跌额（当天价格变动绝对值）
    change_pct: float | None  # 涨跌幅百分比
    previous_close: float | None  # 前收盘价
    currency: str  # 货币代码，默认为 "USD"
    last_update: str | None  # 最后更新时间字符串
    status: str  # 状态标识，如 "ok"（成功）、"missing"（缺数据）、"error"（错误）
    error: str | None = None  # 错误信息，仅在出错时有值

    def to_dict(self) -> dict[str, object]:
        """将数据类实例转换为字典，方便序列化输出"""
        return asdict(self)


def _to_float(value: object) -> float | None:
    """
    将 CNBC 接口返回的原始值安全地转换为浮点数。
    处理空字符串、无效标识符（如 "N/A"）、千分位逗号、百分号等。
    """
    if value is None:
        return None
    text = str(value).strip()
    # 无效或不可用的值统一返回 None
    if not text or text in {"N/A", "N/D", "--", "-"}:
        return None
    # 去除千分位逗号和百分号
    cleaned = text.replace(",", "").replace("%", "")
    # 去除可能的正号 "+"
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_session_label(raw_status: object) -> str:
    """
    将 CNBC 返回的原始市场状态标准化为中文标签。
    若状态未知或为空，返回 "未知"；若不在标准映射中，默认回退为 "常规"（常见情况）。
    """
    status = str(raw_status or "").strip().upper()
    return SESSION_LABELS.get(status, "常规" if status else "未知")


def _build_snapshot(symbol: str, item: dict[str, object], name_hint: str | None = None) -> QuoteSnapshot:
    """
    根据 CNBC 接口返回的一条品种数据构建 QuoteSnapshot 对象。

    参数:
        symbol: 我们请求时使用的代码
        item: CNBC 返回的原始字典数据
        name_hint: 接口返回的名称，优先使用配置中的名称
    """
    # 优先使用全局配置中的品种名称，其次用接口返回的名称提示，最后用代码本身
    profile = ALL_SYMBOLS_BY_SYMBOL.get(symbol)
    display_name = (profile.name if profile else None) or name_hint or symbol

    # 提取各项价格数据并转换为浮点
    price = _to_float(item.get("last"))
    change = _to_float(item.get("change"))
    change_pct = _to_float(item.get("change_pct"))
    previous_close = _to_float(item.get("previous_day_closing"))

    # 市场时段
    session_label = _normalize_session_label(item.get("curmktstatus"))

    # 最后更新时间（优先从 last_timedate 取，其次 last_time）
    last_update = str(item.get("last_timedate") or item.get("last_time") or "").strip() or None

    # 货币代码，缺省为 USD
    currency = str(item.get("currencyCode") or "USD").strip() or "USD"

    # 数据完整性弥补：
    # 如果有 price 和 change，但没有 previous_close，可以反推
    if previous_close is None and price is not None and change is not None:
        previous_close = price - change
    # 如果有 price 和 previous_close，但没有 change，可以计算
    if change is None and price is not None and previous_close is not None:
        change = price - previous_close
    # 如果没有涨跌幅，但有最新价和前收盘价，可以计算百分比
    if change_pct is None and price is not None and previous_close not in (None, 0):
        change_pct = ((price - previous_close) / previous_close) * 100

    # 当价格有效时状态为 "ok"，否则为 "missing"
    status = "ok" if price is not None else "missing"

    return QuoteSnapshot(
        symbol=symbol,
        name=display_name,
        source_symbol=symbol,
        session_label=session_label,
        price=price,
        change=change,
        change_pct=change_pct,
        previous_close=previous_close,
        currency=currency,
        last_update=last_update,
        status=status,
    )


def _error_snapshot(symbol: str, error: Exception) -> QuoteSnapshot:
    """
    构建异常情况下（例如接口报错或完全没有该品种数据）的 QuoteSnapshot 快照，
    将错误信息记录在 error 字段中，状态设为 "error"。
    """
    profile = ALL_SYMBOLS_BY_SYMBOL.get(symbol)
    return QuoteSnapshot(
        symbol=symbol,
        name=profile.name if profile else symbol,
        source_symbol=profile.source_symbol if profile else symbol,
        session_label="不可用",
        price=None,
        change=None,
        change_pct=None,
        previous_close=None,
        currency="USD",
        last_update=None,
        status="error",
        error=str(error),
    )


def fetch_quotes(symbols: list[str]) -> dict[str, QuoteSnapshot]:
    """
    从 CNBC 批量拉取报价信息。

    参数:
        symbols: 需要查询的交易代码列表（可以是混合大小写）

    返回:
        以代码大写为键、QuoteSnapshot 为值的字典。
        对于请求了但接口未返回的代码，会生成一个 error 状态的快照。
    """
    result: dict[str, QuoteSnapshot] = {}

    # 空列表直接返回
    if not symbols:
        return result

    # 发送 GET 请求，用 '|' 连接多个代码
    response = _SESSION.get(
        CNBC_QUOTE_URL,
        params={
            "symbols": "|".join(symbols),
            "requestMethod": "quick",
        },
        timeout=CNBC_TIMEOUT_SECONDS,
    )
    response.raise_for_status()  # 非 2xx 响应会抛出 HTTPError

    payload = response.json()
    # CNBC 返回的数据结构通常嵌套在 FormattedQuoteResult.FormattedQuote 中
    data = payload.get("FormattedQuoteResult", {}).get("FormattedQuote", [])

    # 创建请求代码的大写集合，用于快速匹配
    requested_set = {s.upper() for s in symbols}

    for item in data:
        # 接口返回的代码可能存在额外字符，统一转大写后检查是否在请求集合中
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol or symbol not in requested_set:
            continue

        # 获取名称提示（优先用 name 字段，其次 companyName）
        name_hint = str(item.get("name") or item.get("companyName") or "").strip() or None

        # 根据原始数据构建快照
        result[symbol] = _build_snapshot(symbol, item, name_hint=name_hint)

    # 对于请求了但数据中完全没出现的代码，补充错误快照
    for symbol in symbols:
        if symbol not in result:
            result[symbol] = _error_snapshot(symbol, ValueError(f"CNBC quote missing for {symbol}"))

    return result