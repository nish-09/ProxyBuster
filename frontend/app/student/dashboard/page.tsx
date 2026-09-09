"use client";

import { useCallback, useEffect, useState } from "react";
import { RequireRole } from "@/components/route-guard";
import { SideNavBar } from "@/components/layout/SideNavBar";
import { TopNavBar, DesktopTopBar } from "@/components/layout/TopNavBar";
import { BottomMobileNav } from "@/components/layout/BottomMobileNav";
import { Card } from "@/components/ui/Card";
import {
  studentApi,
  ApiError,
  type StudentDashboardOut,
  type SubjectAttendanceOut,
  type BunkCalculatorOut,
} from "@/lib/api";

function initials(name: string) {
  return name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function Donut({ pct, size = 160 }: { pct: number; size?: number }) {
  return (
    <svg className="circular-chart text-primary" style={{ width: size, height: size }} viewBox="0 0 36 36">
      <path
        className="circle-bg"
        d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
      />
      <path
        className="circle"
        d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
        stroke="currentColor"
        strokeDasharray={`${pct}, 100`}
      />
      <text className="percentage" x="18" y="20.35">
        {pct.toFixed(1)}%
      </text>
    </svg>
  );
}

function SubjectCard({ subject }: { subject: SubjectAttendanceOut }) {
  const warning = subject.percentage < 75;
  return (
    <div
      className={
        warning
          ? "rounded-xl border-2 border-amber-300 bg-gradient-to-br from-white to-amber-50 p-5 flex flex-col relative overflow-hidden"
          : "bg-surface-container-lowest rounded-xl border border-surface-variant card-shadow p-5 flex flex-col"
      }
    >
      <div className="flex justify-between items-start mb-4">
        <div
          className={
            warning
              ? "w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center text-amber-700"
              : "w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-on-surface-variant"
          }
        >
          <span className="material-symbols-outlined">menu_book</span>
        </div>
        <span
          className={
            warning
              ? "font-label-md text-label-md text-amber-700 bg-amber-100 px-2 py-1 rounded border border-amber-200 flex items-center gap-1"
              : "font-label-md text-label-md text-emerald-600 bg-emerald-50 px-2 py-1 rounded"
          }
        >
          {warning && <span className="material-symbols-outlined text-[14px]">warning</span>}
          {warning ? "Action Req" : "Safe"}
        </span>
      </div>
      <h4 className="font-headline-md text-headline-md-mobile text-on-surface mb-1 truncate" title={subject.subject_name}>
        {subject.subject_name}
      </h4>
      <p className="font-body-md text-body-md text-on-surface-variant mb-4">{subject.subject_code}</p>
      <div className="mt-auto">
        <div className="flex justify-between items-end mb-2">
          <span className={`font-display-lg text-display-lg leading-none ${warning ? "text-amber-700" : "text-on-surface"}`}>
            {subject.percentage.toFixed(0)}
            <span className="text-xl">%</span>
          </span>
          <span className="font-label-sm text-label-sm text-on-surface-variant">
            {subject.present + subject.late + subject.manual}/{subject.total}
          </span>
        </div>
        <div className={`w-full rounded-full h-1.5 ${warning ? "bg-amber-100" : "bg-surface-variant"}`}>
          <div
            className={`h-1.5 rounded-full ${warning ? "bg-amber-500" : "bg-emerald-500"}`}
            style={{ width: `${Math.min(subject.percentage, 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function DashboardContent() {
  const [data, setData] = useState<StudentDashboardOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [calcSubject, setCalcSubject] = useState<string>("");
  const [calcResult, setCalcResult] = useState<BunkCalculatorOut | null>(null);
  const [calcLoading, setCalcLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const dashboard = await studentApi.dashboard();
      setData(dashboard);
      if (dashboard.subjects.length > 0) setCalcSubject(dashboard.subjects[0].class_division_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load dashboard.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional fetch-on-mount
    load();
  }, [load]);

  const runCalculator = useCallback(async (classDivisionId: string) => {
    if (!classDivisionId) return;
    setCalcLoading(true);
    try {
      const result = await studentApi.bunkCalculator(classDivisionId);
      setCalcResult(result);
    } catch {
      setCalcResult(null);
    } finally {
      setCalcLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional recalc-on-subject-change
    if (calcSubject) runCalculator(calcSubject);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [calcSubject]);

  if (loading) {
    return (
      <div className="p-container-padding max-w-7xl mx-auto space-y-gutter animate-pulse">
        <div className="h-10 w-64 bg-surface-container-high rounded-lg" />
        <div className="grid grid-cols-1 md:grid-cols-12 gap-gutter">
          <div className="md:col-span-4 h-64 bg-surface-container-high rounded-xl" />
          <div className="md:col-span-8 h-64 bg-surface-container-high rounded-xl" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-container-padding max-w-xl mx-auto">
        <Card className="text-center">
          <p className="font-body-md text-body-md text-error mb-4">{error ?? "Something went wrong."}</p>
          <button onClick={load} className="px-4 py-2 rounded-md bg-primary text-on-primary font-body-md">
            Retry
          </button>
        </Card>
      </div>
    );
  }

  const firstName = data.full_name.split(" ")[0];

  return (
    <div className="p-container-padding max-w-7xl mx-auto space-y-gutter pb-24 md:pb-12">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-stack-lg pt-4 md:pt-8">
        <div>
          <h2 className="font-display-lg text-display-lg text-on-surface">Good morning, {firstName}</h2>
          <p className="font-body-lg text-body-lg text-on-surface-variant mt-2">
            {data.program}, Semester {data.semester}
          </p>
        </div>
        <div className="mt-4 md:mt-0 flex items-center gap-4">
          <span
            className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full font-label-md text-label-md border ${
              data.standing === "good"
                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                : "bg-amber-50 text-amber-700 border-amber-200"
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${data.standing === "good" ? "bg-emerald-500" : "bg-amber-500"}`} />
            {data.standing === "good" ? "Good Standing" : "Needs Attention"}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-12 gap-gutter">
        <Card className="md:col-span-4 flex flex-col justify-between h-full relative overflow-hidden">
          <div>
            <h3 className="font-headline-md text-headline-md text-on-surface mb-1">Overall Attendance</h3>
            <p className="font-body-md text-body-md text-on-surface-variant">Current Academic Semester</p>
          </div>
          <div className="flex-1 flex items-center justify-center py-6">
            <Donut pct={data.overall_percentage} />
          </div>
          <div className="grid grid-cols-2 gap-4 pt-4 border-t border-surface-variant">
            <div>
              <p className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider mb-1">Total Classes</p>
              <p className="font-headline-md text-headline-md text-on-surface">{data.total_classes}</p>
            </div>
            <div>
              <p className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider mb-1">Attended</p>
              <p className="font-headline-md text-headline-md text-primary">{data.attended_classes}</p>
            </div>
          </div>
        </Card>

        <div className="md:col-span-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-gutter">
          {data.subjects.length === 0 ? (
            <Card className="sm:col-span-2 lg:col-span-3 text-center text-on-surface-variant font-body-md text-body-md">
              You are not enrolled in any subjects yet.
            </Card>
          ) : (
            data.subjects.map((s) => <SubjectCard key={s.class_division_id} subject={s} />)
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-12 gap-gutter mt-gutter">
        <div className="md:col-span-5 bg-primary rounded-xl card-shadow p-6 relative overflow-hidden text-on-primary">
          <div className="relative z-10 h-full flex flex-col">
            <div className="flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined text-tertiary-fixed-dim">calculate</span>
              <h3 className="font-headline-md text-headline-md">Bunk Calculator</h3>
            </div>
            <p className="font-body-md text-body-md text-primary-fixed-dim mb-6">
              &ldquo;Can I miss the next class without dropping below 75%?&rdquo;
            </p>
            <div className="bg-surface/10 rounded-lg p-4 backdrop-blur-sm border border-surface/20 mt-auto">
              <div className="flex justify-between items-center mb-3">
                <span className="font-label-md text-label-md text-primary-fixed uppercase tracking-wider">Target Subject</span>
                <select
                  value={calcSubject}
                  onChange={(e) => setCalcSubject(e.target.value)}
                  className="bg-transparent border-b border-primary-fixed-dim text-on-primary text-sm focus:outline-none focus:border-white py-1"
                >
                  {data.subjects.map((s) => (
                    <option className="text-on-surface" key={s.class_division_id} value={s.class_division_id}>
                      {s.subject_name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-end justify-between border-t border-surface/20 pt-3">
                <div>
                  <p className="font-label-sm text-label-sm text-primary-fixed-dim mb-1">If you miss the next class</p>
                  <p className="font-headline-lg text-headline-lg font-bold">
                    {calcLoading || !calcResult ? "—" : `${calcResult.projected_after_missing_1.toFixed(1)}%`}
                  </p>
                </div>
                {calcResult && (
                  <div
                    className={`flex items-center gap-1 px-2 py-1 rounded ${
                      calcResult.classes_can_miss > 0 ? "text-emerald-300 bg-emerald-900/30" : "text-amber-200 bg-amber-900/30"
                    }`}
                  >
                    <span className="material-symbols-outlined text-[16px]">
                      {calcResult.classes_can_miss > 0 ? "check_circle" : "warning"}
                    </span>
                    <span className="font-label-md text-label-md">
                      {calcResult.classes_can_miss > 0
                        ? `Safe to miss ${calcResult.classes_can_miss}`
                        : `Need ${calcResult.classes_needed_to_recover} more`}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="md:col-span-7 bg-surface-container-lowest rounded-xl border border-surface-variant card-shadow flex flex-col overflow-hidden">
          <div className="border-b border-surface-variant px-6 py-4 flex justify-between items-center bg-surface/50">
            <h3 className="font-headline-md text-headline-md text-on-surface">Today&apos;s Schedule</h3>
          </div>
          <div className="divide-y divide-surface-variant flex-1 overflow-y-auto">
            {data.today_schedule.length === 0 ? (
              <p className="px-6 py-6 font-body-md text-body-md text-on-surface-variant text-center">No classes scheduled today.</p>
            ) : (
              data.today_schedule.map((item, i) => {
                const start = new Date(item.scheduled_start);
                const end = new Date(item.scheduled_end);
                const timeFmt = (d: Date) => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
                return (
                  <div
                    key={i}
                    className={`px-6 py-4 flex items-center gap-4 relative ${
                      item.state === "past"
                        ? "opacity-70"
                        : item.state === "current"
                          ? "bg-secondary-container/20"
                          : "bg-surface-container-lowest"
                    }`}
                  >
                    {item.state === "current" && <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary" />}
                    <div className={`w-1 flex-shrink-0 h-10 rounded-full ${item.state === "current" ? "bg-primary" : "bg-surface-dim"}`} />
                    <div className="w-16 text-center">
                      <p className={`font-label-md text-label-md ${item.state === "current" ? "text-primary font-bold" : "text-on-surface-variant"}`}>
                        {timeFmt(start)}
                      </p>
                      <p className="font-label-sm text-label-sm text-outline">{timeFmt(end)}</p>
                    </div>
                    <div className="flex-1">
                      <p className={`font-body-lg text-body-lg text-on-surface ${item.state === "past" ? "line-through font-medium" : "font-semibold"}`}>
                        {item.subject_name}
                      </p>
                      {item.room && (
                        <p className="font-body-md text-body-md text-on-surface-variant flex items-center gap-1">
                          <span className="material-symbols-outlined text-[14px]">location_on</span> {item.room}
                        </p>
                      )}
                    </div>
                    {item.state === "current" && (
                      <span className="flex h-3 w-3 relative">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-primary" />
                      </span>
                    )}
                    {item.state === "upcoming" && (
                      <span className="hidden sm:block text-outline">
                        <span className="material-symbols-outlined">schedule</span>
                      </span>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function StudentDashboardPage() {
  return (
    <RequireRole role="student">
      <div className="flex min-h-screen bg-surface">
        <SideNavBar role="student" />
        <main className="flex-1 md:ml-[280px] w-full min-h-screen bg-background">
          <TopNavBar userName="" avatarInitials="ST" />
          <div className="hidden md:flex justify-end px-container-padding pt-4">
            <DesktopTopBar userName="" avatarInitials={initials("Student")} />
          </div>
          <DashboardContent />
        </main>
        <BottomMobileNav role="student" />
      </div>
    </RequireRole>
  );
}
