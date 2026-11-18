from reaction_alpha.market_strip import market_read


def test_direction_requires_fresh_agreement_and_displays_opposing_evidence():
    rows = [dict(name=n, percent=p, status="live") for n,p in
            [("NIFTY 50", -.8), ("SENSEX", -.6), ("BANK NIFTY", .2)]]
    read = market_read(rows, "open", False)
    assert read["label"] == "Bearish" and "BANK NIFTY +0.20%" in read["reason"]
    rows[1]["status"] = "stale"
    assert market_read(rows, "open", False)["label"] == "Mixed"
    rows[0]["percent"] = None
    assert market_read(rows, "open", False)["label"] == "Direction unconfirmed"
    assert market_read(rows, "closed", False)["label"] == "Market closed"
