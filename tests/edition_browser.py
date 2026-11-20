"""Deterministic desktop/mobile checks using the real workspace assets."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reaction_alpha.timed_editions import TimedEditions

ASSETS = Path(__file__).resolve().parents[1]/"reaction_alpha/workspace_ui"
OUT = Path(__file__).resolve().parents[1]/"docs/workspace/screenshots"
SLOT = int(datetime.fromisoformat("2026-11-18T09:20:00+05:30").timestamp())


def fixture(path):
    book = TimedEditions(path)
    for symbol, base, sign in [("RELIANCE", 1400, 1), ("INFY", 1500, -1), ("HDFCBANK", 1000, 1)]:
        for t in range(0, 300, 5):
            price = base+sign*t/50
            book.observe(symbol, SLOT-300+t, price, price-.05, price+.05)
    book.tick(SLOT, True)
    data = book.snapshot(SLOT+2)
    data.update(mode="live", context={})
    data["daily_movers"] = dict(day="2026-11-18", covered=3, training_examples=0,
        paired=0, correct=0, neither_correct=0, forecasts=[], movers=[
        dict(symbol="INFY",close=1500,side="Down",at=SLOT,price=1440,percent=-4,
             first_observation=SLOT,initial_pct=-4,nifty_pct=-.5,filing=None)])
    yesterday = deepcopy(data["editions"][0])
    yesterday["slot"] -= 86400
    data["editions"].append(yesterday)
    return data


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as tmp, sync_playwright() as pw:
        initial = fixture(str(Path(tmp)/"paper.db"))
        browser = pw.chromium.launch(channel="msedge")
        for width in (390, 1280):
            page = browser.new_page(viewport=dict(width=width, height=900))
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            data = deepcopy(initial)

            def route(r):
                path = r.request.url.split(".test", 1)[1]
                if path == "/" or path.startswith("/history") or path == "/demo":
                    return r.fulfill(path=str(ASSETS/"index.html"))
                if path.startswith("/workspace-assets/"):
                    return r.fulfill(path=str(ASSETS/Path(path).name))
                if path.endswith("/stream"):
                    return r.abort()
                if path.startswith("/api/timed-editions"):
                    return r.fulfill(json=data)
                if path == "/api/health":
                    return r.fulfill(json={"mode":"live", "feed_connection":{"status":"live", "last_verified_trade_epoch":SLOT-86400}})
                if path == "/api/market-strip":
                    return r.fulfill(json={"session":"open", "indices":[dict(name=n, level=v, change=c, percent=.3, epoch=SLOT, status=s)
                        for n,v,c,s in [("NIFTY 50",25387.4,96.3,"live"),("SENSEX",82532.19,427.4,"stale"),("BANK NIFTY",62273.25,697.3,"live")]]})
                return r.fulfill(json={"indices":[], "setups":[], "recent":[]})

            page.route("**/*", route)
            page.goto("http://scanner.test/")
            expect(page.locator("#editionSlot")).to_have_value(str(SLOT))
            expect(page.locator("#editionSlot option")).to_have_count(19)
            expect(page.locator("#editionSlot")).not_to_contain_text("17 Nov")
            expect(page.locator("#tradeTime")).to_contain_text("17 Nov 2026")
            expect(page.locator("#editionReport")).to_contain_text("Frozen at publication")
            expect(page.locator("#dailyMovers")).to_contain_text("Already beyond threshold")
            expect(page.locator("#dailyMovers")).to_contain_text("No verified company-specific cause")
            assert page.evaluate("""d => {
              const movers=Array.from({length:100},(_,i)=>({symbol:'EQ'+i,up:true,high_pct:5,current_pct:4,price:100,trade:1}));
              const sweep={covered:100,universe:100,status:'test',movers};
              const region=()=>document.querySelector('.eq-discovery-scroll');
              paintMovers(d,sweep);region().scrollTop=240;paintMovers(d,sweep);
              const ok=region().scrollTop===240 && region().clientHeight<=innerHeight/2 &&
                getComputedStyle(region().querySelector('th')).position==='sticky' &&
                document.documentElement.scrollWidth<=innerWidth;
              paintMovers(d,null);return ok;
            }""", data["daily_movers"])
            states=page.evaluate("""async () => {
              const now=Math.floor(Date.now()/1000);
              const s={symbol:'SAMPLE',side:'LONG',trigger_price:505,stop_loss:500,target1:512,setup_type:'Breakout'};
              const q={epoch:now,price:503,status:'live'};
              setups=[s]; ticker={SAMPLE:q}; scanner(); await detail('SAMPLE');
              const message=document.querySelector('#decisionText').textContent;
              const labels=[entryRead(s,{...q,price:513},now)[0],
                entryRead({...s,side:'SHORT',stop_loss:510,target1:498},{...q,price:497},now)[0],
                entryRead(s,q,now+16)[0],entryRead({...s,setup_state:'ENTERED'},q,now)[0]];
              document.querySelector('#detail').close();selected='';setups=[];scanner();
              return [message,...labels];
            }""")
            assert "Wait for entry" in states[0] and "planned risk" in states[0]
            assert states[1:]==["Missed move","Missed move","Cannot verify entry now","Entry already recorded"]
            page.screenshot(path=OUT/f"timed-scanner-{width}.png", full_page=True)
            page.locator(".pick-reason summary").first.click()
            expect(page.locator(".pick-reason").first).to_contain_text("not predicted fair values")
            expect(page.locator(".pick-reason").first).to_contain_text("Unverified company evidence")
            page.screenshot(path=OUT/f"timed-evidence-{width}.png", full_page=True)
            page.evaluate("loadEditions()")
            expect(page.locator(".pick-reason").first).to_have_attribute("open", "")
            page.locator("#editionSlot").select_option(str(SLOT+6*3600))
            expect(page.locator("#editionReport")).to_contain_text("15:30")
            expect(page.locator("#editionReport")).to_contain_text("Candidate assessment starts")
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            page.goto(f"http://scanner.test/history?edition={SLOT}&pick=RELIANCE")
            expect(page.locator("#editionTitle")).to_have_text("Timed forecast archive")
            expect(page.locator(f'[data-reason="{SLOT}:RELIANCE"]')).to_have_attribute("open", "")
            page.locator("#editionSlot").select_option(str(SLOT-86400))
            expect(page.locator("#editionReport")).to_contain_text("Archived")
            data["preview"]["for_slot"] = SLOT+1200
            data["preview"]["picks"] = deepcopy(data["editions"][0]["picks"])
            data["schedule"]["selected_slot"] = SLOT+1200
            page.goto("http://scanner.test/")
            expect(page.locator("#editionReport")).to_contain_text("Developing candidates")
            expect(page.locator("#editionReport")).not_to_contain_text("Frozen at publication")
            data["editions"] = []
            data["preview"]["picks"] = []
            data["preview"]["connected"] = False
            page.goto("http://scanner.test/")
            expect(page.locator("#editionReport")).to_contain_text("Broker disconnected")
            data["schedule"].update(slots=[], selected_slot=None, session="unknown")
            page.goto("http://scanner.test/")
            expect(page.locator("#editionReport")).to_contain_text("Calendar unavailable")
            page.goto("http://scanner.test/demo")
            expect(page.locator("#editions")).to_be_hidden()
            assert not errors, errors
            page.close()
        browser.close()
    print("Timed research desktop/mobile: schedule, evidence, archive, disconnect, calendar, demo PASS")


if __name__ == "__main__":
    run()
