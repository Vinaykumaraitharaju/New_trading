import { motion } from "framer-motion";
import type { Signal } from "../types";
import { GlassPanel } from "./shared/GlassPanel";

export function LeadSignalPanel({ signal, loading }: { signal: Signal; loading: boolean }) {
  return (
    <GlassPanel className="relative overflow-hidden rounded-[34px] px-7 py-7 md:px-8">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(34,211,238,0.10),transparent_26%),radial-gradient(circle_at_bottom_left,rgba(45,212,191,0.10),transparent_28%)]" />
      <div className="relative">
        <div className={`inline-flex rounded-full border px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.26em] ${
          signal.signal.includes("BULLISH")
            ? "border-emerald-300/20 bg-emerald-300/10 text-emerald-200"
            : signal.signal.includes("BEARISH")
              ? "border-rose-300/20 bg-rose-300/10 text-rose-200"
              : "border-amber-300/20 bg-amber-300/10 text-amber-200"
        }`}>
          {signal.signal}
        </div>

        <div className="mt-6 flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <motion.div
              key={`${signal.stock}-${signal.updated_at}`}
              initial={{ opacity: 0.45, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35 }}
              className="text-5xl font-semibold tracking-[-0.06em] text-white md:text-7xl"
            >
              {signal.stock}
            </motion.div>
            <div className="mt-4 max-w-2xl text-lg leading-8 text-slate-300">
              {signal.event} -> {signal.reaction} -> {signal.expected_move}
            </div>
          </div>

          <div className="w-full max-w-[230px] rounded-[28px] border border-white/10 bg-white/[0.03] px-5 py-5 text-left backdrop-blur-xl lg:text-right">
            <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Confidence</div>
            <div className="mt-4 text-5xl font-semibold tracking-[-0.06em] text-white">{loading ? "--" : signal.confidence}</div>
            <div className="mt-3 text-sm text-slate-400">Updated {new Date(signal.updated_at).toLocaleTimeString()}</div>
          </div>
        </div>

        <div className="mt-7 grid gap-4 md:grid-cols-4">
          <LevelCard label="Entry" value={signal.entry.toFixed(2)} />
          <LevelCard label="Stop" value={signal.sl.toFixed(2)} />
          <LevelCard label="T1" value={signal.t1.toFixed(2)} />
          <LevelCard label="T2" value={signal.t2.toFixed(2)} />
        </div>

        <div className="mt-7 grid gap-4 xl:grid-cols-[1fr_1fr]">
          <div className="rounded-[28px] border border-white/10 bg-white/[0.03] p-5">
            <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Trade Thesis</div>
            <div className="mt-4 grid gap-3">
              {signal.reason.map((item) => (
                <motion.div
                  key={item}
                  whileHover={{ x: 2 }}
                  className="rounded-2xl border border-white/5 bg-black/20 px-4 py-3 text-sm leading-6 text-slate-300"
                >
                  {item}
                </motion.div>
              ))}
            </div>
          </div>

          <div className="rounded-[28px] border border-white/10 bg-white/[0.03] p-5">
            <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Score Mix</div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              {Object.entries(signal.components).map(([name, score]) => (
                <div key={name} className="rounded-2xl border border-white/5 bg-black/20 px-4 py-3">
                  <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">{name}</div>
                  <div className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-white">{score}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </GlassPanel>
  );
}

function LevelCard({ label, value }: { label: string; value: string }) {
  return (
    <motion.div whileHover={{ scale: 1.02 }} transition={{ duration: 0.2 }} className="rounded-[26px] border border-white/10 bg-white/[0.03] px-5 py-5 backdrop-blur-xl">
      <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">{label}</div>
      <div className="mt-4 text-3xl font-semibold tracking-[-0.05em] text-white">{value}</div>
    </motion.div>
  );
}
