"""
行业相对强弱因子（Industry Relative Strength）模块

核心逻辑参考 IBD (Investors Business Daily) Composite Rating 中的 Industry Group Strength 权重设计：
1. 为每只股票匹配对应的行业ETF（如半导体股票对应SOXX，科技股对应XLK）
2. 计算该行业ETF过去3个月相对QQQ（纳斯达克100ETF）的超额收益
3. 行业跑赢QQQ则为个股加分，跑输则扣分
4. 作用：区分个股的涨跌幅是来自板块β（行业整体）还是公司α（个股本身），
   即使同一板块内的股票，在板块弱势时也会被适度降分，避免错判个股α

模块依赖：
- dataclasses: 数据结构封装
- datetime/timedelta: 时间处理与缓存控制
- threading.Lock: 线程安全的缓存操作
- 内部模块 momentum: 提供 _fetch_closes（获取收盘价）、_window_return_pct（计算窗口期收益率）
"""

from __future__ import annotations  # 支持Python 3.7+的后向类型注解兼容

from dataclasses import asdict, dataclass  # 数据类装饰器，简化对象定义/序列化
from datetime import datetime, timedelta   # 时间戳和时间差计算
from threading import Lock                 # 线程锁，保证缓存操作原子性

# 导入内部momentum模块的工具函数（获取收盘价、计算窗口期收益率）
from .momentum import _fetch_closes, _window_return_pct

# ===================== 常量定义 =====================
# 缓存有效期：4小时（单位：秒），避免频繁请求行情数据
INDUSTRY_CACHE_SECONDS = 4 * 3600

# 股票代码 → 代表性行业ETF映射表（核心映射规则）
# 若股票不在此映射中，默认fallback到QQQ（等价于板块无信号，超额收益为0）
SYMBOL_TO_INDUSTRY_ETF: dict[str, str] = {
    # 半导体板块：对应SOXX（半导体ETF）
    "NVDA": "SOXX", "AMD": "SOXX", "TSM": "SOXX", "AVGO": "SOXX",
    "INTC": "SOXX", "MU": "SOXX", "QCOM": "SOXX", "ASML": "SOXX",
    # 大型科技/软件板块：对应XLK（科技精选ETF）
    "MSFT": "XLK", "AAPL": "XLK", "ORCL": "XLK", "CRM": "XLK",
    "ADBE": "XLK", "NOW": "XLK", "PLTR": "XLK", "CRWV": "XLK",
    # 通信服务板块：对应XLC（通信服务ETF）
    "GOOGL": "XLC", "GOOG": "XLC", "META": "XLC", "NFLX": "XLC",
    # 消费板块：对应XLY（非必需消费品ETF）
    "AMZN": "XLY", "TSLA": "XLY",
    # 中概股板块：对应KWEB（中国互联网ETF）
    "BABA": "KWEB", "JD": "KWEB", "PDD": "KWEB", "BIDU": "KWEB",
}

# 行业ETF的基准标的：所有行业ETF都相对QQQ（纳斯达克100ETF）计算超额收益
INDUSTRY_BENCHMARK = "QQQ"

# ===================== 数据结构定义 =====================
@dataclass
class IndustryRSSnapshot:
    """
    行业相对强弱计算结果的数据快照
    存储单只股票的行业ETF收益率、基准收益率、超额收益及计算状态
    """
    symbol: str                  # 股票代码
    industry_etf: str | None     # 匹配的行业ETF代码（None表示无匹配）
    industry_return_3m: float | None  # 行业ETF过去3个月绝对收益率（百分比）
    benchmark_return_3m: float | None # QQQ过去3个月绝对收益率（百分比）
    excess_3m: float | None      # 行业ETF相对QQQ的超额收益率（industry_return_3m - benchmark_return_3m）
    status: str                  # 计算状态：ok(成功)/missing(数据缺失)/fallback(无匹配ETF)/error(计算异常)
    error: str | None = None     # 异常信息（仅status=error时有值）

    def to_dict(self) -> dict[str, object]:
        """将数据快照序列化为字典，便于后续JSON输出/存储"""
        return asdict(self)

# ===================== 缓存相关全局变量 =====================
# 股票行业RS快照缓存：key=股票代码，value=(缓存时间戳, IndustryRSSnapshot对象)
_CACHE: dict[str, tuple[datetime, IndustryRSSnapshot]] = {}
# ETF收盘价缓存：key=ETF代码，value=(缓存时间戳, 收盘价列表)
_ETF_CLOSES_CACHE: dict[str, tuple[datetime, list[float]]] = {}
# 线程锁：保证多线程环境下缓存读写的原子性，避免竞态条件
_LOCK = Lock()

