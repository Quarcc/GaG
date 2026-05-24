"""
🌱 Grow a Garden — Telegram Notification Bot
=============================================
Sends a separate Telegram message per shop section each time
that section's restock timer expires. Also monitors weather
and alerts when a new weather event appears.

Commands (register these in @BotFather):
  /stock     — fetch and show current stock right now
  /watchlist — show the current watched items list

SETUP
-----
1. pip install requests beautifulsoup4 python-dotenv
2. Create bot via @BotFather → /newbot → copy token
3. Register commands via @BotFather → /setcommands:
       stock - Show current stock right now
       watchlist - Show watched items list
4. Get chat ID via https://api.telegram.org/bot<TOKEN>/getUpdates
5. Fill in .env with BOT_TOKEN, CHAT_ID1, CHAT_ID2
6. Run: python main.py
"""

import time
import re
import requests
import threading
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import os

# ─── CONFIG ───────────────────────────────────────────────────
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_IDS  = [os.getenv("CHAT_ID1"), os.getenv("CHAT_ID2")]

WATCHED_ITEMS = [
    "Chrimson Thorn",
    "Zebrazinkle",
    "Octobloom",
    "Alien Apple",
    "Pollenvine",
    "Bug Egg",
    "Jungle Egg",
    "Master Sprinkler",
    "Grandmaster Sprinkler",
    "Medium Toy",
    "Medium Treat",
    "Levelup Lollipop",
    # Add more here ↓
]

EXCLUDED_ITEMS = {
    "broccoli",
    "potato",
}

EXCLUDED_EVENT_KEYWORDS = [
    "easter",
    "chocolate",
    "gummy",
]

URL            = "https://www.growagardenstocknow.com/"
BUFFER_SECONDS = 5
FALLBACK_POLL  = 300
WEATHER_POLL   = 30
TZ_SGT         = timezone(timedelta(hours=8))

SECTION_TIMESTAMP_MAP = {
    "Seeds Stock":    "seeds",
    "Gear Stock":     "gear",
    "Egg Stock":      "egg",
    "Event Stock":    "event",
    "Merchant Stock": "merchant",
}

SECTION_EMOJI = {
    "Seeds Stock":    "🌱",
    "Gear Stock":     "🛠️",
    "Egg Stock":      "🥚",
    "Event Stock":    "🎪",
    "Merchant Stock": "🛒",
}

# ─── STATE ────────────────────────────────────────────────────
section_state: dict[str, dict] = {}
last_weather_names: set[str]   = set()
last_weather_poll:  float       = 0.0

# Shared cache of the last successfully parsed stock + timestamps
# Written by the polling loop, read by /stock command handler
cache_lock       = threading.Lock()
cached_stock:      dict        = {}
cached_timestamps: dict        = {}
cached_at:         float       = 0.0   # unix time of last successful fetch

# Tracks the last Telegram update_id we've processed (for command polling)
last_update_id: int = 0

# ─── TELEGRAM ─────────────────────────────────────────────────

def send_telegram(message: str, chat_id: str = None):
    """Send to a specific chat_id, or broadcast to all CHAT_IDS if none given."""
    targets = [chat_id] if chat_id else CHAT_IDS
    for cid in targets:
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": cid, "text": message, "parse_mode": "HTML"},
                timeout=10
            ).raise_for_status()
        except Exception as e:
            print(f"  [Telegram error] {e}")


def get_updates() -> list[dict]:
    """Poll Telegram for new messages/commands."""
    global last_update_id
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
            params={"offset": last_update_id + 1, "timeout": 5},
            timeout=10
        )
        r.raise_for_status()
        updates = r.json().get("result", [])
        if updates:
            last_update_id = updates[-1]["update_id"]
        return updates
    except Exception as e:
        print(f"  [getUpdates error] {e}")
        return []

# ─── PAGE FETCH ───────────────────────────────────────────────

