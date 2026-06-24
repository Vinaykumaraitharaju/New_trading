import { motion } from "framer-motion";
import { GlassPanel } from "./shared/GlassPanel";

export function EmptyStatePanel({ loading }: { loading: boolean }) {
  return (
    <GlassPanel className="relative overflow-hidden rounded-[34px] px-8 py-12">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(34,211,238,0.08),transparent_26%),radial-gradient(circle_at_80%_20%,rgba(168,85,247,0.10),transparent_24%)]" />
      <div className="relative text-center">
        <div className="mx-auto grid h-20 w-20 place-items-center rounded-full border border-white/10 bg-white/[0.03]">
          <ScanningPulse />
        </div>
        <h2 className="mt-6 text-3xl font-semibold tracking-[-0.05em] text-white">No strong trades yet.</h2>
        <p className="mx-auto mt-4 max-w-2xl text-base leading-7 text-slate-300 md:text-lg">
          {loading
            ? "Booting the reaction engine and syncing live market context."
            : "No strong trades yet. Engine scanning for clean setups."}
        </p>
        <div className="mt-6 inline-flex items-center gap-3 rounded-full border border-white/10 bg-white/[0.03] px-5 py-3 text-sm text-slate-300">
          <span className="font-medium">Scanning</span>
          <AnimatedDots />
        </div>
      </div>
    </GlassPanel>
  );
}

function ScanningPulse() {
  return (
    <div className="relative flex h-10 w-10 items-center justify-center">
      <span className="absolute h-10 w-10 animate-ping rounded-full bg-cyan-300/20" />
      <span className="absolute h-7 w-7 rounded-full bg-cyan-300/20 blur-md" />
      <span className="relative h-3.5 w-3.5 rounded-full bg-cyan-300 shadow-[0_0_18px_rgba(34,211,238,0.55)]" />
    </div>
  );
}

function AnimatedDots() {
  return (
    <div className="flex gap-1.5">
      {[0, 1, 2].map((idx) => (
        <motion.span
          key={idx}
          animate={{ opacity: [0.25, 1, 0.25], y: [0, -2, 0] }}
          transition={{ duration: 1.2, repeat: Number.POSITIVE_INFINITY, delay: idx * 0.18 }}
          className="h-2 w-2 rounded-full bg-cyan-300"
        />
      ))}
    </div>
  );
}
