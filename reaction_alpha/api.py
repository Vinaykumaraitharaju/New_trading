from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

from .config import ReactionAlphaConfig
from .display_time import indian_time
from .service import ReactionAlphaService


KOTAK_LOGIN_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Kotak Login</title>
  <style>
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #080b10; color: #f7f8fb; font-family: system-ui, sans-serif; }
    main { width: min(420px, calc(100vw - 32px)); padding: 28px; border: 1px solid rgba(255,255,255,.12); border-radius: 14px; background: #101620; box-shadow: 0 24px 80px rgba(0,0,0,.35); }
    h1 { margin: 0 0 8px; font-size: 24px; }
    p { margin: 0 0 18px; color: #a8b3c7; line-height: 1.55; }
    label { display: block; margin: 14px 0 8px; color: #d4af37; font-size: 13px; font-weight: 700; }
    input { width: 100%; padding: 13px 14px; border: 1px solid rgba(255,255,255,.16); border-radius: 10px; background: #070a0f; color: #fff; font-size: 18px; letter-spacing: .12em; box-sizing: border-box; }
    input[name="secret"] { font-size: 14px; letter-spacing: 0; }
    button { width: 100%; margin-top: 18px; padding: 13px 14px; border: 0; border-radius: 10px; background: #d4af37; color: #070a0f; font-weight: 800; cursor: pointer; }
    pre { white-space: pre-wrap; margin: 18px 0 0; color: #a8ffcf; }
    a { color: #d4af37; }
  </style>
</head>
<body>
  <main>
    <h1>Kotak Login</h1>
    <p>Enter your current authenticator code to open this page with the live feed.</p>
    <form id="form">
      <label for="totp">Current TOTP</label>
      <input id="totp" name="totp" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" required />
      <label for="secret">Admin secret, if configured</label>
      <input id="secret" name="secret" type="password" autocomplete="current-password" />
      <button type="submit">Start Kotak Live Feed</button>
    </form>
    <pre id="result" role="status"></pre>
    <p style="margin-top:18px"><a href="/">Back to dashboard</a></p>
  </main>
  <script>
    const form = document.getElementById("form");
    const result = document.getElementById("result");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      result.textContent = "Submitting...";
      const totp = new FormData(form).get("totp");
      const secret = new FormData(form).get("secret");
      const headers = { "Content-Type": "application/json" };
      if (secret) headers["X-Reaction-Alpha-Secret"] = secret;
      const button = form.querySelector("button");
      button.disabled = true;
      try {
      const response = await fetch("/api/kotak/totp", {
        method: "POST",
        headers,
        body: JSON.stringify({ totp_code: totp })
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.detail || payload.message || "Login failed.");
      form.reset();
      if (location.pathname === "/kotak-login") location.replace("/");
      else location.reload();
      } catch (err) {
        result.textContent = err.message || "Could not reach Kotak. Please try again.";
      } finally {
        button.disabled = false;
      }
    });
  </script>
</body>
</html>"""


def build_demo_signal_map() -> dict[str, dict[str, Any]]:
    snapshot = build_demo_snapshot()
    return {str(item["stock"]).upper(): item for item in snapshot["top_signals"]}


def build_demo_paper_trades(session_anchor: datetime | None = None) -> dict[str, Any]:
    now = datetime.now()
    session_anchor = session_anchor or now.replace(hour=9, minute=24, second=0, microsecond=0)
    session_anchor = session_anchor.replace(microsecond=0)
    elapsed_sec = max((now - session_anchor).total_seconds(), 0.0)
    wave = ((int(elapsed_sec // 2) % 18) - 9) * 0.08
    session_date = now.date().isoformat()
    def stamp(minutes_after_open: int) -> str:
        return (session_anchor + timedelta(minutes=minutes_after_open)).isoformat(timespec="seconds")

    trades = [
        {
            "id": 501,
            "symbol": "RELIANCE",
            "signal": "ELITE BULLISH",
            "setup_type": "BREAKOUT_CONTINUATION",
            "regime": "TRENDING",
            "direction": "BULLISH",
            "state": "CLOSED",
            "result": "T2_HIT",
            "score": 21,
            "confidence": "93%",
            "entry_trigger": 2948.25,
            "stop_loss": 2928.80,
            "target1": 2972.40,
            "target2": 2996.55,
            "trigger_price": 2949.10,
            "exit_price": 2994.80,
            "live_price": 2994.80,
            "gross_pnl_points": 45.70,
            "cost_points": 1.20,
            "pnl_points": 44.50,
            "mae_points": 3.25,
            "mfe_points": 48.30,
            "t1_hit": 1,
            "t2_hit": 1,
            "sl_category": None,
            "created_at": stamp(10),
            "updated_at": stamp(51),
            "entered_at": stamp(11),
            "exited_at": stamp(51),
        },
        {
            "id": 502,
            "symbol": "ICICIBANK",
            "signal": "REVERSAL ALERT",
            "setup_type": "FAILED_BREAKOUT_REVERSAL",
            "regime": "EXPANSION",
            "direction": "BEARISH",
            "state": "CLOSED",
            "result": "TIME_EXIT_T1",
            "score": 18,
            "confidence": "88%",
            "entry_trigger": 1224.10,
            "stop_loss": 1237.55,
            "target1": 1210.35,
            "target2": 1196.60,
            "trigger_price": 1223.65,
            "exit_price": 1208.90,
            "live_price": 1208.90,
            "gross_pnl_points": 14.75,
            "cost_points": 0.62,
            "pnl_points": 14.13,
            "mae_points": 2.80,
            "mfe_points": 18.20,
            "t1_hit": 1,
            "t2_hit": 0,
            "sl_category": None,
            "created_at": stamp(23),
            "updated_at": stamp(68),
            "entered_at": stamp(23),
            "exited_at": stamp(68),
        },
        {
            "id": 503,
            "symbol": "HDFCBANK",
            "signal": "ABSORPTION ZONE",
            "setup_type": "ABSORPTION_BUILDUP",
            "regime": "COMPRESSION",
            "direction": "BULLISH",
            "state": "OPEN",
            "result": "OPEN",
            "score": 16,
            "confidence": "81%",
            "entry_trigger": 1682.40,
            "stop_loss": 1669.20,
            "target1": 1694.10,
            "target2": 1705.80,
            "trigger_price": 1683.05,
            "exit_price": None,
            "live_price": round(1688.25 + wave, 2),
            "gross_pnl_points": round(5.20 + wave, 2),
            "cost_points": 0.52,
            "pnl_points": round(4.68 + wave, 2),
            "mae_points": 1.65,
            "mfe_points": 7.10,
            "t1_hit": 0,
            "t2_hit": 0,
            "sl_category": None,
            "created_at": stamp(76),
            "updated_at": now.isoformat(timespec="seconds"),
            "entered_at": stamp(77),
            "exited_at": None,
        },
        {
            "id": 504,
            "symbol": "INFY",
            "signal": "STRONG BULLISH",
            "setup_type": "PULLBACK_CONTINUATION",
            "regime": "TRENDING",
            "direction": "BULLISH",
            "state": "CLOSED",
            "result": "SL_HIT",
            "score": 15,
            "confidence": "76%",
            "entry_trigger": 1518.40,
            "stop_loss": 1509.70,
            "target1": 1530.20,
            "target2": 1542.00,
            "trigger_price": 1518.85,
            "exit_price": 1509.20,
            "live_price": 1509.20,
            "gross_pnl_points": -9.65,
            "cost_points": 0.55,
            "pnl_points": -10.20,
            "mae_points": 10.10,
            "mfe_points": 3.30,
            "t1_hit": 0,
            "t2_hit": 0,
            "sl_category": "fast_failure",
            "created_at": stamp(42),
            "updated_at": stamp(49),
            "entered_at": stamp(43),
            "exited_at": stamp(49),
        },
    ]
    pending = [
        {
            "id": 601,
            "symbol": "TCS",
            "signal": "ABSORPTION ZONE",
            "setup_type": "ABSORPTION_BUILDUP",
            "regime": "COMPRESSION",
            "direction": "BULLISH",
            "state": "PENDING",
            "status": "Awaiting breakout",
            "score": 17,
            "confidence": "79%",
            "entry_trigger": 3894.50,
            "stop_loss": 3878.20,
            "target1": 3911.40,
            "target2": 3927.80,
            "live_price": round(3889.70 + wave, 2),
            "distance_points": round(3894.50 - (3889.70 + wave), 2),
            "distance_pct": round(((3894.50 - (3889.70 + wave)) / 3894.50) * 100, 2),
            "created_at": stamp(82),
            "updated_at": now.isoformat(timespec="seconds"),
            "expires_at": stamp(102),
            "age_sec": round(max((now - (session_anchor + timedelta(minutes=82))).total_seconds(), 0.0), 1),
            "stable": True,
        }
    ]
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "analytics": {
            "session_date": session_date,
            "total_trades": 5,
            "history_total_trades": 5,
            "open_trades": 1,
            "closed_trades": 3,
            "pending_triggers": len(pending),
            "expired_trades": 1,
            "sl_hits": 1,
            "t1_hit_rate": 50,
            "t2_hit_rate": 25,
            "win_like_rate": 50,
            "avg_cost_points": 0.72,
            "avg_pnl_points": 13.28,
            "avg_mfe_points": 19.23,
            "avg_mae_points": 4.45,
            "avg_time_to_trigger_sec": 42.0,
            "avg_hold_sec": 1650.0,
            "funnel": {
                "signals": 5,
                "entered": 4,
                "pending": len(pending),
                "expired": 1,
                "entry_conversion_pct": 80,
                "active_pct": 100,
            },
            "outcomes": {
                "sl_hit_pct": 25,
                "t1_hit_pct": 50,
                "t2_hit_pct": 25,
                "time_exit_pct": 0,
                "time_exit_t1_pct": 25,
                "market_close_exit_pct": 0,
            },
            "progression": {
                "entered_to_t1_pct": 50,
                "entered_to_t2_pct": 25,
                "entered_to_sl_pct": 25,
                "entered_to_time_exit_pct": 25,
                "t1_to_t2_pct": 50,
                "t1_only_pct": 25,
            },
            "execution": {
                "avg_cost_points": 0.72,
                "avg_pnl_points": 13.28,
                "avg_mfe_points": 19.23,
                "avg_mae_points": 4.45,
                "avg_time_to_trigger_sec": 42.0,
                "avg_hold_sec": 1650.0,
            },
            "setup_breakdown": [
                {"setup_type": "BREAKOUT_CONTINUATION", "trades": 1, "entries": 1, "expired": 0, "sl_hit_rate": 0, "time_exit_rate": 0, "t1_hit_rate": 100, "t2_hit_rate": 100},
                {"setup_type": "FAILED_BREAKOUT_REVERSAL", "trades": 1, "entries": 1, "expired": 0, "sl_hit_rate": 0, "time_exit_rate": 100, "t1_hit_rate": 100, "t2_hit_rate": 0},
                {"setup_type": "ABSORPTION_BUILDUP", "trades": 2, "entries": 1, "expired": 0, "sl_hit_rate": 0, "time_exit_rate": 0, "t1_hit_rate": 0, "t2_hit_rate": 0},
                {"setup_type": "PULLBACK_CONTINUATION", "trades": 1, "entries": 1, "expired": 0, "sl_hit_rate": 100, "time_exit_rate": 0, "t1_hit_rate": 0, "t2_hit_rate": 0},
            ],
            "sl_breakdown": [{"bucket": "fast_failure", "hits": 1, "pct": 100}],
        },
        "pending_triggers": pending,
        "trades": trades,
    }


def _demo_price_action(anchor: float, direction: str) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    stamp = datetime.now().replace(microsecond=0)
    drift = 0.18 if direction == "up" else -0.16 if direction == "down" else 0.03
    price = anchor - (drift * 18)
    for idx in range(18):
        open_price = price
        close_price = open_price + drift + (((idx % 4) - 1.5) * 0.03)
        high = max(open_price, close_price) + 0.05
        low = min(open_price, close_price) - 0.05
        bars.append(
            {
                "timestamp": stamp.isoformat(timespec="seconds"),
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close_price, 2),
                "volume": round(840 + (idx * 70), 2),
            }
        )
        stamp += timedelta(seconds=1)
        price = close_price
    return bars


def build_demo_snapshot() -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "generated_at": now,
        "tracked_symbols": 48,
        "mode": "demo",
        "market_session": {
            "status": "OPEN",
            "detail": "Demo session live with simulated fallbacks",
            "timestamp_ist": now,
        },
        "indices": [
            {"symbol": "NIFTY", "price": 24382.65, "change": 128.45, "change_pct": 0.53, "trend": "UP"},
            {"symbol": "BANKNIFTY", "price": 56694.20, "change": -184.75, "change_pct": -0.32, "trend": "DOWN"},
            {"symbol": "SENSEX", "price": 78644.95, "change": 362.10, "change_pct": 0.46, "trend": "UP"},
        ],
        "top_signals": [
            {
                "stock": "RELIANCE",
                "event": "VOLUME SPIKE",
                "reaction": "CONTINUATION",
                "signal": "ELITE BULLISH",
                "setup_type": "BREAKOUT_CONTINUATION",
                "regime": "TRENDING",
                "trend": "HH-HL",
                "score": 21,
                "entry": 2948.25,
                "sl": 2928.80,
                "t1": 2972.40,
                "t2": 2996.55,
                "expected_move": "2948.25 -> 2984.00-2996.55",
                "confidence": "93%",
                "reason": [
                    "Strong continuation after event impulse",
                    "Higher-high higher-low structure holding",
                    "Buy-side order flow remains dominant",
                    "VWAP alignment supports continuation",
                    "No trap signature detected",
                ],
                "timestamp": now,
                "updated_at": now,
                "components": {
                    "reaction": 6,
                    "structure": 5,
                    "sr": 4,
                    "pattern": 2,
                    "volume": 4,
                    "orderflow": 3,
                    "vwap": 3,
                    "volatility": 2,
                    "buildup": 2,
                    "fake_move": -0,
                },
                "probability": {"t1_hit_rate": 71, "t2_hit_rate": 41, "sample_size": 34, "live_trades": 0, "basis": "runtime setup model", "regime_adjusted": True},
                "price_action_1s": _demo_price_action(2948.25, "up"),
                "last_price": 2956.4,
                "tape_speed": 42,
                "raw_confidence": 93.0,
                "state": "ACTIVE",
            },
            {
                "stock": "HDFCBANK",
                "event": "PRICE EXPANSION",
                "reaction": "ABSORPTION",
                "signal": "ABSORPTION ZONE",
                "setup_type": "ABSORPTION_BUILDUP",
                "regime": "COMPRESSION",
                "trend": "RANGE-HOLD",
                "score": 16,
                "entry": 1682.40,
                "sl": 1669.20,
                "t1": 1694.10,
                "t2": 1705.80,
                "expected_move": "1682.40 -> 1694.10-1705.80",
                "confidence": "81%",
                "reason": [
                    "Heavy volume with limited displacement",
                    "Buyers absorbing supply near range high",
                    "Compression suggests pending expansion",
                    "VWAP still supportive",
                ],
                "timestamp": now,
                "updated_at": now,
                "components": {
                    "reaction": 4,
                    "structure": 2,
                    "sr": 3,
                    "pattern": 3,
                    "volume": 2,
                    "orderflow": 1,
                    "vwap": 3,
                    "volatility": 1,
                    "buildup": 2,
                    "fake_move": -0,
                },
                "probability": {"t1_hit_rate": 63, "t2_hit_rate": 31, "sample_size": 22, "live_trades": 0, "basis": "runtime setup model", "regime_adjusted": True},
                "price_action_1s": _demo_price_action(1682.40, "flat"),
                "last_price": 1684.15,
                "tape_speed": 28,
                "raw_confidence": 81.0,
                "state": "ACTIVE",
            },
            {
                "stock": "ICICIBANK",
                "event": "ORDER FLOW SHIFT",
                "reaction": "REVERSAL",
                "signal": "REVERSAL ALERT",
                "setup_type": "FAILED_BREAKOUT_REVERSAL",
                "regime": "EXPANSION",
                "trend": "LH-LL",
                "score": 18,
                "entry": 1224.10,
                "sl": 1237.55,
                "t1": 1210.35,
                "t2": 1196.60,
                "expected_move": "1224.10 -> 1210.35-1196.60",
                "confidence": "88%",
                "reason": [
                    "Breakout failed and reversed into supply",
                    "Ask-side pressure accelerated sharply",
                    "Structure flipped bearish after trap",
                    "Momentum now aligned to downside",
                ],
                "timestamp": now,
                "updated_at": now,
                "components": {
                    "reaction": 6,
                    "structure": 4,
                    "sr": 3,
                    "pattern": 1,
                    "volume": 2,
                    "orderflow": 3,
                    "vwap": 2,
                    "volatility": 1,
                    "buildup": 1,
                    "fake_move": -5,
                },
                "probability": {"t1_hit_rate": 69, "t2_hit_rate": 36, "sample_size": 26, "live_trades": 0, "basis": "runtime setup model", "regime_adjusted": True},
                "price_action_1s": _demo_price_action(1224.10, "down"),
                "last_price": 1217.55,
                "tape_speed": 37,
                "raw_confidence": 88.0,
                "state": "ACTIVE",
            },
        ],
    }


async def quote_events(service):
    previous = None
    idle = 0
    while True:
        snapshot = service.market_strip_snapshot()
        if snapshot != previous:
            yield "data: " + json.dumps(snapshot, separators=(",", ":")) + "\n\n"
            previous = snapshot
            idle = 0
        elif idle >= 60:
            yield ": keepalive\n\n"
            idle = 0
        idle += 1
        await asyncio.sleep(0.25)


def create_app(config: ReactionAlphaConfig | None = None) -> FastAPI:
    service = ReactionAlphaService(config=config)
    service.paper_trades.experience.configure_cloud()
    demo_config = ReactionAlphaConfig(
        symbols=["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS"],
        dynamic_universe_enabled=False,
        paper_trading_enabled=True,
        paper_trade_db_path="storage/reaction_alpha_demo_paper_trades.db",
        simulated=True,
        simulated_market_always_open=True,
    )
    demo_service = ReactionAlphaService(config=demo_config)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await service.startup()
        await demo_service.startup()
        try:
            yield
        finally:
            await demo_service.shutdown()
            await service.shutdown()

    app = FastAPI(
        title="Reaction Alpha Engine",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.reaction_alpha = service
    app.state.reaction_alpha_demo = demo_service

    def verify_admin_secret(provided: str | None) -> None:
        expected = service.config.webhook_secret
        if expected and provided != expected:
            raise HTTPException(status_code=403, detail="Invalid admin secret.")

    assets = Path(__file__).with_name("workspace_ui")
    workspace = (assets / "index.html").read_text(encoding="utf-8")
    app.mount("/workspace-assets", StaticFiles(directory=assets), name="workspace-assets")

    @app.get("/api/demo/pretrade/top")
    def demo_scan(force: bool = False) -> dict[str, Any]:
        return demo_service.pretrade_scan(force=force)

    @app.get("/api/market-strip")
    async def market_strip() -> dict[str, Any]:
        return service.market_strip_snapshot()

    @app.get("/api/timed-editions")
    def timed_editions(slot: int | None = None, horizons: bool = False):
        data = service.editions.snapshot(time.time(), slot) if service.editions else {"editions": []}
        return {**data, "mode": "simulated" if service.config.simulated else "live",
                "horizon_trials": service.editions.horizons.report() if horizons and service.editions else [],
                "daily_movers": service.movers.report(time.time()) if service.movers else None,
                "mover_sweep": service.mover_sweep.report(time.time()) if service.mover_sweep else None,
                "context": service.edition_context.latest}

    @app.get("/api/demo/market-strip")
    async def demo_market_strip() -> dict[str, Any]:
        return demo_service.market_strip_snapshot()

    @app.get("/api/demo/market-strip/stream")
    async def demo_market_stream():
        return stream_response(demo_service)

    @app.get("/api/market-strip/stream")
    async def live_market_stream():
        return stream_response(service)

    def stream_response(source):
        return StreamingResponse(quote_events(source), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        snapshot = service.snapshot()
        return {
            "status": "ok",
            "mode": snapshot["mode"],
            "tracked_symbols": snapshot["tracked_symbols"],
            "signals": len(snapshot["top_signals"]),
            "feed_connection": snapshot.get("feed_connection", {}),
        }

    @app.get("/api/signals/top")
    async def top_signals() -> dict[str, Any]:
        return service.snapshot()

    @app.get("/api/pretrade/top")
    def pretrade_top(force: bool = False) -> dict[str, Any]:
        return service.pretrade_scan(force=force)

    @app.get("/api/pretrade/archive")
    async def pretrade_archive(session_date: date | None = None, setup_id: int | None = None) -> dict[str, Any]:
        return service.paper_trades.pretrade_archive_report(session_date=session_date.isoformat() if session_date else service.paper_trades.session_date(), setup_id=setup_id)

    @app.post("/api/kotak/totp")
    async def submit_kotak_totp(payload: dict[str, Any], x_reaction_alpha_secret: str | None = Header(default=None)) -> dict[str, Any]:
        verify_admin_secret(x_reaction_alpha_secret)
        return service.submit_kotak_totp(str(payload.get("totp_code") or ""))

    @app.get("/api/demo/snapshot")
    async def demo_snapshot() -> dict[str, Any]:
        return demo_service.snapshot()

    @app.get("/api/demo/signals/{symbol}")
    async def demo_signal_detail(symbol: str) -> dict[str, Any]:
        return signal_detail_payload(demo_service, symbol)

    @app.get("/api/demo/paper-trades")
    async def demo_paper_trade_journal() -> dict[str, Any]:
        return demo_service.paper_trade_journal(limit=120)

    @app.get("/api/demo/pretrade/archive")
    async def demo_pretrade_archive(setup_id: int | None = None) -> dict[str, Any]:
        return demo_service.paper_trades.pretrade_archive_report(session_date=demo_service.paper_trades.session_date(), setup_id=setup_id)

    @app.post("/api/demo/paper-trades/reset-today")
    async def reset_demo_paper_trades_today() -> dict[str, Any]:
        return demo_service.reset_paper_trades(today_only=True)

    @app.post("/api/demo/paper-trades/reset-all")
    async def reset_demo_paper_trades_all() -> dict[str, Any]:
        return demo_service.reset_paper_trades(today_only=False)

    @app.get("/api/paper-trades")
    async def paper_trade_journal() -> dict[str, Any]:
        return service.paper_trade_journal(limit=120)

    @app.get("/api/paper-trades/analytics")
    async def paper_trade_analytics() -> dict[str, Any]:
        return service.paper_trades.analytics()

    @app.post("/api/paper-trades/reset-today")
    async def reset_paper_trades_today() -> dict[str, Any]:
        return service.reset_paper_trades(today_only=True)

    @app.post("/api/paper-trades/reset-all")
    async def reset_paper_trades_all() -> dict[str, Any]:
        return service.reset_paper_trades(today_only=False)

    @app.get("/api/kotak/login-state")
    async def kotak_login_state() -> dict[str, str]:
        return {"state": service.kotak_login_state()}

    def live_page(html: str) -> str:
        state = service.kotak_login_state()
        if state == "totp_required":
            return KOTAK_LOGIN_HTML
        if state == "connecting":
            return """<!doctype html><html lang="en"><title>Kotak connection</title>
            <p role="status">Checking your Kotak session...</p><script>
            async function check() {
              try {
                const res = await fetch('/api/kotak/login-state', {cache:'no-store'});
                if (res.ok && (await res.json()).state !== 'connecting') {
                  location.reload(); return;
                }
              } catch (_) {}
              setTimeout(check, 1500);
            }
            check();</script></html>"""
        if service.config.simulated:
            return html
        return html.replace("</body>", """<script>
          async function checkKotakOnReturn() {
            if (document.hidden) return;
            try {
              const res = await fetch('/api/kotak/login-state', {cache:'no-store'});
              if (res.ok && (await res.json()).state === 'totp_required') location.reload();
            } catch (_) {}
          }
          document.addEventListener('visibilitychange', checkKotakOnReturn);
          window.addEventListener('pageshow', event => { if (event.persisted) checkKotakOnReturn(); });
        </script></body>""")

    @app.get("/kotak-login", response_class=HTMLResponse)
    async def kotak_login() -> str:
        return KOTAK_LOGIN_HTML

    @app.get("/", response_class=HTMLResponse)
    @app.get("/history", response_class=HTMLResponse)
    @app.get("/pre-trade-scanner", response_class=HTMLResponse)
    @app.get("/journal", response_class=HTMLResponse)
    @app.get("/journal/analytics", response_class=HTMLResponse)
    @app.get("/pretrade/archive", response_class=HTMLResponse)
    @app.get("/stock/{symbol}", response_class=HTMLResponse)
    async def live_workspace(symbol: str = "") -> str:
        return live_page(workspace)

    @app.get("/demo", response_class=HTMLResponse)
    @app.get("/demo/history", response_class=HTMLResponse)
    @app.get("/demo/journal", response_class=HTMLResponse)
    @app.get("/demo/journal/analytics", response_class=HTMLResponse)
    @app.get("/demo/pretrade/archive", response_class=HTMLResponse)
    @app.get("/demo/stock/{symbol}", response_class=HTMLResponse)
    async def demo_workspace(symbol: str = "") -> str:
        return workspace

    @app.get("/api/signals/{symbol}")
    async def signal_detail(symbol: str) -> dict[str, Any]:
        return signal_detail_payload(service, symbol)

    def signal_detail_payload(engine, symbol):
        detail = engine.get_signal_detail(symbol)
        return {**detail, "observation_ist": indian_time(detail.get("last_seen_at") or detail.get("timestamp"))}

    @app.websocket("/ws/signals")
    async def signal_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        queue = await service.hub.subscribe()
        try:
            await websocket.send_json(service.snapshot())
            while True:
                payload = await queue.get()
                await websocket.send_json(payload)
        except WebSocketDisconnect:
            pass
        finally:
            service.hub.unsubscribe(queue)

    return app
