# 兼容Python低版本的类型注解语法，确保注解写法在旧版Python中正常运行
from __future__ import annotations

# 导入FastAPI核心模块：路由、请求体、HTTP异常处理
from fastapi import APIRouter, Body, HTTPException

# 导入项目内部服务模块：
# 简报引擎：生成简报数据
from services.briefing_engine import build_briefing_payload
# 行情数据服务：获取股票实时报价
from services.market_data import fetch_quotes
# 用户自选股服务：新增、查询、删除自选股
from services.user_watchlist import add_symbol, list_symbols, remove_symbol
# 自选股配置：内置的股票配置字典（股票代码→股票信息）
from services.watchlist_config import WATCHLIST_BY_SYMBOL
# 自选股核心服务：构建仪表盘/详情数据、清空仪表盘缓存
from services.watchlist_service import (
    build_dashboard_payload,
    build_detail_payload,
    invalidate_dashboard_cache,
)

# ===================== 路由初始化 =====================
# 创建FastAPI路由实例
# prefix="/api"：所有接口统一前缀为 /api
# tags=["watchlist"]：Swagger文档中归类为【自选股】模块
router = APIRouter(prefix="/api", tags=["watchlist"])


# ===================== 接口定义 =====================

@router.get("/dashboard")
def dashboard() -> dict[str, object]:
    """
    【接口】获取股票监控仪表盘数据
    功能：返回仪表盘核心数据 + 市场简报数据，用于前端大盘展示
    返回值：包含仪表盘数据和简报数据的字典
    """
    # 构建仪表盘核心数据（股票行情、指标、排名等）
    payload = build_dashboard_payload()
    # 基于仪表盘数据，生成市场简报数据（总结、异动提醒等）
    payload["briefing"] = build_briefing_payload(payload)
    # 合并后返回给前端
    return payload


@router.get("/watchlist/{symbol}")
def watchlist_detail(symbol: str) -> dict[str, object]:
    """
    【接口】获取单只股票的详情数据
    路径参数：symbol - 股票代码（如 AAPL、TSLA）
    功能：返回指定股票的完整详情（基本面、技术面、资金面等）
    异常：股票代码不存在时，返回404
    返回值：股票详情字典
    """
    try:
        # 统一转为大写，调用服务构建详情数据
        return build_detail_payload(symbol.upper())
    except KeyError as exc:
        # 捕获股票不存在异常，抛出404 HTTP异常
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}") from exc


@router.get("/briefing")
def briefing() -> dict[str, object]:
    """
    【接口】独立获取市场简报数据
    功能：单独返回大盘/自选股的简报总结，无需依赖仪表盘数据
    返回值：简报数据字典
    """
    return build_briefing_payload()


@router.get("/user-watchlist")
def get_user_watchlist() -> dict[str, object]:
    """
    【接口】获取用户自选股列表 + 系统内置股票列表
    功能：前端展示「内置股票」和「用户自定义股票」双列表
    返回值：字典，包含builtin（内置股票）、user（用户自选股）
    """
    # 调用服务查询用户添加的所有自选股
    user_symbols = list_symbols()
    # 遍历系统内置股票配置，格式化数据（代码+名称）
    builtin = [
        {"symbol": symbol, "name": profile.name}
        for symbol, profile in WATCHLIST_BY_SYMBOL.items()
    ]
    # 返回双列表数据
    return {"builtin": builtin, "user": user_symbols}


@router.post("/user-watchlist")
def add_user_symbol(body: dict = Body(...)) -> dict[str, object]:
    """
    【接口】添加用户自选股
    请求体：必须包含symbol字段（股票代码）
    核心逻辑：
        1. 校验股票代码非空
        2. 校验行情接口可正常获取该股票价格（过滤无效代码）
        3. 校验通过后添加到用户自选股
        4. 清空仪表盘缓存（保证新增后数据刷新）
    异常：代码为空/无效/添加失败时，返回400
    返回值：添加成功的结果字典
    """
    # 从请求体获取股票代码，去除空格并转为大写
    raw_symbol = str(body.get("symbol", "")).strip().upper()
    # 校验：股票代码不能为空
    if not raw_symbol:
        raise HTTPException(status_code=400, detail="symbol 不能为空")

    # ===================== 核心校验：行情可达性校验 =====================
    # 作用：拿不到实时价格的股票代码判定为无效，禁止添加，避免污染缓存
    quotes = fetch_quotes([raw_symbol])
    quote = quotes.get(raw_symbol)
    # 校验：报价不存在 / 状态异常 / 无价格 → 无效代码
    if quote is None or quote.status != "ok" or quote.price is None:
        raise HTTPException(
            status_code=400,
            detail=f"无法从行情源拿到 {raw_symbol} 的价格，请确认美股 symbol 是否正确。",
        )

    # 调用服务添加自选股，返回成功状态和提示信息
    ok, message = add_symbol(raw_symbol)
    # 添加失败则抛出400异常
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    # 清空仪表盘缓存：新增自选股后，仪表盘需要重新加载最新数据
    invalidate_dashboard_cache()
    # 返回添加成功结果
    return {"ok": True, "symbol": raw_symbol, "message": message}


@router.delete("/user-watchlist/{symbol}")
def delete_user_symbol(symbol: str) -> dict[str, object]:
    """
    【接口】删除用户自选股
    路径参数：symbol - 要删除的股票代码
    核心逻辑：
        1. 调用服务删除自选股
        2. 删除失败（股票不在自选股中）返回404
        3. 删除成功后清空仪表盘缓存
    返回值：删除成功的结果字典
    """
    # 调用服务删除自选股，返回删除结果（True/False）
    if not remove_symbol(symbol):
        # 股票不在自选股中 → 抛出404异常
        raise HTTPException(status_code=404, detail=f"{symbol} 不在你的自选股里")

    # 清空仪表盘缓存：删除自选股后刷新数据
    invalidate_dashboard_cache()
    # 返回删除成功结果
    return {"ok": True, "symbol": symbol.upper()}