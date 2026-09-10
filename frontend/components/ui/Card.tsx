import type { ReactNode } from "react";

/** Standard neo-brutalist card shell: white surface, thick black border, hard offset shadow. */
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`bg-surface-container-lowest rounded-lg border-2 border-outline card-shadow p-6 ${className}`}>
      {children}
    </div>
  );
}

/** Solid variant (no blur/translucency) used for overlays and floating panels. */
export function GlassCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`glass-card rounded-lg p-6 glass-shadow ${className}`}>{children}</div>;
}
