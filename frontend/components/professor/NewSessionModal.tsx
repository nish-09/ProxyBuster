"use client";

import { useState } from "react";
import type { UpcomingSessionOut } from "@/lib/api";

interface NewSessionModalProps {
  sessions: UpcomingSessionOut[];
  onClose: () => void;
  onStart: (lectureId: string) => Promise<void>;
}

/** Lightweight "pick a lecture to start attendance for" dialog — no dedicated Stitch screen exists for
 * this, so it reuses the same Card/select/button classes as the rest of the dashboard rather than
 * inventing a new visual language. */
export function NewSessionModal({ sessions, onClose, onStart }: NewSessionModalProps) {
  const [selected, setSelected] = useState<string>(sessions[0]?.lecture_id ?? "");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleStart() {
    if (!selected) return;
    setStarting(true);
    setError(null);
    try {
      await onStart(selected);
    } catch {
      setError("Could not start the session. Please try again.");
      setStarting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-inverse-surface/40 p-4">
      <div className="w-full max-w-md bg-surface-container-lowest border border-outline-variant rounded-xl card-shadow p-stack-md">
        <h3 className="font-headline-md text-headline-md text-on-surface mb-1">Start Attendance Session</h3>
        <p className="font-body-md text-body-md text-on-surface-variant mb-stack-md">
          Choose which lecture you&apos;re starting attendance for.
        </p>

        {sessions.length === 0 ? (
          <p className="font-body-md text-body-md text-on-surface-variant py-4 text-center">
            No upcoming lectures found for today.
          </p>
        ) : (
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="w-full h-10 px-3 bg-surface-container border border-outline-variant rounded-md font-body-md text-body-md focus:ring-2 focus:ring-primary/15 focus:border-primary outline-none mb-stack-md"
          >
            {sessions.map((s) => (
              <option key={s.lecture_id} value={s.lecture_id} disabled={s.has_active_session}>
                {s.subject_name} • {s.division_name}
                {s.has_active_session ? " (session already active)" : ""}
              </option>
            ))}
          </select>
        )}

        {error && <p className="font-body-md text-body-md text-error mb-stack-sm">{error}</p>}

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-md border border-outline-variant text-on-surface font-label-md text-label-md hover:bg-surface-container-high transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleStart}
            disabled={!selected || starting || sessions.length === 0}
            className="px-4 py-2 rounded-md bg-primary text-on-primary font-label-md text-label-md hover:bg-primary/90 transition-colors disabled:opacity-60"
          >
            {starting ? "Starting..." : "Start Session"}
          </button>
        </div>
      </div>
    </div>
  );
}
