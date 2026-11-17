# Timed picks: live paper research

The EC2 service, not a browser timer, publishes up to five independent price-touch forecasts at 09:20 IST and every 20 minutes through 15:00 on supported open sessions. The first setup uses 09:15-09:19; later batches use their immediately preceding five minutes. The monitored universe is the existing Kotak subscription, not every NSE-listed stock. Missing a slot while offline does not generate a retrospective prediction. An empty batch is a valid result.

Version opening-pressure-v1 uses the observed range, direction, distance from the high/low, quote spread, and directional efficiency (net movement divided by total sampled movement). A measured opposite five-minute NIFTY move larger than 0.1% filters a candidate; unavailable benchmark coverage is explicit. A breakout entry is just beyond the measured range. Stop distance is half the range or four spreads, whichever is larger, with a five-paise floor. T1 and T2 use one and two stop distances. These are research levels, not exchange-rounded orders. No new positions or broker orders are created by this feature.

Each edition stores actual publication time, fixed levels, source context and outcomes in the live paper SQLite database. The first post-publication trade beyond T1 without a recorded entry is a missed move. T1 must be observed after entry and strictly before minute 10; T2 before minute 20. Early touches have actual timestamps. Targets and stops are evaluated from verified observations, not candles, and cannot establish what happened between observations. A feed disconnect, restart or observation gap over 45 seconds makes an active result insufficient data, not a loss. Reading an edition never runs a scan. History and Scanner show the latest 40 editions.

Each edition looks back up to 90 days at the same IST slot and direction. It freezes the earlier measured calls, sessions and timely T1 counts. This is the rate from publication, not the conditional win rate after entry. A research-only shadow ordering adds a small historical adjustment once 30 calls and five earlier sessions are available. It does not override the original list or promise better returns; the two orderings must be compared prospectively. Only real, published picks count. On EC2 the SQLite ledger survives code-only updates; it still needs independent backups.

## External context

The context worker polls every 15 minutes independently of prices. No source below can confirm an entry or change a published target.

- ECB: daily USD/INR reference derived as INR per EUR divided by USD per EUR. Informational, not a real-time FX quote. [Reference rates](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html).
- US Federal Reserve Board: latest dated monetary policy release, not comprehensive global news. [Official RSS feeds](https://www.federalreserve.gov/feeds/feeds.htm).
- Optional SEC EDGAR: latest 6-K/20-F for the mapped US filers INFY and ICICIBANK, not all Indian exchange announcements. Configure REACTION_ALPHA_SEC_USER_AGENT with the operator's chosen organisation and contact email to enable; it is sent to the SEC, not shown in the UI. A filing is evidence of publication, not an inferred earnings beat. [API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [access policy](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

Missing sources are labelled unavailable or not configured. Demo does not poll these sources or train the live ledger. A successful EC2 deployment is not evidence of prediction quality.
