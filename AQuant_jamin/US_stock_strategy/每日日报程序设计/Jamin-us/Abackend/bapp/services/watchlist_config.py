from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StockProfile:
    symbol: str
    source_symbol: str
    name: str
    group: str = "自选股"
    industry_role: str = ""
    thesis: str = ""
    valuation_note: str = ""
    risk_note: str = ""
    entry_note: str = ""
    base_bias: int = 0
    valuation_bias: int = 0
    risk_penalty: int = 0
    benchmarks: tuple[str, ...] = ("QQQ",)
    chain_links: tuple[str, ...] = ()
    catalysts: tuple[str, ...] = ()
    is_user_added: bool = False


def build_auto_profile(symbol: str, name: str | None = None) -> StockProfile:
    """用户输入的任意美股，自动生成最小 profile。

    打分完全交给动态因子（EPS Revisions + 真动量 + 相对强弱 + 当日涨跌）。
    所有静态 bias 字段默认 0，研究笔记字段默认空。
    """
    symbol = symbol.upper().strip()
    return StockProfile(
        symbol=symbol,
        source_symbol=symbol,
        name=name or symbol,
        is_user_added=True,
    )


WATCHLIST: tuple[StockProfile, ...] = (
    StockProfile(
        symbol="NVDA",
        source_symbol="nvda.us",
        name="英伟达",
        group="AI 算力链",
        industry_role="AI 训练/推理 GPU 龙头",
        thesis="AI 资本开支仍在扩张，Blackwell 与后续平台周期支撑高景气，但高预期意味着不能只看财报强弱，还要看价格确认。",
        valuation_note="成长性最强之一，但估值消化需要持续兑现订单、毛利率和交付节奏。",
        risk_note="高波动、高预期和中国限制仍是三大短线扰动源。",
        entry_note="更适合等回踩、等趋势重新转强后试买，而不是无条件追高。",
        base_bias=4,
        valuation_bias=-1,
        risk_penalty=2,
        benchmarks=("QQQ", "SOXX", "TSM"),
        chain_links=("TSM", "MSFT", "AMZN", "GOOGL"),
        catalysts=("AI 资本开支", "新 GPU 周期", "云厂商订单"),
    ),
    StockProfile(
        symbol="TSM",
        source_symbol="tsm.us",
        name="台积电",
        group="AI 算力链",
        industry_role="AI 上游核心晶圆代工",
        thesis="财报与指引仍体现 AI 需求强劲，但股价短线会受高预期、半导体情绪和扩产成本共同影响。",
        valuation_note="中线基本面扎实，关键在先进制程利用率能否继续支撑高毛利与高资本开支。",
        risk_note="海外扩产、地缘与半导体板块轮动会放大短线波动。",
        entry_note="更像中线偏多标的，短线适合等回踩或等盘面重新确认。",
        base_bias=3,
        valuation_bias=0,
        risk_penalty=1,
        benchmarks=("SOXX", "NVDA", "QQQ"),
        chain_links=("NVDA", "MSFT", "AMZN", "GOOGL"),
        catalysts=("AI 晶圆需求", "先进制程", "资本开支"),
    ),
    StockProfile(
        symbol="MSFT",
        source_symbol="msft.us",
        name="微软",
        group="平台与应用层",
        industry_role="云与企业 AI 平台",
        thesis="Azure、Copilot 和企业软件粘性让它兼具现金流与 AI 兑现能力，是七姐妹里更均衡的资产。",
        valuation_note="估值不便宜，但盈利质量和现金流韧性较强。",
        risk_note="AI 投入转化速度若放缓，估值扩张空间会受限。",
        entry_note="更适合逢回调关注，作为组合里的质量型 AI 仓位。",
        base_bias=3,
        valuation_bias=0,
        risk_penalty=1,
        benchmarks=("QQQ",),
        chain_links=("NVDA", "TSM", "AMZN", "GOOGL"),
        catalysts=("Azure", "Copilot", "企业软件"),
    ),
    StockProfile(
        symbol="META",
        source_symbol="meta.us",
        name="Meta",
        group="平台与应用层",
        industry_role="广告平台 + AI 提效",
        thesis="广告现金流和模型投入并存，AI 对广告效率和用户时长的拉动让基本面仍偏强。",
        valuation_note="相对部分 AI 热门股，估值压力没那么极端。",
        risk_note="监管与广告周期回落是主要变量。",
        entry_note="更偏向逢回调跟踪，等趋势回暖时可尝试买入。",
        base_bias=3,
        valuation_bias=1,
        risk_penalty=1,
        benchmarks=("QQQ",),
        chain_links=("NVDA", "TSM", "GOOGL"),
        catalysts=("广告效率", "Reels", "Llama 生态"),
    ),
    StockProfile(
        symbol="AMZN",
        source_symbol="amzn.us",
        name="亚马逊",
        group="平台与应用层",
        industry_role="电商 + AWS AI 基建",
        thesis="AWS 与广告仍是利润弹性的核心，AI 能见度主要看云业务再加速和资本开支兑现。",
        valuation_note="更看利润率改善和 AWS 增速，而不是单纯讲故事。",
        risk_note="零售利润率和云增速一旦低于预期，市场会快速调低想象空间。",
        entry_note="偏向回调跟踪，适合等财报或云业务确认后试买。",
        base_bias=2,
        valuation_bias=0,
        risk_penalty=1,
        benchmarks=("QQQ",),
        chain_links=("NVDA", "TSM", "MSFT", "GOOGL"),
        catalysts=("AWS", "广告", "利润率改善"),
    ),
    StockProfile(
        symbol="GOOGL",
        source_symbol="goog.us",
        name="谷歌",
        group="平台与应用层",
        industry_role="搜索 + 云 + AI 分发",
        thesis="搜索基本盘和云业务仍稳，但 AI 搜索变现与资本开支效率需要更多时间验证。",
        valuation_note="相较增长质量，估值并不算最贵，属于中性偏多。",
        risk_note="反垄断和 AI 搜索商业化不确定性仍在。",
        entry_note="更适合观察财报和趋势共振，确认后再加仓。",
        base_bias=2,
        valuation_bias=1,
        risk_penalty=1,
        benchmarks=("QQQ",),
        chain_links=("NVDA", "TSM", "MSFT", "AMZN"),
        catalysts=("搜索广告", "Google Cloud", "AI 搜索"),
    ),
    StockProfile(
        symbol="AAPL",
        source_symbol="aapl.us",
        name="苹果",
        group="平台与应用层",
        industry_role="消费电子平台",
        thesis="现金流和生态护城河仍强，但当前 AI 叙事和硬件换机周期没有显著强化。",
        valuation_note="估值并不便宜，却缺少最强的增长斜率。",
        risk_note="硬件需求疲软和中国市场压力仍会拖慢情绪修复。",
        entry_note="更适合先观望，等增长和新产品叙事重新增强。",
        base_bias=0,
        valuation_bias=-1,
        risk_penalty=1,
        benchmarks=("QQQ",),
        chain_links=("TSM",),
        catalysts=("新品周期", "服务收入", "AI 终端功能"),
    ),
    StockProfile(
        symbol="TSLA",
        source_symbol="tsla.us",
        name="特斯拉",
        group="平台与应用层",
        industry_role="新能源车 + 自动驾驶高波动资产",
        thesis="长期想象力仍在，但当前盈利和汽车业务压力更直接，短线更容易被交易成高波动题材。",
        valuation_note="估值对执行力要求极高，容错率偏低。",
        risk_note="价格战、交付波动与市场情绪反转都会放大回撤。",
        entry_note="更适合观望或仅在强确认时轻仓试错。",
        base_bias=-1,
        valuation_bias=-2,
        risk_penalty=3,
        benchmarks=("QQQ",),
        chain_links=("TSM", "NVDA"),
        catalysts=("自动驾驶", "机器人", "交付数据"),
    ),
)


