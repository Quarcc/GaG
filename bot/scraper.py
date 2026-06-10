import re
import asyncio
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
from config import URL, EXCLUDED_ITEMS, EXCLUDED_EVENT_KEYWORDS


def fetch_page() -> str | None:
    """
    Fetches the page HTML using a real headless Chromium browser.
    Handles Cloudflare / captcha protection that blocks requests/urllib.
    Returns raw HTML string or None on failure.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            page = context.new_page()

            # Block images, fonts, media — we only need HTML
            page.route("**/*", lambda route: route.abort()
                if route.request.resource_type in ["image", "media", "font", "stylesheet"]
                else route.continue_()
            )

            page.goto(URL, wait_until="domcontentloaded", timeout=30000)

            # Wait until at least one stock article is visible
            page.wait_for_selector("article[aria-label]", timeout=15000)

            html = page.content()
            browser.close()
            return html

    except PlaywrightTimeout:
        print("  [Fetch error] Page load timed out.")
        return None
    except Exception as e:
        print(f"  [Fetch error] {e}")
        return None


def parse_weather(html: str) -> list[dict]:
    """
    Parses all active weather entries from the Weather Info section.
    Returns: [{"name": "🌧️ Rain"}, ...]
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