"""
Run this and paste the full output here so we can see exactly
what the HTML contains around the weather section.

    pip install requests beautifulsoup4
    python weather_debug.py
"""

import requests
import re
from bs4 import BeautifulSoup

URL = "https://www.growagardenstocknow.com/"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Cache-Control": "no-cache",
}

print("Fetching page...")
r = requests.get(URL, headers=headers, timeout=15)
print(f"HTTP {r.status_code} — {len(r.text):,} bytes\n")

soup = BeautifulSoup(r.text, "html.parser")

# ── 1. Find the weather section ───────────────────────────────
section = soup.find("section", attrs={"aria-label": "Weather Info"})
print(f"Weather section found: {section is not None}")
if not section:
    print("STOP — no Weather Info section in the HTML.")
    exit()

# ── 2. Print raw HTML of the weather section ──────────────────
print("\n--- RAW WEATHER SECTION HTML ---")
print(section.prettify()[:3000])  # first 3000 chars is enough
print("--- END ---\n")

# ── 3. Find all weather_N divs ────────────────────────────────
divs = section.find_all("div", id=re.compile(r"^weather_\d+$"))
print(f"weather_N divs found: {len(divs)}")
for div in divs:
    print(f"\n  div id: {div['id']}")

    # All spans directly inside
    direct_spans = div.find_all("span", recursive=False)
    print(f"  direct child spans: {len(direct_spans)}")
    for s in direct_spans:
        print(f"    span id={s.get('id','—')}  text={repr(s.get_text(strip=True)[:80])}")

    # All spans anywhere inside
    all_spans = div.find_all("span")
    print(f"  all nested spans: {len(all_spans)}")
    for s in all_spans:
        print(f"    span id={s.get('id','—')}  text={repr(s.get_text(strip=True)[:80])}")