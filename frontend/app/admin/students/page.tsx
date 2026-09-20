"use client";

import { useCallback, useEffect, useState } from "react";
import { RequireRole } from "@/components/route-guard";
import { SideNavBar } from "@/components/layout/SideNavBar";
import { TopNavBar, DesktopTopBar } from "@/components/layout/TopNavBar";
import { BottomMobileNav } from "@/components/layout/BottomMobileNav";
import { useAuth } from "@/lib/auth-context";
import { SkeletonBlock } from "@/components/ui/Skeleton";
import { PageError } from "@/components/ui/PageError";
import { adminApi, ApiError, errorMessage, type AdminStudentOut } from "@/lib/api";

const inputClass =
  "w-full h-10 px-3 bg-surface-container border border-outline-variant rounded-md text-body-md font-body-md focus:outline-none focus:border-primary transition-all";
const labelClass = "block font-label-sm text-label-sm text-on-surface-variant mb-1";

function initials(name: string) {
  return name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

function CreateStudentForm({ onCreated, onClose }: { onCreated: () => void; onClose: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [rollNumber, setRollNumber] = useState("");
  const [program, setProgram] = useState("");
  const [semester, setSemester] = useState("1");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await adminApi.createStudent({
        email,
        password,
        full_name: fullName,
        roll_number: rollNumber,
        program,
        semester: Number(semester),
      });
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create student.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="bg-surface-container-lowest rounded-xl border border-outline-variant shadow-sm p-5 mb-gutter grid grid-cols-1 md:grid-cols-3 gap-4">
      <div>
        <label className={labelClass}>Full name</label>
        <input required value={fullName} onChange={(e) => setFullName(e.target.value)} className={inputClass} />
      </div>
      <div>
        <label className={labelClass}>Email</label>
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
      </div>
      <div>
        <label className={labelClass}>Initial password</label>
        <input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} />
      </div>
      <div>
        <label className={labelClass}>Roll number</label>
        <input required value={rollNumber} onChange={(e) => setRollNumber(e.target.value)} className={inputClass} />
      </div>
      <div>
        <label className={labelClass}>Program</label>
        <input required placeholder="B.Tech Computer Science" value={program} onChange={(e) => setProgram(e.target.value)} className={inputClass} />
      </div>
      <div>
        <label className={labelClass}>Semester</label>
        <input type="number" min={1} max={12} required value={semester} onChange={(e) => setSemester(e.target.value)} className={inputClass} />
      </div>
      {error && <p className="md:col-span-3 font-body-md text-body-md text-error">{error}</p>}
      <div className="md:col-span-3 flex gap-2 justify-end">
        <button type="button" onClick={onClose} className="px-4 py-2 rounded-md border border-outline-variant text-on-surface font-label-md text-label-md hover:bg-surface-container-high transition-colors">
          Cancel
        </button>
        <button type="submit" disabled={submitting} className="px-4 py-2 rounded-md bg-primary text-on-primary font-label-md text-label-md hover:bg-primary/90 transition-colors disabled:opacity-60">
          {submitting ? "Creating..." : "Create Student"}
        </button>
      </div>
    </form>
  );
}

function StudentsContent() {
  const { user } = useAuth();
  const [students, setStudents] = useState<AdminStudentOut[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setStudents(await adminApi.students(q || undefined));
    } catch (err) {
      setLoadError(errorMessage(err, "Could not load this page. Please try again."));
    } finally {
      setLoading(false);
    }
  }, [q]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard fetch-on-mount
    load();
  }, [load]);

  async function toggleActive(s: AdminStudentOut) {
    setBusyId(s.id);
    try {
      const updated = await adminApi.updateStudent(s.id, { is_active: !s.is_active });
      setStudents((prev) => prev.map((x) => (x.id === s.id ? updated : x)));
    } catch (err) {
      setLoadError(errorMessage(err, "Could not update this account."));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="bg-background text-on-background font-body-md antialiased flex min-h-screen">
      <SideNavBar role="admin" />
      <main className="flex-1 min-w-0 md:ml-[280px] min-h-screen bg-surface-container-low">
        <TopNavBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} showSearch onSearch={setQ} />
        <div className="p-container-padding max-w-[1400px] mx-auto space-y-stack-lg pb-24">
          {loadError && <PageError message={loadError} onRetry={() => void load()} />}
          <header className="flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div>
              <h2 className="font-display-lg text-display-lg text-on-surface mb-1">Students</h2>
              <p className="font-body-lg text-body-lg text-on-surface-variant">{students.length} students</p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <DesktopTopBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} showSearch onSearch={setQ} />
              <button
                onClick={() => setShowCreate((v) => !v)}
                className="flex items-center gap-2 bg-primary text-on-primary px-5 py-2 rounded-lg shadow-sm hover:bg-primary/90 transition-colors"
              >
                <span className="material-symbols-outlined text-sm">add</span>
                <span className="font-label-md text-label-md">New Student</span>
              </button>
            </div>
          </header>

          {showCreate && (
            <CreateStudentForm
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
                    {["Name", "Roll No.", "Email", "Program", "Sem", "Status", ""].map((h) => (
                      <th key={h} className="p-4 font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/30">
                  {loading &&
                    Array.from({ length: 6 }).map((_, i) => (
                      <tr key={i}>
                        {Array.from({ length: 7 }).map((__, c) => (
                          <td key={c} className="p-4">
                            <SkeletonBlock className="h-4 w-full" />
                          </td>
                        ))}
                      </tr>
                    ))}
                  {!loading && students.length === 0 && (
                    <tr>
                      <td colSpan={7} className="p-6 text-center font-body-md text-body-md text-on-surface-variant">
                        No students yet.
                      </td>
                    </tr>
                  )}
                  {!loading && students.map((s) => (
                    <tr key={s.id} className="hover:bg-surface-container-low transition-colors">
                      <td className="p-4 font-body-md font-semibold text-on-surface">{s.full_name}</td>
                      <td className="p-4 font-body-md text-body-md text-on-surface-variant">{s.roll_number}</td>
                      <td className="p-4 font-body-md text-body-md text-on-surface-variant">{s.email}</td>
                      <td className="p-4 font-body-md text-body-md text-on-surface-variant">{s.program}</td>
                      <td className="p-4 font-body-md text-body-md text-on-surface-variant">{s.semester}</td>
                      <td className="p-4">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            s.is_active ? "bg-tertiary-container text-on-tertiary-container border border-outline" : "bg-error-container text-error"
                          }`}
                        >
                          {s.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td className="p-4 text-right">
                        <button
                          disabled={busyId === s.id}
                          onClick={() => toggleActive(s)}
                          className="px-3 min-h-9 rounded-md border border-outline-variant text-on-surface font-label-sm text-label-sm hover:bg-surface-container-high transition-colors disabled:opacity-50"
                        >
                          {s.is_active ? "Deactivate" : "Activate"}
                        </button>
                      </td>
                    </tr>
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

export default function AdminStudentsPage() {
  return (
    <RequireRole role="admin">
      <StudentsContent />
    </RequireRole>
  );
}
