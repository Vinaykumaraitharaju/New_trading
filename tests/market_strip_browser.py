"""Check actual demo rendering and independent polling. Set WORKSPACE_URL to a local preview."""
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    base = os.getenv("WORKSPACE_URL", "http://127.0.0.1:8081")
    out = Path("docs/workspace")
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=os.getenv("BROWSER_CHANNEL", "msedge"))
        for width in (1366, 390):
            page = browser.new_page(viewport={"width": width, "height": 880})
            page.goto(base + "/demo", wait_until="domcontentloaded")
            expect(page.locator("#scanActivity")).to_contain_text("symbols", timeout=60000)
            expect(page.locator(".index-quote .badge")).to_have_text(["simulated"]*3, timeout=60000)
            boxes = [tile.bounding_box() for tile in page.locator(".index-quote").all()]
            if width == 390:
                assert boxes[0]["y"] < boxes[1]["y"] < boxes[2]["y"]
            else:
                assert boxes[0]["y"] == boxes[1]["y"] == boxes[2]["y"]
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=out/f"market-strip-{width}.png")
            requests = []
            page.on("request", lambda r: requests.append(r.url))
            page.evaluate("async () => {await updateStrip(); await updateStrip()}")
            assert requests and all("/market-strip" in url for url in requests), requests
            before = page.locator("#content").inner_text()
            page.route("**/api/demo/market-strip",lambda route:route.abort())
            page.evaluate("updateStrip()")
            expect(page.locator("#cashSession")).to_contain_text("unavailable")
            assert page.locator("#content").inner_text() == before
            page.goto(base + "/demo/history")
            expect(page.locator("#title")).to_have_text("Research history")
            expect(page.locator("#marketStrip")).to_be_hidden()
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
