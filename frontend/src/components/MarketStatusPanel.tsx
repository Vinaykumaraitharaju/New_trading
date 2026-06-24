import { motion } from "framer-motion";
import type { Snapshot } from "../types";
import { GlassPanel } from "./shared/GlassPanel";

export function MarketStatusPanel({ snapshot, loading }: { snapshot: Snapshot; loading: boolean }) {
  const session = snapshot.market_session;
  const isOpen = session?.status === "OPEN";

  return (
    <GlassPanel
      className={`relative overflow-hidden px-6 py-6 md:px-7 ${
        isOpen
          ? "ring-1 ring-cyan-300/30 shadow-[0_0_38px_rgba(56,189,248,0.12)]"
          : "shadow-[0_0_32px_rgba(129,140,248,0.08)]"
      }`}
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_right_top,rgba(45,212,191,0.08),transparent_28%),radial-gradient(circle_at_left_bottom,rgba(139,92,246,0.08),transparent_32%)]" />

      <div className="relative grid gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
        <div className="rounded-[26px] border border-white/10 bg-white/[0.03] p-5 backdrop-blur-xl">
          <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Market Session</div>
          <div
            className={`mt-5 text-4xl font-semibold tracking-[-0.05em] ${
              isOpen ? "text-cyan-300 drop-shadow-[0_0_18px_rgba(34,211,238,0.22)]" : "text-amber-300"
            }`}
          >
            {loading ? "SYNCING" : session?.status ?? "CLOSED"}
          </div>
          <div className="mt-3 text-sm leading-6 text-slate-300">
            {loading ? "Syncing live session state..." : session?.detail ?? "Market session status unavailable."}
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-[1fr_1fr]">
          <div className="rounded-[26px] border border-white/10 bg-white/[0.03] p-5 backdrop-blur-xl">
            <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">India Time</div>
            <AnimatedNumberText
              className="mt-4 text-2xl font-semibold tracking-[-0.04em] text-white"
              value={loading ? "Loading..." : formatIndianTime(session?.timestamp_ist)}
            />
            <div className="mt-3 text-sm text-slate-400">Asia/Kolkata session heartbeat</div>
          </div>

          <div className="rounded-[26px] border border-white/10 bg-white/[0.03] p-5 backdrop-blur-xl">
            <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Desk Note</div>
            <motion.p
              key={`${session?.status}-${snapshot.generated_at}`}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35 }}
              className="mt-4 text-sm leading-7 text-slate-300"
            >
              {loading
                ? "Pulling live market context and session intelligence."
                : isOpen
                  ? "Live scanning is active. Signals are promoted only when event quality and post-event reaction align."
                  : "Market is closed. The board remains available for review while the engine waits for the next live session."}
            </motion.p>
          </div>
        </div>
      </div>
    </GlassPanel>
  );
}

function formatIndianTime(value?: string) {
  if (!value) return "Unavailable";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "medium"
  }).format(new Date(value));
}

function AnimatedNumberText({ value, className }: { value: string; className?: string }) {
  return (
    <motion.div
      key={value}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={className}
    >
      {value}
    </motion.div>
  );
}