def fetch_page() -> str | None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    try:
        r = requests.get(URL, headers=headers, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  [Fetch error] {e}")
        return None

# ─── PARSERS ──────────────────────────────────────────────────

def parse_restock_timestamps(html: str) -> dict[str, int]:
    pattern = re.compile(
        r'startCountdown\(\s*"([^"]+_ts)"\s*,\s*(\d+)\s*,\s*"[^"]*"\s*\)'
    )
    return {
        m.group(1).replace("_ts", ""): int(m.group(2))
        for m in pattern.finditer(html)
    }


def parse_weather(html: str) -> list[dict]:
    soup     = BeautifulSoup(html, "html.parser")
    weathers = []
    section  = soup.find("section", attrs={"aria-label": "Weather Info"})
    if not section:
        return weathers

    for div in section.find_all("div", id=re.compile(r"^weather_\d+$")):
        name = None
        for span in div.find_all("span", recursive=False):
            text = span.get_text(strip=True)
            if text and text != "●":
                name = text
                break
        if not name:
            for span in div.find_all("span"):
                text = span.get_text(strip=True)
                if text and text != "●":
                    name = text
                    break
        if not name:
            continue
        weathers.append({"name": name})

    return weathers


def is_excluded_event_item(name: str) -> bool:
    return any(kw in name.lower() for kw in EXCLUDED_EVENT_KEYWORDS)


def parse_stock(html: str) -> dict:
    soup   = BeautifulSoup(html, "html.parser")
    result = {}

    for article in soup.find_all("article", attrs={"aria-label": True}):
        section = article["aria-label"]

        if section == "Seeds Stock":
            sub_items   = {"Daily Deals": [], "Shop": []}
            current_sub = None
            for tag in article.find_all(["h3", "li"]):
                if tag.name == "h3":
                    label = tag.get_text(strip=True).lower()
                    current_sub = "Daily Deals" if "daily" in label else "Shop" if "shop" in label else None
                    continue
                if tag.name == "li" and current_sub:
                    name_tag = tag.find("span", class_=lambda c: c and "text-[15px]" in c and "break-words" in c)
                    qty_tag  = tag.find("span", class_=lambda c: c and "text-[13px]" in c and "whitespace-nowrap" in c)
                    if not name_tag:
                        continue
                    name = name_tag.get_text(strip=True)
                    if not name or name.lower() in EXCLUDED_ITEMS:
                        continue
                    qty = 0
                    if qty_tag:
                        try:
                            qty = int(qty_tag.get_text(strip=True).replace("Qty:", "").strip())
                        except ValueError:
                            qty = 1
                    sub_items[current_sub].append({"name": name, "qty": qty})
            result[section] = sub_items
            continue

        items = []
        for li in article.find_all("li"):
            name_tag = li.find("span", class_=lambda c: c and "text-[15px]" in c and "break-words" in c)
            qty_tag  = li.find("span", class_=lambda c: c and "text-[13px]" in c and "whitespace-nowrap" in c)
            if not name_tag:
                continue
            name = name_tag.get_text(strip=True)
            if not name or name == "No accepted plants right now.":
                continue
            if name.lower() in EXCLUDED_ITEMS:
                continue
            if section == "Event Stock" and is_excluded_event_item(name):
                continue
            qty = 0
            if qty_tag:
                try:
                    qty = int(qty_tag.get_text(strip=True).replace("Qty:", "").strip())
                except ValueError:
                    qty = 1
            items.append({"name": name, "qty": qty})
        result[section] = items

    return result

# ─── FORMATTING ───────────────────────────────────────────────

def format_time_until(ts: int) -> str:
    diff = int(ts - time.time())
    if diff <= 0:
        return "now"
    m, s = divmod(diff, 60)
    return f"{m}m {s}s" if m else f"{s}s"


def now_sgt() -> str:
    return datetime.now(TZ_SGT).strftime("%H:%M")


def build_item_lines(items: list[dict], watched: list[str]) -> list[str]:
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
    header: str = None,   # optional override for the first line
) -> str:
    emoji    = SECTION_EMOJI.get(section, "📦")
    next_str = format_time_until(next_restock_ts) if next_restock_ts else "unknown"

    lines = []
    lines.append(header or f"{emoji} <b>{section}</b> — restocked at {now_sgt()} (GMT+8)")
    lines.append(f"⏱ Next restock in: <b>{next_str}</b>")

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
    """
    new_weathers: just-appeared weathers (triggers the alert)
    all_weathers: every currently active weather (shown in the message)
    """
    display = all_weathers if all_weathers else new_weathers
    new_names = {w["name"] for w in new_weathers}
    lines = [f"🌦 <b>Weather Alert!</b> — {now_sgt()} (GMT+8)", ""]
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

# ─── COMMAND HANDLERS ─────────────────────────────────────────

def handle_watchlist(chat_id: str):
    lines = ["📋 <b>Current Watchlist</b>", ""]
    for i, item in enumerate(WATCHED_ITEMS, 1):
        lines.append(f"  {i}. {item}")
    lines.append("")
    lines.append(f"<i>{len(WATCHED_ITEMS)} items watched</i>")
    send_telegram("\n".join(lines), chat_id)


def handle_weather(chat_id: str):
    """Reply with all currently active weathers, or a clear-sky message if none."""
    with cache_lock:
        html_age = time.time() - cached_at

    # Fetch fresh if cache is older than 60s (weather changes fast)
    if html_age > 60 or not cached_at:
        html = fetch_page()
        if not html:
            send_telegram("❌ Could not reach the stock page. Try again shortly.", chat_id)
            return
    else:
        # Re-fetch since we don't cache raw html, only parsed stock
        html = fetch_page()
        if not html:
            send_telegram("❌ Could not reach the stock page. Try again shortly.", chat_id)
            return

    weathers = parse_weather(html)
    msg      = build_current_weather_message(weathers)
    send_telegram(msg, chat_id)


