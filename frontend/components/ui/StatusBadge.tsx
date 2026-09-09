/**
 * Attendance status pill. Color mapping ported from the exact classes used in
 * design/attendance_history_mobile/code.html and design/detailed_attendance_sheet/code.html:
 *   Present -> text-primary bg-primary-fixed/30
 *   Absent  -> text-error bg-error-container/30
 *   Late    -> text-secondary bg-secondary-container/30
 *   Manual  -> bg-surface-variant text-on-surface-variant
 * Suspicious has no badge example in the exports; extended consistently using the
 * tertiary (violet) token per DESIGN.md's status-color spec.
 */
const STYLES: Record<string, string> = {
  present: "text-primary bg-primary-fixed/30",
  absent: "text-error bg-error-container/30",
  late: "text-secondary bg-secondary-container/30",
  manual: "bg-surface-variant text-on-surface-variant",
  suspicious: "text-tertiary bg-tertiary-fixed/30",
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
  const style = STYLES[key] ?? "bg-surface-variant text-on-surface-variant";
  const label = LABELS[key] ?? status;
  return (
    <span className={`inline-flex items-center font-label-sm text-label-sm px-2 py-0.5 rounded ${style} ${className}`}>
      {label}
    </span>
  );
}
