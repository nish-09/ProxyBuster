import type { ReactNode } from "react";

/** Standard clay card shell: soft extruded warm-clay panel, thin border, layered shadow
 * (outer warm-dark drop shadow + a white highlight on the opposite edge) — reads as
 * physically raised off the page, not a flat floating rectangle. */
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`bg-surface-container-lowest rounded-lg border border-outline card-shadow p-6 ${className}`}>
      {children}
    </div>
  );
}

/** Solid variant used for overlays and floating panels (modals, popovers). */
export function GlassCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`glass-card rounded-lg p-6 glass-shadow ${className}`}>{children}</div>;
}

/** Aliases matching the Claymorphism design-system naming (ClayCard/ClayPanel) — same
 * component, so existing call sites keep working unchanged while new code can opt into
 * the more descriptive name. */
export const ClayCard = Card;
export const ClayPanel = GlassCard;
