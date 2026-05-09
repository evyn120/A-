"""
US stock anomaly detector for daily report.

Purpose:
1. Detect unusual US stock moves from existing market.json.
2. Do not send emails.
3. Do not depend on Russell1000 stock universe.
4. Use only the stocks already collected by your own daily_report system.
"""

from __future__ import annotations

import math
from html import escape
from typing import Any, Dict, List, Optional


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Safely convert value to float.
    Supports number, string with %, comma, etc.
    """
    if value is None:
        return default

    try:
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
            if value == "":
                return default
        return float(value)
    except Exception:
        return default


def _format_volume(volume: Optional[float]) -> str:
    """
    Format volume for display.
    """
    if volume is None:
        return "N/A"

    if volume >= 1_000_000_000:
        return f"{volume / 1_000_000_000:.1f}B"
    if volume >= 1_000_000:
        return f"{volume / 1_000_000:.1f}M"
    if volume >= 1_000:
        return f"{volume / 1_000:.0f}K"

    return str(int(volume))


def _unique_stocks(stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate stocks by symbol.
    Later data will not overwrite earlier data.
    """
    seen = set()
    result = []

    for stock in stocks:
        symbol = str(stock.get("symbol", "")).strip()
        if not symbol:
            continue

        if symbol in seen:
            continue

        seen.add(symbol)
        result.append(stock)

    return result


def collect_us_anomalies(
    market_data: Dict[str, Any],
    change_threshold: float = 5.0,
    large_change_threshold: float = 8.0,
    volume_threshold: float = 20_000_000,
    max_items: int = 15,
) -> List[Dict[str, Any]]:
    """
    Collect unusual US stock movements from market_data.

    It uses the existing market.json structure:
    market_data["us"]["stocks"]
    market_data["us"]["top_gainers"]
    market_data["us"]["top_losers"]

    Detection logic:
    1. Absolute daily change >= change_threshold
    2. Absolute daily change >= large_change_threshold means strong anomaly
    3. Volume >= volume_threshold means heavy-volume anomaly
    4. If a stock has volume_ratio or z_score fields in the future, it will use them too.
    """

    us_data = market_data.get("us", {})
    candidates = []

    candidates.extend(us_data.get("stocks", []))
    candidates.extend(us_data.get("top_gainers", []))
    candidates.extend(us_data.get("top_losers", []))

    candidates = _unique_stocks(candidates)

    anomalies = []

    for stock in candidates:
        if "error" in stock:
            continue

        symbol = str(stock.get("symbol", "")).strip()
        name = str(stock.get("name", symbol)).strip()
        close = _to_float(stock.get("close"))
        change_pct = _to_float(stock.get("change_pct"))
        volume = _to_float(stock.get("volume"))

        if change_pct is None:
            continue

        volume_ratio = _to_float(stock.get("volume_ratio"))
        z_score = _to_float(stock.get("z_score"))

        reasons = []
        anomaly_type = []

        abs_change = abs(change_pct)

        if abs_change >= large_change_threshold:
            if change_pct > 0:
                reasons.append(f"單日大漲 {change_pct:+.2f}%")
                anomaly_type.append("strong_up")
            else:
                reasons.append(f"單日大跌 {change_pct:+.2f}%")
                anomaly_type.append("strong_down")
        elif abs_change >= change_threshold:
            if change_pct > 0:
                reasons.append(f"漲幅顯著 {change_pct:+.2f}%")
                anomaly_type.append("up")
            else:
                reasons.append(f"跌幅顯著 {change_pct:+.2f}%")
                anomaly_type.append("down")

        if volume is not None and volume >= volume_threshold:
            reasons.append(f"成交量放大至 {_format_volume(volume)}")
            anomaly_type.append("heavy_volume")

        if volume_ratio is not None and volume_ratio >= 2.0:
            reasons.append(f"成交量約為近期均量 {volume_ratio:.1f} 倍")
            anomaly_type.append("volume_ratio")

        if z_score is not None and abs(z_score) >= 2.5:
            reasons.append(f"收益率偏離近期均值，Z-Score={z_score:.2f}")
            anomaly_type.append("z_score")

        if not reasons:
            continue

        # Score determines display order.
        score = abs_change * 2

        if volume is not None and volume > 0:
            score += min(math.log10(volume), 10)

        if volume_ratio is not None:
            score += volume_ratio * 2

        if z_score is not None:
            score += abs(z_score) * 2

        anomalies.append(
            {
                "symbol": symbol,
                "name": name,
                "close": close,
                "change_pct": change_pct,
                "volume": volume,
                "volume_text": _format_volume(volume),
                "reasons": reasons,
                "type": anomaly_type,
                "score": score,
            }
        )

    anomalies.sort(key=lambda x: x["score"], reverse=True)

    return anomalies[:max_items]


def build_us_anomaly_prompt_text(
    market_data: Dict[str, Any],
    max_items: int = 10,
) -> str:
    """
    Build plain text anomaly section for LLM prompt.
    """
    anomalies = collect_us_anomalies(market_data, max_items=max_items)

    if not anomalies:
        return "今日未檢測到顯著美股價量異動。"

    lines = []

    for item in anomalies:
        change_pct = item["change_pct"]
        direction = "上漲" if change_pct > 0 else "下跌"

        lines.append(
            f"- {item['name']}({item['symbol']}): "
            f"{direction} {change_pct:+.2f}%，"
            f"收盤價 {item['close']}，"
            f"成交量 {item['volume_text']}；"
            f"異動原因：{'；'.join(item['reasons'])}"
        )

    return "\n".join(lines)


def make_us_anomaly_html(
    market_data: Dict[str, Any],
    max_items: int = 12,
) -> str:
    """
    Generate HTML section for US anomaly monitor.
    Can be inserted into generate_html().
    """
    anomalies = collect_us_anomalies(market_data, max_items=max_items)

    if not anomalies:
        return """
<section class="section anomaly-section">
  <div class="section-title">
    <span class="section-icon">📡</span>
    <span>美股異動監控</span>
  </div>
  <p class="analysis-text">今日未檢測到顯著美股價量異動。</p>
</section>
"""

    cards = ""

    for item in anomalies:
        pct = item["change_pct"]
        css_class = "price-up" if pct > 0 else "price-down"
        arrow = "▲" if pct > 0 else "▼"

        reasons_html = "".join(
            f"<li>{escape(reason)}</li>" for reason in item["reasons"]
        )

        close_text = "" if item["close"] is None else escape(str(item["close"]))

        cards += f"""
<div class="anomaly-card">
  <div class="anomaly-header">
    <div>
      <div class="anomaly-name">{escape(item["name"])}</div>
      <div class="symbol">{escape(item["symbol"])}</div>
    </div>
    <div class="{css_class} anomaly-change">{arrow} {pct:+.2f}%</div>
  </div>
  <div class="anomaly-meta">
    <span>收盤價：{close_text}</span>
    <span>成交量：{escape(item["volume_text"])}</span>
  </div>
  <ul class="anomaly-reasons">
    {reasons_html}
  </ul>
</div>
"""

    return f"""
<section class="section anomaly-section">
  <div class="section-title">
    <span class="section-icon">📡</span>
    <span>美股異動監控</span>
  </div>
  <div class="anomaly-grid">
    {cards}
  </div>
</section>
"""