BENCHMARKS: tuple[StockProfile, ...] = (
    StockProfile(
        symbol="QQQ",
        source_symbol="qqq.us",
        name="纳指 ETF",
        group="基准",
        industry_role="大盘科技风险偏好",
        thesis="用于判断平台科技股整体情绪。",
        valuation_note="",
        risk_note="",
        entry_note="",
        base_bias=0,
        valuation_bias=0,
        risk_penalty=0,
        benchmarks=(),
        chain_links=(),
        catalysts=(),
    ),
    StockProfile(
        symbol="SOXX",
        source_symbol="soxx.us",
        name="半导体 ETF",
        group="基准",
        industry_role="半导体板块风险偏好",
        thesis="用于判断 AI 算力链与芯片板块相对强弱。",
        valuation_note="",
        risk_note="",
        entry_note="",
        base_bias=0,
        valuation_bias=0,
        risk_penalty=0,
        benchmarks=(),
        chain_links=(),
        catalysts=(),
    ),
)


WATCHLIST_BY_SYMBOL = {item.symbol: item for item in WATCHLIST}
BENCHMARKS_BY_SYMBOL = {item.symbol: item for item in BENCHMARKS}
ALL_SYMBOLS = WATCHLIST + BENCHMARKS
ALL_SYMBOLS_BY_SYMBOL = {item.symbol: item for item in ALL_SYMBOLS}
