"""日报相关 API + 页面入口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from services.daily_report_service import (
    DailyReport,
    latest_report,
    list_reports,
    _reports_dir,
)

router = APIRouter(tags=["daily_report"])


def _to_dict(r: DailyReport) -> dict:
    return {
        "date": r.date,
        "display": r.display,
        "html_url": f"/daily/{r.date}",
        "json_url": f"/daily/{r.date}.json" if r.json_path else None,
    }


@router.get("/api/daily-reports")
def api_list_reports() -> dict:
    items = list_reports()
    return {
        "count": len(items),
        "items": [_to_dict(r) for r in items],
        "latest": _to_dict(items[0]) if items else None,
    }


@router.get("/daily/", response_class=HTMLResponse, include_in_schema=False)
def daily_index() -> HTMLResponse:
    """日报首页：列出所有日期。也可以做成读取 docs/index.html 模板。"""
    items = list_reports()
    if not items:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;padding:40px;"
            "background:#0b1020;color:#e2e8f0;'>"
            "<h1>📊 港美股日报</h1>"
            "<p>还没有任何日报。请先运行 <code>python -m daily_report.scripts.run_daily</code> "
            "生成第一份。</p></body></html>"
        )
    rows = "\n".join(
        f'<li><a href="/daily/{r.date}">{r.display}'
        f'{"（最新）" if i == 0 else ""}</a></li>'
        for i, r in enumerate(items)
    )
    return HTMLResponse(f"""
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>📊 港美股日报</title>
<style>
  body {{ font-family: "PingFang SC","Microsoft YaHei",sans-serif;
         background:#0b1020;color:#e2e8f0;padding:40px;max-width:880px;margin:0 auto; }}
  a {{ color:#93c5fd;text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  ul {{ line-height:2; padding-left:20px; }}
  .back {{ display:inline-block;margin-bottom:18px;color:#94a3b8; }}
</style>
</head>
<body>
  <a class="back" href="/">← 返回决策看板</a>
  <h1>📊 港美股日报</h1>
  <p style="color:#94a3b8;">每日自动生成 · 港股 + 美股 + 总经分析</p>
  <ul>{rows}</ul>
</body>
</html>
""")


@router.get("/daily/{date}", response_class=HTMLResponse, include_in_schema=False)
def daily_html(date: str) -> FileResponse:
    target = _reports_dir() / f"stock-{date}.html"
    if not target.exists():
        raise HTTPException(404, detail=f"没有 {date} 的日报")
    return FileResponse(target, media_type="text/html; charset=utf-8")


@router.get("/daily/{date}.json", include_in_schema=False)
def daily_json(date: str) -> FileResponse:
    target = _reports_dir() / f"stock-{date}.json"
    if not target.exists():
        raise HTTPException(404, detail=f"没有 {date} 的 JSON")
    return FileResponse(target, media_type="application/json; charset=utf-8")
