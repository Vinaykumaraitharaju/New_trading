import { startTransition, useEffect, useRef, useState } from "react";
import type { Snapshot } from "../types";
import { buildSimulatedSnapshot } from "../lib/simulateSnapshot";

const fallbackSnapshot: Snapshot = {
  generated_at: new Date().toISOString(),
  top_signals: [],
  tracked_symbols: 0,
  mode: "loading",
  market_session: {
    status: "CLOSED",
    detail: "Initializing market context",
    timestamp_ist: new Date().toISOString()
  },
  indices: [
    { symbol: "NIFTY", price: 0, change: 0, change_pct: 0, trend: "FLAT" },
    { symbol: "BANKNIFTY", price: 0, change: 0, change_pct: 0, trend: "FLAT" },
    { symbol: "SENSEX", price: 0, change: 0, change_pct: 0, trend: "FLAT" }
  ]
};

export function useSignalFeed() {
  const [snapshot, setSnapshot] = useState<Snapshot>(fallbackSnapshot);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const lastLeadRef = useRef<string>("");
  const latestSnapshotRef = useRef<Snapshot>(fallbackSnapshot);

  useEffect(() => {
    latestSnapshotRef.current = snapshot;
  }, [snapshot]);

  useEffect(() => {
    audioRef.current = new Audio(
      "data:audio/wav;base64,UklGRlQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YSwAAAAA////AAAA////AAAA////AAAA"
    );
  }, []);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/signals`);

    socket.onopen = () => {
      setConnected(true);
    };
    socket.onclose = () => {
      setConnected(false);
    };
    socket.onerror = () => {
      setConnected(false);
    };
    socket.onmessage = (event) => {
      const raw = JSON.parse(event.data) as Partial<Snapshot>;
      const next: Snapshot = {
        ...fallbackSnapshot,
        ...raw,
        market_session: {
          ...fallbackSnapshot.market_session,
          ...(raw.market_session ?? {})
        },
        indices: raw.indices ?? fallbackSnapshot.indices,
        top_signals: raw.top_signals ?? []
      };
      const leader = next.top_signals[0]?.stock ?? "";
      if (leader && leader !== lastLeadRef.current) {
        void audioRef.current?.play().catch(() => undefined);
        lastLeadRef.current = leader;
      }
      startTransition(() => {
        setSnapshot(next);
        setLoading(false);
      });
    };

    return () => socket.close();
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => {
      const next = buildSimulatedSnapshot(latestSnapshotRef.current);
      startTransition(() => {
        setSnapshot(next);
        setLoading(false);
      });
    }, 2000);

    return () => window.clearInterval(interval);
  }, []);

  return { snapshot, connected, loading };
}