# ===================== 内部工具函数 =====================
def _get_etf_closes(symbol: str) -> list[float]:
    """
    获取ETF的收盘价列表（带缓存），避免重复请求行情数据
    :param symbol: ETF代码（如SOXX/XLK/QQQ）
    :return: 收盘价列表（按时间正序排列），无数据时返回空列表
    """
    now = datetime.now()  # 当前时间戳，用于判断缓存是否过期
    # 加锁读取缓存，保证线程安全
    with _LOCK:
        cached = _ETF_CLOSES_CACHE.get(symbol)
        # 缓存存在且未过期（小于4小时），直接返回缓存的收盘价
        if cached and now - cached[0] < timedelta(seconds=INDUSTRY_CACHE_SECONDS):
            return cached[1]
    # 缓存失效/不存在，调用momentum模块获取最新收盘价
    closes = _fetch_closes(symbol)
    # 获取到有效收盘价时，更新缓存（加锁保证原子性）
    if closes:
        with _LOCK:
            _ETF_CLOSES_CACHE[symbol] = (now, closes)
    return closes

def _compute(symbol: str) -> IndustryRSSnapshot:
    """
    核心计算逻辑：单只股票的行业相对强弱快照
    :param symbol: 股票代码（如NVDA/MSFT）
    :return: 行业RS快照对象（IndustryRSSnapshot）
    """
    # 第一步：匹配股票对应的行业ETF
    etf = SYMBOL_TO_INDUSTRY_ETF.get(symbol)
    # 无匹配的ETF → 状态标记为fallback（基准QQQ，无超额收益）
    if etf is None:
        return IndustryRSSnapshot(
            symbol=symbol, industry_etf=None,
            industry_return_3m=None, benchmark_return_3m=None, excess_3m=None,
            status="fallback",
        )
    # 第二步：计算行业ETF和基准QQQ的3个月收益率
    try:
        # 获取行业ETF和基准QQQ的收盘价（带缓存）
        etf_closes = _get_etf_closes(etf)
        bench_closes = _get_etf_closes(INDUSTRY_BENCHMARK)
        # 收盘价数据缺失 → 状态标记为missing
        if not etf_closes or not bench_closes:
            return IndustryRSSnapshot(
                symbol=symbol, industry_etf=etf,
                industry_return_3m=None, benchmark_return_3m=None, excess_3m=None,
                status="missing",
            )
        # 计算3个月收益率（63个交易日≈3个月）
        # _window_return_pct: 输入收盘价列表+窗口期长度，返回收益率（百分比）
        etf_3m = _window_return_pct(etf_closes, 63)
        bench_3m = _window_return_pct(bench_closes, 63)
        # 收益率计算失败（如窗口期数据不足）→ 状态标记为missing
        if etf_3m is None or bench_3m is None:
            return IndustryRSSnapshot(
                symbol=symbol, industry_etf=etf,
                industry_return_3m=etf_3m, benchmark_return_3m=bench_3m, excess_3m=None,
                status="missing",
            )
        # 计算超额收益：行业ETF收益率 - QQQ收益率
        excess_3m = etf_3m - bench_3m
        # 计算成功 → 状态标记为ok，返回完整快照
        return IndustryRSSnapshot(
            symbol=symbol, industry_etf=etf,
            industry_return_3m=etf_3m, benchmark_return_3m=bench_3m,
            excess_3m=excess_3m, status="ok",
        )
    # 捕获所有异常（如网络错误、数据格式错误等）→ 状态标记为error，记录异常信息
    except Exception as exc:  # noqa: BLE001（允许捕获所有异常，保证程序鲁棒性）
        return IndustryRSSnapshot(
            symbol=symbol, industry_etf=etf,
            industry_return_3m=None, benchmark_return_3m=None, excess_3m=None,
            status="error", error=str(exc),
        )

# ===================== 对外暴露的接口函数 =====================
def get_industry_rs(symbol: str) -> IndustryRSSnapshot:
    """
    获取单只股票的行业相对强弱快照（带缓存）
    :param symbol: 股票代码
    :return: 行业RS快照对象
    """
    now = datetime.now()
    # 第一步：检查缓存，优先返回未过期的缓存数据
    with _LOCK:
        cached = _CACHE.get(symbol)
        if cached and now - cached[0] < timedelta(seconds=INDUSTRY_CACHE_SECONDS):
            return cached[1]
    # 第二步：缓存失效/不存在，调用核心计算函数
    snap = _compute(symbol)
    # 第三步：更新缓存（仅成功/ fallback状态缓存，避免缓存异常数据）
    with _LOCK:
        if snap.status in ("ok", "fallback"):
            _CACHE[symbol] = (now, snap)
        else:
            # 计算失败（missing/error）时，若有历史缓存则返回历史数据，保证可用性
            cached = _CACHE.get(symbol)
            if cached:
                return cached[1]
    # 返回最新计算结果（无论是否缓存）
    return snap

def get_industry_rs_batch(symbols: list[str]) -> dict[str, IndustryRSSnapshot]:
    """
    批量获取多只股票的行业相对强弱快照
    :param symbols: 股票代码列表
    :return: 字典（key=股票代码，value=行业RS快照对象）
    """
    # 遍历股票列表，调用单只股票接口，返回批量结果
    return {s: get_industry_rs(s) for s in symbols}