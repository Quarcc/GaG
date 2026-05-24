"""
🌱 Grow a Garden — Telegram Notification Bot
=============================================
Sends a separate Telegram message per shop section each time
that section's restock timer expires. Also monitors weather
and alerts when a new weather event appears.

SETUP
-----
1. pip install requests beautifulsoup4 python-dotenv
2. Create bot via @BotFather → copy token
3. Get chat ID via https://api.telegram.org/bot<TOKEN>/getUpdates
4. Fill in .env with BOT_TOKEN, CHAT_ID1, CHAT_ID2
5. Run: python main.py
"""

import time
import re
import requests
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

# Items to always hide — removed from game or unwanted
EXCLUDED_ITEMS = {
    "broccoli",
    "potato",
}

# Event items to filter out by keyword (case-insensitive)
EXCLUDED_EVENT_KEYWORDS = [
    "easter",
    "chocolate",
]

URL            = "https://www.growagardenstocknow.com/"
BUFFER_SECONDS = 5
FALLBACK_POLL  = 300
WEATHER_POLL   = 60   # check weather every 60s
TZ_SGT         = timezone(timedelta(hours=8))  # GMT+8

# Seeds are now ONE combined message, split internally by header
SECTION_TIMESTAMP_MAP = {
    "Seeds Stock":   "seeds",
    "Gear Stock":    "gear",
    "Egg Stock":     "egg",
    "Event Stock":   "event",
    "Merchant Stock":"merchant",
}

SECTION_EMOJI = {
    "Seeds Stock":    "🌱",
    "Gear Stock":     "🛠️",
    "Egg Stock":      "🥚",
    "Event Stock":    "🎪",
    "Merchant Stock": "🛒",
}

WEATHER_EMOJI = {
    "gentledrizzle":  "🌦️",
    "rain":           "🌧️",
    "thunderstorm":   "⛈️",
    "sunshower":      "🌈",
    "bloodmoon":      "🌕",
    "jelly":          "🪼",
    "meteor":         "☄️",
    "windy":          "🌬️",
    "frost":          "❄️",
    "fog":            "🌫️",
    "heatwave":       "🌡️",
    "snow":           "🌨️",
    "sandstorm":      "🌪️",
}

def get_weather_emoji(name: str) -> str:
    key = name.lower().replace(" ", "")
    for k, v in WEATHER_EMOJI.items():
        if k in key:
            return v
    return "🌤️"

# ─── STATE ────────────────────────────────────────────────────
section_state: dict[str, dict] = {}
last_weather_names: set[str]   = set()   # tracks active weathers
last_weather_poll:  float       = 0.0

# ─── TELEGRAM ─────────────────────────────────────────────────

def send_telegram(message: str):
    for chat_id in CHAT_IDS:
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                timeout=10
            ).raise_for_status()
        except Exception as e:
            print(f"  [Telegram error] {e}")

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
    """
    Parses weather entries from the Weather Info section.
    Each entry: { name, countdown }
    Looks for div[id^="weather_"] containing the name span and countdown span.
    Skips entries where countdown text is "ended".
    """
    soup    = BeautifulSoup(html, "html.parser")
    weathers = []

    section = soup.find("section", attrs={"aria-label": "Weather Info"})
    if not section:
        return weathers

    # Each weather row: <div id="weather_1" ...>
    for div in section.find_all("div", id=re.compile(r"^weather_\d+$")):
        # Name is the last <span> directly in this div (after the dot span)
        spans = div.find_all("span", recursive=False)
        name  = None
        for span in spans:
            text = span.get_text(strip=True)
            if text and text != "●":
                name = text
                break

        # Fallback: any span that isn't the dot
        if not name:
            for span in div.find_all("span"):
                text = span.get_text(strip=True)
                if text and text != "●":
                    name = text
                    break

        if not name:
            continue

        # Countdown: <span id="weather_countdown_N">
        #   contains a nested <span>Ends in: 1m 15s</span>
        idx           = div["id"].split("_")[-1]
        countdown_tag = section.find("span", id=f"weather_countdown_{idx}")
        countdown     = ""
        if countdown_tag:
            # Grab all text inside including nested spans
            full_text = countdown_tag.get_text(separator=" ", strip=True)
            # Skip ended weathers
            if "ended" in full_text.lower():
                continue
            # Strip the "Ends in:" prefix if present, keep just the time
            countdown = re.sub(r"(?i)ends\s*in\s*:?\s*", "", full_text).strip()

        weathers.append({"name": name, "countdown": countdown})


    return weathers


def is_excluded_event_item(name: str) -> bool:
    name_lower = name.lower()
    return any(kw in name_lower for kw in EXCLUDED_EVENT_KEYWORDS)


def parse_stock(html: str) -> dict[str, list | dict]:
    """
    Returns stock dict.
    Seeds Stock value is a dict: {"Daily Deals": [...], "Shop": [...]}
    All other sections return a plain list.
    """
    soup   = BeautifulSoup(html, "html.parser")
    result = {}

    for article in soup.find_all("article", attrs={"aria-label": True}):
        section = article["aria-label"]

        # ── Seeds Stock: split by h3 subheaders ──────────────
        if section == "Seeds Stock":
            sub_items: dict[str, list] = {"Daily Deals": [], "Shop": []}
            current_sub = None

            for tag in article.find_all(["h3", "li"]):
                if tag.name == "h3":
                    label = tag.get_text(strip=True).lower()
                    if "daily" in label:
                        current_sub = "Daily Deals"
                    elif "shop" in label:
                        current_sub = "Shop"
                    else:
                        current_sub = None
                    continue

                if tag.name == "li" and current_sub:
                    name_tag = tag.find(
                        "span",
                        class_=lambda c: c and "text-[15px]" in c and "break-words" in c
                    )
                    qty_tag = tag.find(
                        "span",
                        class_=lambda c: c and "text-[13px]" in c and "whitespace-nowrap" in c
                    )
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

        # ── All other sections ────────────────────────────────
        items = []
        for li in article.find_all("li"):
            name_tag = li.find(
                "span",
                class_=lambda c: c and "text-[15px]" in c and "break-words" in c
            )
            qty_tag = li.find(
                "span",
                class_=lambda c: c and "text-[13px]" in c and "whitespace-nowrap" in c
            )
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
    """Returns formatted item lines with ⭐ for watched."""
    lines = []
    for i in items:
        marker = "⭐" if any(w.lower() == i["name"].lower() for w in watched) else "  "
        lines.append(f"   {marker} {i['name']}  ×{i['qty']}")
    return lines


