"""日报数据服务：列出可用日期、读取 HTML/JSON。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


_FILENAME_RE = re.compile(r"^stock-(\d{4}-\d{2}-\d{2})\.html$")


def _reports_dir() -> Path:
    """日报产物目录，优先读环境变量。"""
    env = os.environ.get("DAILY_REPORTS_DIR")
    if env:
        return Path(env)
    # 回退：源码模式下默认放在 <repo>/data/daily_reports/
    return Path(__file__).resolve().parents[3] / "data" / "daily_reports"


@dataclass
class DailyReport:
    date: str          # "2026-05-08"
    html_path: Path
    json_path: Path | None

    @property
    def display(self) -> str:
        d = datetime.strptime(self.date, "%Y-%m-%d")
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        return f"{d.year}年{d.month}月{d.day}日 星期{weekdays[d.weekday()]}"


def list_reports() -> list[DailyReport]:
    """按日期倒序返回所有可用日报。"""
    base = _reports_dir()
    if not base.exists():
        return []
    out: list[DailyReport] = []
    for p in base.glob("stock-*.html"):
        m = _FILENAME_RE.match(p.name)
        if not m:
            continue
        date = m.group(1)
        json_path = p.with_suffix(".json")
        out.append(DailyReport(
            date=date,
            html_path=p,
            json_path=json_path if json_path.exists() else None,
        ))
    out.sort(key=lambda r: r.date, reverse=True)
    return out


def latest_report() -> DailyReport | None:
    items = list_reports()
    return items[0] if items else None
