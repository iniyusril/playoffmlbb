from playwright.sync_api import sync_playwright

URL = "https://liquipedia.net/mobilelegends/MPL/Indonesia/Season_17/Regular_Season"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(3000)
    html = page.content()
    with open("liquipedia_page.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("WROTE", len(html))
    browser.close()
