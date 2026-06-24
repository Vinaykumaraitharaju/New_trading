import { AnimatePresence, motion } from "framer-motion";
import { useSignalFeed } from "./hooks/useSignalFeed";
import { EngineStateStrip } from "./components/EngineStateStrip";
import { EmptyStatePanel } from "./components/EmptyStatePanel";
import { HeaderSection } from "./components/HeaderSection";
import { IndicesSection } from "./components/IndicesSection";
import { LeadSignalPanel } from "./components/LeadSignalPanel";
import { MarketStatusPanel } from "./components/MarketStatusPanel";
import { RankingRail } from "./components/RankingRail";
import { TopTradeGrid } from "./components/TopTradeGrid";

export default function App() {
  const { snapshot, connected, loading } = useSignalFeed();
  const leadSignal = snapshot.top_signals[0] ?? null;

  return (
    <main className="terminal-shell min-h-screen overflow-hidden bg-[linear-gradient(180deg,#0b1220_0%,#0a0f1a_44%,#05080f_100%)] text-text">
      <BackgroundOrbs />
      <NoiseOverlay />

      <div className="relative mx-auto flex min-h-screen w-full max-w-[1480px] flex-col gap-5 px-4 py-5 md:px-6 xl:px-8">
        <HeaderSection snapshot={snapshot} connected={connected} loading={loading} />
        <MarketStatusPanel snapshot={snapshot} loading={loading} />
        <IndicesSection snapshot={snapshot} loading={loading} />
        <EngineStateStrip snapshot={snapshot} loading={loading} />

        <AnimatePresence mode="wait">
          {leadSignal ? (
            <motion.section
              key="signal-layout"
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.35, ease: [0.2, 0.8, 0.2, 1] }}
              className="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_420px]"
            >
              <LeadSignalPanel signal={leadSignal} loading={loading} />
              <RankingRail signals={snapshot.top_signals} loading={loading} />
            </motion.section>
          ) : (
            <motion.div
              key="empty-layout"
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.35, ease: [0.2, 0.8, 0.2, 1] }}
            >
              <EmptyStatePanel loading={loading} />
            </motion.div>
          )}
        </AnimatePresence>

        <TopTradeGrid signals={snapshot.top_signals} loading={loading} />
      </div>
    </main>
  );
}

function BackgroundOrbs() {
  return (
    <>
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute left-[-9rem] top-[-5rem] h-80 w-80 rounded-full bg-cyan-400/10 blur-3xl" />
        <div className="absolute right-[-6rem] top-16 h-72 w-72 rounded-full bg-fuchsia-500/10 blur-3xl" />
        <div className="absolute bottom-[-10rem] left-1/3 h-96 w-96 rounded-full bg-teal-400/10 blur-3xl" />
      </div>
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(82,168,255,0.12),transparent_28%),radial-gradient(circle_at_bottom_right,rgba(148,87,255,0.08),transparent_24%)]" />
    </>
  );
}

function NoiseOverlay() {
  return <div className="noise-overlay pointer-events-none absolute inset-0 opacity-[0.08]" />;
}
