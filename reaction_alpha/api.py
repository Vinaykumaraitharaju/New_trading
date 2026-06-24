from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .config import ReactionAlphaConfig
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
    <p>Enter the current 6-digit authenticator code after the app is deployed in live mode.</p>
    <form id="form">
      <label for="totp">Current TOTP</label>
      <input id="totp" name="totp" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" required />
      <label for="secret">Admin secret, if configured</label>
      <input id="secret" name="secret" type="password" autocomplete="current-password" />
      <button type="submit">Start Kotak Live Feed</button>
    </form>
    <pre id="result"></pre>
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
      const response = await fetch("/api/kotak/totp", {
        method: "POST",
        headers,
        body: JSON.stringify({ totp_code: totp })
      });
      const payload = await response.json();
      result.textContent = payload.message || JSON.stringify(payload, null, 2);
    });
  </script>
</body>
</html>"""


PRETRADE_SCANNER_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Pre-Trade Scanner</title>
  <style>
    :root { color-scheme: dark; --bg:#070a0f; --panel:#101620; --soft:#151d2a; --line:rgba(255,255,255,.10); --text:#f7f8fb; --muted:#9aa7ba; --gold:#d4af37; --bull:#00ffb2; --bear:#ff4d6d; --cyan:#42d8ff; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--text); background:radial-gradient(circle at top right, rgba(66,216,255,.10), transparent 25%), linear-gradient(180deg,#0c1119,#05070b); min-height:100vh; }
    .wrap { max-width:1420px; margin:0 auto; padding:22px; display:grid; gap:16px; }
    .top { display:flex; align-items:flex-start; justify-content:space-between; gap:14px; flex-wrap:wrap; }
    h1 { margin:0; font-size:34px; letter-spacing:-.03em; }
    .muted { color:var(--muted); line-height:1.55; }
    .nav { display:flex; gap:10px; flex-wrap:wrap; }
    a, button { color:inherit; }
    .btn { border:1px solid var(--line); background:rgba(255,255,255,.04); border-radius:10px; padding:10px 13px; text-decoration:none; font-weight:700; cursor:pointer; }
    .btn.primary { color:#080b10; background:var(--gold); border-color:transparent; }
    .grid { display:grid; grid-template-columns: 360px 1fr; gap:16px; align-items:start; }
    .panel { background:linear-gradient(180deg, rgba(16,22,32,.94), rgba(8,11,17,.96)); border:1px solid var(--line); border-radius:14px; padding:16px; box-shadow:0 24px 70px rgba(0,0,0,.28); }
    .k { font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--muted); }
    .v { margin-top:6px; font-size:26px; font-weight:850; }
    .pill-row { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
    .pill { display:inline-flex; padding:7px 9px; border-radius:999px; border:1px solid var(--line); background:rgba(255,255,255,.035); font-size:12px; color:var(--muted); }
    .pill.good { color:var(--bull); background:rgba(0,255,178,.08); }
    .pill.bad { color:var(--bear); background:rgba(255,77,109,.08); }
    .pill.gold { color:var(--gold); background:rgba(212,175,55,.08); }
    .setups { display:grid; gap:12px; }
    .card { display:grid; grid-template-columns: minmax(180px, 1fr) 1.4fr 1fr; gap:14px; padding:16px; border:1px solid var(--line); border-radius:14px; background:rgba(255,255,255,.035); }
    .sym { font-size:25px; font-weight:900; }
    .score { font-size:30px; font-weight:900; color:var(--gold); }
    .levels { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-top:10px; }
    .level { padding:9px; border-radius:10px; background:rgba(255,255,255,.035); border:1px solid rgba(255,255,255,.06); }
    .level span { display:block; color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.13em; margin-bottom:4px; }
    ul { margin:8px 0 0; padding-left:18px; color:#c7d0df; line-height:1.5; }
    .empty { padding:24px; color:var(--muted); border:1px dashed var(--line); border-radius:14px; }
    .live-strip { display:flex; align-items:center; gap:10px; margin-top:10px; color:var(--muted); font-size:12px; }
    .pulse { width:10px; height:10px; border-radius:999px; background:var(--bull); box-shadow:0 0 0 0 rgba(0,255,178,.55); animation:pulse 1.4s infinite; }
    @keyframes pulse { 0% { box-shadow:0 0 0 0 rgba(0,255,178,.55); } 70% { box-shadow:0 0 0 10px rgba(0,255,178,0); } 100% { box-shadow:0 0 0 0 rgba(0,255,178,0); } }
    @media (max-width: 1000px) { .grid, .card { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div>
        <h1>Pre-Trade Setup Scanner</h1>
        <div class="muted">Upcoming trades ranked by market context, sector strength, price structure, candles, volume, VWAP, risk/reward, and fakeout risk.</div>
        <div class="live-strip"><span class="pulse"></span><span id="liveStatus">Live scan ready</span><span id="countdown"></span></div>
      </div>
      <div class="nav">
        <a class="btn" href="/">Dashboard</a>
        <a class="btn" href="/journal">Journal</a>
        <button class="btn primary" id="refreshBtn">Refresh Scan</button>
      </div>
    </div>
    <div class="grid">
      <aside class="panel">
        <div class="k">Market Bias</div>
        <div class="v" id="marketBias">Loading...</div>
        <div class="muted" id="marketDetail"></div>
        <div class="pill-row" id="marketPills"></div>
        <div style="height:16px"></div>
        <div class="k">Sector Leaders</div>
        <div class="pill-row" id="sectors"></div>
        <div style="height:16px"></div>
        <div class="k">Scan Stats</div>
        <div class="muted" id="stats"></div>
      </aside>
      <main class="setups" id="setups"><div class="empty">Loading scanner...</div></main>
    </div>
  </div>
  <script>
    const fmt = (v) => Number(v || 0).toFixed(2);
    const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[ch]));
    const list = (items) => (items || []).slice(0, 4).map((item) => `<li>${esc(item)}</li>`).join("");
    const refreshEveryMs = 6000;
    let inFlight = false;
    let lastUpdatedText = "Waiting for first scan";
    let nextRefreshAt = 0;
    function labelClass(label) {
      const raw = String(label || "");
      if (raw.includes("READY")) return "good";
      if (raw.includes("AVOID") || raw.includes("RISK") || raw.includes("LATE")) return "bad";
      return "gold";
    }
    async function load(force = false) {
      if (inFlight) return;
      inFlight = true;
      document.getElementById("setups").innerHTML = `<div class="empty">Scanning market...</div>`;
      try {
        const res = await fetch(`/api/pretrade/top${force ? "?force=true" : ""}`);
        const data = await res.json();
        document.getElementById("liveStatus").textContent = data.status === "ok" ? `Scanning live on ${data.source || "market data"}` : "Scanner warming up";
        const market = data.market || {};
        document.getElementById("marketBias").textContent = `${market.bias || "-"} ${market.strength ? Math.round(market.strength) : ""}`;
        document.getElementById("marketDetail").textContent = market.explanation || data.message || "";
        document.getElementById("marketPills").innerHTML = [
          market.risk_state,
          market.regime,
          market.day_type,
          market.volatility
        ].filter(Boolean).map((item) => `<span class="pill gold">${esc(item)}</span>`).join("");
        document.getElementById("sectors").innerHTML = (data.sectors || []).map((s) => `<span class="pill ${String(s.bias).toLowerCase().includes("bull") ? "good" : String(s.bias).toLowerCase().includes("bear") ? "bad" : ""}">${esc(s.sector)} ${Math.round(s.score || 0)}</span>`).join("") || `<span class="pill">No sector read</span>`;
        const stats = data.stats || {};
        lastUpdatedText = data.generated_at ? `Updated ${data.generated_at.replace("T", " ")}` : lastUpdatedText;
        document.getElementById("stats").textContent = `${stats.scanned || 0} scanned | ${stats.shortlisted || 0} shortlisted | ${stats.selected || 0} ranked | ${stats.elapsed_ms || 0} ms | ${lastUpdatedText}`;
        const setups = data.setups || [];
        document.getElementById("setups").innerHTML = setups.map((s) => `
          <section class="card">
            <div>
              <div class="pill ${labelClass(s.scanner_label)}">${esc(s.scanner_label)}</div>
              <div class="sym">${esc(s.symbol)}</div>
              <div class="muted">${esc(s.name)} | ${esc(s.sector)}</div>
              <div class="score">${Math.round(Number(s.final_selector_score || s.confidence || 0))}</div>
              <div class="pill-row">
                <span class="pill">${esc(s.trade_direction || s.direction)}</span>
                <span class="pill">${esc(s.setup_type)}</span>
                <span class="pill">${esc(s.pre_breakout_status)}</span>
              </div>
            </div>
            <div>
              <div class="k">Why This Is Forming</div>
              <div class="muted">${esc(s.prediction_explanation || s.pre_trade_note || s.remarks)}</div>
              <ul>${list(s.trader_logic || s.preparation_signals || s.reasons)}</ul>
              <div class="k" style="margin-top:12px;">What Must Happen</div>
              <ul>${list(s.activation_rules || [s.what_must_happen])}</ul>
            </div>
            <div>
              <div class="levels">
                <div class="level"><span>LTP</span>${fmt(s.ltp)}</div>
                <div class="level"><span>VWAP</span>${fmt(s.vwap)}</div>
                <div class="level"><span>Entry High</span>${fmt(s.entry_high)}</div>
                <div class="level"><span>Entry Low</span>${fmt(s.entry_low)}</div>
                <div class="level"><span>Stop</span>${fmt(s.stop_loss)}</div>
                <div class="level"><span>Target 1</span>${fmt(s.target1)}</div>
                <div class="level"><span>Target 2</span>${fmt(s.target2)}</div>
                <div class="level"><span>R:R</span>${Number(s.rr || 0).toFixed(2)}</div>
              </div>
              <div class="pill-row">
                <span class="pill">Volume ${esc(s.volume_state)}</span>
                <span class="pill">VWAP ${esc(s.vwap_state)}</span>
                <span class="pill">Trap ${esc(s.trap_risk)}</span>
              </div>
              <div class="muted" style="margin-top:10px;">Invalid: ${esc(s.invalid_scenario || s.invalidation_note)}</div>
            </div>
          </section>
        `).join("") || `<div class="empty">${esc(data.message || "No clean pre-trade setup right now.")}</div>`;
      } catch (err) {
        document.getElementById("liveStatus").textContent = "Scanner refresh failed, retrying";
        document.getElementById("setups").innerHTML = `<div class="empty">Scanner refresh failed. Trying again automatically.</div>`;
      } finally {
        inFlight = false;
        nextRefreshAt = Date.now() + refreshEveryMs;
      }
    }
    document.getElementById("refreshBtn").addEventListener("click", () => load(true));
    load();
    setInterval(() => {
      if (document.visibilityState === "visible") {
        const remaining = Math.max(0, Math.ceil((nextRefreshAt - Date.now()) / 1000));
        document.getElementById("countdown").textContent = remaining ? `Next scan in ${remaining}s` : "Scanning now";
        if (!remaining) {
          load(true);
        }
      }
    }, 1000);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        load(true);
      }
    });
  </script>
</body>
</html>"""


