# Pretrade evidence: tick-touch-v1

The scanner proposes a direction; the archive tests it. Neither a score nor a paper entry is an order. Setup family names describe how a candidate was selected. This first protocol tests a subsequent price touch, not a completed-candle breakout.

## What the deployed endpoint showed

On 2026-11-15 the public /api/pretrade/archive returned five active calls, one entered, none closed. CIPLA (bearish, avoid) had publication, entry and latest price all at 1391.80, with no exit. CLEANMAX (bullish, watching) stayed at 1317.60 below its 1328.27 trigger. These records cannot establish directional accuracy, a loss, or an arrival sequence within a candle. Legacy rows have no timestamped T1 or verified exchange trade time. Do not pool them with the new protocol.

## Two separate questions

- **Direction:** use the first eligible tick within one minute after publication, then the first eligible tick 30 to 31 elapsed minutes later. Returns greater than +0.20% are bullish, below -0.20% bearish, otherwise neutral. No qualifying endpoint means no label. The windows are intentionally narrow; they do not roll over to the next trading day. This is not a calendar-adjusted historical backtest.
- **Price path:** freeze the levels and deadline at publication. Longs enter at or above entry high; shorts at or below entry low. A first observation already at or past T1 is a missed entry. A stop touched before entry invalidates the call; an avoid call cannot enter. T1-first survives a later stop. At the deadline, an incomplete path stays unresolved; missing ticks do not prove a miss. The first observed barrier need not be the first actual exchange trade to cross it.
- **Evidence:** scan snapshots are indicative only. Simulated calls use simulated ticks. Live calls need a timestamped trade, no more than 15 seconds old at receipt. Unknown time formats fail closed; equal or older timestamps cannot advance the path. Multiple trades with the same exchange timestamp cannot be reliably ordered.

## Reading the results

Use /api/pretrade/archive?session_date=YYYY-MM-DD. Compare scanner and publication-time market direction on the same measured rows, by source. Look at published, measured and paired counts before correctness. The rows are correlated across symbols and days; these counts are not independent trials or profit estimates. Persistent archive storage is required for multi-day evaluation; local SQLite on an ephemeral Render filesystem is insufficient.

Next evaluation: collect multiple trading sessions, check eligible-tick coverage by symbol and stale-feed rate, record point-in-time sector-relative strength and prior-range breakout baselines, then use expanding training windows with untouched later sessions. Report day-block uncertainty, transaction costs, spread and slippage before interpreting paper results as executable returns. No threshold was optimized against the five deployed rows.

## Data boundaries

Use the authenticated broker stream for intraday evidence. NSE's [research data inventory](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/Data%20list%20under%20NSE%20Data%20Sharing%20Policy%20for%20Research%20and%20Analysis_20250728.pdf) distinguishes daily market reports from corporate filings. End-of-day records cannot order intraday barriers. Public visibility does not establish permission for automated commercial use; review [NSE non-display terms](https://www.nseindia.com/static/market-data/non-display-data) before integrating a new feed. No unverified third-party source was added.
