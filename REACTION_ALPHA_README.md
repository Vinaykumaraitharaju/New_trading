# Reaction Alpha Engine

Production-oriented intraday signal stack built around Kotak Neo live ticks and a reaction-first workflow:

- Detect abnormal market events
- Classify post-event reaction as continuation, reversal, or absorption
- Score each symbol across structure, S/R, volume, order flow, VWAP, volatility, and buildup
- Publish only the top 3-5 trades over REST and WebSocket

## Backend

- Entry point: `reaction_alpha_main.py`
- FastAPI app factory: `reaction_alpha/api.py`
- WebSocket stream: `/ws/signals`
- REST endpoints:
  - `/api/health`
  - `/api/signals/top`
  - `/api/signals/{symbol}`

### Run backend

```bash
python reaction_alpha_main.py
```

### Key env vars

- `REACTION_ALPHA_SYMBOLS=RELIANCE,HDFCBANK,ICICIBANK,INFY,TCS`
- `REACTION_ALPHA_SIMULATED=true`
- `REACTION_ALPHA_TOP_N=5`
- `KOTAK_CONSUMER_KEY=...`
- `KOTAK_MOBILE_NUMBER=...`
- `KOTAK_UCC=...`
- `KOTAK_MPIN=...`
- `KOTAK_TOTP_SECRET=...`
- `TELEGRAM_BOT_TOKEN=...`
- `TELEGRAM_CHAT_ID=...`

Set `REACTION_ALPHA_SIMULATED=false` to use the Kotak live feed.

## Frontend

React + Tailwind dashboard lives in `frontend/`.

### Run frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` and `/ws` to `http://localhost:8000`.

## Verification

Python modules compile with:

```bash
python -m compileall reaction_alpha reaction_alpha_main.py
```

This workspace currently does not have `pytest` installed, so test execution requires:

```bash
python -m pip install pytest
python -m pytest tests/test_reaction_alpha_engine.py
```
