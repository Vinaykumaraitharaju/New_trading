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