def build_section_message(
    section: str,
    stock_value,           # list[dict] or dict{"Daily Deals":[], "Shop":[]}
    watched: list[str],
    next_restock_ts: int | None,
) -> str:
    emoji    = SECTION_EMOJI.get(section, "📦")
    next_str = format_time_until(next_restock_ts) if next_restock_ts else "unknown"

    lines = []
    lines.append(f"{emoji} <b>{section}</b> — restocked at {now_sgt()} (GMT+8)")
    lines.append(f"⏱ Next restock in: <b>{next_str}</b>")

    # ── Seeds: combined message with two subsections ──────────
    if isinstance(stock_value, dict):
        all_items = stock_value.get("Daily Deals", []) + stock_value.get("Shop", [])

        # Watched hits across both subsections
        watched_hits = [
            i for i in all_items
            if any(w.lower() == i["name"].lower() for w in watched)
        ]
        if watched_hits:
            lines.append("")
            lines.append("✨ <b>Watched items in stock:</b>")
            for i in watched_hits:
                lines.append(f"   • {i['name']}  ×{i['qty']}")

        # Daily Deals subsection
        daily = stock_value.get("Daily Deals", [])
        lines.append("")
        lines.append("💥 <b>Daily Deals:</b>")
        if daily:
            lines.extend(build_item_lines(daily, watched))
        else:
            lines.append("   <i>(none)</i>")

        # Shop subsection
        shop = stock_value.get("Shop", [])
        lines.append("")
        lines.append("🏪 <b>Shop:</b>")
        if shop:
            lines.extend(build_item_lines(shop, watched))
        else:
            lines.append("   <i>(none)</i>")

    # ── All other sections: flat list ─────────────────────────
    else:
        items = stock_value
        watched_hits = [
            i for i in items
            if any(w.lower() == i["name"].lower() for w in watched)
        ]
        if watched_hits:
            lines.append("")
            lines.append("✨ <b>Watched items in stock:</b>")
            for i in watched_hits:
                lines.append(f"   • {i['name']}  ×{i['qty']}")

        lines.append("")
        lines.append("📦 <b>All items:</b>")
        if items:
            lines.extend(build_item_lines(items, watched))
        else:
            lines.append("   <i>(nothing in stock)</i>")

    return "\n".join(lines)


def build_weather_message(new_weathers: list[dict]) -> str:
    lines = []
    lines.append(f"🌤️ <b>Weather Update</b> — {now_sgt()} (GMT+8)")
    lines.append("")
    for w in new_weathers:
        emoji = get_weather_emoji(w["name"])
        cd    = f"  ⏳ {w['countdown']}" if w["countdown"] else ""
        lines.append(f"  {emoji} <b>{w['name']}</b>{cd}")
    return "\n".join(lines)

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
    """
    Compares current weather names to the last known set.
    Sends a message only for newly appearing weathers.
    """
    global last_weather_names

    weathers     = parse_weather(html)
    current_names = {w["name"] for w in weathers}
    new_weathers  = [w for w in weathers if w["name"] not in last_weather_names]

    if new_weathers:
        msg = build_weather_message(new_weathers)
        send_telegram(msg)
        print(f"  🌤️  Weather alert: {[w['name'] for w in new_weathers]}")

    last_weather_names = current_names


def next_wakeup(timestamps: dict[str, int]) -> float:
    now    = time.time()
    future = [ts for ts in timestamps.values() if ts > now]
    if not future:
        return FALLBACK_POLL
    # Wake up at the sooner of: next restock OR next weather poll
    next_restock = max(0, min(future) - now) + BUFFER_SECONDS
    next_weather = max(0, WEATHER_POLL - (now - last_weather_poll))
    return min(next_restock, next_weather)

# ─── MAIN LOOP ────────────────────────────────────────────────

def main():
    global last_weather_poll

    print("🌱 Grow a Garden Telegram Bot started!")
    print(f"   Watching: {WATCHED_ITEMS}\n")

    send_telegram(
        "🌱 <b>Grow a Garden Bot is online!</b>\n\n"
        f"Watching for: {', '.join(WATCHED_ITEMS)}\n\n"
        "You'll get a message per shop every time it restocks,\n"
        "plus weather alerts whenever new weather appears! 🌸"
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

        # ── Weather check (every WEATHER_POLL seconds) ────────
        if time.time() - last_weather_poll >= WEATHER_POLL:
            check_weather(html)
            last_weather_poll = time.time()

        wait    = next_wakeup(timestamps)
        wake_at = datetime.fromtimestamp(time.time() + wait, TZ_SGT).strftime("%H:%M:%S")
        print(f"  💤 Sleeping {wait:.0f}s — next check at {wake_at} SGT\n")
        time.sleep(wait)


if __name__ == "__main__":
    main()