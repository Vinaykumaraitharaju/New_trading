import type { PropsWithChildren } from "react";

export function GlassPanel({ children, className = "" }: PropsWithChildren<{ className?: string }>) {
  return (
    <div
      className={`relative border border-white/10 bg-white/[0.03] shadow-[0_20px_60px_rgba(0,0,0,0.26),inset_0_1px_0_rgba(255,255,255,0.04)] backdrop-blur-xl ${className}`}
    >
      {children}
    </div>
  );
}
