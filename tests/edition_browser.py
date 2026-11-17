"""Offline browser check of the timed-edition report using the actual workspace assets."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ASSETS = Path(__file__).resolve().parents[1]/"reaction_alpha/workspace_ui"
SLOT = 1794887400
PICK = dict(symbol="ABC", direction="Bullish", entry=100, stop=99, t1=101, t2=102,
            state="T1 reached", entered=SLOT+60, hit1=SLOT+250, ended=None,
            prior_calls=1, prior_days=1, prior_t1=0, shadow_rank=1)


def run():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge")
        for width in (390, 1280):
            page = browser.new_page(viewport=dict(width=width, height=844))
            def route(r):
                path = r.request.url.split(".test", 1)[1]
                if path == "/":
                    return r.fulfill(path=str(ASSETS/"index.html"))
                if path.startswith("/workspace-assets/"):
                    return r.fulfill(path=str(ASSETS/Path(path).name))
                if path.endswith("/stream"):
                    return r.abort()
                if path == "/api/timed-editions":
                    return r.fulfill(json={"mode":"live", "editions":[
                        dict(slot=SLOT+1200, picks=[], connected=True), dict(slot=SLOT,picks=[PICK],connected=True)]})
                return r.fulfill(json={"indices":[], "setups":[]})
            page.route("**/*", route)
            page.goto("http://scanner.test/")
            expect(page.locator("#editionReport")).to_contain_text("No qualifying setup")
            page.locator("#editionSlot").select_option(str(SLOT))
            expect(page.locator("#editionReport")).to_contain_text("T1 reached")
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            page.close()
        browser.close()


if __name__ == "__main__":
    run()
