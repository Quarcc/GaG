"""
🌱 Grow a Garden — Telegram Notification Bot
=============================================
Scrapes growagardenstocknow.com every 5 minutes and sends
Telegram alerts when watched items are in stock.

SETUP
-----
1. pip install requests beautifulsoup4

2. Create a Telegram bot:
   - Message @BotFather → /newbot → copy the token

3. Get your chat ID:
   - Have her message the bot, then visit:
   - https://api.telegram.org/bot<TOKEN>/getUpdates
   - Find "chat": {"id": 123456789}

4. Edit WATCHED_ITEMS below with the exact names she wants

5. Run: python gag_telegram_bot.py
"""

import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────
BOT_TOKEN = "8901777057:AAH6D_UQ5y-6IluI0vx6GdJnWOBxfLVQjw4"
CHAT_ID   = "1845876445"

# Exact item names to watch (case-insensitive)
WATCHED_ITEMS = [
    "Sugar Apple",
    "Grape",
    "Mango",
    "Beanstalk",
    "Mushroom",
    "Carrot",
    "Common Egg",
    "Broccoli"
    # Add more here ↓
]

POLL_INTERVAL = 60  # seconds between checks (site refreshes every 5 min)
URL = "https://www.growagardenstocknow.com/"

# ─── STATE ────────────────────────────────────────────────────
# Tracks what we've already alerted so we don't spam every poll
already_notified: set[str] = set()

# ─── HELPERS ──────────────────────────────────────────────────

def send_telegram(message: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10
        ).raise_for_status()
    except Exception as e:
        print(f"[Telegram error] {e}")


def fetch_stock() -> dict[str, list[dict]]:
    """
    Scrapes the page and returns a dict like:
    {
      "Seeds Stock": [{"name": "Carrot", "qty": 3}, ...],
      "Gear Stock":  [...],
      ...
    }
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        r = requests.get(URL, headers=headers, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[Fetch error] {e}")
        return {}

    soup = BeautifulSoup(r.text, "html.parser")
    result = {}

    # Each shop is an <article aria-label="Seeds Stock"> etc.
    for article in soup.find_all("article", attrs={"aria-label": True}):
        section_name = article["aria-label"]  # e.g. "Seeds Stock"
        items = []

        for li in article.find_all("li"):
            # Name is in <span class="text-[15px] break-words text-left">
            name_tag = li.find("span", class_=lambda c: c and "text-[15px]" in c and "break-words" in c)
            # Qty is in <span class="text-[13px] whitespace-nowrap ...">Qty: N</span>
            qty_tag  = li.find("span", class_=lambda c: c and "text-[13px]" in c and "whitespace-nowrap" in c)

            if not name_tag:
                continue

            name = name_tag.get_text(strip=True)
            qty  = 0
            if qty_tag:
                qty_text = qty_tag.get_text(strip=True)  # "Qty: 3"
                try:
                    qty = int(qty_text.replace("Qty:", "").strip())
                except ValueError:
                    qty = 1  # present but unparseable = assume 1

            if name and name != "No accepted plants right now.":
                items.append({"name": name, "qty": qty})

        if items:
            result[section_name] = items

    return result


def check_and_notify(stock: dict[str, list[dict]]):
    global already_notified

    alerts = []
    current_in_stock: set[str] = set()

    for section, items in stock.items():
        for item in items:
            name = item["name"]
            qty  = item["qty"]
            current_in_stock.add(name)

            # Skip if we already notified for this restock cycle
            if name in already_notified:
                continue

            if any(w.lower() == name.lower() for w in WATCHED_ITEMS):
                alerts.append(
                    f"🌱 <b>{name}</b>  ×{qty}\n"
                    f"   Shop: {section}"
                )
                already_notified.add(name)

    # Clear notification memory for items no longer in stock
    # so we alert again when they reappear next restock
    already_notified &= current_in_stock

    if alerts:
        now = datetime.now().strftime("%H:%M:%S")
        msg = f"🌸 <b>Grow a Garden — Stock Alert!</b> ({now})\n\n" + "\n\n".join(alerts)
        send_telegram(msg)
        print(f"[{now}] ✅ Sent alert: {[a.split('<b>')[1].split('</b>')[0] for a in alerts]}")
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] No watched items in stock.")


# ─── MAIN ─────────────────────────────────────────────────────

def main():
    print("🌱 Grow a Garden Telegram Bot started!")
    print(f"   Watching: {WATCHED_ITEMS}")
    print(f"   Polling every {POLL_INTERVAL}s\n")

    send_telegram(
        "🌱 <b>Grow a Garden Bot is online!</b>\n\n"
        f"Watching for: {', '.join(WATCHED_ITEMS)}\n"
        "I'll ping you the moment they're in stock! 🌸"
    )

    while True:
        stock = fetch_stock()
        if stock:
            check_and_notify(stock)
        else:
            print("Could not fetch stock, retrying next cycle.")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()