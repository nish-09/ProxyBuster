"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { RequireRole } from "@/components/route-guard";
import { SideNavBar } from "@/components/layout/SideNavBar";
import { TopNavBar, DesktopTopBar } from "@/components/layout/TopNavBar";
import { BottomMobileNav } from "@/components/layout/BottomMobileNav";
import { useAuth } from "@/lib/auth-context";
import { professorApi, type ActiveSubjectOut, type StudentListItem } from "@/lib/api";

function initials(name: string) {
  return name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

function StudentsContent() {
  const { user } = useAuth();
  const [subjects, setSubjects] = useState<ActiveSubjectOut[]>([]);
  const [q, setQ] = useState("");
  const [classDivisionId, setClassDivisionId] = useState("");
  const [minPct, setMinPct] = useState("");
  const [maxPct, setMaxPct] = useState("");
  const [sort, setSort] = useState("name");
  const [items, setItems] = useState<StudentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    professorApi.dashboard().then((res) => setSubjects(res.active_subjects));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await professorApi.students({
        q: q || undefined,
        class_division_id: classDivisionId || undefined,
        min_pct: minPct ? Number(minPct) : undefined,
        max_pct: maxPct ? Number(maxPct) : undefined,
        sort,
      });
      setItems(res.items);
    } catch {
      setError("Could not load students.");
    } finally {
      setLoading(false);
    }
  }, [q, classDivisionId, minPct, maxPct, sort]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  return (
    <div className="bg-background text-on-background font-body-md antialiased flex min-h-screen">
      <SideNavBar role="professor" />
      <main className="flex-1 md:ml-[280px] min-h-screen bg-surface-container-low flex flex-col">
        <TopNavBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
        <div className="flex-1 p-container-padding max-w-[1400px] mx-auto w-full flex flex-col gap-gutter pb-24">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-gutter">
            <div>
              <h2 className="font-headline-lg text-headline-lg text-on-surface mb-1">Students</h2>
              <p className="font-body-md text-body-md text-on-surface-variant">Search, filter, and review student attendance.</p>
            </div>
            <DesktopTopBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
          </div>

          <div className="flex flex-wrap items-center gap-stack-sm bg-surface-container-lowest border border-outline-variant rounded-xl p-4 shadow-sm">
            <div className="relative flex items-center w-full sm:w-56">
              <span className="material-symbols-outlined absolute left-3 text-outline text-[18px]">search</span>
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search name or roll..."
                className="h-10 pl-9 pr-3 bg-surface-container border border-outline-variant rounded-md font-body-md text-body-md focus:outline-none focus:border-primary outline-none w-full"
              />
            </div>
            <select
              value={classDivisionId}
              onChange={(e) => setClassDivisionId(e.target.value)}
              className="h-10 px-3 bg-surface-container border border-outline-variant rounded-md font-body-md text-body-md outline-none"
            >
              <option value="">All Classes</option>
              {subjects.map((s) => (
                <option key={s.class_division_id} value={s.class_division_id}>
                  {s.subject_name} • {s.division_name}
                </option>
              ))}
            </select>
            <input
              type="number"
              value={minPct}
              onChange={(e) => setMinPct(e.target.value)}
              placeholder="Min %"
              className="h-10 w-24 px-3 bg-surface-container border border-outline-variant rounded-md font-body-md text-body-md outline-none"
            />
            <input
              type="number"
              value={maxPct}
              onChange={(e) => setMaxPct(e.target.value)}
              placeholder="Max %"
              className="h-10 w-24 px-3 bg-surface-container border border-outline-variant rounded-md font-body-md text-body-md outline-none"
            />
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className="h-10 px-3 bg-surface-container border border-outline-variant rounded-md font-body-md text-body-md outline-none"
            >
              <option value="name">Name (A-Z)</option>
              <option value="-name">Name (Z-A)</option>
              <option value="percentage">Attendance % (Low-High)</option>
              <option value="-percentage">Attendance % (High-Low)</option>
            </select>
          </div>

          <div className="bg-surface-container-lowest border border-outline-variant rounded-xl shadow-sm overflow-hidden">
            {loading ? (
              <div className="p-8 text-center font-body-md text-body-md text-on-surface-variant">Loading...</div>
            ) : error ? (
              <div className="p-8 text-center font-body-md text-body-md text-error">{error}</div>
            ) : items.length === 0 ? (
              <div className="p-8 text-center font-body-md text-body-md text-on-surface-variant">No students match these filters.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse min-w-[480px]">
                  <thead className="bg-surface-container-lowest border-b border-outline">
                    <tr>
                      <th className="py-3 px-4 font-label-md text-label-md text-on-surface-variant">Student</th>
                      <th className="py-3 px-4 font-label-md text-label-md text-on-surface-variant">Program</th>
                      <th className="py-3 px-4 font-label-md text-label-md text-on-surface-variant text-right">Attendance</th>
                    </tr>
                  </thead>
                  <tbody className="font-body-md text-body-md text-on-surface divide-y divide-surface-variant">
                    {items.map((s) => (
                      <tr key={s.student_id} className="hover:bg-surface-container-low transition-colors">
                        <td className="py-3 px-4">
                          <Link href={`/professor/students/${s.student_id}`} className="flex items-center gap-3 group">
                            <div className="w-8 h-8 rounded-full bg-tertiary-container text-on-tertiary-container flex items-center justify-center font-label-md flex-shrink-0">
                              {initials(s.full_name)}
                            </div>
                            <div className="min-w-0">
                              <div className="font-medium group-hover:text-primary transition-colors truncate">{s.full_name}</div>
                              <div className="font-label-sm text-outline">Roll: {s.roll_number}</div>
                            </div>
                          </Link>
                        </td>
                        <td className="py-3 px-4 text-on-surface-variant whitespace-nowrap">
                          {s.program} • Sem {s.semester}
                        </td>
                        <td className={`py-3 px-4 text-right font-medium whitespace-nowrap ${s.standing === "warning" ? "text-error" : ""}`}>
                          {s.overall_percentage.toFixed(0)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </main>
      <BottomMobileNav role="professor" />
    </div>
  );
}

export default function ProfessorStudentsPage() {
  return (
    <RequireRole role="professor">
      <StudentsContent />
    </RequireRole>
  );
}
