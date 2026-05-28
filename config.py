from dotenv import load_dotenv
from datetime import timezone, timedelta
import os

load_dotenv()

# ─── Telegram ─────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_IDS  = [os.getenv("CHAT_ID1"), os.getenv("CHAT_ID2")]

# ─── Excluded ───────────────────────────────────────

EXCLUDED_ITEMS = {
    "broccoli",
    "potato",
}

EXCLUDED_EVENT_KEYWORDS = [
    "easter",
    "chocolate",
    "gummy",
]

# ─── Timing ───────────────────────────────────────────────────
BUFFER_SECONDS = 5
FALLBACK_POLL  = 300
WEATHER_POLL   = 30
TZ_SGT         = timezone(timedelta(hours=8))  # GMT+8

# ─── Site ─────────────────────────────────────────────────────
URL = "https://www.growagardenstocknow.com/"

# ─── Shop sections ────────────────────────────────────────────
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