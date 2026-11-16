# Reaction Alpha workspace

| Previous bookmark | Current destination |
| --- | --- |
| / and /pre-trade-scanner | Scanner at / |
| /stock/SYMBOL | Scanner with the stock drawer open |
| /pretrade/archive and #setup-ID | History / Forecasts, retaining the selected forecast |
| /journal | History / Paper trades |
| /journal/analytics | History / Performance |
| /demo and equivalent /demo/... bookmarks | Same views using simulated data |
| /kotak-login | Existing manual login; expired sessions also prompt on the requested page |

Canonical history links are /history, /history?tab=trades and /history?tab=performance. /history?setup=ID looks up the exact forecast, including older records outside the recent list. Forecasts are observational; they are not fills. The live feed timestamp is based on verified broker trades, not an HTTP refresh.

The six PNGs show deterministic demo fixtures, not live recommendations. Run the API suite with pytest tests. With the simulated app running locally and Playwright installed, run python tests/workspace_browser.py for the desktop and phone flow and screenshots. WORKSPACE_URL overrides the default preview address; BROWSER_CHANNEL overrides msedge.

## Index strip

The visible live Scanner streams changed index and ranked-stock snapshots from the existing Kotak connection, up to four times per second. If the display stream disconnects, the browser polls once per second instead. Neither path authenticates, opens another broker socket or reranks setups. Rows without a newer verified tick retain the labelled scan snapshot. Manual Refresh requests a new ranking scan even when the automatic load is busy.

Live paper entries require a fresh, ordered Kotak trade and timestamped two-sided book with positive quantities. Confirmation uses the last traded price; execution uses the ask for buys and bid for sells, plus modelled slippage. A price-only observation can advance a forecast but cannot fill a paper trade. Replayed observations cannot create extra fills; trades sharing a timestamp require increasing cumulative volume. From 15:20 IST, the next qualifying quote closes the symbol's open paper positions. Reading the dashboard or losing the feed does not manufacture an exit. These are hypothetical fills, not exchange executions or real orders.

On /demo, symbols generate synthetic trades independently, with variable gaps. The visible scanner receives changed quote snapshots over one event stream (up to four snapshots per second); one-second polling is the fallback. Multiple trades can occur between displayed snapshots. Demo paper entries check the last trade for confirmation, then price buys from the simulated ask and sells from the bid before applying configured slippage. Open positions are marked on the exit side. This is a practice model, not an exchange replay: no queue priority, partial fills, guaranteed latency or real orders.

Index subscriptions use [Kotak's documented segment/name pairs](https://github.com/Kotak-Neo/kotak-neo-python/blob/main/docs/functions/websocket/market_feed.md). Change uses the index packet's scaled level and close_price, the same reference the pinned SDK uses to decode index change. A missing close is not inferred from the last tick. A positive, ordered source timestamp is required; receipts and scan timestamps cannot make a quote live. During normal trading, live means connected and at most 15 seconds old; 15-60 seconds is delayed, older or disconnected is stale. After hours the last observed level is not an official closing value. After a cold start there is no last-known observation until one arrives.

The session label is the scheduled NSE normal cash market, not a guarantee of exchange availability or an independent BSE trading-status feed. Calendar coverage is 2026 only; outside coverage it reports unknown. Sources: [annual cash holidays](https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf), [January election amendment](https://nsearchives.nseindia.com/content/circulars/CMTR72260.pdf), [Sunday Budget session](https://nsearchives.nseindia.com/content/circulars/CMTR72349.pdf), [Muhurat session](https://nsearchives.nseindia.com/content/circulars/CMTR76941.pdf). Review exchange amendments before extending coverage.
