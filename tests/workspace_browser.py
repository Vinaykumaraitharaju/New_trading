"""Run against the local simulated preview: python tests/workspace_browser.py."""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

BASE = os.getenv("WORKSPACE_URL", "http://127.0.0.1:8077")
OUT = Path("docs/workspace")


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=os.getenv("BROWSER_CHANNEL", "msedge"))
        for width in (1366, 390):
            page = browser.new_page(viewport={"width": width, "height": 840})
            page.goto(BASE + "/demo", wait_until="domcontentloaded")
            expect(page.locator("#refreshTime")).not_to_have_text("Pending", timeout=60000)
            rows = [dict(symbol=s, sector=sector, side=side, setup_id=i+1, entry_high=entry,
                         trigger_price=entry, ltp=entry-1 if side=="LONG" else entry+1, stop_loss=entry-10 if side=="LONG" else entry+10,
                         target1=entry+20 if side=="LONG" else entry-20, target2=entry+40 if side=="LONG" else entry-40,
                         scanner_band=band, setup_type="Price touch", entered_at=None)
                    for i,(s,sector,side,entry,band) in enumerate([
                        ("RELIANCE","Energy","LONG",1410,"near-trigger"),("INFY","Technology","SHORT",1520,"watchlist"),
                        ("HDFCBANK","Banking","LONG",990,"watchlist"),("CIPLA","Healthcare","SHORT",1390,"avoid")])]
            page.route("**/api/demo/pretrade/top*",lambda r:r.fulfill(json={"setups":rows}))
            page.goto(BASE+"/demo")
            expect(page.get_by_text("No actionable setups",exact=True)).to_be_visible()
            expect(page.get_by_text("Nearest candidate:",exact=False)).to_contain_text("INFY")
            page.screenshot(path=OUT/f"scanner-{width}.png")
            page.locator("#sort").select_option("symbol")
            page.locator("a[data-stock=RELIANCE]").scroll_into_view_if_needed()
            scroll_before = page.evaluate("scrollY")
            page.get_by_role("link",name="RELIANCE",exact=True).click()
            expect(page.locator("dialog")).to_contain_text("Tick at or above")
            expect(page.locator("dialog")).to_contain_text("1,400")
            page.screenshot(path=OUT/f"detail-{width}.png")
            page.go_back()
            expect(page.locator("dialog")).not_to_be_visible()
            expect(page.locator("#sort")).to_have_value("symbol")
            expect(page.locator("a[data-stock=RELIANCE]")).to_be_focused()
            assert abs(page.evaluate("scrollY") - scroll_before) <= 1
            page.locator("#band").select_option("avoid")
            expect(page.locator("a[data-stock]")).to_have_count(1)
            page.locator("a[data-stock]").click()
            page.route("**/api/demo/pretrade/archive*",lambda r:r.fulfill(json={"recent":[dict(id=4,symbol="CIPLA",
                       setup_type="Price touch",result="SL_HIT",first_barrier="T1",direction="BEARISH",entered_at="10:01:00",
                       t1_at="10:08:00",exited_at="10:15:00",entry_trigger=1390,stop_loss=1400,target1=1370,target2=1350)]}))
            page.get_by_role("link",name="Forecast #4 timeline").click()
            expect(page.get_by_text("T1 before stop")).to_be_visible()
            page.screenshot(path=OUT/f"history-{width}.png")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            for path,title in [("/pre-trade-scanner","Market scanner"),("/demo/journal","Research history"),("/demo/journal/analytics","Research history"),("/demo/pretrade/archive#setup-4","Research history")]:
                page.goto(BASE+path)
                expect(page.locator("h1")).to_have_text(title)
            page.route("**/api/health",lambda r:r.fulfill(json={"mode":"live","feed_connection":{"status":"live","last_verified_trade_epoch":100}}))
            page.route("**/api/kotak/login-state",lambda r:r.fulfill(json={"state":"not_required"}))
            page.route("**/api/pretrade/top*",lambda r:r.fulfill(json={"setups":[]}))
            page.goto(BASE+"/")
            expect(page.locator("#connection")).to_have_text("Live / stale or unverified")
            expect(page.get_by_text("No setups match this filter.")).to_be_visible()
            page.close()
        browser.close()


if __name__ == "__main__":
    run()
