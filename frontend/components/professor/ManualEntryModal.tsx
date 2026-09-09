"use client";

import { useState } from "react";
import type { StudentListItem } from "@/lib/api";

interface ManualEntryModalProps {
  students: StudentListItem[];
  onClose: () => void;
  onSubmit: (payload: { student_id: string; status: "present" | "absent" | "late"; reason: string }) => Promise<void>;
}

export function ManualEntryModal({ students, onClose, onSubmit }: ManualEntryModalProps) {
  const [studentId, setStudentId] = useState(students[0]?.student_id ?? "");
  const [status, setStatus] = useState<"present" | "absent" | "late">("present");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    if (!studentId || reason.trim().length < 3) {
      setError("Please select a student and enter a reason (at least 3 characters).");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({ student_id: studentId, status, reason: reason.trim() });
    } catch {
      setError("Could not save this manual entry. Please try again.");
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-inverse-surface/40 p-4">
      <div className="w-full max-w-md bg-surface-container-lowest border border-outline-variant rounded-xl card-shadow p-stack-md">
        <h3 className="font-headline-md text-headline-md text-on-surface mb-1 flex items-center gap-2">
          <span className="material-symbols-outlined text-primary">edit_note</span>
          Manual Attendance Entry
        </h3>
        <p className="font-body-md text-body-md text-on-surface-variant mb-stack-md">
          For legitimate cases only — every manual action is recorded in the audit log.
        </p>

        <div className="space-y-stack-sm">
          <div>
            <label className="block font-label-md text-label-md text-on-surface-variant mb-1">Student</label>
            <select
              value={studentId}
              onChange={(e) => setStudentId(e.target.value)}
              className="w-full h-10 px-3 bg-surface-container border border-outline-variant rounded-md font-body-md text-body-md focus:ring-2 focus:ring-primary/15 focus:border-primary outline-none"
            >
              {students.map((s) => (
                <option key={s.student_id} value={s.student_id}>
                  {s.full_name} — {s.roll_number}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block font-label-md text-label-md text-on-surface-variant mb-1">Status</label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as "present" | "absent" | "late")}
              className="w-full h-10 px-3 bg-surface-container border border-outline-variant rounded-md font-body-md text-body-md focus:ring-2 focus:ring-primary/15 focus:border-primary outline-none"
            >
              <option value="present">Present</option>
              <option value="late">Late</option>
              <option value="absent">Absent</option>
            </select>
          </div>
          <div>
            <label className="block font-label-md text-label-md text-on-surface-variant mb-1">Reason</label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={2}
              placeholder="e.g. Phone dead, QR scan failed"
              className="w-full px-3 py-2 bg-surface-container border border-outline-variant rounded-md font-body-md text-body-md focus:ring-2 focus:ring-primary/15 focus:border-primary outline-none resize-none"
            />
          </div>
        </div>

        {error && <p className="font-body-md text-body-md text-error mt-stack-sm">{error}</p>}

        <div className="flex gap-2 justify-end mt-stack-md">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-md border border-outline-variant text-on-surface font-label-md text-label-md hover:bg-surface-container-high transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || students.length === 0}
            className="px-4 py-2 rounded-md bg-primary text-on-primary font-label-md text-label-md hover:bg-primary/90 transition-colors disabled:opacity-60"
          >
            {submitting ? "Saving..." : "Mark Attendance"}
          </button>
        </div>
      </div>
    </div>
  );
}
