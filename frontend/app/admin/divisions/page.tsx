"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { RequireRole } from "@/components/route-guard";
import { SideNavBar } from "@/components/layout/SideNavBar";
import { TopNavBar, DesktopTopBar } from "@/components/layout/TopNavBar";
import { BottomMobileNav } from "@/components/layout/BottomMobileNav";
import { useAuth } from "@/lib/auth-context";
import {
  adminApi,
  ApiError,
  errorMessage,
  type AdminDivisionOut,
  type AdminEnrollmentOut,
  type AdminProfessorOut,
  type AdminStudentOut,
  type AdminSubjectOut,
} from "@/lib/api";
import { PageError } from "@/components/ui/PageError";

const inputClass =
  "w-full h-10 px-3 bg-surface-container border border-outline-variant rounded-md text-body-md font-body-md focus:outline-none focus:border-primary transition-all";
const labelClass = "block font-label-sm text-label-sm text-on-surface-variant mb-1";

function initials(name: string) {
  return name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

function CreateDivisionForm({
  subjects,
  professors,
  onCreated,
  onClose,
}: {
  subjects: AdminSubjectOut[];
  professors: AdminProfessorOut[];
  onCreated: () => void;
  onClose: () => void;
}) {
  const [subjectId, setSubjectId] = useState(subjects[0]?.id ?? "");
  const [professorId, setProfessorId] = useState(professors[0]?.id ?? "");
  const [name, setName] = useState("Div A");
  const [semester, setSemester] = useState("1");
  const [room, setRoom] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!subjectId || !professorId) {
      setError("Create a subject and a professor first.");
      return;
    }
    setSubmitting(true);
    try {
      await adminApi.createDivision({
        subject_id: subjectId,
        professor_id: professorId,
        name,
        semester: Number(semester),
        room: room || undefined,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create division.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="bg-surface-container-lowest rounded-xl border border-outline-variant shadow-sm p-5 mb-gutter grid grid-cols-1 md:grid-cols-3 gap-4">
      <div>
        <label className={labelClass}>Subject</label>
        <select value={subjectId} onChange={(e) => setSubjectId(e.target.value)} className={inputClass}>
          {subjects.map((s) => (
            <option key={s.id} value={s.id}>
              {s.code} — {s.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className={labelClass}>Professor</label>
        <select value={professorId} onChange={(e) => setProfessorId(e.target.value)} className={inputClass}>
          {professors.map((p) => (
            <option key={p.id} value={p.id}>
              {p.full_name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className={labelClass}>Division name</label>
        <input required placeholder="Div A" value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
      </div>
      <div>
        <label className={labelClass}>Semester</label>
        <input type="number" min={1} max={12} required value={semester} onChange={(e) => setSemester(e.target.value)} className={inputClass} />
      </div>
      <div>
        <label className={labelClass}>Room</label>
        <input placeholder="Room 204" value={room} onChange={(e) => setRoom(e.target.value)} className={inputClass} />
      </div>
      {error && <p className="md:col-span-3 font-body-md text-body-md text-error">{error}</p>}
      <div className="md:col-span-3 flex gap-2 justify-end">
        <button type="button" onClick={onClose} className="px-4 py-2 rounded-md border border-outline-variant text-on-surface font-label-md text-label-md hover:bg-surface-container-high transition-colors">
          Cancel
        </button>
        <button type="submit" disabled={submitting} className="px-4 py-2 rounded-md bg-primary text-on-primary font-label-md text-label-md hover:bg-primary/90 transition-colors disabled:opacity-60">
          {submitting ? "Creating..." : "Create Division"}
        </button>
      </div>
    </form>
  );
}

function EnrollmentManager({ division, allStudents }: { division: AdminDivisionOut; allStudents: AdminStudentOut[] }) {
  const [enrollments, setEnrollments] = useState<AdminEnrollmentOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setEnrollments(await adminApi.enrollments(division.id));
    } catch (err) {
      setError(errorMessage(err, "Could not load enrollments."));
    } finally {
      setLoading(false);
    }
  }, [division.id]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard fetch-on-mount
    load();
  }, [load]);

  const enrolledIds = new Set(enrollments.map((e) => e.student_id));
  const available = allStudents.filter((s) => !enrolledIds.has(s.id));

  async function handleAdd() {
    if (!selected) return;
    setError(null);
    setBusy(true);
    try {
      await adminApi.createEnrollment(selected, division.id);
      setSelected("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not enroll student.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(enrollmentId: string) {
    setBusy(true);
    try {
      await adminApi.deleteEnrollment(enrollmentId);
      await load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-4 bg-surface-container-low border-t border-outline-variant/50">
      <div className="flex items-center gap-2 mb-3">
        <select value={selected} onChange={(e) => setSelected(e.target.value)} className={`${inputClass} max-w-xs`}>
          <option value="">Select a student to enroll...</option>
          {available.map((s) => (
            <option key={s.id} value={s.id}>
              {s.full_name} ({s.roll_number})
            </option>
          ))}
        </select>
        <button
          onClick={handleAdd}
          disabled={!selected || busy}
          className="px-3 py-2 rounded-md bg-primary text-on-primary font-label-sm text-label-sm hover:bg-primary/90 transition-colors disabled:opacity-60"
        >
          Enroll
        </button>
      </div>
      {error && <p className="font-body-md text-body-md text-error mb-2">{error}</p>}
      {loading ? (
        <p className="font-body-md text-body-md text-on-surface-variant">Loading roster...</p>
      ) : enrollments.length === 0 ? (
        <p className="font-body-md text-body-md text-on-surface-variant">No students enrolled yet.</p>
      ) : (
        <ul className="space-y-1">
          {enrollments.map((e) => (
            <li key={e.id} className="flex items-center justify-between px-3 py-1.5 bg-surface rounded-md border border-outline-variant/50">
              <span className="font-body-md text-body-md text-on-surface">
                {e.student_name} <span className="text-on-surface-variant">({e.roll_number})</span>
              </span>
              <button
                disabled={busy}
                onClick={() => handleRemove(e.id)}
                className="font-label-sm text-label-sm text-error hover:underline disabled:opacity-50"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DivisionsContent() {
  const { user } = useAuth();
  const [divisions, setDivisions] = useState<AdminDivisionOut[]>([]);
  const [subjects, setSubjects] = useState<AdminSubjectOut[]>([]);
  const [professors, setProfessors] = useState<AdminProfessorOut[]>([]);
  const [students, setStudents] = useState<AdminStudentOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [d, s, p, st] = await Promise.all([
        adminApi.divisions(),
        adminApi.subjects(),
        adminApi.professors(),
        adminApi.students(),
      ]);
      setDivisions(d);
      setSubjects(s);
      setProfessors(p);
      setStudents(st);
    } catch (err) {
      setLoadError(errorMessage(err, "Could not load this page. Please try again."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard fetch-on-mount
    load();
  }, [load]);

  return (
    <div className="bg-background text-on-background font-body-md antialiased flex min-h-screen">
      <SideNavBar role="admin" />
      <main className="flex-1 min-w-0 md:ml-[280px] min-h-screen bg-surface-container-low">
        <TopNavBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
        <div className="p-container-padding max-w-[1400px] mx-auto space-y-stack-lg pb-24">
          {loadError && <PageError message={loadError} onRetry={() => void load()} />}
          <header className="flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div>
              <h2 className="font-display-lg text-display-lg text-on-surface mb-1">Class Divisions</h2>
              <p className="font-body-lg text-body-lg text-on-surface-variant">
                {divisions.length} divisions — click a row to manage its enrolled students
              </p>
            </div>
            <div className="flex items-center gap-3">
              <DesktopTopBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
              <button
                onClick={() => setShowCreate((v) => !v)}
                className="flex items-center gap-2 bg-primary text-on-primary px-5 py-2 rounded-lg shadow-sm hover:bg-primary/90 transition-colors"
              >
                <span className="material-symbols-outlined text-sm">add</span>
                <span className="font-label-md text-label-md">New Division</span>
              </button>
            </div>
          </header>

          {showCreate && (
            <CreateDivisionForm
              subjects={subjects}
              professors={professors}
              onClose={() => setShowCreate(false)}
              onCreated={() => {
                setShowCreate(false);
                load();
              }}
            />
          )}

          <div className="bg-surface-container-lowest rounded-xl border border-outline-variant shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="bg-surface-container-lowest border-b border-outline-variant/50">
                  <tr>
                    {["Subject", "Division", "Professor", "Sem", "Room", "Enrolled", ""].map((h) => (
                      <th key={h} className="p-4 font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/30">
                  {!loading && divisions.length === 0 && (
                    <tr>
                      <td colSpan={7} className="p-6 text-center font-body-md text-body-md text-on-surface-variant">
                        No class divisions yet. Create a subject and a professor first, then create a division here.
                      </td>
                    </tr>
                  )}
                  {divisions.map((d) => (
                    <Fragment key={d.id}>
                      <tr
                        className="hover:bg-surface-container-low transition-colors cursor-pointer"
                        onClick={() => setExpanded((cur) => (cur === d.id ? null : d.id))}
                      >
                        <td className="p-4 font-body-md text-body-md text-on-surface">
                          {d.subject_code} — {d.subject_name}
                        </td>
                        <td className="p-4 font-body-md font-semibold text-on-surface">{d.name}</td>
                        <td className="p-4 font-body-md text-body-md text-on-surface-variant">{d.professor_name}</td>
                        <td className="p-4 font-body-md text-body-md text-on-surface-variant">{d.semester}</td>
                        <td className="p-4 font-body-md text-body-md text-on-surface-variant">{d.room ?? "TBD"}</td>
                        <td className="p-4 font-body-md text-body-md text-on-surface-variant">{d.enrolled_count}</td>
                        <td className="p-4 text-right">
                          <span className="material-symbols-outlined text-on-surface-variant">
                            {expanded === d.id ? "expand_less" : "expand_more"}
                          </span>
                        </td>
                      </tr>
                      {expanded === d.id && (
                        <tr>
                          <td colSpan={7} className="p-0">
                            <EnrollmentManager division={d} allStudents={students} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>
      <BottomMobileNav role="admin" />
    </div>
  );
}

export default function AdminDivisionsPage() {
  return (
    <RequireRole role="admin">
      <DivisionsContent />
    </RequireRole>
  );
}
