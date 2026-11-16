"""Exercise the one-second ticker and manual refresh during an in-flight scan."""
import asyncio
import os

from playwright.async_api import async_playwright, expect


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel=os.getenv("BROWSER_CHANNEL","msedge"))
        page = await browser.new_page()
        started, release = asyncio.Event(), asyncio.Event()
        scans, pulses = [], []
        async def scan(route):
            scans.append(route.request.url)
            started.set()
            await release.wait()
            await route.fulfill(json={"setups":[{"symbol":"ABC","direction":"LONG","ltp":100,"trigger_price":105,
                                                "scanner_band":"watchlist","stop_loss":98}]})
        async def pulse(route):
            pulses.append(1)
            await route.fulfill(json={"indices":[],"session":"open","quotes":{
                "ABC":{"price":100+len(pulses),"epoch":1770000000+len(pulses),"status":"simulated"}}})
        await page.route("**/api/demo/pretrade/top*",scan)
        await page.route("**/api/demo/market-strip",pulse)
        await page.route("**/api/demo/market-strip/stream",lambda route:route.abort())
        await page.goto(os.getenv("WORKSPACE_URL","http://127.0.0.1:8084")+"/demo")
        await asyncio.wait_for(started.wait(),15)
        await page.locator("#refresh").click()
        await expect(page.locator("#refreshStatus")).to_have_text("Refresh queued")
        release.set()
        await expect(page.locator("#refreshStatus")).to_contain_text("Updated")
        assert len(scans)==2 and scans[-1].endswith("force=true")
        first = await page.locator("[data-price]").inner_text()
        await expect(page.locator("[data-price]")).not_to_have_text(first,timeout=3500)
        assert len(scans)==2
        await page.route("**/api/demo/pretrade/top?force=true",lambda route:route.abort())
        await page.locator("#refresh").click()
        await expect(page.locator("#refreshStatus")).to_contain_text("Refresh failed")
        await expect(page.locator("#refresh")).to_be_enabled()
        await browser.close()


if __name__=="__main__":
    asyncio.run(run())
