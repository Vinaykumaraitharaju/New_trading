import { motion } from "framer-motion";
import type { Signal } from "../types";

export function TopTradeGrid({ signals, loading }: { signals: Signal[]; loading: boolean }) {
  return (
    <section className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
      {signals.slice(0, 3).map((signal, idx) => (
        <motion.article
          key={`${signal.stock}-${idx}`}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: idx * 0.04 }}
          whileHover={{ scale: 1.02, y: -2 }}
          className="glass-card rounded-[30px] border border-white/10 bg-white/[0.03] px-6 py-6 backdrop-blur-xl"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-2xl font-semibold tracking-[-0.04em] text-white">{signal.stock}</div>
              <div className="mt-3 inline-flex rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[11px] uppercase tracking-[0.24em] text-slate-300">
                {signal.reaction}
              </div>
            </div>
            <div className="text-right">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Confidence</div>
              <div className="mt-2 text-3xl font-semibold tracking-[-0.05em] text-white">{loading ? "--" : signal.confidence}</div>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3">
            <MiniLevel label="Entry" value={signal.entry.toFixed(2)} />
            <MiniLevel label="SL" value={signal.sl.toFixed(2)} />
            <MiniLevel label="T1" value={signal.t1.toFixed(2)} />
            <MiniLevel label="T2" value={signal.t2.toFixed(2)} />
          </div>

          <div className="mt-5 text-sm leading-6 text-slate-400">{signal.reason.slice(0, 3).join(" | ")}</div>
        </motion.article>
      ))}
    </section>
  );
}

function MiniLevel({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/8 bg-black/20 px-4 py-3">
      <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="mt-2 text-lg font-semibold tracking-[-0.04em] text-white">{value}</div>
    </div>
  );
}
