import { motion } from "framer-motion";
import type { Signal } from "../types";
import { GlassPanel } from "./shared/GlassPanel";

export function RankingRail({ signals, loading }: { signals: Signal[]; loading: boolean }) {
  return (
    <GlassPanel className="h-fit rounded-[34px] px-6 py-6">
      <div className="flex items-baseline justify-between gap-4">
        <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Top Signals</div>
        <div className="text-sm text-slate-400">{loading ? "Syncing" : `${signals.length} live cards`}</div>
      </div>

      <div className="mt-5 grid gap-4">
        {signals.map((signal, idx) => {
          const bull = signal.signal.includes("BULLISH");
          const width = Math.max(12, Math.min(100, Math.round((signal.score / 24) * 100)));

          return (
            <motion.div
              key={`${signal.stock}-${signal.updated_at}-${idx}`}
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.32, delay: idx * 0.03 }}
              whileHover={{ scale: 1.02, x: -1 }}
              className="rounded-[26px] border border-white/10 bg-white/[0.03] px-5 py-5 backdrop-blur-xl"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-2xl font-semibold tracking-[-0.04em] text-white">{signal.stock}</div>
                  <div className="mt-2 text-[11px] uppercase tracking-[0.24em] text-slate-400">{signal.signal}</div>
                </div>
                <div className="text-right">
                  <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Score</div>
                  <div className="mt-2 text-3xl font-semibold tracking-[-0.05em] text-white">{signal.score}</div>
                </div>
              </div>
              <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-white/8">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${width}%` }}
                  transition={{ duration: 0.7 }}
                  className={`h-full rounded-full ${bull ? "bg-gradient-to-r from-emerald-300 via-cyan-300 to-cyan-400" : "bg-gradient-to-r from-rose-400 via-fuchsia-400 to-violet-400"}`}
                />
              </div>
              <div className="mt-4 text-sm leading-6 text-slate-400">{signal.expected_move}</div>
            </motion.div>
          );
        })}
      </div>
    </GlassPanel>
  );
}
