import type { ReactNode } from "react";

/** Standard skeuomorphic card shell: raised slate-blue panel, thin border, layered shadow
 * (soft inner top highlight + outer drop shadow) — a physical panel, not a floating rectangle. */
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`bg-surface-container-lowest rounded-lg border border-outline card-shadow p-6 ${className}`}>
      {children}
    </div>
  );
}

/** Solid variant used for overlays and floating panels. */
export function GlassCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`glass-card rounded-lg p-6 glass-shadow ${className}`}>{children}</div>;
}
