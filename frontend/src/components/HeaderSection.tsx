import { AnimatePresence, motion } from "framer-motion";
import type { Snapshot } from "../types";
import { formatCompactNumber } from "../lib/formatters";
import { GlassPanel } from "./shared/GlassPanel";
import { LoadingBar } from "./shared/LoadingBar";

type HeaderSectionProps = {
  snapshot: Snapshot;
  connected: boolean;
  loading: boolean;
};

export function HeaderSection({ snapshot, connected, loading }: HeaderSectionProps) {
  const strongSignals = snapshot.top_signals.length;

  return (
    <section className="grid gap-5 lg:grid-cols-[minmax(0,1.6fr)_420px]">
      <GlassPanel className="relative overflow-hidden px-7 py-7 md:px-8 md:py-8">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_10%_0%,rgba(34,211,238,0.12),transparent_30%),radial-gradient(circle_at_90%_10%,rgba(168,85,247,0.12),transparent_30%)]" />
        <div className="relative">
          <div className="mb-5 inline-flex items-center gap-3 text-[11px] font-semibold uppercase tracking-[0.34em] text-cyan-100/70">
            <span className="h-px w-10 bg-gradient-to-r from-cyan-300/80 to-transparent" />
            Reaction-Based Alpha Engine
          </div>

          <div className="max-w-4xl">
            <h1 className="max-w-3xl text-4xl font-semibold leading-[0.96] tracking-[-0.05em] text-white md:text-6xl">
              Top intraday opportunities only.
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300 md:text-xl">
              Live event detection, AI reaction scoring, and institutional-grade setup selection built for clean intraday decision-making.
            </p>
          </div>

          <AnimatePresence>
            {loading ? (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="mt-8"
              >
                <LoadingBar />
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      </GlassPanel>

      <div className="grid grid-cols-2 gap-4">
        <StatusCard label="Feed" value={connected ? "LIVE" : "SYNC"} tone="bull" loading={loading} />
        <StatusCard label="Mode" value={(snapshot.mode || "live").toUpperCase()} tone="cyan" loading={loading} />
        <StatusCard label="Universe" value={formatCompactNumber(snapshot.tracked_symbols)} tone="teal" loading={loading} />
        <StatusCard label="Signals" value={formatCompactNumber(strongSignals)} tone="violet" loading={loading} />
      </div>
    </section>
  );
}

function StatusCard({
  label,
  value,
  tone,
  loading
}: {
  label: string;
  value: string;
  tone: "bull" | "cyan" | "teal" | "violet";
  loading: boolean;
}) {
  const toneMap = {
    bull: "from-emerald-400/20 to-emerald-500/5 text-emerald-300 shadow-[0_0_28px_rgba(52,211,153,0.14)]",
    cyan: "from-cyan-400/20 to-cyan-500/5 text-cyan-300 shadow-[0_0_28px_rgba(34,211,238,0.14)]",
    teal: "from-teal-400/20 to-teal-500/5 text-teal-300 shadow-[0_0_28px_rgba(45,212,191,0.14)]",
    violet: "from-violet-400/20 to-violet-500/5 text-violet-300 shadow-[0_0_28px_rgba(168,85,247,0.14)]"
  }[tone];

  return (
    <motion.div
      whileHover={{ scale: 1.02, y: -2 }}
      transition={{ duration: 0.2 }}
      className={`glass-card rounded-[28px] border border-white/10 bg-gradient-to-br ${toneMap} px-5 py-5 backdrop-blur-xl`}
    >
      <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">{label}</div>
      <div className="mt-4 text-3xl font-semibold tracking-[-0.05em] text-white">
        {loading ? <span className="shimmer-text">Loading</span> : value}
      </div>
    </motion.div>
  );
}
