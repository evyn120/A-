"""
用户自定义股票池（阶段 0：单用户 + JSON 文件存储）。

阶段 0 目标：让单个用户可以在页面上自由添加/删除美股 symbol，
所有改动落地到本地 JSON 文件，下次启动还在。

阶段 1 升级路径：把 `_load` / `_save` 换成 SQLite 的 user_watchlists 表，
并让 `list_symbols` / `add_symbol` / `remove_symbol` 带 user_id 参数即可。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock

from .watchlist_config import WATCHLIST_BY_SYMBOL  # 内置核心股票池的映射，防止重复添加


# 自选股存储文件路径，可通过环境变量 USER_WATCHLIST_PATH 自定义，默认 data/user_watchlist.json
_STORAGE_PATH = Path(os.getenv("USER_WATCHLIST_PATH", "data/user_watchlist.json"))
# 线程锁，保护对 JSON 文件的并发读写
_LOCK = Lock()


def _ensure_storage() -> None:
    """
    确保存储文件存在。

    若目录不存在则递归创建；若文件不存在则创建一个包含空 symbol 列表的初始 JSON。
    """
    _STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _STORAGE_PATH.exists():
        _STORAGE_PATH.write_text(json.dumps({"symbols": []}, ensure_ascii=False), encoding="utf-8")


def _load() -> list[str]:
    """
    从 JSON 文件读取当前的用户自选股列表。

    所有代码统一转为大写，确保大小写不敏感。
    若文件损坏或读取失败，返回空列表作为降级处理。
    """
    _ensure_storage()
    try:
        data = json.loads(_STORAGE_PATH.read_text(encoding="utf-8"))
        symbols = data.get("symbols", [])
        # 过滤掉非字符串元素，统一转大写
        return [str(s).upper() for s in symbols if isinstance(s, str)]
    except (json.JSONDecodeError, OSError):
        # 文件损坏或系统 I/O 错误时返回空列表，由下次写入修复
        return []


def _save(symbols: list[str]) -> None:
    """
    将用户自选股列表写入 JSON 文件。

    以带缩进的美化格式保存，方便手动检查。
    """
    _ensure_storage()
    payload = json.dumps({"symbols": symbols}, ensure_ascii=False, indent=2)
    _STORAGE_PATH.write_text(payload, encoding="utf-8")


def list_symbols() -> list[str]:
    """
    查询当前用户自选股列表（线程安全）。

    返回包含所有自选股大写代码的列表副本。
    """
    with _LOCK:
        return list(_load())


def add_symbol(symbol: str) -> tuple[bool, str]:
    """
    添加一个股票代码到用户自选股。

    返回:
        (是否新增成功, 原因描述)

    规则:
        - 代码必须以字母数字组成，允许包含 '.' 和 '-'（如 BRK.B）
        - 不允许重复添加已在核心股票池中的品种（WATCHLIST_BY_SYMBOL）
        - 不允许重复添加已存在于自选股中的品种
    """
    symbol = symbol.upper().strip()
    # 基本合法性检查：非空且仅由字母、数字、点、横线组成
    if not symbol or not symbol.replace(".", "").replace("-", "").isalnum():
        return False, "symbol 格式不合法"

    # 禁止重复添加内置核心池的品种
    if symbol in WATCHLIST_BY_SYMBOL:
        return False, f"{symbol} 已经在内置核心股票池里，无需重复添加"

    with _LOCK:
        current = _load()
        if symbol in current:
            return False, f"{symbol} 已经在你的自选股里"
        current.append(symbol)
        _save(current)

    return True, f"{symbol} 已加入自选股"


def remove_symbol(symbol: str) -> bool:
    """
    从用户自选股中删除一个股票代码。

    返回:
        True  删除成功
        False 代码不在自选股中，无需操作
    """
    symbol = symbol.upper().strip()
    with _LOCK:
        current = _load()
        if symbol not in current:
            return False
        current.remove(symbol)
        _save(current)
    return True