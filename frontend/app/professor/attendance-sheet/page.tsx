"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { RequireRole } from "@/components/route-guard";
import { SideNavBar } from "@/components/layout/SideNavBar";
import { TopNavBar, DesktopTopBar } from "@/components/layout/TopNavBar";
import { BottomMobileNav } from "@/components/layout/BottomMobileNav";
import { useAuth } from "@/lib/auth-context";
import { professorApi, type ActiveSubjectOut, type AttendanceSheetOut } from "@/lib/api";

function initials(name: string) {
  return name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

function isoDaysAgo(days: number) {
  // Built from local Y/M/D (not toISOString, which converts to UTC and can shift the
  // calendar date backwards for timezones ahead of UTC in the early-morning hours).
  const d = new Date();
  d.setDate(d.getDate() - days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

const STATUS_LETTER: Record<string, string> = { present: "P", absent: "A", late: "L", manual: "M", suspicious: "S" };
const CELL_STYLE: Record<string, string> = {
  present: "bg-tertiary-fixed text-on-tertiary-fixed",
  late: "bg-secondary-fixed text-on-secondary-fixed",
  absent: "bg-error-container text-on-error-container",
  manual: "bg-surface-variant text-on-surface-variant",
};

function SheetContent() {
  const { user } = useAuth();
  const [subjects, setSubjects] = useState<ActiveSubjectOut[]>([]);
  const [classDivisionId, setClassDivisionId] = useState<string>("");
  const [dateFrom, setDateFrom] = useState(isoDaysAgo(14));
  const [dateTo, setDateTo] = useState(isoDaysAgo(0));
  const [search, setSearch] = useState("");
  const [sheet, setSheet] = useState<AttendanceSheetOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    professorApi.dashboard().then((res) => {
      setSubjects(res.active_subjects);
      if (res.active_subjects.length > 0) setClassDivisionId(res.active_subjects[0].class_division_id);
    });
  }, []);

  const loadSheet = useCallback(async () => {
    if (!classDivisionId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await professorApi.attendanceSheet({ class_division_id: classDivisionId, date_from: dateFrom, date_to: dateTo });
      setSheet(res);
    } catch {
      setError("Could not load the attendance sheet.");
    } finally {
      setLoading(false);
    }
  }, [classDivisionId, dateFrom, dateTo]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard fetch-on-mount/filter-change
    loadSheet();
  }, [loadSheet]);

  const filteredRows = useMemo(() => {
    if (!sheet) return [];
    const q = search.trim().toLowerCase();
    if (!q) return sheet.rows;
    return sheet.rows.filter((r) => r.full_name.toLowerCase().includes(q) || r.roll_number.toLowerCase().includes(q));
  }, [sheet, search]);

  function exportCsv() {
    if (!sheet) return;
    const header = ["Student", "Roll Number", ...sheet.columns.map((c) => c.label), "Avg %"];
    const lines = [header.join(",")];
    for (const row of filteredRows) {
      const cells = sheet.columns.map((c) => STATUS_LETTER[row.cells[c.lecture_id]?.status ?? ""] ?? "");
      lines.push([`"${row.full_name}"`, row.roll_number, ...cells, row.avg_pct.toFixed(0)].join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `attendance-sheet-${dateFrom}-to-${dateTo}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="bg-background text-on-background font-body-md antialiased flex min-h-screen">
      <SideNavBar role="professor" />
      <main className="flex-1 md:ml-[280px] min-h-screen bg-surface-container-low flex flex-col">
        <TopNavBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
        <div className="flex-1 p-container-padding max-w-[1400px] mx-auto w-full flex flex-col gap-gutter pb-24">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-gutter">
            <div>
              <h2 className="font-headline-lg text-headline-lg text-on-surface mb-1">Attendance Sheet</h2>
              <p className="font-body-md text-body-md text-on-surface-variant">
                Review attendance records, identify anomalies, and export data.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-stack-sm">
              <DesktopTopBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
              <select
                value={classDivisionId}
                onChange={(e) => setClassDivisionId(e.target.value)}
                className="h-10 px-3 bg-surface-container-lowest border border-outline-variant rounded-md font-body-md text-body-md focus:outline-none focus:border-primary outline-none min-w-[160px]"
              >
                {subjects.map((s) => (
                  <option key={s.class_division_id} value={s.class_division_id}>
                    {s.subject_name} • {s.division_name}
                  </option>
                ))}
              </select>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="h-10 px-3 bg-surface-container-lowest border border-outline-variant rounded-md font-body-md text-body-md outline-none"
              />
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="h-10 px-3 bg-surface-container-lowest border border-outline-variant rounded-md font-body-md text-body-md outline-none"
              />
              <div className="relative flex items-center">
                <span className="material-symbols-outlined absolute left-3 text-outline text-[18px]">search</span>
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search student..."
                  className="h-10 pl-9 pr-3 bg-surface-container-lowest border border-outline-variant rounded-md font-body-md text-body-md focus:outline-none focus:border-primary outline-none w-full md:w-56"
                />
              </div>
              <button
                onClick={exportCsv}
                disabled={!sheet}
                className="h-10 px-4 bg-primary text-on-primary font-label-md text-label-md rounded-md hover:bg-primary/90 transition-colors flex items-center gap-2 disabled:opacity-50"
              >
                <span className="material-symbols-outlined text-[18px]">download</span>
                Export
              </button>
            </div>
          </div>

          {/* Tighter radius than the rest of the app on purpose (spec: "do not make the
              table excessively rounded") — this should read as a register, not a card. */}
          <div className="flex-1 bg-surface-container-lowest border border-outline-variant rounded-md clay-raised overflow-hidden flex flex-col relative min-h-[300px]">
            {loading && <div className="p-8 text-center font-body-md text-body-md text-on-surface-variant">Loading...</div>}
            {error && <div className="p-8 text-center font-body-md text-body-md text-error">{error}</div>}
            {!loading && !error && sheet && (
              <>
                <div className="flex-1 overflow-auto custom-scrollbar relative">
                  <table className="w-full text-left border-collapse min-w-[800px]">
                    <thead className="sticky top-0 bg-surface-container-lowest border-b border-outline z-10">
                      <tr>
                        <th className="py-3 px-4 font-label-md text-label-md text-on-surface-variant whitespace-nowrap bg-surface-container-lowest">
                          Student Information
                        </th>
                        {sheet.columns.map((c) => (
                          <th key={c.lecture_id} className="py-3 px-4 font-label-md text-label-md text-on-surface-variant whitespace-nowrap text-center">
                            {c.label}
                          </th>
                        ))}
                        <th className="py-3 px-4 font-label-md text-label-md text-on-surface-variant whitespace-nowrap text-right">Avg %</th>
                      </tr>
                    </thead>
                    <tbody className="font-body-md text-body-md text-on-surface divide-y divide-surface-variant">
                      {filteredRows.map((row) => (
                        <tr
                          key={row.student_id}
                          className={row.suspicious ? "bg-error-container/10 hover:bg-error-container/20 transition-colors" : "hover:bg-surface-container-low transition-colors"}
                        >
                          <td className={`py-3 px-4 flex items-center gap-3 border-l-4 ${row.suspicious ? "border-error" : "border-transparent"}`}>
                            <div className="w-8 h-8 rounded-full bg-tertiary-container text-on-tertiary-container flex items-center justify-center font-label-md">
                              {initials(row.full_name)}
                            </div>
                            <div>
                              <div className={`font-medium flex items-center gap-1 ${row.suspicious ? "text-error" : ""}`}>
                                {row.full_name}
                                {row.suspicious && (
                                  <span className="material-symbols-outlined text-[14px]" title={row.suspicious_reason ?? "Anomalous pattern detected"}>
                                    warning
                                  </span>
                                )}
                              </div>
                              <div className="font-label-sm text-outline">Roll: {row.roll_number}</div>
                            </div>
                          </td>
                          {sheet.columns.map((c) => {
                            const cell = row.cells[c.lecture_id];
                            const status = cell?.status ?? null;
                            return (
                              <td key={c.lecture_id} className="py-3 px-4 text-center">
                                {status ? (
                                  <span
                                    className={`inline-flex items-center justify-center w-6 h-6 rounded font-label-md ${CELL_STYLE[status] ?? "bg-surface-variant text-on-surface-variant"}`}
                                    title={cell?.method === "manual" ? "Manual Entry" : status}
                                  >
                                    {STATUS_LETTER[status] ?? "?"}
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center justify-center w-6 h-6 rounded bg-surface-container text-outline font-label-md">—</span>
                                )}
                              </td>
                            );
                          })}
                          <td className={`py-3 px-4 text-right font-medium ${row.avg_pct < 75 ? "text-error" : ""}`}>{row.avg_pct.toFixed(0)}%</td>
                        </tr>
                      ))}
                      {filteredRows.length === 0 && (
                        <tr>
                          <td colSpan={sheet.columns.length + 2} className="py-10 text-center text-on-surface-variant">
                            No students match your search.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <div className="bg-surface-container py-3 px-4 border-t border-outline-variant flex flex-wrap items-center justify-between gap-2 text-label-sm">
                  <div className="flex items-center gap-4">
                    <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-tertiary-fixed border border-tertiary/20 block" /> Present (P)</span>
                    <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-error-container border border-error/20 block" /> Absent (A)</span>
                    <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-secondary-fixed border border-secondary/20 block" /> Late (L)</span>
                    <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-surface-variant border border-outline/20 block" /> Manual (M)</span>
                  </div>
                  <div className="flex items-center gap-2 text-on-surface-variant">
                    <span className="w-3 h-3 rounded-sm bg-error-container/30 border border-error block" /> Suspicious Pattern Detected
                  </div>
                </div>
              </>
            )}
            {!loading && !error && !sheet && (
              <div className="p-8 text-center font-body-md text-body-md text-on-surface-variant">Select a subject to view its roster.</div>
            )}
          </div>
        </div>
      </main>
      <BottomMobileNav role="professor" />
    </div>
  );
}

export default function AttendanceSheetPage() {
  return (
    <RequireRole role="professor">
      <SheetContent />
    </RequireRole>
  );
}
