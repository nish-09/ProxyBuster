"use client";

import { useCallback, useEffect, useState } from "react";
import { RequireRole } from "@/components/route-guard";
import { SideNavBar } from "@/components/layout/SideNavBar";
import { TopNavBar, DesktopTopBar } from "@/components/layout/TopNavBar";
import { BottomMobileNav } from "@/components/layout/BottomMobileNav";
import { useAuth } from "@/lib/auth-context";
import { adminApi, ApiError, type AdminSubjectOut } from "@/lib/api";

const inputClass =
  "w-full h-10 px-3 bg-surface-container border border-outline-variant rounded-md text-body-md font-body-md focus:ring-2 focus:ring-primary/15 focus:border-primary transition-all";
const labelClass = "block font-label-sm text-label-sm text-on-surface-variant mb-1";

function initials(name: string) {
  return name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

function CreateSubjectForm({ onCreated, onClose }: { onCreated: () => void; onClose: () => void }) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [credits, setCredits] = useState("3");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await adminApi.createSubject({ code, name, credits: Number(credits) });
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create subject.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="bg-surface rounded-xl border border-outline-variant shadow-sm p-5 mb-gutter grid grid-cols-1 md:grid-cols-3 gap-4">
      <div>
        <label className={labelClass}>Subject code</label>
        <input required placeholder="CS-301" value={code} onChange={(e) => setCode(e.target.value)} className={inputClass} />
      </div>
      <div>
        <label className={labelClass}>Subject name</label>
        <input required placeholder="Data Structures" value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
      </div>
      <div>
        <label className={labelClass}>Credits</label>
        <input type="number" min={1} max={12} required value={credits} onChange={(e) => setCredits(e.target.value)} className={inputClass} />
      </div>
      {error && <p className="md:col-span-3 font-body-md text-body-md text-error">{error}</p>}
      <div className="md:col-span-3 flex gap-2 justify-end">
        <button type="button" onClick={onClose} className="px-4 py-2 rounded-md border border-outline-variant text-on-surface font-label-md text-label-md hover:bg-surface-container-high transition-colors">
          Cancel
        </button>
        <button type="submit" disabled={submitting} className="px-4 py-2 rounded-md bg-primary text-on-primary font-label-md text-label-md hover:bg-primary/90 transition-colors disabled:opacity-60">
          {submitting ? "Creating..." : "Create Subject"}
        </button>
      </div>
    </form>
  );
}

function SubjectsContent() {
  const { user } = useAuth();
  const [subjects, setSubjects] = useState<AdminSubjectOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setSubjects(await adminApi.subjects());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard fetch-on-mount
    load();
  }, [load]);

  async function handleDelete(s: AdminSubjectOut) {
    setRowError(null);
    setBusyId(s.id);
    try {
      await adminApi.deleteSubject(s.id);
      setSubjects((prev) => prev.filter((x) => x.id !== s.id));
    } catch (err) {
      setRowError(err instanceof ApiError ? err.message : "Could not delete subject.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="bg-background text-on-background font-body-md antialiased flex min-h-screen">
      <SideNavBar role="admin" />
      <main className="flex-1 md:ml-[280px] min-h-screen bg-surface-container-low">
        <TopNavBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
        <div className="p-container-padding max-w-[1400px] mx-auto space-y-stack-lg pb-24">
          <header className="flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div>
              <h2 className="font-display-lg text-display-lg text-on-surface mb-1">Subjects</h2>
              <p className="font-body-lg text-body-lg text-on-surface-variant">{subjects.length} subjects</p>
            </div>
            <div className="flex items-center gap-3">
              <DesktopTopBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
              <button
                onClick={() => setShowCreate((v) => !v)}
                className="flex items-center gap-2 bg-primary text-on-primary px-5 py-2 rounded-lg shadow-sm hover:bg-primary/90 transition-colors"
              >
                <span className="material-symbols-outlined text-sm">add</span>
                <span className="font-label-md text-label-md">New Subject</span>
              </button>
            </div>
          </header>

          {showCreate && (
            <CreateSubjectForm
              onClose={() => setShowCreate(false)}
              onCreated={() => {
                setShowCreate(false);
                load();
              }}
            />
          )}

          {rowError && (
            <div className="bg-error-container/30 border border-error/20 rounded-lg p-4 text-error font-body-md text-body-md">
              {rowError}
            </div>
          )}

          <div className="bg-surface rounded-xl border border-outline-variant shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="bg-surface-container-lowest border-b border-outline-variant/50">
                  <tr>
                    {["Code", "Name", "Credits", ""].map((h) => (
                      <th key={h} className="p-4 font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/30">
                  {!loading && subjects.length === 0 && (
                    <tr>
                      <td colSpan={4} className="p-6 text-center font-body-md text-body-md text-on-surface-variant">
                        No subjects yet.
                      </td>
                    </tr>
                  )}
                  {subjects.map((s) => (
                    <tr key={s.id} className="hover:bg-surface-container-low transition-colors">
                      <td className="p-4 font-body-md font-semibold text-on-surface">{s.code}</td>
                      <td className="p-4 font-body-md text-body-md text-on-surface-variant">{s.name}</td>
                      <td className="p-4 font-body-md text-body-md text-on-surface-variant">{s.credits}</td>
                      <td className="p-4 text-right">
                        <button
                          disabled={busyId === s.id}
                          onClick={() => handleDelete(s)}
                          className="px-3 py-1.5 rounded-md border border-error/30 text-error font-label-sm text-label-sm hover:bg-error-container/20 transition-colors disabled:opacity-50"
                        >
                          Delete
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

export default function AdminSubjectsPage() {
  return (
    <RequireRole role="admin">
      <SubjectsContent />
    </RequireRole>
  );
}
