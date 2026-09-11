"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { RequireRole } from "@/components/route-guard";
import { SideNavBar } from "@/components/layout/SideNavBar";
import { TopNavBar, DesktopTopBar } from "@/components/layout/TopNavBar";
import { BottomMobileNav } from "@/components/layout/BottomMobileNav";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Card } from "@/components/ui/Card";
import { studentApi, ApiError, type AttendanceHistoryEntry, type StudentDashboardOut } from "@/lib/api";

function pad(n: number) {
  return n.toString().padStart(2, "0");
}
function isoDate(d: Date) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
function monthBounds(year: number, month: number) {
  const from = new Date(year, month, 1);
  const to = new Date(year, month + 1, 0);
  return { from, to };
}

function statusColor(status: string): string {
  switch (status) {
    case "present":
      return "bg-primary";
    case "late":
      return "bg-secondary";
    case "manual":
      return "bg-tertiary";
    default:
      return "bg-error";
  }
}

function downloadCsv(entries: AttendanceHistoryEntry[]) {
  const header = ["Date", "Subject", "Professor", "Status", "Method"];
  const rows = entries.map((e) => [
    e.scheduled_start,
    e.subject_name,
    e.professor_name,
    e.status,
    e.method,
  ]);
  const csv = [header, ...rows].map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "attendance_history.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function AttendanceContent() {
  const today = new Date();
  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());
  const [subjectId, setSubjectId] = useState<string>("all");
  const [subjects, setSubjects] = useState<StudentDashboardOut["subjects"]>([]);
  const [entries, setEntries] = useState<AttendanceHistoryEntry[]>([]);
  const [summary, setSummary] = useState({ present: 0, absent: 0, late: 0, manual: 0, total: 0, percentage: 0 });
  const [visibleCount, setVisibleCount] = useState(10);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    studentApi
      .dashboard()
      .then((d) => setSubjects(d.subjects))
      .catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { from, to } = monthBounds(viewYear, viewMonth);
      const result = await studentApi.attendance({
        subject_id: subjectId === "all" ? undefined : subjectId,
        from_date: isoDate(from),
        to_date: isoDate(to),
        limit: 500,
        offset: 0,
      });
      setEntries(result.entries);
      setSummary({
        present: result.present,
        absent: result.absent,
        late: result.late,
        manual: result.manual,
        total: result.total,
        percentage: result.percentage,
      });
      setVisibleCount(10);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load attendance history.");
    } finally {
      setLoading(false);
    }
  }, [subjectId, viewYear, viewMonth]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional fetch-on-mount/filter-change
    load();
  }, [load]);

  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const firstWeekday = new Date(viewYear, viewMonth, 1).getDay();

  const dayStatus = useMemo(() => {
    const map = new Map<number, string>();
    const precedence: Record<string, number> = { absent: 3, late: 2, manual: 1, present: 0 };
    for (const e of entries) {
      const d = new Date(e.scheduled_start);
      if (d.getFullYear() !== viewYear || d.getMonth() !== viewMonth) continue;
      const day = d.getDate();
      const existing = map.get(day);
      if (!existing || (precedence[e.status] ?? 0) > (precedence[existing] ?? 0)) {
        map.set(day, e.status);
      }
    }
    return map;
  }, [entries, viewYear, viewMonth]);

  const sortedEntries = useMemo(
    () => [...entries].sort((a, b) => new Date(b.scheduled_start).getTime() - new Date(a.scheduled_start).getTime()),
    [entries]
  );
  const visibleEntries = sortedEntries.slice(0, visibleCount);

  const monthLabel = new Date(viewYear, viewMonth, 1).toLocaleDateString([], { month: "long", year: "numeric" });

  return (
    <div className="p-4 md:p-container-padding max-w-7xl mx-auto w-full flex flex-col gap-gutter pb-24 md:pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-2">
        <div>
          <h2 className="font-display-lg text-display-lg text-on-surface">My Attendance</h2>
          <p className="font-body-md text-body-md text-on-surface-variant mt-1">Track your academic presence and standing.</p>
        </div>
        <div className="relative min-w-[220px]">
          <select
            value={subjectId}
            onChange={(e) => setSubjectId(e.target.value)}
            className="w-full h-10 pl-3 pr-10 appearance-none bg-surface-container-lowest border border-outline-variant rounded-lg font-body-md text-body-md text-on-surface focus:outline-none focus:outline-none focus:border-primary shadow-sm glass-shadow cursor-pointer"
          >
            <option value="all">All Subjects</option>
            {subjects.map((s) => (
              <option key={s.class_division_id} value={s.class_division_id}>
                {s.subject_name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <Card className="text-center">
          <p className="font-body-md text-body-md text-error mb-4">{error}</p>
          <button onClick={load} className="px-4 py-2 rounded-md bg-primary text-on-primary font-body-md">
            Retry
          </button>
        </Card>
      )}

      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-gutter animate-pulse">
          <div className="lg:col-span-8 h-40 bg-surface-container-high rounded-xl" />
          <div className="lg:col-span-4 h-40 bg-surface-container-high rounded-xl" />
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-gutter">
          <Card className="lg:col-span-8 flex flex-col justify-center">
            <h3 className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider mb-6 border-b border-outline pb-2">
              Overview
            </h3>
            <div className="grid grid-cols-4 gap-4 divide-x divide-surface-variant">
              {[
                { label: "Present", value: summary.present, icon: "check_circle", bg: "bg-primary-container", fg: "text-on-primary-container" },
                { label: "Absent", value: summary.absent, icon: "cancel", bg: "bg-error-container", fg: "text-on-error-container" },
                { label: "Late", value: summary.late, icon: "schedule", bg: "bg-surface-container-high", fg: "text-on-surface-variant" },
                { label: "Manual", value: summary.manual, icon: "edit_note", bg: "bg-tertiary-container", fg: "text-on-tertiary-container" },
              ].map((stat) => (
                <div key={stat.label} className="flex flex-col items-center justify-center text-center px-2">
                  <div className={`w-12 h-12 rounded-full ${stat.bg} ${stat.fg} flex items-center justify-center mb-3`}>
                    <span className="material-symbols-outlined text-[24px]">{stat.icon}</span>
                  </div>
                  <span className="font-display-lg text-display-lg text-on-surface mb-1">{stat.value}</span>
                  <span className="font-label-md text-label-md text-on-surface-variant uppercase">{stat.label}</span>
                </div>
              ))}
            </div>
          </Card>

          <Card className="lg:col-span-4 flex flex-col relative overflow-hidden">
            <h3 className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider mb-4 border-b border-outline pb-2 relative z-10">
              Status
            </h3>
            <div className="flex-1 flex flex-col justify-center items-center relative z-10">
              <div className="relative w-32 h-32 mb-4">
                <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                  <circle className="text-surface-container-high" cx="50" cy="50" fill="transparent" r="40" stroke="currentColor" strokeWidth="8" />
                  <circle
                    className="text-primary"
                    cx="50"
                    cy="50"
                    fill="transparent"
                    r="40"
                    stroke="currentColor"
                    strokeDasharray="251.2"
                    strokeDashoffset={251.2 - (251.2 * Math.min(summary.percentage, 100)) / 100}
                    strokeLinecap="round"
                    strokeWidth="8"
                  />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="font-headline-lg text-headline-lg text-on-surface font-bold">{summary.percentage.toFixed(0)}%</span>
                  <span className="font-label-sm text-label-sm text-on-surface-variant">Overall</span>
                </div>
              </div>
              <div className="bg-primary-container/20 border border-primary-container rounded-lg p-3 w-full text-center">
                <p className="font-body-md text-body-md text-on-primary-fixed-variant">This month, {summary.total} lecture(s) recorded.</p>
              </div>
            </div>
          </Card>

          <Card className="lg:col-span-4">
            <div className="flex items-center justify-between border-b border-outline pb-2 mb-4">
              <h3 className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">{monthLabel}</h3>
              <div className="flex gap-1">
                <button
                  onClick={() => {
                    const m = viewMonth - 1;
                    if (m < 0) {
                      setViewMonth(11);
                      setViewYear((y) => y - 1);
                    } else setViewMonth(m);
                  }}
                  className="text-on-surface-variant hover:text-primary transition-colors"
                >
                  <span className="material-symbols-outlined text-[16px]">chevron_left</span>
                </button>
                <button
                  onClick={() => {
                    const m = viewMonth + 1;
                    if (m > 11) {
                      setViewMonth(0);
                      setViewYear((y) => y + 1);
                    } else setViewMonth(m);
                  }}
                  className="text-on-surface-variant hover:text-primary transition-colors"
                >
                  <span className="material-symbols-outlined text-[16px]">chevron_right</span>
                </button>
              </div>
            </div>
            <div className="grid grid-cols-7 gap-1 text-center mb-2">
              {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
                <span key={i} className="font-label-sm text-label-sm text-outline">
                  {d}
                </span>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1 text-center">
              {Array.from({ length: firstWeekday }).map((_, i) => (
                <div key={`e${i}`} />
              ))}
              {Array.from({ length: daysInMonth }).map((_, i) => {
                const day = i + 1;
                const status = dayStatus.get(day);
                return (
                  <div key={day} className="py-1 font-body-md text-body-md flex flex-col items-center">
                    {day}
                    {status && <span className={`w-1.5 h-1.5 rounded-full mt-0.5 ${statusColor(status)}`} />}
                  </div>
                );
              })}
            </div>
          </Card>

          <Card className="lg:col-span-8 !p-0 flex flex-col overflow-hidden">
            <div className="p-6 border-b border-outline flex justify-between items-center bg-surface/50">
              <h3 className="font-headline-md text-headline-md text-on-surface">Recent Lectures</h3>
              <button
                onClick={() => downloadCsv(sortedEntries)}
                className="flex items-center gap-2 font-label-md text-label-md text-primary hover:text-primary-fixed-dim transition-colors"
              >
                <span className="material-symbols-outlined text-[18px]">download</span>
                EXPORT
              </button>
            </div>
            <div className="overflow-x-auto custom-scrollbar">
              {visibleEntries.length === 0 ? (
                <p className="p-8 text-center font-body-md text-body-md text-on-surface-variant">No lectures recorded this month.</p>
              ) : (
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-surface border-b border-outline-variant">
                      <th className="py-3 px-6 font-label-md text-label-md text-outline uppercase tracking-wider font-semibold">Date &amp; Time</th>
                      <th className="py-3 px-6 font-label-md text-label-md text-outline uppercase tracking-wider font-semibold">Subject</th>
                      <th className="py-3 px-6 font-label-md text-label-md text-outline uppercase tracking-wider font-semibold">Professor</th>
                      <th className="py-3 px-6 font-label-md text-label-md text-outline uppercase tracking-wider font-semibold text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-variant">
                    {visibleEntries.map((e) => (
                      <tr key={e.id} className="hover:bg-surface-container-low transition-colors">
                        <td className="py-4 px-6">
                          <div className="font-body-md text-body-md text-on-surface font-medium">
                            {new Date(e.scheduled_start).toLocaleDateString()}
                          </div>
                          <div className="font-label-sm text-label-sm text-on-surface-variant mt-0.5">
                            {new Date(e.scheduled_start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                          </div>
                        </td>
                        <td className="py-4 px-6 font-body-md text-body-md text-on-surface-variant">{e.subject_name}</td>
                        <td className="py-4 px-6 font-body-md text-body-md text-on-surface-variant">{e.professor_name}</td>
                        <td className="py-4 px-6 text-right">
                          <StatusBadge status={e.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            {visibleCount < sortedEntries.length && (
              <div className="p-4 border-t border-outline bg-surface/30 flex justify-center">
                <button
                  onClick={() => setVisibleCount((c) => c + 10)}
                  className="font-label-md text-label-md text-primary hover:text-on-primary-fixed-variant transition-colors flex items-center gap-1 uppercase tracking-wider"
                >
                  Load More <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
                </button>
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}

export default function StudentAttendancePage() {
  return (
    <RequireRole role="student">
      <div className="flex min-h-screen bg-surface">
        <SideNavBar role="student" />
        <div className="flex-1 md:ml-[280px] flex flex-col min-h-screen">
          <TopNavBar userName="" avatarInitials="ST" />
          <div className="hidden md:flex justify-end px-container-padding pt-4">
            <DesktopTopBar userName="" avatarInitials="ST" />
          </div>
          <AttendanceContent />
        </div>
        <BottomMobileNav role="student" />
      </div>
    </RequireRole>
  );
}
