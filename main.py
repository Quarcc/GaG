"""
🌱 Grow a Garden — Telegram Notification Bot
=============================================
Sends a separate Telegram message per shop section each time
that section's restock timer expires. Each message includes
the full stock list and time until the next restock.

SETUP
-----
1. pip install requests beautifulsoup4
2. Create bot via @BotFather → copy token
3. Get chat ID via https://api.telegram.org/bot<TOKEN>/getUpdates
4. Fill in BOT_TOKEN, CHAT_ID, and WATCHED_ITEMS below
5. Run: python main.py
"""

import time
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv
import os

# ─── CONFIG ───────────────────────────────────────────────────
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_IDS   = [os.getenv("CHAT_ID1"), os.getenv("CHAT_ID2")]

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

URL            = "https://www.growagardenstocknow.com/"
BUFFER_SECONDS = 5    # seconds after restock before we scrape
FALLBACK_POLL  = 300  # fallback if timestamps can't be parsed

# Maps the timestamp key from the page JS → the shop section aria-label
# e.g. "seeds" timestamp controls "Seeds Stock" and "Season Stock"
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
# Per-section: last stock snapshot and last notified set
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
    """
    Extracts Unix timestamps from inline JS:
      startCountdown("seeds_ts", 1779596400, "seeds_stock_status");
    Returns {"seeds": 1779596400, "gear": 1779596400, ...}
    """
    pattern = re.compile(
        r'startCountdown\(\s*"([^"]+_ts)"\s*,\s*(\d+)\s*,\s*"[^"]*"\s*\)'
    )
    return {
        m.group(1).replace("_ts", ""): int(m.group(2))
        for m in pattern.finditer(html)
    }


def parse_stock(html: str) -> dict[str, list[dict]]:
    """
    Returns {"Seeds Stock": [{"name": ..., "qty": ...}, ...], ...}
    """
    soup   = BeautifulSoup(html, "html.parser")
    result = {}

    for article in soup.find_all("article", attrs={"aria-label": True}):
        section = article["aria-label"]
        items   = []

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
            qty = 0
            if qty_tag:
                try:
                    qty = int(qty_tag.get_text(strip=True).replace("Qty:", "").strip())
                except ValueError:
                    qty = 1
            items.append({"name": name, "qty": qty})

        result[section] = items  # include empty sections too

    return result

# ─── FORMATTING ───────────────────────────────────────────────

def format_time_until(ts: int) -> str:
    """Returns '4m 32s' or 'now' from a Unix timestamp."""
    diff = int(ts - time.time())
    if diff <= 0:
        return "now"
    m, s = divmod(diff, 60)
    return f"{m}m {s}s" if m else f"{s}s"


def build_section_message(
    section: str,
    items: list[dict],
    watched: list[str],
    next_restock_ts: int | None,
) -> str:
    """
    Builds the full Telegram message for one shop section.

    Layout:
      🌱 Seeds Stock — restocked at 14:35
      ⏱ Next restock in: 4m 58s

      ✨ Watched items in stock:
         • Sugar Apple  ×1
         • Grape        ×2

      📦 All items:
         • Blueberry    ×3
         • Carrot       ×18
         ...
    """
    emoji       = SECTION_EMOJI.get(section, "📦")
    now_str     = datetime.now().strftime("%H:%M")
    next_str    = format_time_until(next_restock_ts) if next_restock_ts else "unknown"

    lines = []
    lines.append(f"{emoji} <b>{section}</b> — restocked at {now_str}")
    lines.append(f"⏱ Next restock in: <b>{next_str}</b>")

    # Watched items
    watched_hits = [
        i for i in items
        if any(w.lower() == i["name"].lower() for w in watched)
    ]
    if watched_hits:
        lines.append("")
        lines.append("✨ <b>Watched items in stock:</b>")
        for i in watched_hits:
            lines.append(f"   • {i['name']}  ×{i['qty']}")

    # All items
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
    """
    Returns True if this section's restock timer has just expired
    (i.e. the timestamp changed since last time we checked, or
    this is the first run).
    """
    current_ts = timestamps.get(ts_key)
    if current_ts is None:
        return False

    state = section_state.setdefault(section, {"last_ts": None})
    if state["last_ts"] is None:
        # First run — record timestamp but don't send (avoid spam on startup)
        state["last_ts"] = current_ts
        return False

    if current_ts != state["last_ts"]:
        # Timestamp changed → a new restock cycle started
        state["last_ts"] = current_ts
        return True

    return False


def next_wakeup(timestamps: dict[str, int]) -> float:
    """Sleep until the soonest upcoming restock + buffer."""
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
        now_str = datetime.now().strftime("%H:%M:%S")
        print(f"[{now_str}] Fetching page...")

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
                # Find the NEXT restock for this section (the new timestamp)
                next_ts = timestamps.get(ts_key)
                items   = stock[section]
                msg     = build_section_message(section, items, WATCHED_ITEMS, next_ts)
                send_telegram(msg)
                print(f"  📨 Sent: {section} ({len(items)} items)")
                sent_count += 1
                time.sleep(0.5)  # small delay between messages

        if sent_count == 0:
            print(f"  — No sections restocked this cycle.")

        wait    = next_wakeup(timestamps)
        wake_at = datetime.fromtimestamp(time.time() + wait).strftime("%H:%M:%S")
        print(f"  💤 Sleeping {wait:.0f}s — next check at {wake_at}\n")
        time.sleep(wait)


if __name__ == "__main__":
    main()