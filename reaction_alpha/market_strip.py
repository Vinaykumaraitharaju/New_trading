"""Read-only projections of the existing feed. No broker calls or scan execution."""
from datetime import datetime, time
from math import isfinite
from threading import Lock
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
NAMES = {"NIFTY": "NIFTY 50", "SENSEX": "SENSEX", "BANKNIFTY": "BANK NIFTY"}
# NSE cash market circulars CMTR71775, CMTR72260, CMTR72349 and CMTR76941.
HOLIDAYS = set("01-15 01-26 03-03 03-26 03-31 04-03 04-14 05-01 05-28 06-26 09-14 10-02 10-20 11-10 11-24 12-25".split())


def session(epoch):
    local = datetime.fromtimestamp(epoch, IST)
    if local.year != 2026:
        return "unknown"
    day = local.strftime("%m-%d")
    if day == "11-08":
        start = time(14, 20)
    elif day in HOLIDAYS or (local.weekday() >= 5 and day != "02-01"):
        return "closed"
    else:
        start = time(9, 15)
    return "open" if start <= local.time() < time(15, 30) else "closed"


def market_read(rows, market, simulated):
    labels = {"simulated"} if simulated else {"live"}
    usable = [r for r in rows if r["status"] in labels and r["percent"] is not None]
    if market != "open" and not simulated:
        return {"label": "Market closed" if market == "closed" else "Session unknown",
                "reason": "No live direction call outside a confirmed open session."}
    if len(usable) < 2:
        return {"label": "Direction unconfirmed", "reason": "Need two fresh index quotes with verified previous closes."}
    down = sum(r["percent"] < 0 for r in usable)
    up = sum(r["percent"] > 0 for r in usable)
    label = "Bearish" if down >= 2 else "Bullish" if up >= 2 else "Flat" if not up and not down else "Mixed"
    detail = ", ".join(f"{r['name']} {r['percent']:+.2f}%" for r in usable)
    return {"label": ("Demo: " if simulated else "") + label,
            "reason": f"{down} below and {up} above previous close among {len(usable)} usable indices: {detail}. "
                      "Index direction only; a news cause is not verified."}


class MarketStrip:
    def __init__(self, simulated):
        self.simulated = simulated
        self.quotes = {}
        self.scan = None
        self.lock = Lock()

    def observe(self, symbol, price, source_time, close, received):
        try:
            epoch = float(source_time)
            if epoch >= 1e12:
                epoch /= 1000
            if symbol not in NAMES or not isfinite(price) or price <= 0 or not 946684800 <= epoch <= received:
                return
            close = float(close or 0)
        except (ValueError, TypeError, OverflowError):
            return
        with self.lock:
            if symbol in self.quotes and self.quotes[symbol][0] >= epoch:
                return
            self.quotes[symbol] = epoch, price, close if isfinite(close) and close > 0 else None

    def completed(self, epoch, scanned):
        with self.lock:
            self.scan = {"epoch": epoch, "symbols": scanned}

    def snapshot(self, now, connected):
        market = session(now)
        rows = []
        with self.lock:
            for symbol, label in NAMES.items():
                epoch, price, close = self.quotes.get(symbol, (None, None, None))
                change = price - close if close else None
                status = "unavailable"
                if epoch is not None:
                    age = now - epoch
                    if self.simulated:
                        status = "simulated"
                    elif market == "closed":
                        status = "last known"
                    elif not connected or market == "unknown" or age > 60 or age < 0:
                        status = "stale"
                    else:
                        status = "live" if age <= 15 else "delayed"
                rows.append(dict(name=label, level=price, change=change, percent=100*change/close if close else None,
                                 epoch=epoch, status=status))
            return {"session": market, "indices": rows, "scan": self.scan,
                    "market_read": market_read(rows, market, self.simulated)}
