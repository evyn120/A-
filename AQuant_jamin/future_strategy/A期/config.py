"""
投资分析工具 - 配置文件
"""
import os

# ==================== 应用配置 ====================
APP_TITLE = "投资分析工具"
APP_ICON = "📊"
LAYOUT = "wide"

# ==================== 数据源配置 ====================
# akshare
# yfinance → akshare 主连代码映射
DEFAULT_SYMBOLS = {
    "沪金":   "AU0",
    "沪银":   "AG0",
    "沪铜":   "CU0",
}

FUTURES_SYMBOLS = {
    # 能源化工
    "原油":   "SC0",
    "燃油":   "FU0",
    "PTA":    "TA0",
    "甲醇":   "MA0",
    "乙二醇": "EG0",
    # 黑色
    "螺纹":   "RB0",
    "热卷":   "HC0",
    "铁矿":   "I0",
    "焦煤":   "JM0",
    "焦炭":   "J0",
    # 有色
    "沪铝":   "AL0",
    "沪锌":   "ZN0",
    "沪镍":   "NI0",
    "沪锡":   "SN0",
    # 农产品
    "豆粕":   "M0",
    "豆油":   "Y0",
    "棕榈":   "P0",
    "玉米":   "C0",
    "白糖":   "SR0",
    "棉花":   "CF0",
    "苹果":   "AP0",
}


# K线周期映射
KLINE_PERIODS = {
    "日K": "1d",
    "周K": "1wk",
    "月K": "1mo",
}

# 数据获取天数
DATA_DAYS = {
    "日K": 365,
    "周K": 730,
    "月K": 1825,
}

# ==================== 技术指标默认参数 ====================
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

KDJ_PERIOD = 9
KDJ_SMOOTH_K = 3
KDJ_SMOOTH_D = 3

RSI_PERIOD = 14

MA_PERIODS = [5, 10, 20, 60, 120, 250]

# ==================== 缠论参数 ====================
CHAN_MIN_BARS = 4  # 最少包含K线数
CHAN_TOLERANCE = 0.0  # 价格容忍度

# ==================== 波浪理论参数 ====================
WAVE_MIN_SIZE = 0.03  # 最小波浪幅度比例

# ==================== 博主/消息源配置 ====================
BLOGGER_SOURCES = {
    "Gold-Eagle Analysts": {"platform": "Gold-Eagle", "url": "https://www.gold-eagle.com/article/gold"},
    "Seeking Alpha": {"platform": "Seeking Alpha", "url": "https://seekingalpha.com/market-news/gold"},
    "Financial Post": {"platform": "Financial Post", "url": "https://financialpost.com/category/commodities/gold"},
}

# 新闻API（预留）
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")

# ==================== 预测评分权重 ====================
PREDICTION_WEIGHTS = {
    "技术面": 0.40,
    "资金面": 0.25,
    "消息面": 0.25,
    "博主观点": 0.10,
}

# ==================== 页面配置 ====================
PAGE_CONFIG = {
    "page_title": APP_TITLE,
    "page_icon": APP_ICON,
    "layout": LAYOUT,
    "initial_sidebar_state": "collapsed",
}

# ==================== 重大经济事件日历 ====================
ECONOMIC_EVENTS = [
    {"name": "非农就业数据", "frequency": "每月第一个周五", "impact": "高"},
    {"name": "CPI消费者价格指数", "frequency": "每月中旬", "impact": "高"},
    {"name": "PPI生产者价格指数", "frequency": "每月中旬", "impact": "中"},
    {"name": "FOMC利率决议", "frequency": "每6-8周", "impact": "极高"},
    {"name": "GDP数据", "frequency": "每季度", "impact": "高"},
    {"name": "初请失业金人数", "frequency": "每周四", "impact": "中"},
    {"name": "零售销售数据", "frequency": "每月中旬", "impact": "中"},
    {"name": "美联储主席讲话", "frequency": "不定期", "impact": "高"},
]

# ==================== 情感分析关键词 ====================
POSITIVE_KEYWORDS = [
    "上涨", "看多", "利好", "突破", "新高", "反弹", "买入", "支撑", "增持",
    "牛市", "上涨趋势", "突破新高", "金叉", "底部", "回暖", "复苏", "涨势",
    "bullish", "rally", "surge", "gain", "support", "uptrend", "buy",
    "rise", "breakthrough", "rebound", "positive", "soar", "climb",
    "outperform", "upgrade", "optimistic", "strong", "growth",
]

NEGATIVE_KEYWORDS = [
    "下跌", "看空", "利空", "破位", "新低", "回调", "卖出", "阻力", "减持",
    "熊市", "下跌趋势", "跌破", "死叉", "顶部", "疲软", "衰退", "跌势",
    "bearish", "decline", "drop", "loss", "resistance", "downtrend", "sell",
    "fall", "breakdown", "correction", "negative", "slump", "crash",
    "underperform", "downgrade", "pessimistic", "weak", "recession",
]

# ==================== UI 配色 ====================
COLORS = {
    "rise": "#ef5350",      # 涨 - 红（中国惯例）
    "fall": "#26a69a",      # 跌 - 绿
    "primary_start": "#4facfe",   # 渐变起点 - 淡蓝
    "primary_end": "#667eea",     # 渐变终点 - 淡紫
    "bg": "#f8f9fa",        # 浅灰背景
    "card_bg": "#ffffff",   # 卡片白色
    "text_primary": "#1e293b",
    "text_secondary": "#64748b",
}
