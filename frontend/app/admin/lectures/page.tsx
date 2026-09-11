"use client";

import { useCallback, useEffect, useState } from "react";
import { RequireRole } from "@/components/route-guard";
import { SideNavBar } from "@/components/layout/SideNavBar";
import { TopNavBar, DesktopTopBar } from "@/components/layout/TopNavBar";
import { BottomMobileNav } from "@/components/layout/BottomMobileNav";
import { useAuth } from "@/lib/auth-context";
import { adminApi, ApiError, type AdminDivisionOut, type AdminLectureOut } from "@/lib/api";

const inputClass =
  "w-full h-10 px-3 bg-surface-container border border-outline-variant rounded-md text-body-md font-body-md focus:outline-none focus:border-primary transition-all";
const labelClass = "block font-label-sm text-label-sm text-on-surface-variant mb-1";

function initials(name: string) {
  return name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

function toLocalInputValue(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function CreateLectureForm({
  divisions,
  onCreated,
  onClose,
}: {
  divisions: AdminDivisionOut[];
  onCreated: () => void;
  onClose: () => void;
}) {
  const now = new Date();
  const inHour = new Date(now.getTime() + 60 * 60 * 1000);

  const [classDivisionId, setClassDivisionId] = useState(divisions[0]?.id ?? "");
  const [topic, setTopic] = useState("");
  const [start, setStart] = useState(toLocalInputValue(now));
  const [end, setEnd] = useState(toLocalInputValue(inHour));
  const [room, setRoom] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!classDivisionId) {
      setError("Create a class division first.");
      return;
    }
    setSubmitting(true);
    try {
      await adminApi.createLecture({
        class_division_id: classDivisionId,
        topic: topic || undefined,
        scheduled_start: new Date(start).toISOString(),
        scheduled_end: new Date(end).toISOString(),
        room: room || undefined,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not schedule lecture.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="bg-surface-container-lowest rounded-xl border border-outline-variant shadow-sm p-5 mb-gutter grid grid-cols-1 md:grid-cols-3 gap-4">
      <div className="md:col-span-3">
        <label className={labelClass}>Class division</label>
        <select value={classDivisionId} onChange={(e) => setClassDivisionId(e.target.value)} className={inputClass}>
          {divisions.map((d) => (
            <option key={d.id} value={d.id}>
              {d.subject_code} — {d.name} ({d.professor_name})
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className={labelClass}>Topic (optional)</label>
        <input value={topic} onChange={(e) => setTopic(e.target.value)} className={inputClass} />
      </div>
      <div>
        <label className={labelClass}>Start</label>
        <input type="datetime-local" required value={start} onChange={(e) => setStart(e.target.value)} className={inputClass} />
      </div>
      <div>
        <label className={labelClass}>End</label>
        <input type="datetime-local" required value={end} onChange={(e) => setEnd(e.target.value)} className={inputClass} />
      </div>
      <div>
        <label className={labelClass}>Room (optional)</label>
        <input value={room} onChange={(e) => setRoom(e.target.value)} className={inputClass} />
      </div>
      {error && <p className="md:col-span-3 font-body-md text-body-md text-error">{error}</p>}
      <div className="md:col-span-3 flex gap-2 justify-end">
        <button type="button" onClick={onClose} className="px-4 py-2 rounded-md border border-outline-variant text-on-surface font-label-md text-label-md hover:bg-surface-container-high transition-colors">
          Cancel
        </button>
        <button type="submit" disabled={submitting} className="px-4 py-2 rounded-md bg-primary text-on-primary font-label-md text-label-md hover:bg-primary/90 transition-colors disabled:opacity-60">
          {submitting ? "Scheduling..." : "Schedule Lecture"}
        </button>
      </div>
    </form>
  );
}

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function LecturesContent() {
  const { user } = useAuth();
  const [lectures, setLectures] = useState<AdminLectureOut[]>([]);
  const [divisions, setDivisions] = useState<AdminDivisionOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [l, d] = await Promise.all([adminApi.lectures(), adminApi.divisions()]);
      setLectures(l);
      setDivisions(d);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard fetch-on-mount
    load();
  }, [load]);

  async function handleDelete(l: AdminLectureOut) {
    setRowError(null);
    setBusyId(l.id);
    try {
      await adminApi.deleteLecture(l.id);
      setLectures((prev) => prev.filter((x) => x.id !== l.id));
    } catch (err) {
      setRowError(err instanceof ApiError ? err.message : "Could not delete lecture.");
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
              <h2 className="font-display-lg text-display-lg text-on-surface mb-1">Lectures</h2>
              <p className="font-body-lg text-body-lg text-on-surface-variant">{lectures.length} most recent lectures</p>
            </div>
            <div className="flex items-center gap-3">
              <DesktopTopBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
              <button
                onClick={() => setShowCreate((v) => !v)}
                className="flex items-center gap-2 bg-primary text-on-primary px-5 py-2 rounded-lg shadow-sm hover:bg-primary/90 transition-colors"
              >
                <span className="material-symbols-outlined text-sm">add</span>
                <span className="font-label-md text-label-md">Schedule Lecture</span>
              </button>
            </div>
          </header>

          {showCreate && (
            <CreateLectureForm
              divisions={divisions}
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

          <div className="bg-surface-container-lowest rounded-xl border border-outline-variant shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="bg-surface-container-lowest border-b border-outline-variant/50">
                  <tr>
                    {["Subject", "Division", "Topic", "Start", "End", "Room", ""].map((h) => (
                      <th key={h} className="p-4 font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/30">
                  {!loading && lectures.length === 0 && (
                    <tr>
                      <td colSpan={7} className="p-6 text-center font-body-md text-body-md text-on-surface-variant">
                        No lectures scheduled yet.
                      </td>
                    </tr>
                  )}
                  {lectures.map((l) => (
                    <tr key={l.id} className="hover:bg-surface-container-low transition-colors">
                      <td className="p-4 font-body-md text-body-md text-on-surface">{l.subject_name}</td>
                      <td className="p-4 font-body-md text-body-md text-on-surface-variant">{l.division_name}</td>
                      <td className="p-4 font-body-md text-body-md text-on-surface-variant">{l.topic ?? "—"}</td>
                      <td className="p-4 font-body-md text-body-md text-on-surface-variant">{formatDateTime(l.scheduled_start)}</td>
                      <td className="p-4 font-body-md text-body-md text-on-surface-variant">{formatDateTime(l.scheduled_end)}</td>
                      <td className="p-4 font-body-md text-body-md text-on-surface-variant">{l.room ?? "TBD"}</td>
                      <td className="p-4 text-right">
                        <button
                          disabled={busyId === l.id}
                          onClick={() => handleDelete(l)}
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

export default function AdminLecturesPage() {
  return (
    <RequireRole role="admin">
      <LecturesContent />
    </RequireRole>
  );
}