UI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Reaction Alpha Engine</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;700;800&family=Orbitron:wght@500;700;800&family=Sora:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      color-scheme: dark;
      --bg: #05070b;
      --bg-deep: #020305;
      --panel: rgba(13, 16, 23, 0.72);
      --panel-soft: rgba(20, 24, 35, 0.74);
      --glass: rgba(255,255,255,0.04);
      --line: rgba(255,255,255,0.08);
      --line-glow: rgba(212,175,55,0.24);
      --gold: #D4AF37;
      --gold-soft: rgba(212,175,55,0.18);
      --bull: #00FFB2;
      --bull-soft: rgba(0,255,178,0.18);
      --bear: #FF4D6D;
      --bear-soft: rgba(255,77,109,0.18);
      --violet: #915EFF;
      --cyan: #42D8FF;
      --text: #F7F8FB;
      --muted: #8D97A8;
    }
    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      font-family: "Sora", system-ui, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 10% 15%, rgba(66,216,255,0.10), transparent 24%),
        radial-gradient(circle at 88% 10%, rgba(145,94,255,0.10), transparent 24%),
        radial-gradient(circle at 45% 100%, rgba(212,175,55,0.08), transparent 32%),
        linear-gradient(180deg, #0b0f16 0%, #070a10 48%, #04060a 100%);
      overflow-x: hidden;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      background:
        linear-gradient(rgba(255,255,255,0.015) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.015) 1px, transparent 1px);
      background-size: 54px 54px;
      mask-image: radial-gradient(circle at center, black, transparent 88%);
      pointer-events: none;
      opacity: .28;
    }
    body::after {
      content: "";
      position: fixed;
      inset: 0;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140' viewBox='0 0 140 140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.82' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)' opacity='.8'/%3E%3C/svg%3E");
      opacity: .045;
      pointer-events: none;
    }
    .orb {
      position: fixed;
      border-radius: 999px;
      filter: blur(70px);
      pointer-events: none;
      opacity: .55;
      animation: drift 16s ease-in-out infinite;
    }
    .orb-a { width: 320px; height: 320px; top: -80px; left: -60px; background: rgba(66,216,255,0.10); }
    .orb-b { width: 280px; height: 280px; top: 8%; right: -70px; background: rgba(145,94,255,0.12); animation-delay: -6s; }
    .orb-c { width: 360px; height: 360px; bottom: -120px; left: 34%; background: rgba(212,175,55,0.08); animation-delay: -10s; }
    @keyframes drift {
      0%,100% { transform: translate3d(0,0,0) scale(1); }
      50% { transform: translate3d(0,16px,0) scale(1.04); }
    }
    .wrap {
      position: relative;
      max-width: 1480px;
      margin: 0 auto;
      padding: 24px;
      display: grid;
      gap: 18px;
    }
    .panel {
      position: relative;
      overflow: hidden;
      background: linear-gradient(180deg, rgba(16,20,29,0.80), rgba(8,10,15,0.86));
      border: 1px solid var(--line);
      border-radius: 20px;
      box-shadow:
        0 24px 70px rgba(0,0,0,0.38),
        inset 0 1px 0 rgba(255,255,255,0.04),
        inset 0 0 0 1px rgba(255,255,255,0.01);
      backdrop-filter: blur(22px);
      -webkit-backdrop-filter: blur(22px);
    }
    .panel::before {
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(118deg, transparent 18%, rgba(255,255,255,0.07) 31%, transparent 46%);
      transform: translateX(-135%);
      animation: sweep 9s linear infinite;
      pointer-events: none;
      opacity: .6;
    }
    @keyframes sweep {
      0% { transform: translateX(-135%); }
      18%, 100% { transform: translateX(160%); }
    }
    .header-grid {
      display: grid;
      grid-template-columns: minmax(0,1.65fr) 420px;
      gap: 18px;
    }
    .hero {
      padding: 30px 32px;
      min-height: 250px;
      background:
        radial-gradient(circle at top left, rgba(66,216,255,0.12), transparent 28%),
        radial-gradient(circle at top right, rgba(212,175,55,0.10), transparent 32%),
        linear-gradient(180deg, rgba(14,18,26,0.86), rgba(8,10,15,0.90));
    }
    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: .32em;
      text-transform: uppercase;
      color: rgba(212,175,55,0.92);
    }
    .eyebrow::before {
      content: "";
      width: 34px;
      height: 1px;
      background: linear-gradient(90deg, rgba(212,175,55,1), rgba(212,175,55,0));
    }
    .hero h1 {
      margin: 18px 0 14px;
      max-width: 860px;
      font-family: "Orbitron", "Sora", sans-serif;
      font-size: 60px;
      line-height: .96;
      letter-spacing: -.05em;
    }
    .hero p {
      max-width: 720px;
      margin: 0;
      font-size: 19px;
      line-height: 1.65;
      color: #A8B3C7;
    }
    .hero-links {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 22px;
    }
    .hero-link {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 11px 16px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.10);
      background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02));
      color: var(--text);
      text-decoration: none;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: .14em;
      text-transform: uppercase;
      transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
    }
    .hero-link:hover {
      transform: translateY(-2px) scale(1.02);
      border-color: rgba(212,175,55,0.28);
      box-shadow: 0 12px 28px rgba(0,0,0,0.22), 0 0 20px rgba(212,175,55,0.08);
    }
    .hero-link.primary {
      color: var(--gold);
      border-color: rgba(212,175,55,0.24);
      box-shadow: 0 0 22px rgba(212,175,55,0.06);
    }
    .status-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }
    .status-card {
      padding: 18px;
      min-height: 118px;
      border-radius: 18px;
      border: 1px solid rgba(255,255,255,0.08);
      background:
        radial-gradient(circle at top right, rgba(255,255,255,0.04), transparent 34%),
        linear-gradient(180deg, rgba(20,25,36,0.86), rgba(10,13,19,0.88));
      transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease;
    }
    .status-card:hover {
      transform: translateY(-3px) scale(1.02);
      border-color: rgba(255,255,255,0.16);
    }
    .status-card .label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .24em;
      color: var(--muted);
    }
    .status-card .value {
      margin-top: 14px;
      font-family: "JetBrains Mono", monospace;
      font-size: 34px;
      font-weight: 800;
      letter-spacing: -.06em;
    }
    .live-dot {
      display: inline-flex;
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: var(--bull);
      box-shadow: 0 0 16px rgba(0,255,178,0.7);
      animation: pulse 1.2s ease-in-out infinite;
      margin-right: 10px;
      vertical-align: middle;
    }
    @keyframes pulse {
      0%,100% { transform: scale(1); opacity: 1; }
      50% { transform: scale(1.35); opacity: .65; }
    }
    .tone-live { color: var(--bull); text-shadow: 0 0 24px rgba(0,255,178,0.15); }
    .tone-blue { color: var(--cyan); text-shadow: 0 0 24px rgba(66,216,255,0.15); }
    .tone-gold { color: var(--gold); text-shadow: 0 0 22px rgba(212,175,55,0.14); }
    .content-grid {
      display: grid;
      grid-template-columns: minmax(0,1.55fr) 420px;
      gap: 18px;
    }
    .sub-grid {
      display: grid;
      gap: 18px;
    }
    .market-card {
      display: grid;
      grid-template-columns: 320px minmax(0,1fr);
      gap: 16px;
      padding: 18px;
    }
    .market-card.open {
      border-color: rgba(212,175,55,0.28);
      box-shadow:
        0 24px 70px rgba(0,0,0,0.38),
        0 0 40px rgba(212,175,55,0.08),
        inset 0 0 0 1px rgba(212,175,55,0.06);
    }
    .market-session-box,
    .market-meta-box {
      border-radius: 18px;
      border: 1px solid rgba(255,255,255,0.07);
      padding: 18px;
      background: linear-gradient(180deg, rgba(21,25,37,0.82), rgba(9,11,17,0.86));
    }
    .market-session-value {
      margin-top: 14px;
      font-family: "Orbitron", sans-serif;
      font-size: 34px;
      font-weight: 800;
      letter-spacing: -.04em;
    }
    .market-session-value.open { color: var(--bull); text-shadow: 0 0 22px rgba(0,255,178,0.18); }
    .market-session-value.closed { color: var(--gold); text-shadow: 0 0 22px rgba(212,175,55,0.12); }
    .market-meta-box .time {
      margin-top: 14px;
      font-family: "JetBrains Mono", monospace;
      font-size: 24px;
      font-weight: 700;
      letter-spacing: -.03em;
    }
    .indices-card,
    .engine-card,
    .hero-card,
    .rail-card,
    .empty-card { padding: 20px; }
    .section-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }
    .section-title .left {
      font-size: 11px;
      letter-spacing: .28em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .section-title .right {
      font-size: 13px;
      color: var(--muted);
    }
    .indices-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0,1fr));
      gap: 14px;
    }
    .index-tile {
      padding: 18px;
      border-radius: 18px;
      border: 1px solid rgba(255,255,255,0.08);
      background:
        radial-gradient(circle at top right, rgba(66,216,255,0.10), transparent 28%),
        linear-gradient(180deg, rgba(20,24,35,0.86), rgba(10,12,18,0.90));
      transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease;
    }
    .index-tile:hover {
      transform: translateY(-4px) scale(1.02);
      border-color: rgba(212,175,55,0.18);
      box-shadow: 0 16px 32px rgba(0,0,0,0.22), 0 0 28px rgba(66,216,255,0.06);
    }
    .index-symbol {
      font-size: 11px;
      letter-spacing: .26em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .index-price {
      margin-top: 14px;
      font-family: "JetBrains Mono", monospace;
      font-size: 34px;
      font-weight: 800;
      letter-spacing: -.06em;
    }
    .index-change {
      margin-top: 10px;
      font-size: 17px;
      font-weight: 700;
    }
    .bullish { color: var(--bull); }
    .bearish { color: var(--bear); }
    .neutral { color: var(--gold); }
    .progress-track {
      margin-top: 16px;
      height: 10px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(255,255,255,0.08);
      box-shadow: inset 0 0 10px rgba(0,0,0,0.18);
    }
    .progress-fill {
      height: 100%;
      border-radius: 999px;
      box-shadow: 0 0 22px currentColor;
      transition: width .6s ease;
    }
    .engine-strip {
      display: grid;
      grid-template-columns: repeat(3, minmax(0,1fr));
      gap: 14px;
    }
    .summary-strip {
      display: grid;
      grid-template-columns: repeat(4, minmax(0,1fr));
      gap: 14px;
    }
    .summary-tile {
      padding: 16px 18px;
      border-radius: 18px;
      border: 1px solid rgba(255,255,255,0.07);
      background: linear-gradient(180deg, rgba(19,23,34,0.84), rgba(8,10,15,0.88));
    }
    .summary-value {
      margin-top: 12px;
      font-family: "JetBrains Mono", monospace;
      font-size: 28px;
      font-weight: 800;
      letter-spacing: -.05em;
    }
    .summary-meta { margin-top: 8px; font-size: 13px; line-height: 1.6; color: #AAB4C5; }
    .engine-tile {
      padding: 18px;
      border-radius: 18px;
      border: 1px solid rgba(255,255,255,0.07);
      background: linear-gradient(180deg, rgba(19,23,34,0.84), rgba(8,10,15,0.88));
      transition: transform .22s ease, box-shadow .22s ease;
    }
    .engine-tile:hover { transform: translateY(-3px) scale(1.02); }
    .engine-title { font-size: 11px; text-transform: uppercase; letter-spacing: .24em; color: var(--muted); }
    .engine-value {
      margin-top: 14px;
      display: flex;
      align-items: center;
      gap: 10px;
      font-family: "Orbitron", sans-serif;
      font-size: 28px;
      font-weight: 700;
      letter-spacing: -.04em;
    }
    .engine-meta { margin-top: 12px; font-size: 14px; line-height: 1.6; color: #AAB4C5; }
    .hero-card {
      background:
        radial-gradient(circle at top right, rgba(212,175,55,0.10), transparent 24%),
        radial-gradient(circle at bottom left, rgba(66,216,255,0.08), transparent 24%),
        linear-gradient(180deg, rgba(16,20,29,0.82), rgba(8,10,15,0.90));
      border-color: rgba(255,255,255,0.10);
      box-shadow:
        0 24px 70px rgba(0,0,0,0.38),
        0 0 40px rgba(212,175,55,0.06),
        inset 0 0 0 1px rgba(255,255,255,0.02);
    }
    .hero-card.active {
      animation: heroPulse 2.6s ease-in-out infinite;
    }
    @keyframes heroPulse {
      0%,100% { box-shadow: 0 24px 70px rgba(0,0,0,0.38), 0 0 34px rgba(212,175,55,0.05), inset 0 0 0 1px rgba(255,255,255,0.02); }
      50% { box-shadow: 0 24px 70px rgba(0,0,0,0.38), 0 0 54px rgba(212,175,55,0.10), inset 0 0 0 1px rgba(255,255,255,0.02); }
    }
    .hero-head {
      display: grid;
      grid-template-columns: minmax(0,1fr) 220px;
      gap: 18px;
      align-items: start;
    }
    .signal-badge {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 10px 16px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: .18em;
      text-transform: uppercase;
      border: 1px solid rgba(255,255,255,0.10);
      backdrop-filter: blur(8px);
    }
    .signal-badge.bull {
      color: var(--bull);
      background: rgba(0,255,178,0.08);
      box-shadow: 0 0 24px rgba(0,255,178,0.07);
    }
    .signal-badge.bear {
      color: var(--bear);
      background: rgba(255,77,109,0.08);
      box-shadow: 0 0 24px rgba(255,77,109,0.06);
    }
    .signal-badge.neutral {
      color: var(--gold);
      background: rgba(212,175,55,0.08);
      box-shadow: 0 0 24px rgba(212,175,55,0.06);
    }
    .hero-symbol {
      margin-top: 18px;
      font-family: "Orbitron", sans-serif;
      font-size: 62px;
      font-weight: 800;
      line-height: .95;
      letter-spacing: -.05em;
    }
    .hero-note {
      margin-top: 12px;
      max-width: 620px;
      font-size: 17px;
      line-height: 1.7;
      color: #AAB4C5;
    }
    .ring-wrap {
      display: grid;
      justify-items: center;
      gap: 10px;
      padding: 10px 6px 0;
    }
    .ring {
      position: relative;
      width: 148px;
      height: 148px;
      display: grid;
      place-items: center;
    }
    .ring svg {
      width: 148px;
      height: 148px;
      transform: rotate(-90deg);
      filter: drop-shadow(0 0 16px rgba(212,175,55,0.14));
    }
    .ring-value {
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      text-align: center;
    }
    .ring-value .big {
      font-family: "JetBrains Mono", monospace;
      font-size: 34px;
      font-weight: 800;
      line-height: 1;
    }
    .ring-value .small {
      margin-top: 6px;
      font-size: 11px;
      letter-spacing: .22em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .meta-note { font-size: 13px; color: var(--muted); text-align: center; }
    .hero-lower {
      display: grid;
      grid-template-columns: 1.1fr 1fr;
      gap: 16px;
      margin-top: 20px;
    }
    .levels-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0,1fr));
      gap: 12px;
    }
    .level-card {
      padding: 16px;
      border-radius: 16px;
      border: 1px solid rgba(255,255,255,0.08);
      background:
        radial-gradient(circle at top right, rgba(255,255,255,0.04), transparent 32%),
        linear-gradient(180deg, rgba(23,28,40,0.86), rgba(10,12,18,0.88));
      transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease;
    }
    .level-card:hover {
      transform: translateY(-2px) scale(1.02);
      border-color: rgba(212,175,55,0.18);
      box-shadow: 0 0 22px rgba(212,175,55,0.05);
    }
    .level-label {
      font-size: 10px;
      letter-spacing: .24em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .level-value {
      margin-top: 12px;
      font-family: "JetBrains Mono", monospace;
      font-size: 28px;
      font-weight: 800;
      letter-spacing: -.05em;
    }
    .thesis-box,
    .strength-box {
      padding: 18px;
      border-radius: 18px;
      border: 1px solid rgba(255,255,255,0.07);
      background: linear-gradient(180deg, rgba(18,22,31,0.84), rgba(9,11,17,0.88));
    }
    .thesis-list {
      display: grid;
      gap: 10px;
      margin-top: 14px;
    }
    .thesis-item {
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.04);
      font-size: 14px;
      line-height: 1.55;
      color: #D5DCE7;
    }
    .thesis-item::before {
      content: "•";
      color: var(--gold);
      margin-right: 10px;
    }
    .strength-line {
      margin-top: 16px;
      display: grid;
      gap: 16px;
    }
    .strength-track {
      height: 12px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(255,255,255,0.08);
      box-shadow: inset 0 0 10px rgba(0,0,0,0.18);
    }
    .strength-fill {
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, rgba(212,175,55,0.55), rgba(212,175,55,1), rgba(66,216,255,0.9));
      box-shadow: 0 0 22px rgba(212,175,55,0.28);
      transition: width .6s ease;
    }
    .sentiment-row {
      display: grid;
      gap: 10px;
    }
    .sentiment-bar {
      height: 12px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(255,255,255,0.08);
      display: grid;
      grid-template-columns: var(--bull-part, 50%) var(--bear-part, 50%);
    }
    .sentiment-bull { background: linear-gradient(90deg, rgba(0,255,178,0.5), rgba(0,255,178,1)); box-shadow: 0 0 18px rgba(0,255,178,0.22); }
    .sentiment-bear { background: linear-gradient(90deg, rgba(255,77,109,0.9), rgba(255,77,109,0.45)); box-shadow: 0 0 18px rgba(255,77,109,0.16); }
    .strength-metrics {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      font-size: 13px;
      color: var(--muted);
    }
    .speed-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.08);
      background: linear-gradient(180deg, rgba(20,25,36,0.88), rgba(10,12,18,0.88));
      font-size: 12px;
      color: #D7DEEA;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02);
    }
    .speed-pill .tag {
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: #92A0B5;
      font-size: 10px;
    }
    .speed-pill .value {
      font-family: "JetBrains Mono", monospace;
      font-weight: 700;
      color: #F6F8FC;
    }
    .speed-pill.fast {
      border-color: rgba(0,255,178,0.18);
      box-shadow: 0 0 18px rgba(0,255,178,0.08), inset 0 0 0 1px rgba(0,255,178,0.05);
    }
    .speed-pill.fast .value { color: var(--bull); }
    .speed-pill.moderate {
      border-color: rgba(66,216,255,0.16);
      box-shadow: 0 0 18px rgba(66,216,255,0.08), inset 0 0 0 1px rgba(66,216,255,0.05);
    }
    .speed-pill.moderate .value { color: var(--cyan); }
    .speed-pill.slow {
      border-color: rgba(212,175,55,0.18);
      box-shadow: 0 0 18px rgba(212,175,55,0.06), inset 0 0 0 1px rgba(212,175,55,0.04);
    }
    .speed-pill.slow .value { color: var(--gold); }
    .speed-line {
      display: grid;
      gap: 8px;
      margin-top: 14px;
    }
    .speed-bar {
      height: 10px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(255,255,255,0.08);
    }
    .speed-fill {
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, rgba(212,175,55,0.55), rgba(66,216,255,0.75), rgba(0,255,178,0.95));
      box-shadow: 0 0 18px rgba(66,216,255,0.18);
    }
    .rail-card { display: grid; gap: 14px; }
    .rail-list { display: grid; gap: 12px; }
    .signal-card {
      padding: 16px;
      border-radius: 18px;
      border: 1px solid rgba(255,255,255,0.08);
      background:
        radial-gradient(circle at top right, rgba(66,216,255,0.06), transparent 26%),
        linear-gradient(180deg, rgba(20,24,35,0.86), rgba(10,12,18,0.88));
      transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease;
      cursor: pointer;
    }
    .signal-card:hover {
      transform: translateY(-3px) scale(1.02);
      border-color: rgba(212,175,55,0.16);
      box-shadow: 0 16px 32px rgba(0,0,0,0.22);
    }
    .signal-card.active {
      border-color: rgba(212,175,55,0.28);
      box-shadow: 0 0 28px rgba(212,175,55,0.08), 0 16px 32px rgba(0,0,0,0.22);
    }
    .signal-card-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
    }
    .signal-name {
      font-family: "Orbitron", sans-serif;
      font-size: 24px;
      font-weight: 700;
      letter-spacing: -.04em;
    }
    .signal-sub {
      margin-top: 8px;
      font-size: 10px;
      letter-spacing: .22em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .score-box {
      text-align: right;
    }
    .score-box .label {
      font-size: 10px;
      letter-spacing: .20em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .score-box .value {
      margin-top: 8px;
      font-family: "JetBrains Mono", monospace;
      font-size: 28px;
      font-weight: 800;
    }
    .empty-card {
      text-align: center;
      padding: 56px 28px;
      background:
        radial-gradient(circle at center, rgba(212,175,55,0.08), transparent 26%),
        linear-gradient(180deg, rgba(16,20,29,0.80), rgba(8,10,15,0.90));
    }
    .empty-ring {
      width: 78px;
      height: 78px;
      margin: 0 auto;
      border-radius: 999px;
      display: grid;
      place-items: center;
      border: 1px solid rgba(212,175,55,0.18);
      background: rgba(212,175,55,0.05);
      box-shadow: 0 0 22px rgba(212,175,55,0.08);
    }
    .scan-dots {
      display: inline-flex;
      gap: 8px;
      margin-top: 16px;
      align-items: center;
    }
    .scan-dots span {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--gold);
      opacity: .35;
      animation: blink 1.4s ease-in-out infinite;
    }
    .scan-dots span:nth-child(2) { animation-delay: .18s; }
    .scan-dots span:nth-child(3) { animation-delay: .36s; }
    @keyframes blink {
      0%,100% { opacity: .25; transform: translateY(0); }
      50% { opacity: 1; transform: translateY(-2px); }
    }
    .mono { font-family: "JetBrains Mono", monospace; }
    .muted { color: var(--muted); }
    .smallcaps {
      font-size: 11px;
      letter-spacing: .28em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .detail-card {
      padding: 20px;
      display: grid;
      gap: 16px;
      background:
        radial-gradient(circle at top right, rgba(212,175,55,0.08), transparent 22%),
        linear-gradient(180deg, rgba(16,20,29,0.82), rgba(8,10,15,0.90));
    }
    .detail-grid {
      display: grid;
      grid-template-columns: 1.15fr .85fr;
      gap: 16px;
    }
    .detail-box {
      padding: 16px;
      border-radius: 16px;
      border: 1px solid rgba(255,255,255,0.07);
      background: rgba(255,255,255,0.03);
    }
    .detail-head {
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: start;
    }
    .detail-symbol {
      font-family: "Orbitron", sans-serif;
      font-size: 34px;
      font-weight: 700;
      letter-spacing: -.04em;
    }
    .detail-summary {
      margin-top: 8px;
      color: #B7C1D0;
      line-height: 1.7;
      font-size: 14px;
    }
    .detail-stats {
      display: grid;
      grid-template-columns: repeat(2, minmax(0,1fr));
      gap: 12px;
    }
    .detail-stat {
      padding: 14px;
      border-radius: 14px;
      border: 1px solid rgba(255,255,255,0.06);
      background: rgba(255,255,255,0.03);
    }
    .detail-stat .k {
      font-size: 10px;
      letter-spacing: .22em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .detail-stat .v {
      margin-top: 10px;
      font-family: "JetBrains Mono", monospace;
      font-size: 22px;
      font-weight: 700;
      letter-spacing: -.04em;
    }
    .component-list {
      display: grid;
      gap: 10px;
    }
    .component-row {
      display: grid;
      grid-template-columns: 84px 1fr 42px;
      align-items: center;
      gap: 10px;
    }
    .component-name {
      font-size: 11px;
      letter-spacing: .18em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .component-track {
      height: 10px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(255,255,255,0.08);
    }
    .component-fill {
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, rgba(212,175,55,0.55), rgba(66,216,255,0.85));
      box-shadow: 0 0 16px rgba(212,175,55,0.18);
    }
    .detail-reasons {
      display: grid;
      gap: 10px;
    }
    .detail-reason {
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.05);
      font-size: 14px;
      line-height: 1.65;
      color: #D2D9E4;
    }
    @media (max-width: 1080px) {
      .header-grid, .content-grid, .market-card, .hero-head, .hero-lower {
        grid-template-columns: 1fr;
      }
      .detail-grid { grid-template-columns: 1fr; }
      .status-grid { grid-template-columns: 1fr 1fr; }
      .indices-grid, .engine-strip { grid-template-columns: 1fr; }
      .levels-grid { grid-template-columns: 1fr 1fr; }
      .hero h1 { font-size: 46px; }
      .hero-symbol { font-size: 48px; }
    }
    @media (max-width: 720px) {
      .wrap { padding: 16px; }
      .hero, .status-grid, .engine-strip, .summary-strip { grid-template-columns: 1fr; }
      .indices-grid { grid-template-columns: 1fr; }
      .levels-grid { grid-template-columns: 1fr 1fr; }
      .hero h1 { font-size: 38px; }
      .hero p { font-size: 16px; }
      .hero-symbol { font-size: 38px; }
      .ring { width: 124px; height: 124px; }
      .ring svg { width: 124px; height: 124px; }
    }
  </style>
</head>
<body>
  <div class="orb orb-a"></div>
  <div class="orb orb-b"></div>
  <div class="orb orb-c"></div>
  <div class="wrap">
    <section class="header-grid">
      <div class="panel hero">
        <div class="eyebrow">Reaction Alpha Engine</div>
        <h1>Top intraday opportunities only.</h1>
        <p>Live event detection, AI reaction scoring, and high-conviction execution framing designed for a professional intraday desk.</p>
        <div class="hero-links">
          <a class="hero-link primary" href="" id="journalLink">Paper Journal</a>
          <a class="hero-link primary" href="/pre-trade-scanner">Pre-Trade Scanner</a>
          <a class="hero-link" href="" id="analyticsLink">Analytics</a>
          <button class="hero-link" id="resetTodayBtn" type="button">Reset Today</button>
          <button class="hero-link" id="resetAllBtn" type="button">Reset All</button>
        </div>
      </div>
      <div class="status-grid">
        <div class="panel status-card">
          <div class="label">Feed</div>
          <div class="value tone-live" id="feedState"><span class="live-dot"></span>LIVE</div>
        </div>
        <div class="panel status-card">
          <div class="label">Mode</div>
          <div class="value tone-blue" id="mode">LIVE</div>
        </div>
        <div class="panel status-card">
          <div class="label">Universe</div>
          <div class="value tone-gold mono" id="universe">0</div>
        </div>
        <div class="panel status-card">
          <div class="label">Signals</div>
          <div class="value tone-gold mono" id="signalCount">0</div>
        </div>
      </div>
    </section>
    <div id="content"></div>
  </div>
  <script>
    const snapshotEndpoint = window.__SNAPSHOT_ENDPOINT__ || "/api/signals/top";
    const websocketPath = window.__WS_ENDPOINT__ ?? "/ws/signals";
    const content = document.getElementById("content");
    const feedState = document.getElementById("feedState");
    const modeEl = document.getElementById("mode");
    const universeEl = document.getElementById("universe");
    const signalCountEl = document.getElementById("signalCount");
    document.getElementById("journalLink").href = window.__JOURNAL_LINK__ || "/journal";
    document.getElementById("analyticsLink").href = window.__ANALYTICS_LINK__ || "/journal/analytics";
    const resetTodayEndpoint = window.__PAPER_RESET_TODAY__ || "";
    const resetAllEndpoint = window.__PAPER_RESET_ALL__ || "";
    const resetTodayBtn = document.getElementById("resetTodayBtn");
    const resetAllBtn = document.getElementById("resetAllBtn");
    if (resetTodayBtn) {
      resetTodayBtn.disabled = !resetTodayEndpoint;
      resetTodayBtn.onclick = async () => {
        if (!resetTodayEndpoint) return;
        await fetch(resetTodayEndpoint, { method: "POST" });
        await initialLoad();
      };
    }
    if (resetAllBtn) {
      resetAllBtn.disabled = !resetAllEndpoint;
      resetAllBtn.onclick = async () => {
        if (!resetAllEndpoint) return;
        await fetch(resetAllEndpoint, { method: "POST" });
        await initialLoad();
      };
    }
    let currentSnapshot = null;
    let selectedSymbol = null;

    const formatChange = (value) => `${value > 0 ? "+" : ""}${Number(value || 0).toFixed(2)}`;
    const toneClass = (change) => change > 0 ? "bullish" : change < 0 ? "bearish" : "neutral";
    const badgeTone = (signal) => {
      if ((signal.signal || "").includes("BULLISH")) return "bull";
      if ((signal.signal || "").includes("BEARISH") || signal.reaction === "REVERSAL") return "bear";
      return "neutral";
    };
    const strengthPct = (score) => Math.max(8, Math.min(100, Math.round((Number(score || 0) / 24) * 100)));
    const ringLength = 2 * Math.PI * 48;

    function speedMetrics(signal) {
      const speed = signal?.context?.speed || {};
      const velocity15 = Number(speed.velocity_15s_bps || 0);
      const velocity30 = Number(speed.velocity_30s_bps || 0);
      const score = Math.max(0, Math.min(100, Math.round((velocity15 / 45) * 100)));
      let tone = "slow";
      let label = "Building";
      if (velocity15 >= 22 || velocity30 >= 38) {
        tone = "fast";
        label = "Fast";
      } else if (velocity15 >= 14 || velocity30 >= 24) {
        tone = "moderate";
        label = "Active";
      }
      return { velocity15, velocity30, score, tone, label };
    }

    function speedPill(signal) {
      const speed = speedMetrics(signal);
      return `<div class="speed-pill ${speed.tone}"><span class="tag">Speed</span><span class="value">${speed.label} ${speed.velocity15.toFixed(1)} bps</span></div>`;
    }

    function formatSetupType(setup) {
      const raw = String(setup || 'EVENT_REACTION');
      return raw.toLowerCase().split('_').map((part) => part ? part[0].toUpperCase() + part.slice(1) : '').join(' ');
    }

    function setupUiTag(setup) {
      const map = {
        SHOCK_BREAKDOWN_CONTINUATION: { label: 'Sudden Breakdown', tone: '#FF4D6D', bg: 'rgba(255,77,109,0.14)' },
        PANIC_BOUNCE_FAILURE: { label: 'Panic Bounce Fail', tone: '#FF9F43', bg: 'rgba(255,159,67,0.14)' },
        FLUSH_EXHAUSTION_REVERSAL: { label: 'Flush Reversal', tone: '#00FFB2', bg: 'rgba(0,255,178,0.14)' },
      };
      return map[String(setup || '').toUpperCase()] || null;
    }

    function setupUiBlock(setup) {
      const label = formatSetupType(setup);
      const tag = setupUiTag(setup);
      if (!tag) return `<span>${label}</span>`;
      return `
        <div style="display:grid; gap:6px;">
          <span>${label}</span>
          <span style="display:inline-flex; width:max-content; padding:4px 10px; border-radius:999px; font-size:10px; letter-spacing:.16em; text-transform:uppercase; color:${tag.tone}; background:${tag.bg}; border:1px solid ${tag.bg};">${tag.label}</span>
        </div>
      `;
    }

    function getMarketSentiment(snapshot) {
      const signals = snapshot.top_signals || [];
      const indices = snapshot.indices || [];
      let bull = 0;
      let bear = 0;
      signals.forEach((signal) => {
        if ((signal.signal || "").includes("BULLISH")) bull += 2;
        else if ((signal.signal || "").includes("BEARISH") || signal.reaction === "REVERSAL") bear += 2;
      });
      indices.forEach((item) => {
        if ((item.change_pct || 0) >= 0) bull += 1;
        else bear += 1;
      });
      const total = Math.max(1, bull + bear);
      return {
        bull: Math.round((bull / total) * 100),
        bear: 100 - Math.round((bull / total) * 100)
      };
    }

    function confidenceRing(percent) {
      const numeric = Math.max(0, Math.min(100, parseInt(String(percent).replace("%",""), 10) || 0));
      const dash = ringLength - (ringLength * numeric / 100);
      return `
        <div class="ring-wrap">
          <div class="ring">
            <svg viewBox="0 0 120 120" fill="none">
              <circle cx="60" cy="60" r="48" stroke="rgba(255,255,255,0.08)" stroke-width="8" />
              <circle cx="60" cy="60" r="48" stroke="url(#goldRing)" stroke-width="8" stroke-linecap="round" stroke-dasharray="${ringLength}" stroke-dashoffset="${dash}" />
              <defs>
                <linearGradient id="goldRing" x1="0" y1="0" x2="120" y2="120">
                  <stop offset="0%" stop-color="#D4AF37" />
                  <stop offset="55%" stop-color="#42D8FF" />
                  <stop offset="100%" stop-color="#00FFB2" />
                </linearGradient>
              </defs>
            </svg>
            <div class="ring-value">
              <div>
                <div class="big">${numeric}%</div>
                <div class="small">Confidence</div>
              </div>
            </div>
          </div>
          <div class="meta-note">Live conviction ring</div>
        </div>
      `;
    }

    function render(snapshot) {
      currentSnapshot = snapshot;
      modeEl.textContent = (snapshot.mode || "-").toUpperCase();
      universeEl.textContent = snapshot.tracked_symbols || 0;
      signalCountEl.textContent = (snapshot.top_signals || []).length;
      const market = snapshot.market_session || { status: "-", detail: "", timestamp_ist: new Date().toISOString() };
      const paper = snapshot.paper_trades || {};
      const sentiment = getMarketSentiment(snapshot);
      const marketOpen = (market.status || "").toUpperCase() === "OPEN";

      const marketPanel = `
        <section class="panel market-card ${marketOpen ? "open" : ""}">
          <div class="market-session-box">
            <div class="smallcaps">Market Session</div>
            <div class="market-session-value ${marketOpen ? "open" : "closed"}">${market.status}</div>
            <div class="muted" style="margin-top:10px; line-height:1.7;">${market.detail}</div>
          </div>
          <div class="market-meta-box">
            <div class="smallcaps">India Time</div>
            <div class="time">${new Date(market.timestamp_ist).toLocaleString()}</div>
            <div class="muted" style="margin-top:10px; line-height:1.7;">This board updates continuously, but only high-conviction opportunities are elevated into the hero signal slot.</div>
          </div>
        </section>
      `;

      const indices = (snapshot.indices || []).map((index) => {
        const progress = Math.max(10, Math.min(100, Math.abs(index.change_pct || 0) * 36 + 18));
        const tone = toneClass(index.change_pct || 0);
        const fill = tone === "bullish"
          ? "linear-gradient(90deg, rgba(0,255,178,0.45), rgba(0,255,178,1))"
          : tone === "bearish"
            ? "linear-gradient(90deg, rgba(255,77,109,0.95), rgba(255,77,109,0.45))"
            : "linear-gradient(90deg, rgba(212,175,55,0.55), rgba(212,175,55,1))";
        return `
          <div class="index-tile">
            <div class="index-symbol">${index.symbol}</div>
            <div class="index-price">${Number(index.price || 0).toFixed(2)}</div>
            <div class="index-change ${tone}">${formatChange(index.change)} (${formatChange(index.change_pct)}%)</div>
            <div class="progress-track"><div class="progress-fill" style="width:${progress}%; color:${tone === "bullish" ? "#00FFB2" : tone === "bearish" ? "#FF4D6D" : "#D4AF37"}; background:${fill};"></div></div>
          </div>
        `;
      }).join("");

      const indexPanel = `
        <section class="panel indices-card">
          <div class="section-title">
            <div class="left">Live Indices</div>
            <div class="right">Market pulse</div>
          </div>
          <div class="indices-grid">${indices}</div>
        </section>
      `;

      const top = topFallback(snapshot.top_signals || []);
      const engineStrip = `
        <section class="engine-strip">
          <div class="panel engine-tile">
            <div class="engine-title">Selection Style</div>
            <div class="engine-value" style="color:var(--gold);">◆ Strict</div>
            <div class="engine-meta">Multi-factor filter with reaction-first confirmation and hard rejection of weak breakouts.</div>
          </div>
          <div class="panel engine-tile">
            <div class="engine-title">Current State</div>
            <div class="engine-value" style="color:${top ? "var(--bull)" : "var(--cyan)"};"><span class="live-dot"></span>${top ? "Tracking Edge" : "Scanning"}</div>
            <div class="engine-meta">${top ? "A qualified opportunity is active and being tracked in real time." : "Engine is watching event triggers, post-event behavior, and structure alignment."}</div>
          </div>
          <div class="panel engine-tile">
            <div class="engine-title">Why ${top ? "Active" : "Empty"}</div>
            <div class="engine-value" style="color:${top ? "var(--gold)" : "var(--bear)"};">${top ? "High Conviction" : "No Edge"}</div>
            <div class="engine-meta">${top ? "Score, reaction, and structure all support a live bias." : "Nothing is strong enough right now to justify a premium trade slot."}</div>
          </div>
        </section>
      `;

      const paperStrip = `
        <section class="summary-strip">
          <div class="panel summary-tile">
            <div class="engine-title">Paper Trades</div>
            <div class="summary-value">${paper.total_trades ?? 0}</div>
            <div class="summary-meta">Executed entries recorded for the current session.</div>
          </div>
          <div class="panel summary-tile">
            <div class="engine-title">Open Trades</div>
            <div class="summary-value bullish">${paper.open_trades ?? 0}</div>
            <div class="summary-meta">Trades that have triggered and are still live.</div>
          </div>
          <div class="panel summary-tile">
            <div class="engine-title">Pending Triggers</div>
            <div class="summary-value neutral">${paper.pending_triggers ?? 0}</div>
            <div class="summary-meta">Scanner-style candidates waiting for confirmed entry.</div>
          </div>
          <div class="panel summary-tile">
            <div class="engine-title">Avg PnL</div>
            <div class="summary-value ${(Number(paper.avg_pnl_points || 0) >= 0) ? "bullish" : "bearish"}">${Number(paper.avg_pnl_points || 0).toFixed(2)}</div>
            <div class="summary-meta">Session paper result after trade costs.</div>
          </div>
        </section>
      `;

      if (!top) {
        content.innerHTML = `
          <section class="content-grid">
            <div class="sub-grid">
              ${marketPanel}
              ${indexPanel}
              ${engineStrip}
              ${paperStrip}
              <section class="panel empty-card">
                <div class="empty-ring">⌁</div>
                <div style="margin-top:18px; font-family:'Orbitron',sans-serif; font-size:30px; letter-spacing:-.04em;">No strong trades yet</div>
                <div class="muted" style="margin-top:12px; max-width:560px; margin-inline:auto; line-height:1.8;">
                  Engine scanning for clean setups. Event quality, structure alignment, and reaction confirmation are still below the promotion threshold.
                </div>
                <div class="scan-dots"><span></span><span></span><span></span></div>
              </section>
            </div>
            <aside class="panel rail-card">
              <div class="section-title">
                <div class="left">Top Signals</div>
                <div class="right">Awaiting promotion</div>
              </div>
              <div class="muted" style="line-height:1.8;">The side rail will populate the moment one or more opportunities clear the live scoring threshold.</div>
            </aside>
          </section>
        `;
        return;
      }

      const thesis = (top.reason || []).map((item) => `<div class="thesis-item">${item}</div>`).join("");
      const railSignals = (snapshot.top_signals || []).map((signal) => `
        <a class="signal-card" href="${window.__DETAIL_LINK_PREFIX__ || '/stock/'}${signal.stock}" style="display:block; color:inherit; text-decoration:none;">
          <div class="signal-card-head">
            <div>
              <div class="signal-name">${signal.stock}</div>
              <div class="signal-sub">${signal.signal}</div>
            </div>
            <div class="score-box">
              <div class="label">Score</div>
              <div class="value">${signal.score}</div>
            </div>
          </div>
          <div style="margin-top:12px;">${speedPill(signal)}</div>
          <div class="progress-track"><div class="progress-fill" style="width:${strengthPct(signal.score)}%; color:${(signal.signal || "").includes("BULLISH") ? "#00FFB2" : (signal.signal || "").includes("BEARISH") ? "#FF4D6D" : "#D4AF37"}; background:${(signal.signal || "").includes("BULLISH") ? "linear-gradient(90deg, rgba(0,255,178,0.45), rgba(0,255,178,1))" : (signal.signal || "").includes("BEARISH") ? "linear-gradient(90deg, rgba(255,77,109,0.95), rgba(255,77,109,0.45))" : "linear-gradient(90deg, rgba(212,175,55,0.55), rgba(212,175,55,1))"};"></div></div>
          <div class="muted" style="margin-top:12px; line-height:1.7;">${signal.expected_move}</div>
          <div class="muted" style="margin-top:8px; font-size:12px; color:#D4AF37;">${signal.context?.pattern?.label || "Pattern not confirmed yet"}</div>
          <div class="muted" style="margin-top:8px; font-size:12px;">${setupUiBlock(signal.setup_type)}<div style="margin-top:6px;">${signal.regime || "BALANCED"} | T1 ${signal.probability?.t1_hit_rate ?? "--"}%</div></div>
        </a>
      `).join("");

      content.innerHTML = `
        <section class="content-grid">
          <div class="sub-grid">
            ${marketPanel}
            ${indexPanel}
            ${engineStrip}
            ${paperStrip}
            <section class="panel hero-card active">
              <div class="hero-head">
                <div>
                  <div class="signal-badge ${badgeTone(top)}">${top.signal}</div>
                  <div class="hero-symbol">${top.stock}</div>
                  <div class="hero-note">${top.event} -> ${top.reaction} -> ${top.expected_move}</div>
                  <div class="muted" style="margin-top:10px; color:#D4AF37; line-height:1.7;">Pattern: ${top.context?.pattern?.label || "Pattern not confirmed yet"}</div>
                  <div class="muted" style="margin-top:10px; line-height:1.8;">${setupUiBlock(top.setup_type)}<div style="margin-top:6px;">Regime: ${top.regime || "BALANCED"} | Runtime T1 ${top.probability?.t1_hit_rate ?? "--"}% | T2 ${top.probability?.t2_hit_rate ?? "--"}%</div></div>
                  <div style="margin-top:14px;">${speedPill(top)}</div>
                </div>
                ${confidenceRing(top.confidence)}
              </div>
              <div class="hero-lower">
                <div>
                  <div class="smallcaps">Trade Levels</div>
                  <div class="levels-grid" style="margin-top:14px;">
                    <div class="level-card"><div class="level-label">Entry Trigger</div><div class="level-value">${Number(top.entry).toFixed(2)}</div></div>
                    <div class="level-card"><div class="level-label">Stop Loss</div><div class="level-value">${Number(top.sl).toFixed(2)}</div></div>
                    <div class="level-card"><div class="level-label">Target 1</div><div class="level-value">${Number(top.t1).toFixed(2)}</div></div>
                    <div class="level-card"><div class="level-label">Target 2</div><div class="level-value">${Number(top.t2).toFixed(2)}</div></div>
                  </div>
                  <div class="thesis-box" style="margin-top:16px;">
                    <div class="section-title" style="margin:0;">
                      <div class="left">Trade Thesis</div>
                      <div class="right">High conviction</div>
                    </div>
                    <div class="thesis-list">${thesis}</div>
                  </div>
                </div>
                <div class="strength-box">
                  <div class="section-title" style="margin:0;">
                    <div class="left">Power Meter</div>
                    <div class="right mono">${top.score}/24</div>
                  </div>
                  <div class="strength-line">
                    <div>
                      <div class="strength-metrics"><span>Strength</span><span class="mono">${strengthPct(top.score)}%</span></div>
                      <div class="strength-track"><div class="strength-fill" style="width:${strengthPct(top.score)}%;"></div></div>
                    </div>
                    <div class="speed-line">
                      <div class="strength-metrics"><span>Speed Bias</span><span class="mono">${speedMetrics(top).velocity15.toFixed(1)} bps / 15s</span></div>
                      <div class="speed-bar"><div class="speed-fill" style="width:${speedMetrics(top).score}%;"></div></div>
                    </div>
                    <div class="sentiment-row" style="--bull-part:${sentiment.bull}%; --bear-part:${sentiment.bear}%;">
                      <div class="strength-metrics"><span>Market Sentiment</span><span><span class="bullish mono">${sentiment.bull}% Bullish</span> / <span class="bearish mono">${sentiment.bear}% Bearish</span></span></div>
                      <div class="sentiment-bar"><div class="sentiment-bull"></div><div class="sentiment-bear"></div></div>
                    </div>
                    <div class="muted" style="line-height:1.8;">This signal has premium placement because the reaction engine, structure filter, pressure read, and regime-adjusted setup model are aligned.</div>
                    <div class="muted" style="line-height:1.8;">Runtime model: T1 ${top.probability?.t1_hit_rate ?? "--"}% | T2 ${top.probability?.t2_hit_rate ?? "--"}% | Basis ${top.probability?.basis ?? "setup model"} | Samples ${top.probability?.sample_size ?? "--"}</div>
                  </div>
                </div>
              </div>
            </section>
          </div>
          <aside class="panel rail-card">
            <div class="section-title">
              <div class="left">Top Signals</div>
              <div class="right">${snapshot.top_signals.length} active</div>
            </div>
            <div class="rail-list">${railSignals}</div>
          </aside>
        </section>
      `;
    }

    function topFallback(signals) {
      return (signals || [])[0] || null;
    }

    async function initialLoad() {
      const res = await fetch(snapshotEndpoint);
      const data = await res.json();
      render(data);
    }

    function startPolling(loader, intervalMs) {
      let running = false;
      setInterval(async () => {
        if (running) return;
        running = true;
        try {
          await loader();
        } finally {
          running = false;
        }
      }, intervalMs);
    }

    initialLoad().catch(() => {
      content.innerHTML = '<section class="panel empty-card"><div style="font-family:Orbitron,sans-serif;font-size:28px;">Unable to load snapshot</div></section>';
    });

    if (websocketPath) {
      const protocol = location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(`${protocol}://${location.host}${websocketPath}`);
      socket.onopen = () => { feedState.innerHTML = '<span class="live-dot"></span>LIVE'; };
      socket.onclose = () => { feedState.textContent = "RETRYING"; };
      socket.onerror = () => { feedState.textContent = "ERROR"; };
      socket.onmessage = (event) => render(JSON.parse(event.data));
    } else {
      feedState.textContent = "DEMO";
      startPolling(() => initialLoad().catch(() => undefined), 1000);
    }
  </script>
</body>
</html>
"""


def demo_html() -> str:
    return UI_HTML.replace(
        "<body>",
        "<body><script>window.__SNAPSHOT_ENDPOINT__='/api/demo/snapshot'; window.__WS_ENDPOINT__=''; window.__DETAIL_LINK_PREFIX__='/demo/stock/'; window.__JOURNAL_LINK__='/demo/journal'; window.__ANALYTICS_LINK__='/demo/journal/analytics'; window.__PAPER_RESET_TODAY__='/api/demo/paper-trades/reset-today'; window.__PAPER_RESET_ALL__='/api/demo/paper-trades/reset-all';</script>",
        1,
    )


DETAIL_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Signal Detail</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;700;800&family=Orbitron:wght@500;700;800&family=Sora:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      color-scheme: dark;
      --gold: #D4AF37;
      --bull: #00FFB2;
      --bear: #FF4D6D;
      --text: #F7F8FB;
      --muted: #8D97A8;
      --line: rgba(255,255,255,0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Sora", system-ui, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 10% 15%, rgba(66,216,255,0.10), transparent 24%),
        radial-gradient(circle at 88% 10%, rgba(145,94,255,0.10), transparent 24%),
        radial-gradient(circle at 45% 100%, rgba(212,175,55,0.08), transparent 32%),
        linear-gradient(180deg, #0b0f16 0%, #070a10 48%, #04060a 100%);
      min-height: 100vh;
    }
    .wrap { max-width: 1180px; margin: 0 auto; padding: 24px; display: grid; gap: 18px; }
    .panel {
      position: relative; overflow: hidden; border-radius: 20px; border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(16,20,29,0.80), rgba(8,10,15,0.86));
      box-shadow: 0 24px 70px rgba(0,0,0,0.38), inset 0 1px 0 rgba(255,255,255,0.04);
      backdrop-filter: blur(22px); -webkit-backdrop-filter: blur(22px);
    }
    .back {
      display: inline-flex; align-items: center; gap: 8px; width: fit-content;
      padding: 10px 14px; border-radius: 999px; border: 1px solid var(--line);
      color: var(--text); text-decoration: none; background: rgba(255,255,255,0.03);
    }
    .hero { padding: 24px; display: grid; gap: 16px; }
    .head { display: flex; justify-content: space-between; gap: 16px; align-items: start; }
    .eyebrow { font-size: 11px; letter-spacing: .28em; text-transform: uppercase; color: var(--muted); }
    .badge {
      display: inline-flex; align-items: center; padding: 10px 16px; border-radius: 999px; font-size: 11px; font-weight: 700;
      letter-spacing: .18em; text-transform: uppercase; border: 1px solid var(--line); margin-top: 12px;
    }
    .bull { color: var(--bull); background: rgba(0,255,178,0.08); }
    .bear { color: var(--bear); background: rgba(255,77,109,0.08); }
    .neutral { color: var(--gold); background: rgba(212,175,55,0.08); }
    .symbol { margin-top: 12px; font-family: "Orbitron", sans-serif; font-size: 56px; font-weight: 800; letter-spacing: -.05em; }
    .subtitle { margin-top: 10px; color: #B4BECC; line-height: 1.75; max-width: 720px; }
    .meta { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; }
    .box, .meta-card { padding: 16px; border-radius: 16px; border: 1px solid var(--line); background: rgba(255,255,255,0.03); }
    .k { font-size: 10px; text-transform: uppercase; letter-spacing: .22em; color: var(--muted); }
    .v { margin-top: 10px; font-family: "JetBrains Mono", monospace; font-size: 26px; font-weight: 800; letter-spacing: -.04em; }
    .grid { display: grid; grid-template-columns: 1.2fr .8fr; gap: 18px; }
    .micro-grid { display: grid; grid-template-columns: 1.2fr .8fr; gap: 18px; }
    .list { display: grid; gap: 10px; margin-top: 14px; }
    .item { padding: 12px 14px; border-radius: 14px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.04); line-height: 1.65; color: #D2D9E4; }
    .component-row { display: grid; grid-template-columns: 84px 1fr 42px; align-items: center; gap: 10px; margin-top: 10px; }
    .component-track { height: 10px; border-radius: 999px; overflow: hidden; background: rgba(255,255,255,0.08); }
    .component-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, rgba(212,175,55,0.55), rgba(66,216,255,0.85)); box-shadow: 0 0 16px rgba(212,175,55,0.18); }
    .speed-pill { display:inline-flex; align-items:center; gap:8px; padding:8px 12px; border-radius:999px; border:1px solid rgba(255,255,255,0.08); background:linear-gradient(180deg, rgba(20,25,36,0.88), rgba(10,12,18,0.88)); font-size:12px; color:#D7DEEA; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02); }
    .speed-pill .tag { letter-spacing:0.18em; text-transform:uppercase; color:#92A0B5; font-size:10px; }
    .speed-pill .value { font-family:"JetBrains Mono", monospace; font-weight:700; color:#F6F8FC; }
    .speed-pill.fast { border-color:rgba(0,255,178,0.18); box-shadow:0 0 18px rgba(0,255,178,0.08), inset 0 0 0 1px rgba(0,255,178,0.05); }
    .speed-pill.fast .value { color:var(--bull); }
    .speed-pill.moderate { border-color:rgba(66,216,255,0.16); box-shadow:0 0 18px rgba(66,216,255,0.08), inset 0 0 0 1px rgba(66,216,255,0.05); }
    .speed-pill.moderate .value { color:var(--cyan); }
    .speed-pill.slow { border-color:rgba(212,175,55,0.18); box-shadow:0 0 18px rgba(212,175,55,0.06), inset 0 0 0 1px rgba(212,175,55,0.04); }
    .speed-pill.slow .value { color:var(--gold); }
    .micro-chart { margin-top: 16px; min-height: 380px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.05); background:
      linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01)),
      linear-gradient(180deg, rgba(66,216,255,0.05), transparent 45%);
      padding: 14px; overflow: hidden; }
    .chart-header { display:flex; flex-wrap:wrap; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:12px; }
    .chart-title { font-family:"Orbitron",sans-serif; font-size:22px; letter-spacing:-.04em; }
    .chart-subtitle { margin-top:6px; color:#AEB8C8; font-size:13px; }
    .ohlc-strip { display:flex; flex-wrap:wrap; gap:10px; justify-content:flex-end; }
    .ohlc-pill { display:inline-flex; gap:8px; align-items:center; padding:8px 10px; border-radius:999px; border:1px solid rgba(255,255,255,0.06); background:rgba(255,255,255,0.03); font-family:"JetBrains Mono",monospace; font-size:12px; }
    .ohlc-pill span:first-child { color:#8D97A8; }
    .chart-shell { position: relative; height: 330px; border-radius: 14px; overflow: hidden; background:
      linear-gradient(180deg, rgba(10,14,20,0.88), rgba(8,11,16,0.94)); }
    .chart-shell svg { display: block; width: 100%; height: 100%; }
    .chart-toolbar { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:12px; margin-top:14px; }
    .timeframes { display:flex; flex-wrap:wrap; gap:8px; }
    .tf-btn {
      display:inline-flex; align-items:center; justify-content:center; min-width:52px; padding:8px 12px; border-radius:999px;
      border:1px solid rgba(255,255,255,0.08); background:rgba(255,255,255,0.03); color:#D3DBE7; font:inherit;
      font-size:12px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; cursor:pointer;
    }
    .tf-btn.active { color:var(--gold); border-color:rgba(212,175,55,0.28); box-shadow:0 0 18px rgba(212,175,55,0.12); background:rgba(212,175,55,0.08); }
    .tf-note { color:#AEB8C8; font-size:13px; line-height:1.7; }
    .chart-legend { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
    .legend-item { display: inline-flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 999px; border: 1px solid rgba(255,255,255,0.06); background: rgba(255,255,255,0.03); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: #C7D0DE; }
    .legend-dot { width: 10px; height: 10px; border-radius: 999px; box-shadow: 0 0 12px currentColor; }
    .quote-ribbon { display:flex; gap:10px; margin-top:10px; flex-wrap:wrap; }
    .quote-box { min-width:136px; padding:10px 12px; border-radius:14px; border:1px solid rgba(255,255,255,0.06); font-family:"JetBrains Mono",monospace; background:rgba(255,255,255,0.03); }
    .quote-box .label { font-size:10px; letter-spacing:.18em; color:#8D97A8; text-transform:uppercase; }
    .quote-box .price { margin-top:6px; font-size:24px; font-weight:800; }
    .micro-stat-grid { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 12px; margin-top: 16px; }
    .micro-stat { padding: 14px; border-radius: 14px; border: 1px solid rgba(255,255,255,0.05); background: rgba(255,255,255,0.03); }
    .micro-label { font-size: 10px; text-transform: uppercase; letter-spacing: .2em; color: var(--muted); }
    .micro-value { margin-top: 8px; font-family: "JetBrains Mono", monospace; font-size: 22px; font-weight: 800; letter-spacing: -.04em; }
    .micro-sub { margin-top: 6px; color: #AEB8C8; font-size: 13px; }
    .empty { padding: 42px 24px; text-align: center; color: var(--muted); line-height: 1.8; }
    @media (max-width: 900px) { .head, .grid, .micro-grid, .meta, .micro-stat-grid { grid-template-columns: 1fr; display: grid; } .symbol { font-size: 40px; } .micro-chart { min-height: 300px; } .chart-shell { height: 260px; } }
  </style>
</head>
<body>
  <div class="wrap">
    <a class="back" id="backLink" href="/">← Back to dashboard</a>
    <div id="app"></div>
  </div>
  <script>
    const app = document.getElementById("app");
    const symbol = window.__DETAIL_SYMBOL__;
    const endpoint = window.__DETAIL_ENDPOINT__;
    document.getElementById("backLink").href = window.__BACK_LINK__ || "/";
    let selectedFrame = "1m";

    function badgeTone(signal) {
      if ((signal.signal || "").includes("BULLISH")) return "bull";
      if ((signal.signal || "").includes("BEARISH") || signal.reaction === "REVERSAL") return "bear";
      return "neutral";
    }

    function speedMetrics(signal) {
      const speed = signal?.context?.speed || {};
      const velocity15 = Number(speed.velocity_15s_bps || 0);
      const velocity30 = Number(speed.velocity_30s_bps || 0);
      let tone = "slow";
      let label = "Building";
      if (velocity15 >= 22 || velocity30 >= 38) {
        tone = "fast";
        label = "Fast";
      } else if (velocity15 >= 14 || velocity30 >= 24) {
        tone = "moderate";
        label = "Active";
      }
      return { velocity15, velocity30, tone, label };
    }

    function speedPill(signal) {
      const speed = speedMetrics(signal);
      return `<div class="speed-pill ${speed.tone}"><span class="tag">Speed</span><span class="value">${speed.label} ${speed.velocity15.toFixed(1)} bps</span></div>`;
    }

    function formatSetupType(setup) {
      const raw = String(setup || 'EVENT_REACTION');
      return raw.toLowerCase().split('_').map((part) => part ? part[0].toUpperCase() + part.slice(1) : '').join(' ');
    }

    function setupUiTag(setup) {
      const map = {
        SHOCK_BREAKDOWN_CONTINUATION: { label: 'Sudden Breakdown', tone: 'var(--bear)', bg: 'rgba(255,77,109,0.14)' },
        PANIC_BOUNCE_FAILURE: { label: 'Panic Bounce Fail', tone: 'var(--gold)', bg: 'rgba(212,175,55,0.14)' },
        FLUSH_EXHAUSTION_REVERSAL: { label: 'Flush Reversal', tone: 'var(--bull)', bg: 'rgba(0,255,178,0.14)' },
      };
      return map[String(setup || '').toUpperCase()] || null;
    }

    function setupUiBlock(setup) {
      const label = formatSetupType(setup);
      const tag = setupUiTag(setup);
      if (!tag) return `<span>${label}</span>`;
      return `
        <div style="display:grid; gap:6px;">
          <span>${label}</span>
          <span style="display:inline-flex; width:max-content; padding:4px 10px; border-radius:999px; font-size:10px; letter-spacing:.16em; text-transform:uppercase; color:${tag.tone}; background:${tag.bg}; border:1px solid ${tag.bg};">${tag.label}</span>
        </div>
      `;
    }

    function buildPriceActionChart(chartData, signal, frame) {
      const bars = Array.isArray(chartData?.[frame]) ? chartData[frame] : [];
      if (!bars.length) {
        return '<div class="empty" style="padding:24px 0;">Waiting for 1-second price action...</div>';
      }
      const width = 940;
      const height = 330;
      const padLeft = 56;
      const padRight = 82;
      const padTop = 16;
      const padBottom = 28;
      const plotWidth = width - padLeft - padRight;
      const volumeHeight = 72;
      const priceHeight = height - padTop - padBottom - volumeHeight - 16;
      const volumeTop = padTop + priceHeight + 16;
      const chartBars = bars.slice(-(frame === "1m" ? 90 : frame === "5m" ? 72 : frame === "15m" ? 60 : 48));
      const latest = chartBars[chartBars.length - 1];
      const levels = [signal.entry, signal.sl, signal.t1, signal.t2].map((v) => Number(v || 0)).filter((v) => v > 0);
      const lows = chartBars.map((bar) => Number(bar.low || bar.close || 0)).concat(levels);
      const highs = chartBars.map((bar) => Number(bar.high || bar.close || 0)).concat(levels);
      const minLow = Math.min(...lows);
      const maxHigh = Math.max(...highs);
      const range = Math.max(maxHigh - minLow, 0.01);
      const toY = (price) => padTop + ((maxHigh - price) / range) * priceHeight;
      const candleGap = 3;
      const candleWidth = Math.max(5, Math.min(14, (plotWidth / chartBars.length) - candleGap));
      const xStep = plotWidth / chartBars.length;
      const maxVolume = Math.max(...chartBars.map((bar) => Number(bar.volume || 0)), 1);

      const grid = Array.from({ length: 5 }, (_, idx) => {
        const y = padTop + (priceHeight / 4) * idx;
        const price = maxHigh - (range / 4) * idx;
        return `
          <line x1="${padLeft}" y1="${y}" x2="${width - padRight}" y2="${y}" stroke="rgba(255,255,255,0.07)" stroke-dasharray="4 6" />
          <text x="${width - padRight + 8}" y="${y + 4}" fill="rgba(180,190,204,0.88)" font-size="11" font-family="JetBrains Mono, monospace">${price.toFixed(2)}</text>
        `;
      }).join("");

      const candles = chartBars.map((bar, idx) => {
        const open = Number(bar.open || bar.close || 0);
        const close = Number(bar.close || open);
        const high = Number(bar.high || Math.max(open, close));
        const low = Number(bar.low || Math.min(open, close));
        const x = padLeft + idx * xStep + (xStep - candleWidth) / 2;
        const centerX = x + candleWidth / 2;
        const wickTop = toY(high);
        const wickBottom = toY(low);
        const bodyTop = toY(Math.max(open, close));
        const bodyBottom = toY(Math.min(open, close));
        const bodyHeight = Math.max(bodyBottom - bodyTop, 2);
        const rising = close >= open;
        const fill = rising ? "rgba(0,255,178,0.92)" : "rgba(255,77,109,0.92)";
        const stroke = rising ? "rgba(66,216,255,0.65)" : "rgba(212,175,55,0.55)";
        return `
          <g>
            <line x1="${centerX}" y1="${wickTop}" x2="${centerX}" y2="${wickBottom}" stroke="${stroke}" stroke-width="1.4" />
            <rect x="${x}" y="${bodyTop}" width="${candleWidth}" height="${bodyHeight}" rx="2" fill="${fill}" stroke="${stroke}" stroke-width="1" />
          </g>
        `;
      }).join("");

      const volumes = chartBars.map((bar, idx) => {
        const open = Number(bar.open || bar.close || 0);
        const close = Number(bar.close || open);
        const volume = Number(bar.volume || 0);
        const x = padLeft + idx * xStep + (xStep - candleWidth) / 2;
        const barHeight = Math.max((volume / maxVolume) * volumeHeight, 2);
        const y = volumeTop + (volumeHeight - barHeight);
        const fill = close >= open ? "rgba(0,255,178,0.52)" : "rgba(255,77,109,0.52)";
        return `<rect x="${x}" y="${y}" width="${candleWidth}" height="${barHeight}" rx="2" fill="${fill}" />`;
      }).join("");

      const levelDefs = [
        { label: "Entry", value: Number(signal.entry || 0), color: "#42D8FF" },
        { label: "SL", value: Number(signal.sl || 0), color: "#FF4D6D" },
        { label: "T1", value: Number(signal.t1 || 0), color: "#D4AF37" },
        { label: "T2", value: Number(signal.t2 || 0), color: "#00FFB2" }
      ].filter((item) => item.value > 0);

      const levelLines = levelDefs.map((item) => {
        const y = toY(item.value);
        return `
          <line x1="${padLeft}" y1="${y}" x2="${width - padRight}" y2="${y}" stroke="${item.color}" stroke-width="1.5" stroke-dasharray="7 6" opacity="0.9" />
          <text x="${width - padRight + 8}" y="${Math.max(12, y - 6)}" fill="${item.color}" font-size="10" font-family="JetBrains Mono, monospace">${item.label}</text>
        `;
      }).join("");

      const lastClose = Number(latest.close || latest.open || 0);
      const priceLineY = toY(lastClose);
      const lastTone = lastClose >= Number(latest.open || lastClose) ? "#00FFB2" : "#FF4D6D";
      const priceLine = `
        <line x1="${padLeft}" y1="${priceLineY}" x2="${width - padRight}" y2="${priceLineY}" stroke="${lastTone}" stroke-width="1.2" stroke-dasharray="3 5" opacity="0.85" />
        <rect x="${width - padRight + 2}" y="${priceLineY - 11}" width="76" height="22" rx="6" fill="${lastTone}" />
        <text x="${width - padRight + 40}" y="${priceLineY + 4}" fill="#081018" font-size="11" text-anchor="middle" font-family="JetBrains Mono, monospace" font-weight="700">${lastClose.toFixed(2)}</text>
      `;

      const timeLabels = chartBars.filter((_, idx) => idx === 0 || idx === Math.floor(chartBars.length / 2) || idx === chartBars.length - 1).map((bar, idx, arr) => {
        const actualIndex = chartBars.indexOf(bar);
        const x = padLeft + actualIndex * xStep + xStep / 2;
        const raw = String(bar.timestamp || '').split('T')[1] || '';
        const stamp = raw.slice(0, 8);
        return `<text x="${x}" y="${height - 8}" fill="rgba(141,151,168,0.92)" font-size="10" text-anchor="middle" font-family="JetBrains Mono, monospace">${stamp}</text>`;
      }).join("");

      const legend = `
        <div class="chart-header">
          <div>
            <div class="chart-title">${signal.stock} Intraday Chart</div>
            <div class="chart-subtitle">${frame} candles, live session context, trade levels and volume</div>
          </div>
          <div class="ohlc-strip">
            <div class="ohlc-pill"><span>O</span><strong>${Number(latest.open || 0).toFixed(2)}</strong></div>
            <div class="ohlc-pill"><span>H</span><strong>${Number(latest.high || 0).toFixed(2)}</strong></div>
            <div class="ohlc-pill"><span>L</span><strong>${Number(latest.low || 0).toFixed(2)}</strong></div>
            <div class="ohlc-pill"><span>C</span><strong style="color:${lastTone};">${lastClose.toFixed(2)}</strong></div>
          </div>
        </div>
        <div class="chart-toolbar">
          <div class="timeframes">
            ${["1m","5m","15m","1h"].map((tf) => `<button class="tf-btn ${tf === frame ? "active" : ""}" data-frame="${tf}">${tf}</button>`).join("")}
          </div>
          <div class="tf-note">${bars.length} observed ${frame} candles from today only. This chart grows as the engine sees more of the session.</div>
        </div>
        <div class="quote-ribbon">
          <div class="quote-box"><div class="label">Entry</div><div class="price" style="color:#42D8FF;">${Number(signal.entry || 0).toFixed(2)}</div></div>
          <div class="quote-box"><div class="label">Stop</div><div class="price" style="color:#FF4D6D;">${Number(signal.sl || 0).toFixed(2)}</div></div>
          <div class="quote-box"><div class="label">Target 1</div><div class="price" style="color:#D4AF37;">${Number(signal.t1 || 0).toFixed(2)}</div></div>
          <div class="quote-box"><div class="label">Target 2</div><div class="price" style="color:#00FFB2;">${Number(signal.t2 || 0).toFixed(2)}</div></div>
        </div>
        <div class="chart-legend">
          <div class="legend-item"><span class="legend-dot" style="color:#42D8FF; background:#42D8FF;"></span>Entry</div>
          <div class="legend-item"><span class="legend-dot" style="color:#FF4D6D; background:#FF4D6D;"></span>Stop Loss</div>
          <div class="legend-item"><span class="legend-dot" style="color:#D4AF37; background:#D4AF37;"></span>Target 1</div>
          <div class="legend-item"><span class="legend-dot" style="color:#00FFB2; background:#00FFB2;"></span>Target 2</div>
          <div class="legend-item"><span class="legend-dot" style="color:#6EF7D5; background:rgba(0,255,178,0.52);"></span>Volume</div>
        </div>
      `;

      return `
        <div class="chart-shell">
          <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Live 1-second chart">
            <defs>
              <linearGradient id="chartFillTop" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="rgba(66,216,255,0.12)" />
                <stop offset="100%" stop-color="rgba(66,216,255,0)" />
              </linearGradient>
            </defs>
            <rect x="${padLeft}" y="${padTop}" width="${plotWidth}" height="${priceHeight}" rx="14" fill="rgba(255,255,255,0.015)" />
            <rect x="${padLeft}" y="${volumeTop}" width="${plotWidth}" height="${volumeHeight}" rx="10" fill="rgba(255,255,255,0.015)" />
            ${grid}
            ${levelLines}
            ${priceLine}
            ${candles}
            ${volumes}
            <text x="${padLeft}" y="${volumeTop - 4}" fill="rgba(141,151,168,0.92)" font-size="10" font-family="JetBrains Mono, monospace">Volume</text>
            ${timeLabels}
          </svg>
        </div>
        ${legend}
      `;
    }

    function render(signal) {
      if (!signal || signal.state === "NOT_ACTIVE") {
        app.innerHTML = `<section class="panel empty"><div class="eyebrow">Selected Stock</div><div style="margin-top:12px; font-family:'Orbitron',sans-serif; font-size:32px;">${symbol}</div><div style="margin-top:12px;">No active high-conviction signal for this stock right now. This page tracks this symbol only and updates live when it qualifies.</div></section>`;
        return;
      }

      const reasons = (signal.reason || []).map((item) => `<div class="item">${item}</div>`).join("");
      const components = Object.entries(signal.components || {}).map(([name, score]) => {
        const width = Math.max(0, Math.min(100, (Math.max(Number(score), 0) / 6) * 100));
        return `<div class="component-row"><div class="k" style="font-size:11px;">${name}</div><div class="component-track"><div class="component-fill" style="width:${width}%;"></div></div><div class="v" style="margin:0; font-size:16px; text-align:right;">${score}</div></div>`;
      }).join("");
      const bars = Array.isArray(signal.price_action_1s) ? signal.price_action_1s : [];
      const firstPrice = bars.length ? Number(bars[0].open || bars[0].close || signal.last_price || signal.entry || 0) : Number(signal.last_price || signal.entry || 0);
      const lastPrice = Number(signal.last_price || signal.entry || 0);
      const microMove = lastPrice - firstPrice;
      const microPct = firstPrice > 0 ? (microMove / firstPrice) * 100 : 0;
      const moveClass = microMove > 0 ? "bull" : microMove < 0 ? "bear" : "neutral";
      const chart = buildPriceActionChart(signal.chart_data || {}, signal, selectedFrame);
      const liveBars = bars.length;

      app.innerHTML = `
        <section class="panel hero">
          <div class="head">
            <div>
              <div class="eyebrow">Single Stock Live Detail</div>
              <div class="badge ${badgeTone(signal)}">${signal.signal}</div>
              <div class="symbol">${signal.stock}</div>
              <div class="subtitle">${signal.event} -> ${signal.reaction} -> ${signal.expected_move}</div>
              <div style="margin-top:10px; color:var(--gold); line-height:1.7;">Pattern: ${signal.context?.pattern?.label || "Pattern not confirmed yet"}</div>
              <div style="margin-top:14px;">${speedPill(signal)}</div>
            </div>
            <div class="box" style="min-width:220px;">
              <div class="k">Last Update</div>
              <div class="v" style="font-size:22px;">${new Date(signal.updated_at).toLocaleTimeString()}</div>
              <div style="margin-top:8px; color:var(--gold); font-weight:700;">${signal.confidence} confidence</div>
              <div style="margin-top:10px; color:#AEB8C8; line-height:1.7;">${setupUiBlock(signal.setup_type)}<div style="margin-top:6px;">${signal.regime || "BALANCED"}</div></div>
            </div>
          </div>
          <div class="meta">
            <div class="meta-card"><div class="k">Trend</div><div class="v">${signal.trend}</div></div>
            <div class="meta-card"><div class="k">Score</div><div class="v">${signal.score}</div></div>
            <div class="meta-card"><div class="k">Entry Trigger</div><div class="v">${Number(signal.entry).toFixed(2)}</div></div>
            <div class="meta-card"><div class="k">Stop Loss</div><div class="v">${Number(signal.sl).toFixed(2)}</div></div>
            <div class="meta-card"><div class="k">Target 1</div><div class="v">${Number(signal.t1).toFixed(2)}</div></div>
            <div class="meta-card"><div class="k">Target 2</div><div class="v">${Number(signal.t2).toFixed(2)}</div></div>
            <div class="meta-card"><div class="k">Reaction</div><div class="v">${signal.reaction}</div></div>
            <div class="meta-card"><div class="k">Trade State</div><div class="v">${signal.state || "READY"}</div></div>
            <div class="meta-card"><div class="k">Regime</div><div class="v">${signal.regime || "BALANCED"}</div></div>
            <div class="meta-card"><div class="k">Runtime T1</div><div class="v">${signal.probability?.t1_hit_rate ?? "--"}%</div></div>
            <div class="meta-card"><div class="k">Runtime T2</div><div class="v">${signal.probability?.t2_hit_rate ?? "--"}%</div></div>
            <div class="meta-card"><div class="k">Samples</div><div class="v">${signal.probability?.sample_size ?? "--"}</div></div>
          </div>
        </section>
        <section class="micro-grid">
          <div class="panel box">
            <div class="eyebrow">1 Second Price Action</div>
            <div class="micro-chart">${chart}</div>
            <div class="micro-stat-grid">
              <div class="micro-stat">
                <div class="micro-label">Last Price</div>
                <div class="micro-value">${lastPrice.toFixed(2)}</div>
                <div class="micro-sub">Selected symbol live tick read</div>
              </div>
              <div class="micro-stat">
                <div class="micro-label">60s Move</div>
                <div class="micro-value ${moveClass}">${microMove >= 0 ? "+" : ""}${microMove.toFixed(2)}</div>
                <div class="micro-sub ${moveClass}">${microPct >= 0 ? "+" : ""}${microPct.toFixed(2)}%</div>
              </div>
              <div class="micro-stat">
                <div class="micro-label">Tape Speed</div>
                <div class="micro-value">${Number(signal.tape_speed || 0)}</div>
                <div class="micro-sub">${liveBars} bars in current micro window</div>
              </div>
              <div class="micro-stat">
                <div class="micro-label">Velocity 15s</div>
                <div class="micro-value">${speedMetrics(signal).velocity15.toFixed(1)} bps</div>
                <div class="micro-sub">${speedMetrics(signal).label} mover profile</div>
              </div>
            </div>
          </div>
          <div class="panel box">
            <div class="eyebrow">Micro Read</div>
            <div class="list">
              <div class="item">This panel aggregates the latest tick stream into 1-second bars so you can see immediate displacement, pause, and acceleration in the selected stock.</div>
              <div class="item">Use tape speed with the 60-second move to judge whether the setup is gaining participation or stalling near your entry trigger.</div>
              <div class="item">Treat this as execution context, not prediction. A rising tape with clean hold around entry improves the odds of follow-through toward T1 first.</div>
              <div class="item">Market context: sector ${signal.context?.sector || "Unknown"} | breadth ${signal.context?.market?.market_breadth ?? "--"}% | sector strength ${signal.context?.market?.sector_strength ?? "--"}% | aligned timeframes ${signal.context?.market?.aligned_timeframes ?? "--"}.</div>
              <div class="item">Current runtime model for this setup: T1 ${signal.probability?.t1_hit_rate ?? "--"}%, T2 ${signal.probability?.t2_hit_rate ?? "--"}%, regime ${signal.regime || "BALANCED"}, basis ${signal.probability?.basis ?? "setup model"}.</div>
            </div>
          </div>
        </section>
        <section class="grid">
          <div class="panel box"><div class="eyebrow">Trade Thesis</div><div class="list">${reasons}</div></div>
          <div class="panel box"><div class="eyebrow">Component Breakdown</div><div style="margin-top:14px;">${components}</div></div>
        </section>
      `;
    }

    document.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const frame = target.getAttribute("data-frame");
      if (!frame || !["1m","5m","15m","1h"].includes(frame)) return;
      selectedFrame = frame;
      load();
    });

    async function load() {
      try {
        const res = await fetch(endpoint);
        const data = await res.json();
        render(data);
      } catch {
        app.innerHTML = '<section class="panel empty">Unable to load this stock detail right now.</section>';
      }
    }

    function startPolling(loader, intervalMs) {
      let running = false;
      setInterval(async () => {
        if (running) return;
        running = true;
        try {
          await loader();
        } finally {
          running = false;
        }
      }, intervalMs);
    }

    load();
    startPolling(load, 1000);
  </script>
</body>
</html>
"""


def detail_html(symbol: str, endpoint: str, back_link: str) -> str:
    return (
        DETAIL_HTML.replace("window.__DETAIL_SYMBOL__", f"'{symbol.upper()}'")
        .replace("window.__DETAIL_ENDPOINT__", f"'{endpoint}'")
        .replace("window.__BACK_LINK__", f"'{back_link}'")
    )


def paper_html(
    endpoint: str,
    back_link: str,
    reset_today_endpoint: str = "",
    reset_all_endpoint: str = "",
    analytics_link: str = "",
) -> str:
    return (
        PAPER_HTML.replace("window.__PAPER_ENDPOINT__", f"'{endpoint}'")
        .replace("window.__PAPER_BACK__", f"'{back_link}'")
        .replace("window.__PAPER_RESET_TODAY__", f"'{reset_today_endpoint}'")
        .replace("window.__PAPER_RESET_ALL__", f"'{reset_all_endpoint}'")
        .replace("window.__PAPER_ANALYTICS_PAGE__", f"'{analytics_link}'")
    )


def analytics_html(endpoint: str, back_link: str, dashboard_link: str) -> str:
    return (
        ANALYTICS_TABLE_HTML.replace("window.__PAPER_ENDPOINT__", f"'{endpoint}'")
        .replace("window.__BACK_LINK__", f"'{back_link}'")
        .replace("window.__DASHBOARD_LINK__", f"'{dashboard_link}'")
    )


PAPER_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Paper Trade Journal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;700;800&family=Orbitron:wght@500;700;800&family=Sora:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root { color-scheme: dark; --bg:#06080d; --panel:rgba(15,18,26,.84); --line:rgba(255,255,255,.08); --text:#f7f8fb; --muted:#91a0b4; --gold:#D4AF37; --bull:#00FFB2; --bear:#FF4D6D; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:"Sora",system-ui,sans-serif; color:var(--text); background:radial-gradient(circle at top right, rgba(66,216,255,.08), transparent 24%), linear-gradient(180deg,#0b0f16 0%,#06080d 100%); min-height:100vh; }
    .wrap { max-width:1320px; margin:0 auto; padding:24px; display:grid; gap:18px; }
    .back { display:inline-flex; align-items:center; gap:8px; width:fit-content; padding:10px 14px; border-radius:999px; border:1px solid var(--line); color:var(--text); text-decoration:none; background:rgba(255,255,255,.03); }
    .panel { border-radius:20px; border:1px solid var(--line); background:linear-gradient(180deg, rgba(16,20,29,0.82), rgba(8,10,15,0.9)); box-shadow:0 24px 70px rgba(0,0,0,.35); backdrop-filter:blur(20px); padding:20px; }
    .title { font-family:"Orbitron",sans-serif; font-size:40px; letter-spacing:-.04em; }
    .muted { color:var(--muted); line-height:1.7; }
    .stats { display:grid; grid-template-columns:repeat(6, minmax(0,1fr)); gap:12px; }
    .stat { padding:16px; border-radius:16px; border:1px solid rgba(255,255,255,.06); background:rgba(255,255,255,.03); }
    .label { font-size:10px; text-transform:uppercase; letter-spacing:.22em; color:var(--muted); }
    .value { margin-top:10px; font-family:"JetBrains Mono",monospace; font-size:28px; font-weight:800; }
    .green { color:var(--bull); }
    .red { color:var(--bear); }
    .gold { color:var(--gold); }
    table { width:100%; border-collapse:collapse; }
    th, td { padding:12px 10px; border-bottom:1px solid rgba(255,255,255,.06); text-align:left; font-size:14px; vertical-align:middle; }
    th { color:var(--muted); font-size:11px; letter-spacing:.18em; text-transform:uppercase; }
    .badge { display:inline-flex; padding:6px 10px; border-radius:999px; font-size:11px; font-weight:700; letter-spacing:.08em; border:1px solid rgba(255,255,255,.08); }
    .badge.open { color:var(--bull); background:rgba(0,255,178,.08); }
    .badge.closed { color:var(--gold); background:rgba(212,175,55,.08); }
    .badge.loss { color:var(--bear); background:rgba(255,77,109,.08); }
    .delta-cell { min-width: 320px; }
    .delta-inline { display:flex; flex-wrap:wrap; gap:8px; }
    .delta-chip { padding:6px 8px; border-radius:10px; border:1px solid rgba(255,255,255,.05); background:rgba(255,255,255,.025); min-width:96px; }
    .delta-label { display:block; font-size:9px; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); margin-bottom:4px; }
    .delta-value { font-family:"JetBrains Mono",monospace; color:var(--text); font-size:12px; }
    .setup-grid { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
    .setup-item { display:flex; align-items:center; justify-content:space-between; gap:14px; padding:12px 0; border-bottom:1px solid rgba(255,255,255,.05); }
    .setup-breakdown-list { display:grid; gap:14px; margin-top:12px; }
    .setup-card { padding:16px; border-radius:16px; border:1px solid rgba(255,255,255,.06); background:rgba(255,255,255,.025); }
    .setup-card-head { display:flex; flex-wrap:wrap; align-items:flex-start; justify-content:space-between; gap:12px; }
    .setup-card-title { font-weight:800; font-size:18px; }
    .setup-card-sub { margin-top:6px; color:var(--muted); font-size:13px; line-height:1.6; }
    .trigger-pill { display:inline-flex; align-items:center; gap:8px; padding:7px 10px; border-radius:999px; border:1px solid rgba(255,255,255,.08); font-size:11px; letter-spacing:.12em; text-transform:uppercase; font-weight:700; }
    .trigger-pill.breakout { color:var(--bull); background:rgba(0,255,178,.08); }
    .trigger-pill.breakdown { color:var(--bear); background:rgba(255,77,109,.08); }
    .setup-pill-row { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
    .mini-pill { display:inline-flex; align-items:center; padding:6px 10px; border-radius:999px; border:1px solid rgba(255,255,255,.08); background:rgba(255,255,255,.03); font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
    .setup-count-grid { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:10px; margin-top:14px; }
    .setup-count { padding:10px 12px; border-radius:12px; border:1px solid rgba(255,255,255,.05); background:rgba(255,255,255,.02); min-height:72px; }
    .setup-count-k { font-size:10px; letter-spacing:.16em; text-transform:uppercase; color:var(--muted); }
    .setup-count-v { margin-top:8px; font-family:"JetBrains Mono",monospace; font-size:22px; font-weight:800; }
    .setup-count-sub { margin-top:4px; font-size:12px; color:var(--muted); }
    .metric-grid { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:12px; margin-top:14px; }
    .metric-tile { padding:14px; border-radius:14px; border:1px solid rgba(255,255,255,.05); background:rgba(255,255,255,.025); min-height:92px; }
    .metric-k { font-size:11px; line-height:1.45; color:var(--muted); }
    .metric-v { margin-top:10px; font-family:"JetBrains Mono",monospace; font-size:24px; font-weight:800; }
    .empty-state { padding:18px; border-radius:14px; border:1px dashed rgba(255,255,255,.08); background:rgba(255,255,255,.015); color:var(--muted); }
    .toolbar { display:grid; gap:16px; margin-top:14px; }
    .toolbar-main { display:flex; flex-wrap:wrap; align-items:flex-start; justify-content:space-between; gap:16px; }
    .toolbar-actions { display:flex; flex-wrap:wrap; gap:12px; }
    .action-btn { display:inline-flex; align-items:center; justify-content:center; gap:8px; min-width:148px; padding:12px 16px; border-radius:14px; border:1px solid rgba(255,255,255,.10); background:linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.025)); color:var(--text); font:inherit; font-weight:700; letter-spacing:.08em; text-transform:uppercase; cursor:pointer; text-decoration:none; }
    .action-btn:hover { border-color:rgba(212,175,55,.28); box-shadow:0 10px 24px rgba(0,0,0,.24), 0 0 18px rgba(212,175,55,.08); }
    .action-btn.primary { color:var(--gold); border-color:rgba(212,175,55,.24); background:linear-gradient(180deg, rgba(212,175,55,.12), rgba(212,175,55,.05)); }
    .action-btn:disabled { opacity:.45; cursor:not-allowed; }
    @media (max-width: 980px) { .stats, .setup-grid, .metric-grid { grid-template-columns:1fr 1fr; } }
    @media (max-width: 700px) { .stats, .setup-grid, .metric-grid { grid-template-columns:1fr; } .title { font-size:30px; } table { display:block; overflow:auto; } }
  </style>
</head>
<body>
  <div class="wrap">
    <a class="back" id="backLink" href="/">← Back to dashboard</a>
    <section class="panel">
      <div class="title">Paper Trade Journal</div>
      <div class="muted" style="margin-top:10px;">The engine now records its own signals as paper trades, waits for trigger entry, then tracks T1, T2, SL, expiry, and time exits so we can measure real hit rates.</div>
    </section>
    <div id="app"></div>
  </div>
  <script>
    const app = document.getElementById("app");
    const paperEndpoint = window.__PAPER_ENDPOINT__ || '/api/paper-trades';
    const resetTodayEndpoint = window.__PAPER_RESET_TODAY__ || '';
    const resetAllEndpoint = window.__PAPER_RESET_ALL__ || '';
    const analyticsPageLink = window.__PAPER_ANALYTICS_PAGE__ || '';
    document.getElementById("backLink").href = window.__PAPER_BACK__ || "/";
    async function postReset(url) {
      if (!url) return;
      await fetch(url, { method: 'POST' });
      await load();
    }
    function badge(result, state) {
      const tone = state === "OPEN" ? "open" : result === "SL_HIT" ? "loss" : "closed";
      return `<span class="badge ${tone}">${result || state}</span>`;
    }
    function formatSetupType(setup) {
      const raw = String(setup || 'EVENT_REACTION');
      return raw.toLowerCase().split('_').map((part) => part ? part[0].toUpperCase() + part.slice(1) : '').join(' ');
    }
    function setupUiTag(setup) {
      const map = {
        SHOCK_BREAKDOWN_CONTINUATION: { label: 'Sudden Breakdown', tone: 'var(--bear)', bg: 'rgba(255,77,109,0.14)' },
        PANIC_BOUNCE_FAILURE: { label: 'Panic Bounce Fail', tone: 'var(--gold)', bg: 'rgba(212,175,55,0.14)' },
        FLUSH_EXHAUSTION_REVERSAL: { label: 'Flush Reversal', tone: 'var(--bull)', bg: 'rgba(0,255,178,0.14)' },
      };
      return map[String(setup || '').toUpperCase()] || null;
    }
    function setupUiCell(setup) {
      const label = formatSetupType(setup);
      const tag = setupUiTag(setup);
      if (!tag) return label;
      return `
        <div style="display:grid; gap:6px;">
          <div>${label}</div>
          <span style="display:inline-flex; width:max-content; padding:4px 10px; border-radius:999px; font-size:10px; letter-spacing:.16em; text-transform:uppercase; color:${tag.tone}; background:${tag.bg}; border:1px solid ${tag.bg};">${tag.label}</span>
        </div>
      `;
    }
    function diff(a, b) {
      return Math.abs(Number(a || 0) - Number(b || 0));
    }
    function render(payload) {
      const a = payload.analytics || {};
      const pending = payload.pending_triggers || [];
      const pendingRows = [...pending]
        .sort((a, b) => String(a.symbol || "").localeCompare(String(b.symbol || "")) || String(a.created_at || "").localeCompare(String(b.created_at || "")))
        .map((item) => `
          <tr>
            <td style="font-weight:700;">${item.symbol}</td>
            <td>${setupUiCell(item.setup_type)}</td>
            <td>${item.direction}</td>
            <td>${item.regime}</td>
            <td>${item.status || "Awaiting trigger"}</td>
            <td>${item.live_price == null ? "--" : Number(item.live_price).toFixed(2)}</td>
            <td class="gold">${Number(item.entry_trigger || 0).toFixed(2)}</td>
            <td>${item.distance_points == null ? "--" : Number(item.distance_points).toFixed(2)}</td>
            <td>${item.distance_pct == null ? "--" : `${Number(item.distance_pct).toFixed(2)}%`}</td>
            <td>${item.created_at ? new Date(item.created_at).toLocaleTimeString() : "-"}</td>
          </tr>
        `).join("") || `<tr><td colspan="10" class="muted">No pending triggers right now.</td></tr>`;
      const rows = (payload.trades || []).map((trade) => `
        <tr>
          <td>${trade.symbol}</td>
          <td>${setupUiCell(trade.setup_type)}</td>
          <td>${trade.regime}</td>
          <td>${trade.direction}</td>
          <td>${badge(trade.result, trade.state)}</td>
          <td>${trade.live_price == null ? "--" : Number(trade.live_price).toFixed(2)}</td>
          <td>${Number(trade.entry_trigger || 0).toFixed(2)}</td>
          <td>${Number(trade.stop_loss || 0).toFixed(2)}</td>
          <td>${Number(trade.target1 || 0).toFixed(2)}</td>
          <td>${Number(trade.target2 || 0).toFixed(2)}</td>
          <td class="delta-cell">
            <div class="delta-inline">
              <div class="delta-chip"><span class="delta-label">E → T1</span><span class="delta-value">${diff(trade.entry_trigger, trade.target1).toFixed(2)}</span></div>
              <div class="delta-chip"><span class="delta-label">E → T2</span><span class="delta-value">${diff(trade.entry_trigger, trade.target2).toFixed(2)}</span></div>
              <div class="delta-chip"><span class="delta-label">T1 → T2</span><span class="delta-value">${diff(trade.target1, trade.target2).toFixed(2)}</span></div>
              <div class="delta-chip"><span class="delta-label">E → SL</span><span class="delta-value">${diff(trade.entry_trigger, trade.stop_loss).toFixed(2)}</span></div>
              <div class="delta-chip"><span class="delta-label">L → E</span><span class="delta-value">${trade.live_price == null ? "--" : diff(trade.live_price, trade.entry_trigger).toFixed(2)}</span></div>
            </div>
          </td>
          <td class="${Number(trade.pnl_points || 0) >= 0 ? "green" : "red"}">${Number(trade.pnl_points || 0).toFixed(2)}</td>
          <td>${trade.t1_hit ? "Yes" : "No"}</td>
          <td>${trade.t2_hit ? "Yes" : "No"}</td>
          <td>${trade.created_at ? new Date(trade.created_at).toLocaleString() : "-"}</td>
        </tr>
      `).join("") || `<tr><td colspan="15" class="muted">No paper trades recorded yet.</td></tr>`;
      const funnel = a.funnel || {};
      const outcomes = a.outcomes || {};
      const metricTile = (label, value, tone = "", suffix = "") => `
        <div class="metric-tile">
          <div class="metric-k">${label}</div>
          <div class="metric-v ${tone}">${value}${suffix}</div>
        </div>
      `;
      app.innerHTML = `
        <section class="panel">
          <div class="toolbar">
            <div class="toolbar-main">
              <div>
                <div class="label">Current Session</div>
                <div class="value" style="font-size:22px;">${a.session_date ?? "-"}</div>
                <div class="muted" style="margin-top:6px;">The journal now defaults to today only, so each trading day starts clean while older records remain in history until reset.</div>
              </div>
            </div>
            <div class="toolbar-actions">
              ${analyticsPageLink ? `<a class="action-btn" href="${analyticsPageLink}">Analytics View</a>` : ``}
              <button class="action-btn primary" id="resetTodayBtn" ${resetTodayEndpoint ? "" : "disabled"}>Reset Today</button>
              <button class="action-btn" id="resetAllBtn" ${resetAllEndpoint ? "" : "disabled"}>Reset All</button>
            </div>
          </div>
        </section>
        <section class="panel stats">
          <div class="stat"><div class="label">Signals</div><div class="value">${funnel.signals ?? 0}</div></div>
          <div class="stat"><div class="label">Entered</div><div class="value green">${funnel.entered ?? 0}</div></div>
          <div class="stat"><div class="label">Pending</div><div class="value gold">${funnel.pending ?? 0}</div></div>
          <div class="stat"><div class="label">Expired</div><div class="value red">${funnel.expired ?? 0}</div></div>
          <div class="stat"><div class="label">Conversion</div><div class="value">${funnel.entry_conversion_pct ?? 0}%</div></div>
          <div class="stat"><div class="label">Open Trades</div><div class="value green">${a.open_trades ?? 0}</div></div>
          <div class="stat"><div class="label">Closed Trades</div><div class="value gold">${a.closed_trades ?? 0}</div></div>
        </section>
        <section class="setup-grid">
          <section class="panel">
            <div class="label">Execution Snapshot</div>
            <div class="metric-grid">
              ${metricTile("Average PnL", Number(a.avg_pnl_points ?? 0).toFixed(2), (a.avg_pnl_points ?? 0) >= 0 ? "green" : "red")}
              ${metricTile("T1 Hit Rate", Number(a.t1_hit_rate ?? 0).toFixed(0), "green", "%")}
              ${metricTile("T2 Hit Rate", Number(a.t2_hit_rate ?? 0).toFixed(0), "gold", "%")}
              ${metricTile("SL Hit %", Number(outcomes.sl_hit_pct ?? 0).toFixed(0), "red", "%")}
            </div>
          </section>
          <section class="panel">
            <div class="label">Analytics Navigation</div>
            <div class="metric-grid">
              ${metricTile("Use Analytics View", "Setup + SL")}
              ${metricTile("Best / Weak Setups", "Visible")}
              ${metricTile("SL Context", "Clear")}
            </div>
          </section>
        </section>
        <section class="panel">
          <div class="label">Pending Triggers</div>
          <div class="muted" style="margin-top:8px;">These are qualified ideas waiting for entry. They are not counted as trades until the trigger actually hits.</div>
          <div style="margin-top:14px; overflow:auto;">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th><th>Setup</th><th>Direction</th><th>Regime</th><th>Status</th>
                  <th>Live</th><th>Entry</th><th>Distance</th><th>Distance %</th><th>Created</th>
                </tr>
              </thead>
              <tbody>${pendingRows}</tbody>
            </table>
          </div>
        </section>
        <section class="panel">
          <div class="label">Recent Paper Trades</div>
          <div style="margin-top:14px; overflow:auto;">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th><th>Setup</th><th>Regime</th><th>Direction</th><th>Status</th><th>Live</th>
                  <th>Entry</th><th>SL</th><th>T1</th><th>T2</th><th>Delta</th><th>PnL</th><th>T1</th><th>T2</th><th>Created</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </section>
      `;
      const resetTodayBtn = document.getElementById('resetTodayBtn');
      const resetAllBtn = document.getElementById('resetAllBtn');
      if (resetTodayBtn) resetTodayBtn.onclick = () => postReset(resetTodayEndpoint);
      if (resetAllBtn) resetAllBtn.onclick = () => postReset(resetAllEndpoint);
    }
    async function load() {
      const res = await fetch(paperEndpoint);
      const data = await res.json();
      render(data);
    }
    function startPolling(loader, intervalMs) {
      let running = false;
      setInterval(async () => {
        if (running) return;
        running = true;
        try {
          await loader();
        } finally {
          running = false;
        }
      }, intervalMs);
    }
    load().catch(() => { app.innerHTML = '<section class="panel"><div class="muted">Unable to load paper-trade journal right now.</div></section>'; });
    startPolling(() => load().catch(() => undefined), 1500);
  </script>
</body>
</html>
"""


ANALYTICS_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Paper Trade Analytics</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;700;800&family=Orbitron:wght@500;700;800&family=Sora:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root { color-scheme: dark; --bg:#06080d; --panel:rgba(15,18,26,.84); --line:rgba(255,255,255,.08); --text:#f7f8fb; --muted:#91a0b4; --gold:#D4AF37; --bull:#00FFB2; --bear:#FF4D6D; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:"Sora",system-ui,sans-serif; color:var(--text); background:radial-gradient(circle at top right, rgba(66,216,255,.08), transparent 24%), linear-gradient(180deg,#0b0f16 0%,#06080d 100%); min-height:100vh; }
    .wrap { max-width:1420px; margin:0 auto; padding:24px; display:grid; gap:18px; }
    .nav-row { display:flex; flex-wrap:wrap; gap:12px; }
    .nav-link { display:inline-flex; align-items:center; gap:8px; width:fit-content; padding:10px 14px; border-radius:999px; border:1px solid var(--line); color:var(--text); text-decoration:none; background:rgba(255,255,255,.03); }
    .panel { border-radius:20px; border:1px solid var(--line); background:linear-gradient(180deg, rgba(16,20,29,0.82), rgba(8,10,15,0.9)); box-shadow:0 24px 70px rgba(0,0,0,.35); backdrop-filter:blur(20px); padding:20px; }
    .title { font-family:"Orbitron",sans-serif; font-size:40px; letter-spacing:-.04em; }
    .muted { color:var(--muted); line-height:1.7; }
    .label { font-size:10px; text-transform:uppercase; letter-spacing:.22em; color:var(--muted); }
    .stats { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:12px; }
    .stat { padding:16px; border-radius:16px; border:1px solid rgba(255,255,255,.06); background:rgba(255,255,255,.03); }
    .value { margin-top:10px; font-family:"JetBrains Mono",monospace; font-size:28px; font-weight:800; }
    .green { color:var(--bull); }
    .red { color:var(--bear); }
    .gold { color:var(--gold); }
    .setup-breakdown-list, .sl-breakdown-list, .summary-list { display:grid; gap:14px; margin-top:12px; }
    .setup-card, .sl-card { padding:16px; border-radius:16px; border:1px solid rgba(255,255,255,.06); background:rgba(255,255,255,.025); }
    .setup-card-head, .sl-card-head { display:flex; flex-wrap:wrap; align-items:flex-start; justify-content:space-between; gap:12px; }
    .setup-card-title, .sl-card-title { font-weight:800; font-size:18px; }
    .setup-card-sub, .sl-card-sub { margin-top:6px; color:var(--muted); font-size:13px; line-height:1.6; }
    .trigger-pill { display:inline-flex; align-items:center; gap:8px; padding:7px 10px; border-radius:999px; border:1px solid rgba(255,255,255,.08); font-size:11px; letter-spacing:.12em; text-transform:uppercase; font-weight:700; }
    .trigger-pill.breakout { color:var(--bull); background:rgba(0,255,178,.08); }
    .trigger-pill.breakdown { color:var(--bear); background:rgba(255,77,109,.08); }
    .pill-row { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
    .mini-pill { display:inline-flex; align-items:center; padding:6px 10px; border-radius:999px; border:1px solid rgba(255,255,255,.08); background:rgba(255,255,255,.03); font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
    .score-pill { display:inline-flex; align-items:center; padding:8px 12px; border-radius:999px; border:1px solid rgba(255,255,255,.08); font-size:11px; letter-spacing:.12em; text-transform:uppercase; font-weight:800; }
    .score-pill.good { color:var(--bull); background:rgba(0,255,178,.08); }
    .score-pill.mixed { color:var(--gold); background:rgba(212,175,55,.08); }
    .score-pill.weak { color:var(--bear); background:rgba(255,77,109,.08); }
    .count-grid { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:10px; margin-top:14px; }
    .count-card { padding:10px 12px; border-radius:12px; border:1px solid rgba(255,255,255,.05); background:rgba(255,255,255,.02); min-height:72px; }
    .count-k { font-size:10px; letter-spacing:.16em; text-transform:uppercase; color:var(--muted); }
    .count-v { margin-top:8px; font-family:"JetBrains Mono",monospace; font-size:22px; font-weight:800; }
    .count-sub { margin-top:4px; font-size:12px; color:var(--muted); }
    .summary-card { padding:16px; border-radius:16px; border:1px solid rgba(255,255,255,.06); background:rgba(255,255,255,.025); }
    .summary-head { display:flex; flex-wrap:wrap; justify-content:space-between; gap:12px; align-items:flex-start; }
    .summary-title { font-weight:800; font-size:17px; }
    .summary-sub { margin-top:6px; color:var(--muted); font-size:13px; line-height:1.6; }
    .sl-context-list { display:grid; gap:10px; margin-top:14px; }
    .sl-context { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:10px; padding:12px; border-radius:12px; border:1px solid rgba(255,255,255,.05); background:rgba(255,255,255,.02); }
    .sl-context-main { font-weight:700; }
    .sl-context-sub { color:var(--muted); font-size:12px; margin-top:4px; }
    .empty-state { padding:18px; border-radius:14px; border:1px dashed rgba(255,255,255,.08); background:rgba(255,255,255,.015); color:var(--muted); }
    .two-col { display:grid; grid-template-columns:1.15fr .85fr; gap:18px; }
    .three-col { display:grid; grid-template-columns:.85fr 1.15fr .9fr; gap:18px; }
    @media (max-width: 980px) { .stats, .count-grid, .two-col, .three-col { grid-template-columns:1fr 1fr; } }
    @media (max-width: 700px) { .stats, .count-grid, .two-col, .three-col { grid-template-columns:1fr; } .title { font-size:30px; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="nav-row">
      <a class="nav-link" id="journalLink" href="/">← Back to journal</a>
      <a class="nav-link" id="dashboardLink" href="/">Dashboard</a>
    </div>
    <section class="panel">
      <div class="title">Journal Analytics</div>
      <div class="muted" style="margin-top:10px;">Use this page to read setup performance and stop-loss behavior clearly by setup, regime, direction, and breakout or breakdown side.</div>
    </section>
    <div id="app"></div>
  </div>
  <script>
    const app = document.getElementById("app");
    const paperEndpoint = window.__PAPER_ENDPOINT__ || '/api/paper-trades';
    document.getElementById("journalLink").href = window.__BACK_LINK__ || '/journal';
    document.getElementById("dashboardLink").href = window.__DASHBOARD_LINK__ || '/';

    function bucketLabel(bucket) {
      return String(bucket || '').replaceAll('_', ' ').replace(/\b\w/g, (ch) => ch.toUpperCase());
    }
    function bucketMeaning(bucket) {
      const map = {
        clean_invalidation: 'Setup failed cleanly before making meaningful progress.',
        reversal_after_progress: 'Trade moved our way first, then reversed enough to hit stop-loss.',
        fast_failure: 'Trade invalidated quickly soon after entry.',
        gave_back_after_t1: 'Trade reached T1 territory, then gave everything back into stop-loss.',
        uncategorized: 'Stop-loss was recorded, but the move did not fit a named bucket yet.',
      };
      return map[String(bucket || '').toLowerCase()] || 'Stop-loss behavior bucket.';
    }
    function setupScore(item) {
      const entries = Number(item.entries || 0);
      if (!entries) return { score: -999, label: 'No Entries Yet', tone: 'mixed', reason: 'No confirmed entries yet, so do not judge this row.' };
      const t2 = Number(item.t2_hit_rate || 0);
      const t1 = Number(item.t1_hit_rate || 0);
      const sl = Number(item.sl_hit_rate || 0);
      const time = Number(item.time_exit_rate || 0);
      const open = Number(item.open_trades || 0);
      const closed = Math.max(entries - open, 0);
      const expectancy = Number(item.expectancy_points || 0);
      const score = (t2 * 1.45) + (t1 * 0.55) - (sl * 1.45) - (time * 0.45) + Math.min(entries * 3, 18) + Math.max(Math.min(expectancy, 8), -8) - Math.min(open * 2, 8);
      if (!closed && open > 0) {
        return { score: score - 12, label: 'Tracking', tone: 'mixed', reason: `Trade is still open. Wait for result before calling it best or weak.` };
      }
      if (sl >= 55 || (entries >= 2 && sl > t2 && sl >= 40) || (entries >= 3 && t1 <= 20 && t2 <= 10)) {
        return { score, label: 'Avoid', tone: 'weak', reason: `Avoid for now: SL ${sl}% is dominating follow-through.` };
      }
      if (entries >= 3 && t2 >= 30 && sl <= 35) {
        return { score, label: 'Best', tone: 'good', reason: `Best proven row: T2 ${t2}% with controlled SL ${sl}% across ${entries} entries.` };
      }
      if (t2 >= 50 && sl <= 25) {
        return { score, label: 'Promising', tone: 'good', reason: `Promising but low sample: T2 ${t2}%, SL ${sl}% across ${entries} entr${entries === 1 ? 'y' : 'ies'}.` };
      }
      if (t1 >= 50 && sl <= 25) {
        return { score, label: 'Scalp Only', tone: 'mixed', reason: `T1 is working (${t1}%) but T2 proof is limited. Prefer quick booking.` };
      }
      return { score, label: 'Wait', tone: 'mixed', reason: `Not best yet: T1 ${t1}%, T2 ${t2}%, SL ${sl}%, Time ${time}%.` };
    }
    function render(payload) {
      const a = payload.analytics || {};
      const funnel = a.funnel || {};
      const setupsWithScore = (a.setup_breakdown || []).map((item) => ({ ...item, review: setupScore(item) }));
      const bestSetups = [...setupsWithScore]
        .filter((item) => Number(item.entries || 0) > 0)
        .sort((a, b) => b.review.score - a.review.score)
        .slice(0, 4);
      const weakSetups = [...setupsWithScore]
        .filter((item) => Number(item.entries || 0) > 0)
        .sort((a, b) => a.review.score - b.review.score)
        .slice(0, 4);
      const bestSetupCards = bestSetups.map((item) => `
        <div class="summary-card">
          <div class="summary-head">
            <div>
              <div class="summary-title">${item.setup_type}</div>
              <div class="summary-sub">${item.regime} | ${item.direction} | ${item.trigger_side}</div>
            </div>
            <div class="score-pill ${item.review.tone}">${item.review.label}</div>
          </div>
          <div class="pill-row">
            <span class="mini-pill">Entries ${item.entries}</span>
            <span class="mini-pill">T2 ${item.t2_hit_rate}%</span>
            <span class="mini-pill">SL ${item.sl_hit_rate}%</span>
            <span class="mini-pill">Time ${item.time_exit_rate}%</span>
          </div>
          <div class="summary-sub">${item.review.reason}</div>
        </div>
      `).join("") || `<div class="empty-state">No qualifying setups yet.</div>`;
      const weakSetupCards = weakSetups.map((item) => `
        <div class="summary-card">
          <div class="summary-head">
            <div>
              <div class="summary-title">${item.setup_type}</div>
              <div class="summary-sub">${item.regime} | ${item.direction} | ${item.trigger_side}</div>
            </div>
            <div class="score-pill ${item.review.tone}">${item.review.label}</div>
          </div>
          <div class="pill-row">
            <span class="mini-pill">Entries ${item.entries}</span>
            <span class="mini-pill">T1 ${item.t1_hit_rate}%</span>
            <span class="mini-pill">T2 ${item.t2_hit_rate}%</span>
            <span class="mini-pill">SL ${item.sl_hit_rate}%</span>
          </div>
          <div class="summary-sub">${item.review.reason}</div>
        </div>
      `).join("") || `<div class="empty-state">No weak setups yet.</div>`;
      const setups = setupsWithScore.map((item) => {
        const triggerClass = String(item.trigger_side || '').toUpperCase() === 'BREAKDOWN' ? 'breakdown' : 'breakout';
        const triggerText = `${item.direction || '-'} ${String(item.trigger_side || 'TRIGGER').replaceAll('_', ' ')}`;
        const timeExitTotal = Number(item.time_exits || 0) + Number(item.market_close_exits || 0);
        return `
          <div class="setup-card">
            <div class="setup-card-head">
              <div>
                <div class="setup-card-title">${item.setup_type}</div>
                <div class="setup-card-sub">${item.regime || '-'} regime | ${item.direction || '-'} direction | ${item.trades} total signals</div>
              </div>
              <div style="display:flex; flex-wrap:wrap; gap:8px; justify-content:flex-end;">
                <div class="score-pill ${item.review.tone}">${item.review.label}</div>
                <div class="trigger-pill ${triggerClass}">${triggerText}</div>
              </div>
            </div>
            <div class="pill-row">
              <span class="mini-pill">Entries ${item.entries}</span>
              <span class="mini-pill">Open ${item.open_trades}</span>
              <span class="mini-pill">Expired ${item.expired}</span>
              <span class="mini-pill">T1 Rate ${item.t1_hit_rate}%</span>
              <span class="mini-pill">T2 Rate ${item.t2_hit_rate}%</span>
              <span class="mini-pill">SL Rate ${item.sl_hit_rate}%</span>
              <span class="mini-pill">Time Exit After T1 ${item.time_exit_after_t1}</span>
            </div>
            <div class="setup-card-sub">${item.review.reason}</div>
            <div class="count-grid">
              <div class="count-card"><div class="count-k">T1 Hits</div><div class="count-v green">${item.t1_hits}</div><div class="count-sub">First target reached</div></div>
              <div class="count-card"><div class="count-k">T2 Hits</div><div class="count-v gold">${item.t2_hits}</div><div class="count-sub">Second target reached</div></div>
              <div class="count-card"><div class="count-k">SL Hits</div><div class="count-v red">${item.sl_hits}</div><div class="count-sub">Stopped out</div></div>
              <div class="count-card"><div class="count-k">Time Exits</div><div class="count-v">${timeExitTotal}</div><div class="count-sub">Timed or market-close exits</div></div>
            </div>
          </div>
        `;
      }).join("") || `<div class="empty-state">No setup analytics yet.</div>`;

      const slBreakdown = (a.sl_breakdown || []).map((item) => {
        const contexts = (item.contexts || []).map((ctx) => {
          const triggerClass = String(ctx.trigger_side || '').toUpperCase() === 'BREAKDOWN' ? 'breakdown' : 'breakout';
          return `
            <div class="sl-context">
              <div>
                <div class="sl-context-main">${ctx.setup_type}</div>
                <div class="sl-context-sub">${ctx.regime || '-'} regime | ${ctx.direction || '-'} direction</div>
              </div>
              <div style="display:flex; align-items:center; gap:8px;">
                <div class="trigger-pill ${triggerClass}">${ctx.trigger_side || 'TRIGGER'}</div>
                <div class="count-v red" style="font-size:18px; margin-top:0;">${ctx.hits}</div>
              </div>
            </div>
          `;
        }).join("");
        return `
          <div class="sl-card">
            <div class="sl-card-head">
              <div>
                <div class="sl-card-title">${bucketLabel(item.bucket)}</div>
                <div class="sl-card-sub">${bucketMeaning(item.bucket)}</div>
              </div>
              <div style="text-align:right;">
                <div class="count-v red" style="font-size:24px; margin-top:0;">${item.hits}</div>
                <div class="count-sub">${item.pct}% of all stop-loss hits</div>
              </div>
            </div>
            <div class="sl-context-list">${contexts || `<div class="empty-state">No setup mix recorded for this stop-loss bucket yet.</div>`}</div>
          </div>
        `;
      }).join("") || `<div class="empty-state">No stop-loss classifications yet.</div>`;

      app.innerHTML = `
        <section class="panel stats">
          <div class="stat"><div class="label">Signals</div><div class="value">${funnel.signals ?? 0}</div></div>
          <div class="stat"><div class="label">Entered</div><div class="value green">${funnel.entered ?? 0}</div></div>
          <div class="stat"><div class="label">Pending</div><div class="value gold">${funnel.pending ?? 0}</div></div>
          <div class="stat"><div class="label">Expired</div><div class="value red">${funnel.expired ?? 0}</div></div>
        </section>
        <section class="three-col">
          <section class="panel">
            <div class="label">Best Intraday Setups</div>
            <div class="summary-list">${bestSetupCards}</div>
          </section>
          <section class="panel">
            <div class="label">Full Setup Analytics</div>
            <div class="setup-breakdown-list">${setups}</div>
          </section>
          <section class="panel">
            <div class="label">Failing / Weak Setups</div>
            <div class="summary-list">${weakSetupCards}</div>
          </section>
        </section>
        <section class="two-col">
          <section class="panel">
            <div class="label">SL Breakdown</div>
            <div class="sl-breakdown-list">${slBreakdown}</div>
          </section>
          <section class="panel">
            <div class="label">How To Read</div>
            <div class="summary-list">
              <div class="summary-card">
                <div class="summary-title">Good For Intraday</div>
                <div class="summary-sub">Higher T2 follow-through, controlled SL rate, and enough entries to trust the pattern.</div>
              </div>
              <div class="summary-card">
                <div class="summary-title">Mixed Read</div>
                <div class="summary-sub">Usable, but still split between follow-through, stop-losses, or time exits.</div>
              </div>
              <div class="summary-card">
                <div class="summary-title">Needs Caution</div>
                <div class="summary-sub">Stop-losses or weak target conversion are dominating, so this setup is not behaving well right now.</div>
              </div>
            </div>
          </section>
        </section>
      `;
    }
    async function load() {
      const res = await fetch(paperEndpoint);
      const data = await res.json();
      render(data);
    }
    function startPolling(loader, intervalMs) {
      let running = false;
      setInterval(async () => {
        if (running) return;
        running = true;
        try {
          await loader();
        } finally {
          running = false;
        }
      }, intervalMs);
    }
    load().catch(() => { app.innerHTML = '<section class="panel"><div class="muted">Unable to load analytics right now.</div></section>'; });
    startPolling(() => load().catch(() => undefined), 1500);
  </script>
</body>
</html>
"""

ANALYTICS_TABLE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Paper Trade Analytics</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;700;800&family=Orbitron:wght@500;700;800&family=Sora:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root { color-scheme: dark; --bg:#06080d; --panel:rgba(15,18,26,.84); --line:rgba(255,255,255,.08); --text:#f7f8fb; --muted:#91a0b4; --gold:#D4AF37; --bull:#00FFB2; --bear:#FF4D6D; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:"Sora",system-ui,sans-serif; color:var(--text); background:radial-gradient(circle at top right, rgba(66,216,255,.08), transparent 24%), linear-gradient(180deg,#0b0f16 0%,#06080d 100%); min-height:100vh; }
    .wrap { max-width:1480px; margin:0 auto; padding:24px; display:grid; gap:18px; }
    .nav-row { display:flex; flex-wrap:wrap; gap:12px; }
    .nav-link { display:inline-flex; align-items:center; gap:8px; width:fit-content; padding:10px 14px; border-radius:999px; border:1px solid var(--line); color:var(--text); text-decoration:none; background:rgba(255,255,255,.03); }
    .panel { border-radius:20px; border:1px solid var(--line); background:linear-gradient(180deg, rgba(16,20,29,0.82), rgba(8,10,15,0.9)); box-shadow:0 24px 70px rgba(0,0,0,.35); backdrop-filter:blur(20px); padding:20px; }
    .title { font-family:"Orbitron",sans-serif; font-size:40px; letter-spacing:-.04em; }
    .muted { color:var(--muted); line-height:1.7; }
    .label { font-size:10px; text-transform:uppercase; letter-spacing:.22em; color:var(--muted); }
    .stats { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:12px; }
    .stat { padding:16px; border-radius:16px; border:1px solid rgba(255,255,255,.06); background:rgba(255,255,255,.03); }
    .value { margin-top:10px; font-family:"JetBrains Mono",monospace; font-size:28px; font-weight:800; }
    .green { color:var(--bull); }
    .red { color:var(--bear); }
    .gold { color:var(--gold); }
    .score-pill { display:inline-flex; align-items:center; padding:8px 12px; border-radius:999px; border:1px solid rgba(255,255,255,.08); font-size:11px; letter-spacing:.12em; text-transform:uppercase; font-weight:800; }
    .score-pill.good { color:var(--bull); background:rgba(0,255,178,.08); }
    .score-pill.mixed { color:var(--gold); background:rgba(212,175,55,.08); }
    .score-pill.weak { color:var(--bear); background:rgba(255,77,109,.08); }
    .trigger-pill { display:inline-flex; align-items:center; gap:8px; padding:7px 10px; border-radius:999px; border:1px solid rgba(255,255,255,.08); font-size:11px; letter-spacing:.12em; text-transform:uppercase; font-weight:700; }
    .trigger-pill.breakout { color:var(--bull); background:rgba(0,255,178,.08); }
    .trigger-pill.breakdown { color:var(--bear); background:rgba(255,77,109,.08); }
    .kpi-row { display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:12px; }
    .kpi-card { padding:16px; border-radius:16px; border:1px solid rgba(255,255,255,.06); background:rgba(255,255,255,.03); }
    .kpi-k { font-size:10px; letter-spacing:.2em; text-transform:uppercase; color:var(--muted); }
    .kpi-v { margin-top:10px; font-family:"JetBrains Mono",monospace; font-size:24px; font-weight:800; }
    .kpi-sub { margin-top:6px; color:var(--muted); font-size:12px; line-height:1.5; }
    .table-wrap { margin-top:14px; overflow:auto; border-radius:16px; border:1px solid rgba(255,255,255,.05); }
    table { width:100%; border-collapse:collapse; min-width:1020px; }
    th, td { padding:12px 10px; border-bottom:1px solid rgba(255,255,255,.06); text-align:left; font-size:14px; vertical-align:middle; }
    th { color:var(--muted); font-size:11px; letter-spacing:.18em; text-transform:uppercase; background:rgba(255,255,255,.02); position:sticky; top:0; }
    tr:hover td { background:rgba(255,255,255,.015); }
    .mono { font-family:"JetBrains Mono",monospace; }
    .cell-strong { font-weight:800; }
    .reason-cell { min-width:260px; color:var(--muted); }
    .empty-state { padding:18px; border-radius:14px; border:1px dashed rgba(255,255,255,.08); background:rgba(255,255,255,.015); color:var(--muted); }
    .section-grid { display:grid; grid-template-columns:1fr; gap:18px; }
    @media (max-width: 980px) { .stats, .kpi-row { grid-template-columns:1fr 1fr; } }
    @media (max-width: 700px) { .stats, .kpi-row { grid-template-columns:1fr; } .title { font-size:30px; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="nav-row">
      <a class="nav-link" id="journalLink" href="/">Back to journal</a>
      <a class="nav-link" id="dashboardLink" href="/">Dashboard</a>
    </div>
    <section class="panel">
      <div class="title">Journal Analytics</div>
      <div class="muted" style="margin-top:10px;">Table view is easier to compare. Use this page to identify which setup, regime, direction, and breakout or breakdown side is good for intraday and which is failing.</div>
    </section>
    <div id="app"></div>
  </div>
  <script>
    const app = document.getElementById("app");
    const paperEndpoint = window.__PAPER_ENDPOINT__ || '/api/paper-trades';
    document.getElementById("journalLink").href = window.__BACK_LINK__ || '/journal';
    document.getElementById("dashboardLink").href = window.__DASHBOARD_LINK__ || '/';

    function bucketLabel(bucket) {
      return String(bucket || '').replaceAll('_', ' ').replace(/\\b\\w/g, (ch) => ch.toUpperCase());
    }
    function bucketMeaning(bucket) {
      const map = {
        clean_invalidation: 'Setup failed cleanly before making meaningful progress.',
        reversal_after_progress: 'Trade moved in favor first, then reversed into stop-loss.',
        fast_failure: 'Trade invalidated quickly after entry.',
        gave_back_after_t1: 'Trade reached T1 area, then gave everything back into stop-loss.',
        uncategorized: 'Stop-loss was recorded, but it did not fit a named bucket yet.',
      };
      return map[String(bucket || '').toLowerCase()] || 'Stop-loss behavior bucket.';
    }
    function formatSetupType(setup) {
      const raw = String(setup || 'EVENT_REACTION');
      return raw.toLowerCase().split('_').map((part) => part ? part[0].toUpperCase() + part.slice(1) : '').join(' ');
    }
    function setupUiTag(setup) {
      const map = {
        SHOCK_BREAKDOWN_CONTINUATION: { label: 'Sudden Breakdown', tone: '#FF4D6D', bg: 'rgba(255,77,109,0.14)' },
        PANIC_BOUNCE_FAILURE: { label: 'Panic Bounce Fail', tone: '#D4AF37', bg: 'rgba(212,175,55,0.14)' },
        FLUSH_EXHAUSTION_REVERSAL: { label: 'Flush Reversal', tone: '#00FFB2', bg: 'rgba(0,255,178,0.14)' },
      };
      return map[String(setup || '').toUpperCase()] || null;
    }
    function setupUiCell(setup) {
      const label = formatSetupType(setup);
      const tag = setupUiTag(setup);
      if (!tag) return label;
      return `
        <div style="display:grid; gap:6px;">
          <div>${label}</div>
          <span style="display:inline-flex; width:max-content; padding:4px 10px; border-radius:999px; font-size:10px; letter-spacing:.16em; text-transform:uppercase; color:${tag.tone}; background:${tag.bg}; border:1px solid ${tag.bg};">${tag.label}</span>
        </div>
      `;
    }
    function setupScore(item) {
      const entries = Number(item.entries || 0);
      if (!entries) return { score: -999, label: 'No Entries Yet', tone: 'mixed', reason: 'No confirmed entries yet, so do not judge this row.' };
      const t2 = Number(item.t2_hit_rate || 0);
      const t1 = Number(item.t1_hit_rate || 0);
      const sl = Number(item.sl_hit_rate || 0);
      const time = Number(item.time_exit_rate || 0);
      const open = Number(item.open_trades || 0);
      const closed = Math.max(entries - open, 0);
      const expectancy = Number(item.expectancy_points || 0);
      const score = (t2 * 1.45) + (t1 * 0.55) - (sl * 1.45) - (time * 0.45) + Math.min(entries * 3, 18) + Math.max(Math.min(expectancy, 8), -8) - Math.min(open * 2, 8);
      if (!closed && open > 0) return { score: score - 12, label: 'Tracking', tone: 'mixed', reason: `Trade is still open. Wait for result before calling it best or weak.` };
      if (sl >= 55 || (entries >= 2 && sl > t2 && sl >= 40) || (entries >= 3 && t1 <= 20 && t2 <= 10)) return { score, label: 'Avoid', tone: 'weak', reason: `Avoid for now: SL ${sl}% is dominating follow-through.` };
      if (entries >= 3 && t2 >= 30 && sl <= 35) return { score, label: 'Best', tone: 'good', reason: `Best proven row: T2 ${t2}% with controlled SL ${sl}% across ${entries} entries.` };
      if (t2 >= 50 && sl <= 25) return { score, label: 'Promising', tone: 'good', reason: `Promising but low sample: T2 ${t2}%, SL ${sl}% across ${entries} entr${entries === 1 ? 'y' : 'ies'}.` };
      if (t1 >= 50 && sl <= 25) return { score, label: 'Scalp Only', tone: 'mixed', reason: `T1 is working (${t1}%) but T2 proof is limited. Prefer quick booking.` };
      return { score, label: 'Wait', tone: 'mixed', reason: `Not best yet: T1 ${t1}%, T2 ${t2}%, SL ${sl}%, Time ${time}%.` };
    }
    function render(payload) {
      const a = payload.analytics || {};
      const funnel = a.funnel || {};
      const setups = (a.setup_breakdown || []).map((item) => ({ ...item, review: setupScore(item) }));
      const enteredRows = setups.filter((item) => Number(item.entries || 0) > 0);
      const goodCount = enteredRows.filter((item) => item.review.tone === 'good').length;
      const weakCount = enteredRows.filter((item) => item.review.tone === 'weak').length;
      const topT2 = [...enteredRows].sort((a, b) => Number(b.t2_hit_rate || 0) - Number(a.t2_hit_rate || 0))[0];
      const topSL = [...enteredRows].sort((a, b) => Number(b.sl_hit_rate || 0) - Number(a.sl_hit_rate || 0))[0];

      const setupRows = setups
        .sort((a, b) =>
          Number(b.review?.score || -999) - Number(a.review?.score || -999) ||
          Number(b.entries || 0) - Number(a.entries || 0) ||
          String(a.setup_type || '').localeCompare(String(b.setup_type || '')) ||
          String(a.regime || '').localeCompare(String(b.regime || '')) ||
          String(a.direction || '').localeCompare(String(b.direction || ''))
        )
        .map((item) => {
          const triggerClass = String(item.trigger_side || '').toUpperCase() === 'BREAKDOWN' ? 'breakdown' : 'breakout';
          return `
            <tr>
              <td class="cell-strong">${setupUiCell(item.setup_type)}</td>
              <td>${item.regime || '-'}</td>
              <td>${item.direction || '-'}</td>
              <td><span class="trigger-pill ${triggerClass}">${item.trigger_side || 'TRIGGER'}</span></td>
              <td class="mono">${item.entries}</td>
              <td class="mono">${item.open_trades}</td>
              <td class="mono">${item.expired}</td>
              <td class="mono green">${item.t1_hit_rate}%</td>
              <td class="mono gold">${item.t2_hit_rate}%</td>
              <td class="mono red">${item.sl_hit_rate}%</td>
              <td class="mono">${item.time_exit_rate}%</td>
              <td><span class="score-pill ${item.review.tone}">${item.review.label}</span></td>
              <td class="reason-cell">${item.review.reason}</td>
            </tr>
          `;
        }).join("") || `<tr><td colspan="13" class="empty-state">No setup analytics yet.</td></tr>`;

      const slRows = (a.sl_breakdown || []).map((item) => {
        const topContext = (item.contexts || [])[0] || {};
        const triggerClass = String(topContext.trigger_side || '').toUpperCase() === 'BREAKDOWN' ? 'breakdown' : 'breakout';
        return `
          <tr>
            <td class="cell-strong">${bucketLabel(item.bucket)}</td>
            <td class="reason-cell">${bucketMeaning(item.bucket)}</td>
            <td class="mono red">${item.hits}</td>
            <td class="mono">${item.pct}%</td>
            <td>${topContext.setup_type ? setupUiCell(topContext.setup_type) : '-'}</td>
            <td>${topContext.regime || '-'}</td>
            <td>${topContext.direction || '-'}</td>
            <td>${topContext.trigger_side ? `<span class="trigger-pill ${triggerClass}">${topContext.trigger_side}</span>` : '-'}</td>
          </tr>
        `;
      }).join("") || `<tr><td colspan="8" class="empty-state">No stop-loss classifications yet.</td></tr>`;

      app.innerHTML = `
        <section class="panel stats">
          <div class="stat"><div class="label">Signals</div><div class="value">${funnel.signals ?? 0}</div></div>
          <div class="stat"><div class="label">Entered</div><div class="value green">${funnel.entered ?? 0}</div></div>
          <div class="stat"><div class="label">Pending</div><div class="value gold">${funnel.pending ?? 0}</div></div>
          <div class="stat"><div class="label">Expired</div><div class="value red">${funnel.expired ?? 0}</div></div>
        </section>
        <section class="kpi-row">
          <div class="kpi-card"><div class="kpi-k">Good Setups</div><div class="kpi-v green">${goodCount}</div><div class="kpi-sub">Rows currently behaving better for intraday trading.</div></div>
          <div class="kpi-card"><div class="kpi-k">Weak Setups</div><div class="kpi-v red">${weakCount}</div><div class="kpi-sub">Rows where stop-loss or weak target conversion is dominating.</div></div>
          <div class="kpi-card"><div class="kpi-k">Best T2 Row</div><div class="kpi-v gold">${topT2 ? topT2.t2_hit_rate + '%' : '--'}</div><div class="kpi-sub">${topT2 ? `${formatSetupType(topT2.setup_type)} | ${topT2.regime} | ${topT2.direction}` : 'No entries yet.'}</div></div>
          <div class="kpi-card"><div class="kpi-k">Highest SL Row</div><div class="kpi-v red">${topSL ? topSL.sl_hit_rate + '%' : '--'}</div><div class="kpi-sub">${topSL ? `${formatSetupType(topSL.setup_type)} | ${topSL.regime} | ${topSL.direction}` : 'No entries yet.'}</div></div>
          <div class="kpi-card"><div class="kpi-k">Reading Rule</div><div class="kpi-v">${enteredRows.length}</div><div class="kpi-sub">Prefer rows with higher T2% and lower SL%. Treat high SL rows as avoid or confirmation-only.</div></div>
        </section>
        <section class="section-grid">
          <section class="panel">
            <div class="label">Setup Performance Table</div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Setup</th><th>Regime</th><th>Direction</th><th>Trigger</th><th>Entries</th><th>Open</th><th>Expired</th><th>T1 %</th><th>T2 %</th><th>SL %</th><th>Time %</th><th>Verdict</th><th>Reading</th>
                  </tr>
                </thead>
                <tbody>${setupRows}</tbody>
              </table>
            </div>
          </section>
          <section class="panel">
            <div class="label">SL Breakdown Table</div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>SL Type</th><th>Meaning</th><th>Hits</th><th>% of SL</th><th>Top Setup</th><th>Top Regime</th><th>Top Direction</th><th>Trigger</th>
                  </tr>
                </thead>
                <tbody>${slRows}</tbody>
              </table>
            </div>
          </section>
        </section>
      `;
    }
    async function load() {
      const res = await fetch(paperEndpoint);
      const data = await res.json();
      render(data);
    }
    function startPolling(loader, intervalMs) {
      let running = false;
      setInterval(async () => {
        if (running) return;
        running = true;
        try {
          await loader();
        } finally {
          running = false;
        }
      }, intervalMs);
    }
    load().catch(() => { app.innerHTML = '<section class="panel"><div class="muted">Unable to load analytics right now.</div></section>'; });
    startPolling(() => load().catch(() => undefined), 1500);
  </script>
</body>
</html>
"""


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


def create_app(config: ReactionAlphaConfig | None = None) -> FastAPI:
    service = ReactionAlphaService(config=config)
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
    async def pretrade_top(force: bool = False) -> dict[str, Any]:
        return service.pretrade_scan(force=force)

    @app.post("/api/kotak/totp")
    async def submit_kotak_totp(payload: dict[str, Any], x_reaction_alpha_secret: str | None = Header(default=None)) -> dict[str, Any]:
        verify_admin_secret(x_reaction_alpha_secret)
        return service.submit_kotak_totp(str(payload.get("totp_code") or ""))

    @app.get("/api/demo/snapshot")
    async def demo_snapshot() -> dict[str, Any]:
        return demo_service.snapshot()

    @app.get("/api/demo/signals/{symbol}")
    async def demo_signal_detail(symbol: str) -> dict[str, Any]:
        return demo_service.get_signal_detail(symbol)

    @app.get("/api/demo/paper-trades")
    async def demo_paper_trade_journal() -> dict[str, Any]:
        return demo_service.paper_trade_journal(limit=120)

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

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> str:
        return UI_HTML

    @app.get("/kotak-login", response_class=HTMLResponse)
    async def kotak_login() -> str:
        return KOTAK_LOGIN_HTML

    @app.get("/pre-trade-scanner", response_class=HTMLResponse)
    async def pretrade_scanner() -> str:
        return PRETRADE_SCANNER_HTML

    @app.get("/journal", response_class=HTMLResponse)
    async def journal() -> str:
        return paper_html("/api/paper-trades", "/", "/api/paper-trades/reset-today", "/api/paper-trades/reset-all", "/journal/analytics")

    @app.get("/demo", response_class=HTMLResponse)
    async def demo_dashboard() -> str:
        return demo_html()

    @app.get("/demo/journal", response_class=HTMLResponse)
    async def demo_journal() -> str:
        return paper_html("/api/demo/paper-trades", "/demo", "/api/demo/paper-trades/reset-today", "/api/demo/paper-trades/reset-all", "/demo/journal/analytics")

    @app.get("/journal/analytics", response_class=HTMLResponse)
    async def journal_analytics() -> str:
        return analytics_html("/api/paper-trades", "/journal", "/")

    @app.get("/demo/journal/analytics", response_class=HTMLResponse)
    async def demo_journal_analytics() -> str:
        return analytics_html("/api/demo/paper-trades", "/demo/journal", "/demo")

    @app.get("/stock/{symbol}", response_class=HTMLResponse)
    async def stock_detail(symbol: str) -> str:
        return detail_html(symbol, f"/api/signals/{symbol.upper()}", "/")

    @app.get("/demo/stock/{symbol}", response_class=HTMLResponse)
    async def demo_stock_detail(symbol: str) -> str:
        return detail_html(symbol, f"/api/demo/signals/{symbol.upper()}", "/demo")

    @app.get("/api/signals/{symbol}")
    async def signal_detail(symbol: str) -> dict[str, Any]:
        return service.get_signal_detail(symbol)

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
