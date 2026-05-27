"""
🌱 Grow a Garden — Telegram Notification Bot
=============================================
Entry point. Runs the main polling loop and starts the
background command listener thread.

SETUP
-----
1. pip install -r requirements.txt
2. Fill in .env:
       BOT_TOKEN=...
       CHAT_ID1=...
       CHAT_ID2=...
3. Register commands in @BotFather → /setcommands:
       stock     - Show current stock right now
       watchlist - Show watched items list
       weather   - Check current in-game weather
4. Run: python main.py
"""

import time
import threading
from datetime import datetime

from config import (
    WATCHED_ITEMS,
    SECTION_TIMESTAMP_MAP,
    FALLBACK_POLL,
    WEATHER_POLL,
    BUFFER_SECONDS,
    TZ_SGT,
)
from bot.scraper import fetch_page, parse_stock, parse_weather
from parse_restock_timestamps.formatter import build_section_message, build_weather_message
from parse_restock_timestamps.telegram import send_telegram
from parse_restock_timestamps.commands import command_listener


def parse_restock_timestamps(html: str) -> dict[str, int]:
    import re
    pattern = re.compile(
        r'startCountdown\(\s*"([^"]+_ts)"\s*,\s*(\d+)\s*,\s*"[^"]*"\s*\)'
    )
    return {
        m.group(1).replace("_ts", ""): int(m.group(2))
        for m in pattern.finditer(html)
    }


# ─── STATE ────────────────────────────────────────────────────
section_state: dict[str, dict] = {}
last_weather_names: set[str]   = set()
last_weather_poll:  float       = 0.0

# Shared cache — written by main loop, read by /stock handler
cache      = {"stock": {}, "timestamps": {}, "at": 0.0}
cache_lock = threading.Lock()


def should_send_for_section(section: str, ts_key: str, timestamps: dict) -> bool:
    current_ts = timestamps.get(ts_key)
    if current_ts is None:
        return False
    state = section_state.setdefault(section, {"last_ts": None})
    if state["last_ts"] is None:
        state["last_ts"] = current_ts
        return False
    if current_ts != state["last_ts"]:
        state["last_ts"] = current_ts
        return True
    return False


def check_weather(html: str):
    global last_weather_names
    weathers      = parse_weather(html)
    current_names = {w["name"] for w in weathers}
    new_weathers  = [w for w in weathers if w["name"] not in last_weather_names]
    if new_weathers:
        msg = build_weather_message(new_weathers, all_weathers=weathers)
        send_telegram(msg)
        print(f"  🌦  Weather alert: {[w['name'] for w in new_weathers]} (active: {list(current_names)})")
    last_weather_names = current_names


def next_wakeup(timestamps: dict) -> float:
    now          = time.time()
    future       = [ts for ts in timestamps.values() if ts > now]
    next_restock = (max(0, min(future) - now) + BUFFER_SECONDS) if future else FALLBACK_POLL
    next_weather = max(0, WEATHER_POLL - (now - last_weather_poll))
    return min(next_restock, next_weather)


def main():
    global last_weather_poll

    print("🌱 Grow a Garden Telegram Bot started!")
    print(f"   Watching: {WATCHED_ITEMS}\n")

    threading.Thread(
        target=command_listener,
        args=(cache, cache_lock),
        daemon=True
    ).start()

    send_telegram(
        "🌱 <b>Grow a Garden Bot is online!</b>\n\n"
        "You'll get a message per shop every time it restocks,\n"
        "plus weather alerts whenever new weather appears!\n\n"
        "📋 /watchlist — see watched items\n"
        "📦 /stock — get current stock now\n"
        "🌦 /weather — check current weather\n\n"
        "🌸 Made with luv~ hehe"
    )

    while True:
        now_str = datetime.now(TZ_SGT).strftime("%H:%M:%S")
        print(f"[{now_str} SGT] Fetching page...")

        html = fetch_page()
        if not html:
            print(f"  Fetch failed — retrying in {FALLBACK_POLL}s.")
            time.sleep(FALLBACK_POLL)
            continue

        timestamps = parse_restock_timestamps(html)
        stock      = parse_stock(html)

        with cache_lock:
            cache["stock"]      = stock
            cache["timestamps"] = timestamps
            cache["at"]         = time.time()

        sent_count = 0
        for section, ts_key in SECTION_TIMESTAMP_MAP.items():
            if section not in stock:
                continue
            if should_send_for_section(section, ts_key, timestamps):
                next_ts = timestamps.get(ts_key)
                msg     = build_section_message(section, stock[section], WATCHED_ITEMS, next_ts)
                send_telegram(msg)
                print(f"  📨 Sent: {section}")
                sent_count += 1
                time.sleep(0.5)

        if sent_count == 0:
            print("  — No sections restocked this cycle.")

        if time.time() - last_weather_poll >= WEATHER_POLL:
            check_weather(html)
            last_weather_poll = time.time()

        wait    = next_wakeup(timestamps)
        wake_at = datetime.fromtimestamp(time.time() + wait, TZ_SGT).strftime("%H:%M:%S")
        print(f"  💤 Sleeping {wait:.0f}s — next check at {wake_at} SGT\n")
        time.sleep(wait)


if __name__ == "__main__":
    main()