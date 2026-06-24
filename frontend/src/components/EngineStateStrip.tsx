import type { ReactNode } from "react";
import { motion } from "framer-motion";
import type { Snapshot } from "../types";
import { GlassPanel } from "./shared/GlassPanel";

export function EngineStateStrip({ snapshot, loading }: { snapshot: Snapshot; loading: boolean }) {
  const hasSignals = snapshot.top_signals.length > 0;

  return (
    <section className="grid gap-4 md:grid-cols-3">
      <EngineCard
        title="Selection Style"
        value="Strict"
        icon="◇"
        detail="Reaction quality, structure, order flow, and momentum alignment must all agree."
        loading={loading}
      />
      <EngineCard
        title="Current State"
        value={loading ? "Syncing" : hasSignals ? "Active Selection" : "Scanning"}
        icon={<PulseDot />}
        detail={hasSignals ? "High-probability setups are on the board." : "Engine is scanning for clean setups and waiting for post-event confirmation."}
        loading={loading}
      />
      <EngineCard
        title="Why Empty"
        value={loading ? "Booting" : hasSignals ? "Edge Found" : "No Edge"}
        icon="△"
        detail={hasSignals ? "At least one setup is above threshold." : "No symbol currently clears the live score threshold with enough conviction."}
        loading={loading}
      />
    </section>
  );
}

function EngineCard({
  title,
  value,
  detail,
  icon,
  loading
}: {
  title: string;
  value: string;
  detail: string;
  icon: ReactNode;
  loading: boolean;
}) {
  return (
    <motion.div whileHover={{ scale: 1.02, y: -2 }} transition={{ duration: 0.2 }}>
      <GlassPanel className="h-full rounded-[28px] px-5 py-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">{title}</div>
            <div className="mt-4 text-2xl font-semibold tracking-[-0.04em] text-white">{loading ? "Loading" : value}</div>
          </div>
          <div className="grid h-11 w-11 place-items-center rounded-2xl border border-white/10 bg-white/[0.03] text-lg text-cyan-300">
            {icon}
          </div>
        </div>
        <p className="mt-4 text-sm leading-6 text-slate-400">{detail}</p>
      </GlassPanel>
    </motion.div>
  );
}

function PulseDot() {
  return (
    <span className="relative flex h-3 w-3">
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-300/70" />
      <span className="relative inline-flex h-3 w-3 rounded-full bg-cyan-300" />
    </span>
  );
}
