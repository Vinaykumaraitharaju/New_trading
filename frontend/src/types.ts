export type Signal = {
  stock: string;
  event: string;
  reaction: string;
  signal: string;
  trend: string;
  score: number;
  entry: number;
  sl: number;
  t1: number;
  t2: number;
  expected_move: string;
  confidence: string;
  reason: string[];
  timestamp: string;
  components: Record<string, number>;
  updated_at: string;
};

export type MarketSession = {
  status: "OPEN" | "CLOSED" | string;
  detail: string;
  timestamp_ist: string;
};

export type IndexCard = {
  symbol: string;
  price: number;
  change: number;
  change_pct: number;
  trend: string;
};

export type Snapshot = {
  generated_at: string;
  top_signals: Signal[];
  tracked_symbols: number;
  mode: string;
  market_session: MarketSession;
  indices: IndexCard[];
};
