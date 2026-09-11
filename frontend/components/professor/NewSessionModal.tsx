"use client";

import { useState } from "react";
import type { ActiveSubjectOut, UpcomingSessionOut } from "@/lib/api";

interface NewSessionModalProps {
  sessions: UpcomingSessionOut[];
  subjects: ActiveSubjectOut[];
  onClose: () => void;
  onStart: (lectureId: string) => Promise<void>;
  onStartAdhoc: (classDivisionId: string, durationMinutes: number) => Promise<void>;
}

const DURATION_OPTIONS = [15, 30, 45, 60, 90];

/** Lightweight "start attendance" dialog — no dedicated Stitch screen exists for this, so it
 * reuses the same Card/select/button classes as the rest of the dashboard. Supports both ways
 * to start attendance (spec #2): picking an existing scheduled lecture, or an ad-hoc session
 * for a subject/division that has no lecture scheduled yet. */
export function NewSessionModal({ sessions, subjects, onClose, onStart, onStartAdhoc }: NewSessionModalProps) {
  const [tab, setTab] = useState<"scheduled" | "adhoc">(sessions.length > 0 ? "scheduled" : "adhoc");
  const [selectedLecture, setSelectedLecture] = useState<string>(sessions[0]?.lecture_id ?? "");
  const [selectedDivision, setSelectedDivision] = useState<string>(subjects[0]?.class_division_id ?? "");
  const [duration, setDuration] = useState(30);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleStartScheduled() {
    if (!selectedLecture) return;
    setStarting(true);
    setError(null);
    try {
      await onStart(selectedLecture);
    } catch {
      setError("Could not start the session. Please try again.");
      setStarting(false);
    }
  }

  async function handleStartAdhoc() {
    if (!selectedDivision) return;
    setStarting(true);
    setError(null);
    try {
      await onStartAdhoc(selectedDivision, duration);
    } catch {
      setError("Could not start the session. Please try again.");
      setStarting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-inverse-surface/40 p-4">
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl clay-raised-lg p-stack-md">
        <h3 className="font-headline-md text-headline-md text-on-surface mb-1">Start Attendance</h3>
        <p className="font-body-md text-body-md text-on-surface-variant mb-stack-md">
          Start from a scheduled lecture, or start an ad-hoc session right now.
        </p>

        <div className="grid grid-cols-2 gap-3 mb-stack-md">
          <button
            onClick={() => setTab("scheduled")}
            className={`flex flex-col items-center gap-1.5 py-4 rounded-lg font-label-md text-label-md transition-all ${
              tab === "scheduled"
                ? "bg-primary text-on-primary clay-raised"
                : "bg-surface-container text-on-surface-variant clay-recessed hover:text-on-surface"
            }`}
          >
            <span className="material-symbols-outlined">event_available</span>
            Scheduled Lecture
          </button>
          <button
            onClick={() => setTab("adhoc")}
            className={`flex flex-col items-center gap-1.5 py-4 rounded-lg font-label-md text-label-md transition-all ${
              tab === "adhoc"
                ? "bg-primary text-on-primary clay-raised"
                : "bg-surface-container text-on-surface-variant clay-recessed hover:text-on-surface"
            }`}
          >
            <span className="material-symbols-outlined">bolt</span>
            Ad-hoc Session
          </button>
        </div>

        {tab === "scheduled" ? (
          sessions.length === 0 ? (
            <p className="font-body-md text-body-md text-on-surface-variant py-4 text-center">
              No upcoming lectures found for today. Use &quot;Ad-hoc Session&quot; instead.
            </p>
          ) : (
            <select
              value={selectedLecture}
              onChange={(e) => setSelectedLecture(e.target.value)}
              className="w-full h-10 px-3 bg-surface-container border border-outline-variant rounded-md font-body-md text-body-md focus:outline-none focus:border-primary outline-none mb-stack-md"
            >
              {sessions.map((s) => (
                <option key={s.lecture_id} value={s.lecture_id} disabled={s.has_active_session}>
                  {s.subject_name} • {s.division_name}
                  {s.has_active_session ? " (session already active)" : ""}
                </option>
              ))}
            </select>
          )
        ) : subjects.length === 0 ? (
          <p className="font-body-md text-body-md text-on-surface-variant py-4 text-center">
            No subjects/divisions assigned to you yet. Contact your admin.
          </p>
        ) : (
          <div className="space-y-stack-sm mb-stack-md">
            <div>
              <label className="block font-label-md text-label-md text-on-surface-variant mb-1">Subject &amp; Division</label>
              <select
                value={selectedDivision}
                onChange={(e) => setSelectedDivision(e.target.value)}
                className="w-full h-10 px-3 bg-surface-container border border-outline-variant rounded-md font-body-md text-body-md focus:outline-none focus:border-primary outline-none"
              >
                {subjects.map((s) => (
                  <option key={s.class_division_id} value={s.class_division_id} disabled={s.has_active_session}>
                    {s.subject_name} • {s.division_name}
                    {s.has_active_session ? " (session already active)" : ""}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block font-label-md text-label-md text-on-surface-variant mb-1">Session Duration</label>
              <select
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
                className="w-full h-10 px-3 bg-surface-container border border-outline-variant rounded-md font-body-md text-body-md focus:outline-none focus:border-primary outline-none"
              >
                {DURATION_OPTIONS.map((d) => (
                  <option key={d} value={d}>
                    {d} min
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {error && <p className="font-body-md text-body-md text-error mb-stack-sm">{error}</p>}

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-md border border-outline-variant text-on-surface font-label-md text-label-md hover:bg-surface-container-high transition-colors"
          >
            Cancel
          </button>
          {tab === "scheduled" ? (
            <button
              onClick={handleStartScheduled}
              disabled={!selectedLecture || starting || sessions.length === 0}
              className="px-4 py-2 rounded-md bg-primary text-on-primary font-label-md text-label-md hover:bg-primary/90 transition-colors disabled:opacity-60"
            >
              {starting ? "Starting..." : "Start Session"}
            </button>
          ) : (
            <button
              onClick={handleStartAdhoc}
              disabled={!selectedDivision || starting || subjects.length === 0}
              className="px-4 py-2 rounded-md bg-primary text-on-primary font-label-md text-label-md hover:bg-primary/90 transition-colors disabled:opacity-60"
            >
              {starting ? "Starting..." : "Start Session"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
