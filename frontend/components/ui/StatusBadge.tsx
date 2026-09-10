/**
 * Attendance status badge. Semantic color mapping (see design system):
 *   Present    -> mint   (success)
 *   Late       -> yellow (warning)
 *   Absent     -> coral  (error/blocked)
 *   Manual     -> blue   (active/professor-initiated)
 *   Suspicious -> coral  (security alert)
 */
const STYLES: Record<string, string> = {
  present: "text-on-tertiary-container bg-tertiary-container border-outline",
  absent: "text-on-error-container bg-error-container border-outline",
  late: "text-on-secondary-container bg-secondary-container border-outline",
  manual: "text-on-primary-container bg-primary-container border-outline",
  suspicious: "text-on-error bg-error border-outline",
};

const LABELS: Record<string, string> = {
  present: "Present",
  absent: "Absent",
  late: "Late",
  manual: "Manual",
  suspicious: "Suspicious",
};

export function StatusBadge({ status, className = "" }: { status: string; className?: string }) {
  const key = status.toLowerCase();
  const style = STYLES[key] ?? "bg-surface-variant text-on-surface-variant border-outline";
  const label = LABELS[key] ?? status;
  return (
    <span
      className={`inline-flex items-center font-label-sm text-label-sm font-bold uppercase tracking-wide px-2 py-0.5 rounded border-2 ${style} ${className}`}
    >
      {label}
    </span>
  );
}