def handle_stock(chat_id: str):
    with cache_lock:
        stock      = dict(cached_stock)
        timestamps = dict(cached_timestamps)
        fetched_at = cached_at

    # If cache is stale (>10 min) or empty, fetch fresh
    if not stock or time.time() - fetched_at > 600:
        send_telegram("⏳ Fetching latest stock...", chat_id)
        html = fetch_page()
        if not html:
            send_telegram("❌ Could not reach the stock page. Try again shortly.", chat_id)
            return
        stock      = parse_stock(html)
        timestamps = parse_restock_timestamps(html)

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
        time.sleep(0.4)  # avoid hitting Telegram rate limit

# ─── COMMAND POLLING LOOP (runs in background thread) ─────────

def command_listener():
    """
    Runs in a separate thread. Polls Telegram for new messages
    every 2 seconds and dispatches /stock and /watchlist commands.
    Only responds to messages from known CHAT_IDS.
    """
    print("  💬 Command listener started.")
    allowed = set(str(c) for c in CHAT_IDS if c)

    while True:
        try:
            updates = get_updates()
            for update in updates:
                msg = update.get("message") or update.get("edited_message")
                if not msg:
                    continue

                chat_id = str(msg["chat"]["id"])
                text    = msg.get("text", "").strip().lower()

                # Only respond to known chat IDs
                if chat_id not in allowed:
                    continue

                if text.startswith("/stock"):
                    print(f"  💬 /stock requested by {chat_id}")
                    threading.Thread(target=handle_stock, args=(chat_id,), daemon=True).start()

                elif text.startswith("/watchlist"):
                    print(f"  💬 /watchlist requested by {chat_id}")
                    handle_watchlist(chat_id)

                elif text.startswith("/weather"):
                    print(f"  💬 /weather requested by {chat_id}")
                    threading.Thread(target=handle_weather, args=(chat_id,), daemon=True).start()

        except Exception as e:
            print(f"  [command_listener error] {e}")

        time.sleep(2)

# ─── SECTION / WEATHER LOGIC ──────────────────────────────────

def should_send_for_section(section: str, ts_key: str, timestamps: dict[str, int]) -> bool:
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
        # Pass all active weathers so message shows the full picture
        msg = build_weather_message(new_weathers, all_weathers=weathers)
        send_telegram(msg)
        print(f"  🌦  Weather alert: {[w['name'] for w in new_weathers]} (active: {list(current_names)})")
    last_weather_names = current_names


def next_wakeup(timestamps: dict[str, int]) -> float:
    now          = time.time()
    future       = [ts for ts in timestamps.values() if ts > now]
    next_restock = (max(0, min(future) - now) + BUFFER_SECONDS) if future else FALLBACK_POLL
    next_weather = max(0, WEATHER_POLL - (now - last_weather_poll))
    return min(next_restock, next_weather)

# ─── MAIN LOOP ────────────────────────────────────────────────

def main():
    global last_weather_poll, cached_stock, cached_timestamps, cached_at

    print("🌱 Grow a Garden Telegram Bot started!")
    print(f"   Watching: {WATCHED_ITEMS}\n")

    # Start command listener in background
    threading.Thread(target=command_listener, daemon=True).start()

    send_telegram(
        "🌱 <b>Grow a Garden Bot is online!</b>\n\n"
        f"Watching for: {', '.join(WATCHED_ITEMS)}\n\n"
        "You'll get a message per shop every time it restocks,\n"
        "plus weather alerts whenever new weather appears!\n\n"
        "📋 /watchlist — see watched items\n"
        "📦 /stock — get current stock now\n"
        "🌦 /weather — check current weather\n"
        "🌸"
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

        # Update shared cache for /stock command
        with cache_lock:
            cached_stock      = stock
            cached_timestamps = timestamps
            cached_at         = time.time()

        # ── Stock section checks ──────────────────────────────
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
            print(f"  — No sections restocked this cycle.")

        # ── Weather check ─────────────────────────────────────
        if time.time() - last_weather_poll >= WEATHER_POLL:
            check_weather(html)
            last_weather_poll = time.time()

        wait    = next_wakeup(timestamps)
        wake_at = datetime.fromtimestamp(time.time() + wait, TZ_SGT).strftime("%H:%M:%S")
        print(f"  💤 Sleeping {wait:.0f}s — next check at {wake_at} SGT\n")
        time.sleep(wait)


if __name__ == "__main__":
    main()