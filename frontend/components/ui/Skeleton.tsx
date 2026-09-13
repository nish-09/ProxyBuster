/**
 * Neo-Brutalist skeleton loading primitives. Every API-driven page should render one of
 * these immediately on mount instead of a blank screen/spinner (see .skeleton-shimmer in
 * globals.css: a lavender block with a neon-lime sweep, no grey/blue/glass). Skeleton
 * dimensions are sized to match their real counterparts so replacing a skeleton with real
 * content never shifts layout.
 */

/** Base building block: a hard-bordered lavender rectangle with the shimmer sweep. */
export function SkeletonBlock({ className = "" }: { className?: string }) {
  return <div className={`skeleton-shimmer rounded-md border border-outline ${className}`} />;
}

/** A single stat/summary card shell — matches the size of the app's usual stat cards. */
export function CardSkeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`bg-surface-container-lowest rounded-lg border border-outline card-shadow p-5 flex flex-col gap-3 ${className}`}>
      <SkeletonBlock className="w-9 h-9 rounded-md" />
      <SkeletonBlock className="w-2/3 h-3" />
      <SkeletonBlock className="w-1/2 h-7" />
    </div>
  );
}

/** Table shell with placeholder rows — renders the real header immediately if passed, so the
 * columns don't jump when data arrives. */
export function TableSkeleton({ rows = 6, columns = 4 }: { rows?: number; columns?: number }) {
  return (
    <div className="bg-surface-container-lowest border border-outline rounded-md overflow-hidden">
      <div className="divide-y divide-outline">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex items-center gap-4 p-4">
            {Array.from({ length: columns }).map((__, c) => (
              <SkeletonBlock key={c} className={`h-4 ${c === 0 ? "flex-[2]" : "flex-1"}`} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Full dashboard shell: header, a row of stat cards, and two content blocks below. Used by
 * the student/professor/admin dashboards while their first API response is in flight. */
const STAT_GRID_COLS: Record<number, string> = {
  2: "lg:grid-cols-2",
  3: "lg:grid-cols-3",
  4: "lg:grid-cols-4",
};

export function DashboardSkeleton({ statCount = 4 }: { statCount?: number }) {
  return (
    <div className="p-container-padding max-w-[1400px] mx-auto w-full space-y-gutter">
      <div className="flex flex-col gap-2">
        <SkeletonBlock className="w-64 h-8" />
        <SkeletonBlock className="w-80 h-4" />
      </div>
      <div className={`grid grid-cols-1 md:grid-cols-2 ${STAT_GRID_COLS[statCount] ?? "lg:grid-cols-4"} gap-gutter`}>
        {Array.from({ length: statCount }).map((_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter">
        <div className="lg:col-span-2 bg-surface-container-lowest rounded-lg border border-outline card-shadow p-5 flex flex-col gap-3">
          <SkeletonBlock className="w-40 h-5 mb-2" />
          <SkeletonBlock className="w-full h-16" />
          <SkeletonBlock className="w-full h-16" />
          <SkeletonBlock className="w-full h-16" />
        </div>
        <div className="bg-surface-container-lowest rounded-lg border border-outline card-shadow p-5 flex flex-col gap-3">
          <SkeletonBlock className="w-32 h-5 mb-2" />
          <SkeletonBlock className="w-full h-12" />
          <SkeletonBlock className="w-full h-12" />
        </div>
      </div>
    </div>
  );
}

/** Attendance sheet shell — the register table with a filter bar above it. */
export function AttendanceSheetSkeleton() {
  return (
    <div className="flex-1 bg-surface-container-lowest border border-outline rounded-md overflow-hidden flex flex-col min-h-[300px]">
      <div className="p-4 flex gap-2 border-b border-outline">
        <SkeletonBlock className="h-9 w-40" />
        <SkeletonBlock className="h-9 w-32" />
        <SkeletonBlock className="h-9 w-32" />
      </div>
      <div className="p-4">
        <TableSkeleton rows={8} columns={6} />
      </div>
    </div>
  );
}

/** Shown the instant a professor clicks "Start Session", before the session/QR endpoints
 * resolve — real subject/division text (already known client-side) renders immediately, only
 * the QR + live counts are placeholders (spec #23: "GENERATING QR", "Present: -- / --"). */
export function LiveSessionSkeleton({ subject, division }: { subject?: string; division?: string }) {
  return (
    <div className="flex-1 p-container-padding flex flex-col gap-gutter max-w-5xl mx-auto w-full">
      <div className="bg-surface-container-lowest rounded-lg border border-outline card-shadow p-stack-md flex flex-col sm:flex-row justify-between items-start sm:items-center gap-stack-sm">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="w-2.5 h-2.5 rounded-full bg-outline pulse-ring" />
            <span className="font-label-sm text-label-sm text-on-surface-variant font-bold">SESSION STARTING</span>
          </div>
          <h2 className="font-display-lg text-display-lg text-on-surface uppercase">
            {subject ?? "Attendance Session"} {division && <span className="text-on-surface-variant font-headline-lg">({division})</span>}
          </h2>
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter flex-1">
        <div className="lg:col-span-2 bg-surface-container-lowest rounded-lg border border-outline card-shadow flex flex-col items-center justify-center min-h-[420px] gap-3 p-4">
          <div className="w-full max-w-64 aspect-square skeleton-shimmer rounded-lg border border-outline flex items-center justify-center">
            <span className="font-label-md text-label-md text-on-surface-variant font-bold uppercase text-center px-2">Generating QR</span>
          </div>
        </div>
        <div className="flex flex-col gap-gutter h-full">
          <CardSkeleton />
          <CardSkeleton className="flex-1" />
        </div>
      </div>
    </div>
  );
}

/** Generic full-page shell for a route not yet covered by a more specific skeleton (used by
 * loading.tsx files) — a header bar plus a couple of content blocks. */
export function PageSkeleton() {
  return (
    <div className="min-h-screen bg-background p-container-padding">
      <div className="max-w-[1400px] mx-auto w-full space-y-gutter">
        <SkeletonBlock className="w-56 h-8" />
        <DashboardSkeleton statCount={4} />
      </div>
    </div>
  );
}

/** Minimal form shell (a handful of labeled input placeholders + an action button). */
export function FormSkeleton({ fields = 4 }: { fields?: number }) {
  return (
    <div className="bg-surface-container-lowest rounded-lg border border-outline card-shadow p-stack-md flex flex-col gap-stack-sm">
      {Array.from({ length: fields }).map((_, i) => (
        <div key={i} className="flex flex-col gap-1">
          <SkeletonBlock className="w-24 h-3" />
          <SkeletonBlock className="w-full h-10" />
        </div>
      ))}
      <SkeletonBlock className="w-32 h-10 mt-2" />
    </div>
  );
}
