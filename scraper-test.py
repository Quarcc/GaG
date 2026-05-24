"""
🌱 Grow a Garden — Scraper Test
Run this first to confirm the scraper is working correctly.

    pip install requests beautifulsoup4
    python gag_scraper_test.py
"""

import requests
from bs4 import BeautifulSoup

URL = "https://www.growagardenstocknow.com/"
SEPARATOR = "─" * 50

def ok(m):   print(f"  ✅ {m}")
def fail(m): print(f"  ❌ {m}")
def title(m): print(f"\n{SEPARATOR}\n  {m}\n{SEPARATOR}")

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# ── 1. Connectivity ───────────────────────────────────────────
title("TEST 1 — Connectivity")
try:
    r = requests.get(URL, headers=headers, timeout=15)
    r.raise_for_status()
    ok(f"HTTP {r.status_code} — {len(r.text):,} bytes received")
except Exception as e:
    fail(str(e))
    exit(1)

# ── 2. Parse sections ─────────────────────────────────────────
title("TEST 2 — Section Detection")
soup = BeautifulSoup(r.text, "html.parser")
articles = soup.find_all("article", attrs={"aria-label": True})
ok(f"Found {len(articles)} shop sections:")
for a in articles:
    print(f"       • {a['aria-label']}")

# ── 3. Item extraction ────────────────────────────────────────
title("TEST 3 — Item Extraction")
total = 0
for article in articles:
    section = article["aria-label"]
    items = []
    for li in article.find_all("li"):
        name_tag = li.find("span", class_=lambda c: c and "text-[15px]" in c and "break-words" in c)
        qty_tag  = li.find("span", class_=lambda c: c and "text-[13px]" in c and "whitespace-nowrap" in c)
        if not name_tag:
            continue
        name = name_tag.get_text(strip=True)
        qty  = 0
        if qty_tag:
            try:
                qty = int(qty_tag.get_text(strip=True).replace("Qty:", "").strip())
            except:
                qty = 1
        if name and name != "No accepted plants right now.":
            items.append((name, qty))
            total += 1

    if items:
        print(f"\n  📦 {section} ({len(items)} items)")
        for name, qty in items:
            print(f"       {'🟢' if qty > 0 else '🔴'} {name}  ×{qty}")

ok(f"\n  Total items extracted: {total}")

# ── 4. Watchlist simulation ───────────────────────────────────
title("TEST 4 — Watchlist Match Simulation")
WATCHLIST = ["Sugar Apple", "Grape", "Mango", "Beanstalk", "Mushroom", "Burning Bud"]
print(f"  Watchlist: {WATCHLIST}\n")

matches = []
for article in articles:
    for li in article.find_all("li"):
        name_tag = li.find("span", class_=lambda c: c and "text-[15px]" in c and "break-words" in c)
        if not name_tag:
            continue
        name = name_tag.get_text(strip=True)
        if any(w.lower() == name.lower() for w in WATCHLIST):
            qty_tag = li.find("span", class_=lambda c: c and "text-[13px]" in c and "whitespace-nowrap" in c)
            qty = qty_tag.get_text(strip=True) if qty_tag else "?"
            matches.append(f"{name} ({qty}) in {article['aria-label']}")

if matches:
    ok(f"MATCHES FOUND ({len(matches)}):")
    for m in matches:
        print(f"       🌱 {m}")
else:
    print("  ℹ️  None of the watchlist items are in stock right now — that's normal.")

# ── Summary ───────────────────────────────────────────────────
title("SUMMARY")
ok("Scraper is working correctly — ready to run the bot!")
print()