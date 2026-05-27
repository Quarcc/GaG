import re
import requests
from bs4 import BeautifulSoup
from config import URL, EXCLUDED_ITEMS, EXCLUDED_EVENT_KEYWORDS


def fetch_page() -> str | None:
    """Download the page HTML. Returns raw text or None on failure."""
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


def parse_weather(html: str) -> list[dict]:
    """
    Parses all active weather entries from the Weather Info section.
    Returns: [{"name": "🌧️ Rain"}, ...]
    Name is taken directly from the page including any emoji.
    """
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
    """
    Parses all shop sections from the page HTML.
    Seeds Stock returns: {"Daily Deals": [...], "Shop": [...]}
    All other sections return: [{"name": ..., "qty": ...}, ...]
    """
    soup   = BeautifulSoup(html, "html.parser")
    result = {}

    for article in soup.find_all("article", attrs={"aria-label": True}):
        section = article["aria-label"]

        # ── Seeds Stock: split by h3 subheaders ──────────────
        if section == "Seeds Stock":
            sub_items   = {"Daily Deals": [], "Shop": []}
            current_sub = None
            for tag in article.find_all(["h3", "li"]):
                if tag.name == "h3":
                    label = tag.get_text(strip=True).lower()
                    current_sub = (
                        "Daily Deals" if "daily" in label else
                        "Shop"        if "shop"  in label else
                        None
                    )
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

        # ── All other sections ────────────────────────────────
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