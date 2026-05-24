"""
🌱 Grow a Garden — Telegram Notification Bot
=============================================
Sends a separate Telegram message per shop section each time
that section's restock timer expires. Each message includes
the full stock list and time until the next restock.

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
TZ_SGT         = timezone(timedelta(hours=8))  # GMT+8

SECTION_TIMESTAMP_MAP = {
    "Seeds Stock — Daily Deals": "seeds",
    "Seeds Stock — Shop":        "seeds",
    "Gear Stock":                "gear",
    "Egg Stock":                 "egg",
    "Event Stock":               "event",
    "Merchant Stock":            "merchant",
}

SECTION_EMOJI = {
    "Seeds Stock — Daily Deals": "💥",
    "Seeds Stock — Shop":        "🌱",
    "Gear Stock":                "🛠️",
    "Egg Stock":                 "🥚",
    "Event Stock":               "🎪",
    "Merchant Stock":            "🛒",
}

# ─── STATE ────────────────────────────────────────────────────
section_state: dict[str, dict] = {}

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


def is_excluded_event_item(name: str) -> bool:
    name_lower = name.lower()
    return any(kw in name_lower for kw in EXCLUDED_EVENT_KEYWORDS)


def parse_stock(html: str) -> dict[str, list[dict]]:
    """
    Returns stock dict. Seeds Stock is split into two keys:
      "Seeds Stock — Daily Deals"
      "Seeds Stock — Shop"
    Event items matching excluded keywords are dropped.
    Items in EXCLUDED_ITEMS are dropped globally.
    """
    soup   = BeautifulSoup(html, "html.parser")
    result = {}

    for article in soup.find_all("article", attrs={"aria-label": True}):
        section = article["aria-label"]

        # ── Seeds Stock: split by h3 subheaders ──────────────
        if section == "Seeds Stock":
            current_sub = None
            sub_items: dict[str, list] = {
                "Seeds Stock — Daily Deals": [],
                "Seeds Stock — Shop":        [],
            }

            for tag in article.find_all(["h3", "li"]):
                if tag.name == "h3":
                    label = tag.get_text(strip=True).lower()
                    if "daily" in label:
                        current_sub = "Seeds Stock — Daily Deals"
                    elif "shop" in label:
                        current_sub = "Seeds Stock — Shop"
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

            for key, items in sub_items.items():
                result[key] = items
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
    """Current time formatted in GMT+8."""
    return datetime.now(TZ_SGT).strftime("%H:%M")


def build_section_message(
    section: str,
    items: list[dict],
    watched: list[str],
    next_restock_ts: int | None,
) -> str:
    emoji    = SECTION_EMOJI.get(section, "📦")
    next_str = format_time_until(next_restock_ts) if next_restock_ts else "unknown"

    lines = []
    lines.append(f"{emoji} <b>{section}</b> — restocked at {now_sgt()} (GMT+8)")
    lines.append(f"⏱ Next restock in: <b>{next_str}</b>")

    watched_hits = [
        i for i in items
        if any(w.lower() == i["name"].lower() for w in watched)
    ]
    if watched_hits:
        lines.append("")
        lines.append("✨ <b>Watched items in stock:</b>")
        for i in watched_hits:
            lines.append(f"   • {i['name']}  ×{i['qty']}")

    if items:
        lines.append("")
        lines.append("📦 <b>All items:</b>")
        for i in items:
            marker = "⭐" if any(w.lower() == i["name"].lower() for w in watched) else "  "
            lines.append(f"   {marker} {i['name']}  ×{i['qty']}")
    else:
        lines.append("")
        lines.append("   <i>(nothing in stock)</i>")

    return "\n".join(lines)

# ─── PER-SECTION LOGIC ────────────────────────────────────────

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


def next_wakeup(timestamps: dict[str, int]) -> float:
    now    = time.time()
    future = [ts for ts in timestamps.values() if ts > now]
    if not future:
        return FALLBACK_POLL
    return max(0, min(future) - now) + BUFFER_SECONDS

# ─── MAIN LOOP ────────────────────────────────────────────────

def main():
    print("🌱 Grow a Garden Telegram Bot started!")
    print(f"   Watching: {WATCHED_ITEMS}\n")

    send_telegram(
        "🌱 <b>Grow a Garden Bot is online!</b>\n\n"
        f"Watching for: {', '.join(WATCHED_ITEMS)}\n\n"
        "You'll get a message per shop every time it restocks,\n"
        "with the full stock list and time until next refresh. 🌸"
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

        sent_count = 0
        for section, ts_key in SECTION_TIMESTAMP_MAP.items():
            if section not in stock:
                continue

            if should_send_for_section(section, ts_key, timestamps):
                next_ts = timestamps.get(ts_key)
                items   = stock[section]
                msg     = build_section_message(section, items, WATCHED_ITEMS, next_ts)
                send_telegram(msg)
                print(f"  📨 Sent: {section} ({len(items)} items)")
                sent_count += 1
                time.sleep(0.5)

        if sent_count == 0:
            print(f"  — No sections restocked this cycle.")

        wait    = next_wakeup(timestamps)
        wake_at = datetime.fromtimestamp(time.time() + wait, TZ_SGT).strftime("%H:%M:%S")
        print(f"  💤 Sleeping {wait:.0f}s — next check at {wake_at} SGT\n")
        time.sleep(wait)


if __name__ == "__main__":
    main()