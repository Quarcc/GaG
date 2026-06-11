"""
🌱 Debug Fetch — run this on Railway via the terminal
to see exactly what HTML the server is receiving.

    python debug_fetch.py
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from config import URL


def debug_fetch():
    print(f"Fetching: {URL}\n")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,800",
            ]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="Asia/Singapore",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        page = context.new_page()
        status_code = None

        # Capture the response status
        def on_response(response):
            nonlocal status_code
            if URL in response.url:
                status_code = response.status
                print(f"Response status: {response.status} — {response.url[:80]}")

        page.on("response", on_response)

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightTimeout:
            print("Timed out waiting for domcontentloaded.")

        html  = page.content()
        title = page.title()

        print(f"Page title: {title!r}")
        print(f"HTML length: {len(html):,} bytes")
        print()

        # Check what we actually got
        html_lower = html.lower()

        if "just a moment" in html_lower or "cf-browser-verification" in html_lower:
            print("❌ CLOUDFLARE CHALLENGE — Railway's IP is being challenged.")
            print("   The bot cannot bypass this without a residential proxy.")
        elif "access denied" in html_lower or "403" in title:
            print("❌ ACCESS DENIED — Cloudflare is blocking Railway's IP outright.")
        elif "article" in html_lower and "aria-label" in html_lower:
            print("✅ Page loaded correctly — stock articles are present!")
        else:
            print("⚠️  Page loaded but stock articles not found.")
            print("   Showing first 2000 chars of HTML:")
            print()
            print(html[:2000])

        browser.close()


if __name__ == "__main__":
    debug_fetch()