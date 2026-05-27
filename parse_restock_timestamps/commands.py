import time
import threading

from config import WATCHED_ITEMS, SECTION_TIMESTAMP_MAP, SECTION_EMOJI
from bot.scraper import fetch_page, parse_weather, parse_stock
from parse_restock_timestamps.formatter import (
    build_section_message,
    build_current_weather_message,
    build_watchlist_message,
    now_sgt,
)
from parse_restock_timestamps.telegram import send_telegram, get_updates


def _parse_timestamps(html: str) -> dict[str, int]:
    """Local import to avoid circular dependency."""
    import re
    pattern = re.compile(
        r'startCountdown\(\s*"([^"]+_ts)"\s*,\s*(\d+)\s*,\s*"[^"]*"\s*\)'
    )
    return {
        m.group(1).replace("_ts", ""): int(m.group(2))
        for m in pattern.finditer(html)
    }


def handle_watchlist(chat_id: str):
    """Reply with the current WATCHED_ITEMS list."""
    send_telegram(build_watchlist_message(WATCHED_ITEMS), chat_id)


def handle_weather(chat_id: str):
    """Fetch fresh page and reply with all currently active weathers."""
    html = fetch_page()
    if not html:
        send_telegram("❌ Could not reach the stock page. Try again shortly.", chat_id)
        return
    from parse_restock_timestamps.formatter import build_current_weather_message
    weathers = parse_weather(html)
    send_telegram(build_current_weather_message(weathers), chat_id)


def handle_stock(chat_id: str, cache: dict):
    """
    Reply with current stock for every section.
    Uses shared cache if fresh (<10 min), otherwise fetches fresh.
    cache keys: "stock", "timestamps", "at"
    """
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
        msg     = build_section_message(section, stock[section], WATCHED_ITEMS, next_ts, header=header)
        send_telegram(msg, chat_id)
        time.sleep(0.4)


def command_listener(cache: dict, cache_lock: threading.Lock):
    """
    Runs in a background thread. Polls Telegram every 2s and
    dispatches /stock, /watchlist, /weather to their handlers.
    Only responds to CHAT_IDS defined in config.
    """
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
                text    = msg.get("text", "").strip().lower()

                if chat_id not in allowed:
                    continue

                if text.startswith("/stock"):
                    print(f"  💬 /stock requested by {chat_id}")
                    with cache_lock:
                        snapshot = dict(cache)
                    threading.Thread(
                        target=handle_stock, args=(chat_id, snapshot), daemon=True
                    ).start()

                elif text.startswith("/watchlist"):
                    print(f"  💬 /watchlist requested by {chat_id}")
                    handle_watchlist(chat_id)

                elif text.startswith("/weather"):
                    print(f"  💬 /weather requested by {chat_id}")
                    threading.Thread(
                        target=handle_weather, args=(chat_id,), daemon=True
                    ).start()

        except Exception as e:
            print(f"  [command_listener error] {e}")

        time.sleep(2)