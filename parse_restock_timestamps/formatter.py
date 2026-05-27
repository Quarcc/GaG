import time
from datetime import datetime
from config import SECTION_EMOJI, TZ_SGT


def format_time_until(ts: int) -> str:
    """Returns '4m 32s' or 'now' from a Unix timestamp."""
    diff = int(ts - time.time())
    if diff <= 0:
        return "now"
    m, s = divmod(diff, 60)
    return f"{m}m {s}s" if m else f"{s}s"


def now_sgt() -> str:
    """Current time as HH:MM in GMT+8."""
    return datetime.now(TZ_SGT).strftime("%H:%M")


def build_item_lines(items: list[dict], watched: list[str]) -> list[str]:
    """Returns formatted item lines, ⭐ for watched items."""
    lines = []
    for i in items:
        marker = "⭐" if any(w.lower() == i["name"].lower() for w in watched) else "  "
        lines.append(f"   {marker} {i['name']}  ×{i['qty']}")
    return lines


def build_section_message(
    section: str,
    stock_value,
    watched: list[str],
    next_restock_ts: int | None,
    header: str = None,
) -> str:
    """
    Builds a Telegram message for one shop section.
    stock_value is either:
      - dict {"Daily Deals": [...], "Shop": [...]}  for Seeds Stock
      - list [{"name": ..., "qty": ...}]            for all other sections
    header overrides the first line (used by /stock command).
    """
    emoji    = SECTION_EMOJI.get(section, "📦")
    next_str = format_time_until(next_restock_ts) if next_restock_ts else "unknown"

    lines = []
    lines.append(header or f"{emoji} <b>{section}</b> — restocked at {now_sgt()} (GMT+8)")
    lines.append(f"⏱ Next restock in: <b>{next_str}</b>")

    # ── Seeds: two subsections in one message ─────────────────
    if isinstance(stock_value, dict):
        all_items    = stock_value.get("Daily Deals", []) + stock_value.get("Shop", [])
        watched_hits = [i for i in all_items if any(w.lower() == i["name"].lower() for w in watched)]
        if watched_hits:
            lines.append("")
            lines.append("✨ <b>Watched items in stock:</b>")
            for i in watched_hits:
                lines.append(f"   • {i['name']}  ×{i['qty']}")

        daily = stock_value.get("Daily Deals", [])
        lines.append("")
        lines.append("💥 <b>Daily Deals:</b>")
        lines.extend(build_item_lines(daily, watched) if daily else ["   <i>(none)</i>"])

        shop = stock_value.get("Shop", [])
        lines.append("")
        lines.append("🏪 <b>Shop:</b>")
        lines.extend(build_item_lines(shop, watched) if shop else ["   <i>(none)</i>"])

    # ── All other sections: flat list ─────────────────────────
    else:
        items        = stock_value
        watched_hits = [i for i in items if any(w.lower() == i["name"].lower() for w in watched)]
        if watched_hits:
            lines.append("")
            lines.append("✨ <b>Watched items in stock:</b>")
            for i in watched_hits:
                lines.append(f"   • {i['name']}  ×{i['qty']}")
        lines.append("")
        lines.append("📦 <b>All items:</b>")
        lines.extend(build_item_lines(items, watched) if items else ["   <i>(nothing in stock)</i>"])

    return "\n".join(lines)


def build_weather_message(new_weathers: list[dict], all_weathers: list[dict] = None) -> str:
    """Alert triggered when new weather appears. Shows all active weathers."""
    display   = all_weathers if all_weathers else new_weathers
    new_names = {w["name"] for w in new_weathers}
    lines     = [f"🌦 <b>Weather Alert!</b> — {now_sgt()} (GMT+8)", ""]
    for w in display:
        tag = " <i>(new!)</i>" if w["name"] in new_names and len(display) > 1 else ""
        lines.append(f"  <b>{w['name']}</b>{tag}")
    return "\n".join(lines)


def build_current_weather_message(weathers: list[dict]) -> str:
    """For /weather command — shows all currently active weathers."""
    lines = [f"🌦 <b>Current Weather</b> — {now_sgt()} (GMT+8)", ""]
    if weathers:
        for w in weathers:
            lines.append(f"  <b>{w['name']}</b>")
    else:
        lines.append("  ☀️ <i>No active weather right now.</i>")
    return "\n".join(lines)


def build_watchlist_message(watched: list[str]) -> str:
    """For /watchlist command."""
    lines = ["📋 <b>Current Watchlist</b>", ""]
    for i, item in enumerate(watched, 1):
        lines.append(f"  {i}. {item}")
    lines.append("")
    lines.append(f"<i>{len(watched)} items watched</i>")
    return "\n".join(lines)