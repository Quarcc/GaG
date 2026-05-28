import time
import threading

from config import SECTION_TIMESTAMP_MAP, SECTION_EMOJI
from bot.scraper import fetch_page, parse_weather, parse_stock
from parse_restock_timestamps.formatter import (
    build_section_message,
    build_current_weather_message,
    now_sgt,
)
from parse_restock_timestamps.telegram import send_telegram, get_updates
from gag_watchlist import (
    load_watchlist,
    watchlist_add,
    watchlist_remove,
    search_items,
)


def _parse_timestamps(html: str) -> dict[str, int]:
    import re
    pattern = re.compile(
        r'startCountdown\(\s*"([^"]+_ts)"\s*,\s*(\d+)\s*,\s*"[^"]*"\s*\)'
    )
    return {
        m.group(1).replace("_ts", ""): int(m.group(2))
        for m in pattern.finditer(html)
    }


# ─── /watchlist ───────────────────────────────────────────────

def handle_watchlist(chat_id: str, args: str = ""):
    """
    /watchlist              → show list
    /watchlist add <item>   → add item
    /watchlist remove <item>→ remove item
    /watchlist search <q>   → search items DB
    """
    args = args.strip()

    # ── /watchlist (no args) ──────────────────────────────────
    if not args:
        items = load_watchlist(chat_id)
        if not items:
            send_telegram(
                "📋 <b>Your Watchlist</b>\n\n"
                "  <i>Your watchlist is empty.</i>\n\n"
                "Add items with:\n"
                "  /watchlist add Grape",
                chat_id
            )
            return

        lines = ["📋 <b>Your Watchlist</b>", ""]
        for i, item in enumerate(items, 1):
            lines.append(f"  {i}. {item}")
        lines.append("")
        lines.append(f"<i>{len(items)} item(s) watched</i>")
        lines.append("")
        lines.append("➕ /watchlist add &lt;item&gt;")
        lines.append("➖ /watchlist remove &lt;item&gt;")
        lines.append("🔍 /watchlist search &lt;query&gt;")
        send_telegram("\n".join(lines), chat_id)
        return

    parts     = args.split(None, 1)
    subcmd    = parts[0].lower()
    item_arg  = parts[1].strip() if len(parts) > 1 else ""

    # ── /watchlist add <item> ─────────────────────────────────
    if subcmd == "add":
        if not item_arg:
            send_telegram(
                "⚠️ Please provide an item name.\n"
                "Example: /watchlist add Grape",
                chat_id
            )
            return
        success, msg = watchlist_add(chat_id, item_arg)
        send_telegram(msg, chat_id)

    # ── /watchlist remove <item> ──────────────────────────────
    elif subcmd == "remove":
        if not item_arg:
            send_telegram(
                "⚠️ Please provide an item name.\n"
                "Example: /watchlist remove Grape",
                chat_id
            )
            return
        success, msg = watchlist_remove(chat_id, item_arg)
        send_telegram(msg, chat_id)

    # ── /watchlist search <query> ─────────────────────────────
    elif subcmd == "search":
        if not item_arg:
            send_telegram(
                "⚠️ Please provide a search query.\n"
                "Example: /watchlist search bean",
                chat_id
            )
            return
        results = search_items(item_arg, limit=10)
        if results:
            lines = [f"🔍 <b>Search results for \"{item_arg}\":</b>", ""]
            for r in results:
                lines.append(f"  • {r}")
            lines.append("")
            lines.append("Add one with: /watchlist add &lt;name&gt;")
            send_telegram("\n".join(lines), chat_id)
        else:
            send_telegram(
                f'🔍 No results found for <b>"{item_arg}"</b>.\n'
                f'Try a shorter or different search term.',
                chat_id
            )

    # ── Unknown subcommand ────────────────────────────────────
    else:
        send_telegram(
            "⚠️ Unknown watchlist command.\n\n"
            "Available commands:\n"
            "  /watchlist\n"
            "  /watchlist add &lt;item&gt;\n"
            "  /watchlist remove &lt;item&gt;\n"
            "  /watchlist search &lt;query&gt;",
            chat_id
        )


# ─── /weather ─────────────────────────────────────────────────

def handle_weather(chat_id: str):
    html = fetch_page()
    if not html:
        send_telegram("❌ Could not reach the stock page. Try again shortly.", chat_id)
        return
    weathers = parse_weather(html)
    send_telegram(build_current_weather_message(weathers), chat_id)


# ─── /stock ───────────────────────────────────────────────────

def handle_stock(chat_id: str, cache: dict):
    """Uses the caller's own watchlist for highlighting."""
    watched    = load_watchlist(chat_id)
    stock      = cache.get("stock", {})
    timestamps = cache.get("timestamps", {})
    fetched_at = cache.get("at", 0.0)

    if not stock or time.time() - fetched_at > 600:
        send_telegram("⏳ Fetching latest stock...", chat_id)
        html = fetch_page()
        if not html:
            send_telegram("❌ Could not reach the stock page. Try again shortly.", chat_id)
            return
        stock      = parse_stock(html)
        timestamps = _parse_timestamps(html)

    if not stock:
        send_telegram("❌ No stock data available right now.", chat_id)
        return

    send_telegram(f"🌱 <b>Current Stock</b> — {now_sgt()} (GMT+8)", chat_id)
    time.sleep(0.3)

    for section, ts_key in SECTION_TIMESTAMP_MAP.items():
        if section not in stock:
            continue
        next_ts = timestamps.get(ts_key)
        emoji   = SECTION_EMOJI.get(section, "📦")
        header  = f"{emoji} <b>{section}</b> — as of {now_sgt()} (GMT+8)"
        msg     = build_section_message(
            section, stock[section], watched, next_ts, header=header
        )
        send_telegram(msg, chat_id)
        time.sleep(0.4)


# ─── Command listener ─────────────────────────────────────────

def command_listener(cache: dict, cache_lock: threading.Lock):
    from config import CHAT_IDS
    allowed = set(str(c) for c in CHAT_IDS if c)

    print("  💬 Command listener started.")

    while True:
        try:
            updates = get_updates()
            for update in updates:
                msg = update.get("message") or update.get("edited_message")
                if not msg:
                    continue

                chat_id = str(msg["chat"]["id"])
                text    = msg.get("text", "").strip()

                if chat_id not in allowed:
                    continue

                text_lower = text.lower()

                # /watchlist [subcommand] [args]
                if text_lower.startswith("/watchlist"):
                    args = text[len("/watchlist"):].strip()
                    print(f"  💬 /watchlist {args!r} from {chat_id}")
                    handle_watchlist(chat_id, args)

                elif text_lower.startswith("/stock"):
                    print(f"  💬 /stock from {chat_id}")
                    with cache_lock:
                        snapshot = dict(cache)
                    threading.Thread(
                        target=handle_stock,
                        args=(chat_id, snapshot),
                        daemon=True
                    ).start()

                elif text_lower.startswith("/weather"):
                    print(f"  💬 /weather from {chat_id}")
                    threading.Thread(
                        target=handle_weather,
                        args=(chat_id,),
                        daemon=True
                    ).start()

        except Exception as e:
            print(f"  [command_listener error] {e}")

        time.sleep(2)