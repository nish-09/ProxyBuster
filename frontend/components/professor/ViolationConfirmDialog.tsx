"use client";

import { useState } from "react";
import { ApiError, type RestrictionDurationValue, type ViolationReasonValue } from "@/lib/api";

interface ViolationConfirmDialogProps {
  studentName: string;
  subjectLabel: string;
  onClose: () => void;
  onConfirm: (payload: { reason: ViolationReasonValue; notes: string; restriction_duration: RestrictionDurationValue; custom_restriction_end?: string }) => Promise<void>;
}

const REASONS: { value: ViolationReasonValue; label: string }[] = [
  { value: "proxy_attendance", label: "Proxy attendance" },
  { value: "not_physically_present", label: "Not physically present" },
  { value: "unauthorized_attendance", label: "Unauthorized attendance" },
  { value: "other", label: "Other" },
];

const DURATIONS: { value: RestrictionDurationValue; label: string }[] = [
  { value: "one_lecture", label: "1 lecture" },
  { value: "one_day", label: "1 day" },
  { value: "three_days", label: "3 days" },
  { value: "seven_days", label: "7 days (default)" },
  { value: "custom", label: "Custom end date" },
];

/** Requires an explicit second step (reason + duration + Confirm) before a violation and its
 * restriction are created — never a single accidental click. See spec section 11. */
export function ViolationConfirmDialog({ studentName, subjectLabel, onClose, onConfirm }: ViolationConfirmDialogProps) {
  const [reason, setReason] = useState<ViolationReasonValue>("proxy_attendance");
  const [notes, setNotes] = useState("");
  const [duration, setDuration] = useState<RestrictionDurationValue>("seven_days");
  const [customEnd, setCustomEnd] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm() {
    if (duration === "custom" && !customEnd) {
      setError("Choose a custom end date and time.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm({
        reason,
        notes: notes.trim(),
        restriction_duration: duration,
        custom_restriction_end: duration === "custom" ? new Date(customEnd).toISOString() : undefined,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record this violation. Please try again.");
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-inverse-surface/40 p-4">
      <div className="w-full max-w-md max-h-[calc(100dvh-2rem)] overflow-y-auto bg-surface-container-lowest border border-outline-variant rounded-xl card-shadow p-stack-md">
        <h3 className="font-headline-md text-headline-md text-on-surface mb-1 flex items-center gap-2">
          <span className="material-symbols-outlined text-error">report</span>
          Mark Attendance Violation
        </h3>
        <p className="font-body-md text-body-md text-on-surface-variant mb-stack-md">
          {studentName} — {subjectLabel}. This creates an audited restriction; it cannot happen by accident.
        </p>

        <div className="space-y-stack-sm">
          <div>
            <label className="block font-label-md text-label-md text-on-surface-variant mb-1.5">Reason</label>
            <div className="space-y-1.5">
              {REASONS.map((r) => (
                <label
                  key={r.value}
                  className={`flex items-center gap-2 px-3 py-2 rounded-md border cursor-pointer transition-colors ${
                    reason === r.value ? "border-primary bg-primary-container/40" : "border-outline-variant"
                  }`}
                >
                  <input type="radio" name="violation-reason" checked={reason === r.value} onChange={() => setReason(r.value)} />
                  <span className="font-body-md text-body-md text-on-surface">{r.label}</span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <label className="block font-label-md text-label-md text-on-surface-variant mb-1">Restriction duration</label>
            <select
              value={duration}
              onChange={(e) => setDuration(e.target.value as RestrictionDurationValue)}
              className="w-full h-10 px-3 bg-surface-container border border-outline-variant rounded-md font-body-md text-body-md focus:outline-none focus:border-primary"
            >
              {DURATIONS.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>

          {duration === "custom" && (
            <div>
              <label className="block font-label-md text-label-md text-on-surface-variant mb-1">Restricted until</label>
              <input
                type="datetime-local"
                value={customEnd}
                onChange={(e) => setCustomEnd(e.target.value)}
                className="w-full h-10 px-3 bg-surface-container border border-outline-variant rounded-md font-body-md text-body-md focus:outline-none focus:border-primary"
              />
            </div>
          )}

          <div>
            <label className="block font-label-md text-label-md text-on-surface-variant mb-1">Additional note (optional)</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="Any context for the record"
              className="w-full px-3 py-2 bg-surface-container border border-outline-variant rounded-md font-body-md text-body-md focus:outline-none focus:border-primary resize-none"
            />
          </div>
        </div>

        {error && <p className="font-body-md text-body-md text-error mt-stack-sm">{error}</p>}

        <div className="flex gap-2 justify-end mt-stack-md">
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 rounded-md border border-outline-variant text-on-surface font-label-md text-label-md hover:bg-surface-container-high transition-colors disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={submitting}
            className="px-4 py-2 rounded-md bg-error text-on-error font-label-md text-label-md hover:bg-error/90 transition-colors disabled:opacity-60"
          >
            {submitting ? "Recording..." : "Confirm Violation"}
          </button>
        </div>
      </div>
    </div>
  );
}
