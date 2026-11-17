"""Dated research context only. Neither provider supplies execution prices."""
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from math import isfinite
import os
import time
from xml.etree import ElementTree

import requests

ECB = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
FED = "https://www.federalreserve.gov/feeds/press_monetary.xml"
FILERS = {"INFY": 1067491, "ICICIBANK": 1103838}


def reference(xml):
    for day in ElementTree.fromstring(xml).iter():
        if "time" not in day.attrib:
            continue
        rates = {r.get("currency"): float(r.attrib["rate"]) for r in day}
        value = rates["INR"]/rates["USD"]
        if not isfinite(value) or value <= 0:
            raise ValueError("Invalid reference")
        return {"date": date.fromisoformat(day.attrib["time"]).isoformat(), "usd_inr": round(value, 4)}
    raise ValueError("Missing dated ECB rates")


class EditionContext:
    def __init__(self):
        self.latest = {"fx": None, "filings": {}, "sec_status": "Not configured"}

    def run(self, stop):
        agent = os.getenv("REACTION_ALPHA_SEC_USER_AGENT", "")
        while not stop.is_set():
            data = {"fx": None, "filings": {}, "sec_status": "Not configured"}
            try:
                r = requests.get(ECB, timeout=5)
                r.raise_for_status()
                data["fx"] = {**reference(r.content), "received": time.time()}
            except (requests.RequestException, KeyError, ValueError, ArithmeticError, ElementTree.ParseError):
                pass
            try:
                r = requests.get(FED, timeout=5)
                r.raise_for_status()
                item = ElementTree.fromstring(r.content).find("./channel/item")
                if item is not None:
                    published = parsedate_to_datetime(item.findtext("pubDate")).timestamp()
                    if published <= time.time():
                        data["fed"] = dict(title=item.findtext("title"), published=published, received=time.time())
            except (requests.RequestException, TypeError, ValueError, ElementTree.ParseError):
                pass
            if "@" in agent:
                data["sec_status"] = "SEC US filings only"
                for symbol, cik in FILERS.items():
                    try:
                        r = requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
                                         headers={"User-Agent": agent}, timeout=5)
                        r.raise_for_status()
                        recent = r.json()["filings"]["recent"]
                        for form, stamp, accession in zip(recent["form"], recent["acceptanceDateTime"], recent["accessionNumber"]):
                            if form in {"6-K", "20-F"}:
                                accepted = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                                if accepted.tzinfo and accepted.timestamp() <= time.time():
                                    data["filings"][symbol] = dict(form=form, published=accepted.timestamp(),
                                                                   received=time.time(), accession=accession)
                                break
                    except (requests.RequestException, KeyError, TypeError, ValueError):
                        data["sec_status"] = "SEC partial or unavailable"
                    if stop.wait(1):
                        return
            self.latest = data
            stop.wait(900)
