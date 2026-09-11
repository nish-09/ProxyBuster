"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { RequireRole } from "@/components/route-guard";
import { SideNavBar } from "@/components/layout/SideNavBar";
import { TopNavBar, DesktopTopBar } from "@/components/layout/TopNavBar";
import { BottomMobileNav } from "@/components/layout/BottomMobileNav";
import { NewSessionModal } from "@/components/professor/NewSessionModal";
import { CardSkeleton } from "@/components/ui/Skeleton";
import { useAuth } from "@/lib/auth-context";
import { professorApi, attendanceApi, type ProfessorDashboardOut, type ActivityFeedItem } from "@/lib/api";

function initials(name: string) {
  return name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function formatTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function timeAgo(iso: string) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function severityIcon(severity: string) {
  if (severity === "high") return { icon: "warning", color: "text-error" };
  if (severity === "medium") return { icon: "info", color: "text-secondary" };
  return { icon: "schedule", color: "text-secondary" };
}

function DashboardContent() {
  const { user } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<ProfessorDashboardOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feed, setFeed] = useState<ActivityFeedItem[]>([]);
  const [showNewSession, setShowNewSession] = useState(false);
  const [busyEventId, setBusyEventId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await professorApi.dashboard();
      setData(res);
      setFeed(res.activity_feed);
    } catch {
      setError("Could not load your dashboard. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard fetch-on-mount
    load();
  }, [load]);

  async function startSession(lectureId: string) {
    const session = await attendanceApi.createSession(lectureId);
    setShowNewSession(false);
    const meta = data?.upcoming_sessions.find((s) => s.lecture_id === lectureId);
    const qs = meta
      ? `?subject=${encodeURIComponent(meta.subject_name)}&division=${encodeURIComponent(meta.division_name)}&room=${encodeURIComponent(meta.room ?? "")}&cd=${encodeURIComponent(meta.class_division_id)}`
      : "";
    router.push(`/professor/session/${session.id}${qs}`);
  }

  async function startAdhocSession(classDivisionId: string, durationMinutes: number) {
    const session = await attendanceApi.createAdhocSession({ class_division_id: classDivisionId, duration_minutes: durationMinutes });
    setShowNewSession(false);
    const meta = data?.active_subjects.find((s) => s.class_division_id === classDivisionId);
    const qs = meta
      ? `?subject=${encodeURIComponent(meta.subject_name)}&division=${encodeURIComponent(meta.division_name)}&cd=${encodeURIComponent(meta.class_division_id)}`
      : "";
    router.push(`/professor/session/${session.id}${qs}`);
  }

  async function handleFlag(id: string) {
    setBusyEventId(id);
    try {
      await professorApi.flagEvent(id);
      setFeed((prev) => prev.map((item) => (item.id === id ? { ...item, status: "flagged" } : item)));
    } finally {
      setBusyEventId(null);
    }
  }

  async function handleDismiss(id: string) {
    setBusyEventId(id);
    try {
      await professorApi.dismissEvent(id);
      setFeed((prev) => prev.map((item) => (item.id === id ? { ...item, status: "dismissed" } : item)));
    } finally {
      setBusyEventId(null);
    }
  }

  return (
    <div className="bg-background text-on-background font-body-md antialiased flex min-h-screen">
      <SideNavBar role="professor" />
      <main className="flex-1 md:ml-[280px] min-h-screen bg-surface-container-low">
        <TopNavBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
        <div className="p-container-padding max-w-[1400px] mx-auto space-y-stack-lg pb-24">
          <header className="flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div>
              <h2 className="font-display-lg text-display-lg text-on-surface mb-1">Professor Dashboard</h2>
              <p className="font-body-lg text-body-lg text-on-surface-variant">
                Welcome back{user ? `, ${user.full_name}` : ""}. Here is today&apos;s overview.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <DesktopTopBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
              <button
                onClick={() => setShowNewSession(true)}
                className="flex items-center gap-2 bg-primary text-on-primary px-5 py-2 rounded-lg shadow-sm hover:bg-primary/90 transition-colors"
              >
                <span className="material-symbols-outlined text-sm">add</span>
                <span className="font-label-md text-label-md">Start Attendance</span>
              </button>
            </div>
          </header>

          {loading && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-gutter">
              {[0, 1, 2, 3].map((i) => (
                <CardSkeleton key={i} />
              ))}
            </div>
          )}

          {error && !loading && (
            <div className="bg-error-container/30 border border-error/20 rounded-lg p-4 text-error font-body-md text-body-md">
              {error}
            </div>
          )}

          {data && !loading && (
            <>
              <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-gutter">
                <div className="bg-surface-container-lowest rounded-xl p-5 border border-outline-variant shadow-sm flex flex-col justify-between h-full relative overflow-hidden">
                  <div className="absolute -right-4 -top-4 w-24 h-24 bg-primary/5 rounded-full blur-xl" />
                  <div className="p-2 bg-primary-container/20 rounded-lg text-primary w-fit mb-4">
                    <span className="material-symbols-outlined">school</span>
                  </div>
                  <div>
                    <p className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider mb-1">
                      Today&apos;s Schedule
                    </p>
                    <div className="flex items-baseline gap-2">
                      <h3 className="font-display-lg text-display-lg text-on-surface">{data.today_classes_count}</h3>
                      <span className="font-body-md text-body-md text-on-surface-variant">Classes</span>
                    </div>
                    <p className="font-label-md text-label-md text-primary mt-2 flex items-center gap-1">
                      <span className="material-symbols-outlined text-[16px]">groups</span>
                      {data.total_students} Students Total
                    </p>
                  </div>
                </div>

                <div className="bg-surface-container-lowest rounded-xl p-5 border border-outline-variant shadow-sm flex flex-col justify-between h-full">
                  <div className="p-2 bg-secondary-container/30 rounded-lg text-secondary w-fit mb-4">
                    <span className="material-symbols-outlined">monitoring</span>
                  </div>
                  <div>
                    <p className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider mb-1">
                      Avg Attendance
                    </p>
                    <h3 className="font-display-lg text-display-lg text-on-surface">
                      {data.avg_attendance_pct.toFixed(0)}%
                    </h3>
                    <div className="w-full bg-surface-container-high h-1.5 rounded-full mt-3 overflow-hidden">
                      <div className="bg-primary h-full rounded-full" style={{ width: `${Math.min(100, data.avg_attendance_pct)}%` }} />
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => router.push("/professor/students")}
                  className="text-left bg-surface-container-lowest rounded-xl p-5 border border-error-container shadow-sm flex flex-col justify-between h-full relative overflow-hidden group hover:border-error transition-colors cursor-pointer"
                >
                  <div className="absolute top-0 right-0 w-1 h-full bg-error" />
                  <div className="p-2 bg-error-container rounded-lg text-error w-fit mb-4">
                    <span className="material-symbols-outlined">warning</span>
                  </div>
                  <div>
                    <p className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider mb-1">
                      Suspicious Events
                    </p>
                    <h3 className="font-display-lg text-display-lg text-error">{data.suspicious_events_count}</h3>
                    <p className="font-label-md text-label-md text-on-surface-variant mt-2 flex items-center gap-1 group-hover:text-error transition-colors">
                      View Incident Log <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
                    </p>
                  </div>
                </button>

                <div className="bg-surface-container-lowest rounded-xl p-5 border border-outline-variant shadow-sm flex flex-col justify-between h-full">
                  <div className="p-2 bg-surface-container-highest rounded-lg text-on-surface-variant w-fit mb-4">
                    <span className="material-symbols-outlined">person_off</span>
                  </div>
                  <div>
                    <p className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider mb-1">
                      Students Below 75%
                    </p>
                    <h3 className="font-display-lg text-display-lg text-on-surface">{data.students_below_threshold_count}</h3>
                    <p className="font-label-md text-label-md text-on-surface-variant mt-2">Across all sections</p>
                  </div>
                </div>
              </section>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter">
                <div className="lg:col-span-2 space-y-gutter">
                  <div className="bg-surface rounded-xl border border-outline-variant shadow-sm p-5">
                    <div className="flex justify-between items-center mb-5 pb-3 border-b border-outline-variant/50">
                      <h3 className="font-headline-md text-headline-md text-on-surface">Active Subjects</h3>
                    </div>
                    {data.active_subjects.length === 0 ? (
                      <p className="font-body-md text-body-md text-on-surface-variant py-6 text-center">
                        No subjects assigned yet.
                      </p>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {data.active_subjects.map((subj) => (
                          <div
                            key={subj.class_division_id}
                            className="p-4 rounded-lg bg-surface-container-low border border-outline-variant/50 hover:bg-surface-container transition-colors"
                          >
                            <div className="flex justify-between items-start mb-3">
                              <div className="w-8 h-8 rounded bg-primary-container/20 text-primary flex items-center justify-center font-bold font-label-md">
                                {subj.subject_code.slice(0, 2)}
                              </div>
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                  subj.has_active_session ? "bg-primary-container text-on-primary-container border border-outline" : "bg-surface-dim text-on-surface-variant"
                                }`}
                              >
                                {subj.has_active_session ? "Active" : "Paused"}
                              </span>
                            </div>
                            <h4 className="font-label-md text-label-md text-on-surface mb-1">{subj.subject_name}</h4>
                            <p className="font-label-sm text-label-sm text-on-surface-variant mb-4">
                              {subj.subject_code} • {subj.division_name}
                            </p>
                            <div className="space-y-2">
                              <div className="flex justify-between text-label-sm">
                                <span className="text-on-surface-variant">Avg Attendance</span>
                                <span className="font-bold text-on-surface">{subj.avg_pct.toFixed(0)}%</span>
                              </div>
                              <div className="w-full bg-outline-variant/30 h-1 rounded-full">
                                <div className="bg-primary h-full rounded-full" style={{ width: `${Math.min(100, subj.avg_pct)}%` }} />
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="bg-surface rounded-xl border border-outline-variant shadow-sm overflow-hidden">
                    <div className="p-5 border-b border-outline-variant/50 bg-surface-container-lowest">
                      <h3 className="font-headline-md text-headline-md text-on-surface">Upcoming Sessions</h3>
                    </div>
                    {data.upcoming_sessions.length === 0 ? (
                      <p className="font-body-md text-body-md text-on-surface-variant py-6 text-center">
                        No upcoming lectures scheduled.
                      </p>
                    ) : (
                      <div className="divide-y divide-outline-variant/30">
                        {data.upcoming_sessions.map((s) => {
                          const [time, period] = formatTime(s.scheduled_start).split(" ");
                          return (
                            <div
                              key={s.lecture_id}
                              className="flex items-center gap-4 p-4 hover:bg-surface-container-low transition-colors group relative pl-5"
                            >
                              <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary" />
                              <div className="flex-shrink-0 w-12 h-12 bg-primary-container/10 rounded-full flex flex-col items-center justify-center text-primary">
                                <span className="font-bold font-label-md text-sm leading-none">{time}</span>
                                <span className="text-[10px] uppercase font-bold leading-none mt-1">{period}</span>
                              </div>
                              <div className="flex-1">
                                <h4 className="font-body-md font-semibold text-on-surface">{s.subject_name}</h4>
                                <p className="font-label-sm text-label-sm text-on-surface-variant flex items-center gap-1 mt-0.5">
                                  <span className="material-symbols-outlined text-[14px]">location_on</span>
                                  {s.room ?? "TBD"} • {s.division_name}
                                </p>
                              </div>
                              <button
                                disabled={s.has_active_session}
                                onClick={() => startSession(s.lecture_id)}
                                className="opacity-0 group-hover:opacity-100 transition-opacity px-4 py-2 bg-primary text-on-primary rounded-lg font-label-md text-label-md shadow-sm disabled:opacity-40 disabled:cursor-not-allowed"
                                title={s.has_active_session ? "A session is already active for this lecture" : undefined}
                              >
                                {s.has_active_session ? "Session Active" : "Start Session"}
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>

                <div className="lg:col-span-1">
                  <div className="bg-surface rounded-xl border border-outline-variant shadow-sm h-full flex flex-col">
                    <div className="p-5 border-b border-outline-variant/50 bg-surface-container-lowest flex justify-between items-center">
                      <h3 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
                        <span className="material-symbols-outlined text-error">gpp_maybe</span>
                        Activity Feed
                      </h3>
                      {feed.filter((f) => f.status === "open").length > 0 && (
                        <span className="px-2 py-0.5 bg-error-container text-error rounded-full font-label-sm text-[10px] font-bold">
                          {feed.filter((f) => f.status === "open").length} New
                        </span>
                      )}
                    </div>
                    <div className="flex-1 p-4 space-y-4 overflow-y-auto custom-scrollbar max-h-[520px]">
                      {feed.length === 0 && (
                        <p className="font-body-md text-body-md text-on-surface-variant text-center py-6">
                          No security events yet.
                        </p>
                      )}
                      {feed.map((item) => {
                        const { icon, color } = severityIcon(item.severity);
                        const resolved = item.status !== "open";
                        return (
                          <div
                            key={item.id}
                            className={
                              item.severity === "high" && !resolved
                                ? "p-3 bg-error/5 border border-error/20 rounded-lg relative overflow-hidden"
                                : "p-3 bg-surface border border-outline-variant/50 rounded-lg relative"
                            }
                          >
                            {item.severity === "high" && !resolved && (
                              <div className="absolute left-0 top-0 bottom-0 w-1 bg-error" />
                            )}
                            <div className="flex items-start gap-3">
                              <span className={`material-symbols-outlined text-lg mt-1 ${color}`}>{icon}</span>
                              <div className="flex-1">
                                <div className="flex justify-between items-start mb-1">
                                  <h4 className="font-label-md text-label-md text-on-surface font-bold capitalize">
                                    {item.type.replace(/_/g, " ")}
                                  </h4>
                                  <span className="text-[10px] text-on-surface-variant">{timeAgo(item.created_at)}</span>
                                </div>
                                <p className="font-body-md text-sm text-on-surface-variant leading-snug">{item.description}</p>
                                {!resolved && (
                                  <div className="mt-2 flex gap-2">
                                    <button
                                      disabled={busyEventId === item.id}
                                      onClick={() => handleFlag(item.id)}
                                      className="px-2 py-1 bg-surface border border-outline-variant rounded text-[11px] font-semibold text-on-surface hover:bg-surface-container transition-colors disabled:opacity-50"
                                    >
                                      Flag
                                    </button>
                                    <button
                                      disabled={busyEventId === item.id}
                                      onClick={() => handleDismiss(item.id)}
                                      className="px-2 py-1 text-[11px] font-semibold text-on-surface-variant hover:text-on-surface transition-colors disabled:opacity-50"
                                    >
                                      Dismiss
                                    </button>
                                  </div>
                                )}
                                {resolved && (
                                  <p className="mt-2 text-[11px] font-semibold text-on-surface-variant capitalize">{item.status}</p>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </main>
      <BottomMobileNav role="professor" />

      {showNewSession && data && (
        <NewSessionModal
          sessions={data.upcoming_sessions}
          subjects={data.active_subjects}
          onClose={() => setShowNewSession(false)}
          onStart={startSession}
          onStartAdhoc={startAdhocSession}
        />
      )}
    </div>
  );
}

export default function ProfessorDashboardPage() {
  return (
    <RequireRole role="professor">
      <DashboardContent />
    </RequireRole>
  );
}
