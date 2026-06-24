import type { IndexCard, Signal, Snapshot } from "../types";

export function buildSimulatedSnapshot(snapshot: Snapshot): Snapshot {
  const nextTime = new Date().toISOString();

  return {
    ...snapshot,
    generated_at: nextTime,
    market_session: {
      ...snapshot.market_session,
      timestamp_ist: nextTime
    },
    indices: snapshot.indices.map((index) => nudgeIndex(index)),
    top_signals: snapshot.top_signals.map((signal, idx) => nudgeSignal(signal, idx))
  };
}

function nudgeIndex(index: IndexCard): IndexCard {
  const drift = pseudoRandom(index.symbol + index.price.toFixed(2), -0.18, 0.18);
  const nextChange = index.change + drift;
  const basePrice = index.price - index.change;
  const nextPrice = Math.max(0, basePrice + nextChange);
  const nextPct = basePrice > 0 ? (nextChange / basePrice) * 100 : index.change_pct;

  return {
    ...index,
    price: round(nextPrice),
    change: round(nextChange),
    change_pct: round(nextPct),
    trend: nextChange > 0 ? "UP" : nextChange < 0 ? "DOWN" : "FLAT"
  };
}

function nudgeSignal(signal: Signal, idx: number): Signal {
  const confidenceNumber = Number.parseFloat(signal.confidence.replace("%", "")) || 0;
  const confidenceDrift = pseudoRandom(`${signal.stock}-${signal.updated_at}`, -1.4, 1.4);
  const nextConfidence = Math.max(50, Math.min(99, confidenceNumber + confidenceDrift));
  const priceDrift = pseudoRandom(`${signal.stock}-${idx}`, -0.18, 0.18);

  return {
    ...signal,
    entry: round(signal.entry + priceDrift),
    sl: round(signal.sl + priceDrift * 0.75),
    t1: round(signal.t1 + priceDrift * 1.15),
    t2: round(signal.t2 + priceDrift * 1.3),
    confidence: `${Math.round(nextConfidence)}%`,
    updated_at: new Date().toISOString()
  };
}

function pseudoRandom(seed: string, low: number, high: number) {
  let hash = 0;
  for (let index = 0; index < seed.length; index += 1) {
    hash = (hash << 5) - hash + seed.charCodeAt(index);
    hash |= 0;
  }
  const normalized = Math.abs(Math.sin(hash)) % 1;
  return low + normalized * (high - low);
}

function round(value: number) {
  return Number(value.toFixed(2));
}
