import type { ReactNode } from "react";

/** Standard bento card shell used across every desktop Stitch export. */
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`bg-surface-container-lowest rounded-xl border border-surface-variant card-shadow p-6 ${className}`}
    >
      {children}
    </div>
  );
}

/** Translucent/blurred variant used for overlays and floating panels. */
export function GlassCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`glass-card rounded-xl p-6 glass-shadow ${className}`}>{children}</div>;
}
