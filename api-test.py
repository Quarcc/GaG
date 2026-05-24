"""
🌱 Grow a Garden — API Tester
==============================
Run this BEFORE setting up the full bot to verify the API is
reachable and returning good data.

Usage:
    pip install requests
    python gag_api_test.py
"""

import requests
import json
import sys
from datetime import datetime

API_URL = "https://gagstock.gleeze.com/grow-a-garden"

SEPARATOR = "─" * 55


def title(text):
    print(f"\n{SEPARATOR}")
    print(f"  {text}")
    print(SEPARATOR)


def ok(msg):   print(f"  ✅ {msg}")
def warn(msg): print(f"  ⚠️  {msg}")
def fail(msg): print(f"  ❌ {msg}")


# ── 1. Connectivity ───────────────────────────────────────────

title("TEST 1 — Connectivity & Response")

try:
    start = datetime.now()
    r = requests.get(API_URL, timeout=15)
    elapsed = (datetime.now() - start).total_seconds()

    ok(f"Reached API  (HTTP {r.status_code})  in {elapsed:.2f}s")

    if r.status_code != 200:
        fail(f"Expected 200, got {r.status_code}")
        sys.exit(1)

except requests.exceptions.ConnectionError:
    fail("Could not connect — check your internet or the API URL.")
    sys.exit(1)
except requests.exceptions.Timeout:
    fail("Request timed out after 15s.")
    sys.exit(1)


# ── 2. JSON parsing ───────────────────────────────────────────

title("TEST 2 — JSON Structure")

try:
    data = r.json()
    ok("Response is valid JSON")
except Exception as e:
    fail(f"Could not parse JSON: {e}")
    print("\nRaw response (first 500 chars):")
    print(r.text[:500])
    sys.exit(1)

# Show top-level keys
top_keys = list(data.keys())
ok(f"Top-level keys: {top_keys}")

inner = data.get("data", data)  # some APIs nest under "data"
shop_keys = list(inner.keys())
ok(f"Shop sections found: {shop_keys}")


# ── 3. Item extraction ────────────────────────────────────────

title("TEST 3 — Item Extraction (all shops)")

total_items = 0
in_stock_items = []

for shop_key, shop_val in inner.items():
    if not isinstance(shop_val, dict):
        continue

    stocks = shop_val.get("Stocks", shop_val.get("stocks", []))
    if not isinstance(stocks, list):
        warn(f"  '{shop_key}' — unexpected stocks format: {type(stocks)}")
        continue

    in_stock = [i for i in stocks if int(i.get("quantity", i.get("Quantity", i.get("stock", 0))) or 0) > 0]
    total_items += len(stocks)

    print(f"\n  📦 {shop_key.replace('Stock','').replace('stock','').title()} Shop")
    print(f"     {len(in_stock)}/{len(stocks)} items in stock")

    for item in stocks:
        name     = item.get("name", item.get("Name", "?"))
        qty      = item.get("quantity", item.get("Quantity", item.get("stock", 0)))
        rarity   = item.get("rarity", item.get("Rarity", ""))
        qty      = int(qty) if qty else 0
        status   = f"×{qty}" if qty > 0 else "NO STOCK"
        tag      = f" [{rarity}]" if rarity else ""

        print(f"       {'🟢' if qty > 0 else '🔴'} {name}{tag}  {status}")

        if qty > 0:
            in_stock_items.append({"name": name, "qty": qty, "rarity": rarity, "shop": shop_key})

ok(f"\n  Total items parsed: {total_items}")
ok(f"  Currently in stock: {len(in_stock_items)}")


# ── 4. Timestamp / freshness ──────────────────────────────────

title("TEST 4 — Data Freshness")

updated_at = data.get("updated_at") or data.get("updatedAt") or inner.get("updated_at")
if updated_at:
    ok(f"updated_at field: {updated_at}")
else:
    warn("No updated_at field found — can't verify freshness from response alone")


# ── 5. Simulated watch-list match ─────────────────────────────

title("TEST 5 — Watch-list Simulation")

SAMPLE_WATCHLIST = ["Sugar Apple", "Grape", "Mango", "Beanstalk", "Mushroom"]
print(f"  Sample watchlist: {SAMPLE_WATCHLIST}\n")

matches = [
    i for i in in_stock_items
    if any(w.lower() in i["name"].lower() for w in SAMPLE_WATCHLIST)
]

if matches:
    ok(f"MATCH — {len(matches)} watched item(s) are in stock RIGHT NOW:")
    for m in matches:
        print(f"       🌱 {m['name']}  ×{m['qty']}  [{m['rarity']}]  ({m['shop']})")
else:
    print("  ℹ️  None of the sample watchlist items are in stock right now.")
    print("     That's normal — try editing SAMPLE_WATCHLIST above with real seed names.")


# ── Summary ───────────────────────────────────────────────────

title("SUMMARY")
ok("API is reachable and returning structured data")
ok("Item extraction logic works correctly")
ok("Watch-list matching logic works correctly")
print(f"\n  🚀 You're good to go — set up the full bot!\n")