import { motion } from "framer-motion";
import type { Snapshot } from "../types";
import { formatSignedPercent } from "../lib/formatters";
import { GlassPanel } from "./shared/GlassPanel";

export function IndicesSection({ snapshot, loading }: { snapshot: Snapshot; loading: boolean }) {
  return (
    <section className="grid gap-5 lg:grid-cols-3">
      {snapshot.indices.map((index, idx) => {
        const positive = index.change >= 0;
        const progress = Math.max(8, Math.min(100, Math.abs(index.change_pct) * 18 + 18));

        return (
          <motion.div
            key={index.symbol}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: idx * 0.04 }}
            whileHover={{ scale: 1.02, y: -3 }}
          >
            <GlassPanel className="group relative h-full overflow-hidden rounded-[30px] px-6 py-6 transition-all duration-300 hover:border-white/20 hover:shadow-[0_0_40px_rgba(34,211,238,0.08)]">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(34,211,238,0.10),transparent_26%),radial-gradient(circle_at_bottom_left,rgba(139,92,246,0.10),transparent_26%)] opacity-70 transition-opacity duration-300 group-hover:opacity-100" />
              <div className="relative">
                <div className="text-[11px] uppercase tracking-[0.3em] text-slate-400">{index.symbol}</div>
                <motion.div
                  key={`${index.symbol}-${index.price}`}
                  initial={{ opacity: 0.4, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.35 }}
                  className="mt-5 text-4xl font-semibold tracking-[-0.06em] text-white"
                >
                  {loading ? <span className="shimmer-text">Loading</span> : index.price.toFixed(2)}
                </motion.div>
                <div className={`mt-3 text-base font-medium ${positive ? "text-emerald-300" : "text-rose-300"}`}>
                  {formatSignedPercent(index.change)} / {formatSignedPercent(index.change_pct)}%
                </div>
                <div className="mt-5 h-2.5 overflow-hidden rounded-full bg-white/8">
                  <motion.div
                    className={`h-full rounded-full ${positive ? "bg-gradient-to-r from-emerald-300 via-cyan-300 to-cyan-400" : "bg-gradient-to-r from-rose-400 via-fuchsia-400 to-violet-400"}`}
                    initial={{ width: 0 }}
                    animate={{ width: `${progress}%` }}
                    transition={{ duration: 0.7, ease: [0.2, 0.8, 0.2, 1] }}
                  />
                </div>
                <div className="mt-4 text-sm text-slate-400">{positive ? "Risk appetite improving" : "Pressure building in the tape"}</div>
              </div>
            </GlassPanel>
          </motion.div>
        );
      })}
    </section>
  );
}
