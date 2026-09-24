"use client";

import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  verificationApi,
  type ClassroomVerificationDetailOut,
  type DecisionActionValue,
  type RestrictionDurationValue,
  type VerificationResultOut,
  type ViolationReasonValue,
} from "@/lib/api";
import { ViolationConfirmDialog } from "@/components/professor/ViolationConfirmDialog";

const MAX_IMAGES = 3;
const POLL_INTERVAL_MS = 2000;
const MAX_POLL_ATTEMPTS = 60; // 2 minutes
const ANALYZING_STEPS = [
  "Uploading images...",
  "Analyzing classroom...",
  "Matching students...",
  "Comparing attendance...",
  "Generating discrepancies...",
];

interface Slot {
  file: File;
  previewUrl: string;
}

type Stage = "capture" | "analyzing" | "review" | "error";

interface ClassroomVerificationModalProps {
  sessionId: string;
  subjectLabel: string;
  onClose: () => void;
}

export function ClassroomVerificationModal({ sessionId, subjectLabel, onClose }: ClassroomVerificationModalProps) {
  const [slots, setSlots] = useState<Slot[]>([]);
  const [stage, setStage] = useState<Stage>("capture");
  const [stepIndex, setStepIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<ClassroomVerificationDetailOut | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const cameraInputRef = useRef<HTMLInputElement>(null);
  const uploadInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stepTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);
  const slotsRef = useRef<Slot[]>([]);

  useEffect(() => {
    slotsRef.current = slots;
  }, [slots]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (pollRef.current) clearInterval(pollRef.current);
      if (stepTimerRef.current) clearInterval(stepTimerRef.current);
      slotsRef.current.forEach((s) => URL.revokeObjectURL(s.previewUrl));
    };
  }, []);

  function addFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setSlots((prev) => {
      const room = MAX_IMAGES - prev.length;
      if (room <= 0) return prev;
      const next = Array.from(files)
        .slice(0, room)
        .map((file) => ({ file, previewUrl: URL.createObjectURL(file) }));
      return [...prev, ...next];
    });
  }

  function removeSlot(index: number) {
    setSlots((prev) => {
      const target = prev[index];
      if (target) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((_, i) => i !== index);
    });
  }

  function stopTimers() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (stepTimerRef.current) {
      clearInterval(stepTimerRef.current);
      stepTimerRef.current = null;
    }
  }

  function pollUntilDone(verificationId: string) {
    let attempts = 0;
    pollRef.current = setInterval(async () => {
      attempts += 1;
      try {
        const result = await verificationApi.get(verificationId);
        if (!mountedRef.current) return;
        if (result.verification.status === "completed") {
          stopTimers();
          setDetail(result);
          setStage("review");
        } else if (result.verification.status === "failed") {
          stopTimers();
          setError(result.verification.error_message ?? "Analysis failed. Please try again.");
          setStage("error");
        } else if (attempts >= MAX_POLL_ATTEMPTS) {
          stopTimers();
          setError("This is taking longer than expected. Check back shortly, or try again.");
          setStage("error");
        }
      } catch (err) {
        if (!mountedRef.current) return;
        if (attempts >= MAX_POLL_ATTEMPTS) {
          stopTimers();
          setError(err instanceof ApiError ? err.message : "Lost connection while analyzing. Please try again.");
          setStage("error");
        }
      }
    }, POLL_INTERVAL_MS);
  }

  async function handleAnalyze() {
    if (slots.length === 0) return;
    setSubmitting(true);
    setError(null);
    setStage("analyzing");
    setStepIndex(0);
    stepTimerRef.current = setInterval(() => {
      setStepIndex((i) => Math.min(i + 1, ANALYZING_STEPS.length - 1));
    }, 1800);
    try {
      const verification = await verificationApi.start(
        sessionId,
        slots.map((s) => s.file)
      );
      pollUntilDone(verification.id);
    } catch (err) {
      stopTimers();
      setError(err instanceof ApiError ? err.message : "Could not start classroom verification. Please try again.");
      setStage("error");
    } finally {
      setSubmitting(false);
    }
  }

  function reset() {
    slots.forEach((s) => URL.revokeObjectURL(s.previewUrl));
    setSlots([]);
    setDetail(null);
    setError(null);
    setStage("capture");
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-inverse-surface/40 p-4">
      <div className="w-full max-w-2xl max-h-[calc(100dvh-2rem)] overflow-y-auto bg-surface-container-lowest border border-outline-variant rounded-xl card-shadow p-stack-md">
        <div className="flex items-center justify-between mb-stack-sm">
          <h3 className="font-headline-md text-headline-md text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary">photo_camera</span>
            Classroom Verification
          </h3>
          <button
            onClick={onClose}
            aria-label="Close"
            className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-surface-container-high text-on-surface-variant transition-colors"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {stage === "capture" && (
          <>
            <p className="font-body-md text-body-md text-on-surface-variant mb-stack-md">
              Capture or upload 1-3 classroom photos. AI suggestions require your verification — nothing here changes
              attendance automatically.
            </p>
            <div className="grid grid-cols-3 gap-3 mb-stack-md">
              {slots.map((slot, i) => (
                <div key={slot.previewUrl} className="relative aspect-square rounded-lg overflow-hidden border border-outline-variant bg-surface-container">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={slot.previewUrl} alt={`Classroom photo ${i + 1}`} className="w-full h-full object-cover" />
                  <button
                    onClick={() => removeSlot(i)}
                    aria-label="Remove photo"
                    className="absolute top-1 right-1 w-7 h-7 rounded-full bg-inverse-surface/70 text-inverse-on-surface flex items-center justify-center"
                  >
                    <span className="material-symbols-outlined text-[16px]">close</span>
                  </button>
                </div>
              ))}
              {slots.length < MAX_IMAGES && (
                <button
                  onClick={() => uploadInputRef.current?.click()}
                  className="aspect-square rounded-lg border-2 border-dashed border-outline-variant flex flex-col items-center justify-center gap-1 text-on-surface-variant hover:bg-surface-container-low transition-colors"
                >
                  <span className="material-symbols-outlined">add_a_photo</span>
                  <span className="font-label-sm text-label-sm">
                    {slots.length}/{MAX_IMAGES}
                  </span>
                </button>
              )}
            </div>

            <input
              ref={cameraInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = "";
              }}
            />
            <input
              ref={uploadInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = "";
              }}
            />

            <div className="flex flex-wrap gap-2 mb-stack-md">
              <button
                onClick={() => cameraInputRef.current?.click()}
                disabled={slots.length >= MAX_IMAGES}
                className="flex-1 min-w-[140px] h-11 rounded-lg border border-outline-variant bg-surface-container text-on-surface font-label-md text-label-md flex items-center justify-center gap-2 disabled:opacity-50 transition-colors"
              >
                <span className="material-symbols-outlined text-[18px]">photo_camera</span>
                Take Photo
              </button>
              <button
                onClick={() => uploadInputRef.current?.click()}
                disabled={slots.length >= MAX_IMAGES}
                className="flex-1 min-w-[140px] h-11 rounded-lg border border-outline-variant bg-surface-container text-on-surface font-label-md text-label-md flex items-center justify-center gap-2 disabled:opacity-50 transition-colors"
              >
                <span className="material-symbols-outlined text-[18px]">upload</span>
                Upload
              </button>
            </div>

            {error && <p className="font-body-md text-body-md text-error mb-stack-sm">{error}</p>}

            <button
              onClick={handleAnalyze}
              disabled={slots.length === 0 || submitting}
              className="w-full h-12 rounded-lg bg-primary text-on-primary font-label-md text-label-md disabled:opacity-60"
            >
              Analyze Classroom
            </button>
          </>
        )}

        {stage === "analyzing" && (
          <div className="flex flex-col items-center justify-center py-stack-lg gap-4">
            <span className="material-symbols-outlined animate-spin text-primary text-5xl">progress_activity</span>
            <p className="font-body-lg text-body-lg text-on-surface" aria-live="polite">
              {ANALYZING_STEPS[stepIndex]}
            </p>
            <p className="font-label-sm text-label-sm text-on-surface-variant text-center max-w-sm">
              This can take a little while — feel free to keep this open, the session keeps running normally.
            </p>
          </div>
        )}

        {stage === "error" && (
          <div className="flex flex-col items-center justify-center py-stack-lg gap-4 text-center">
            <span className="material-symbols-outlined text-error text-5xl">error</span>
            <p className="font-body-md text-body-md text-on-surface">{error}</p>
            <button onClick={reset} className="h-11 px-6 rounded-lg bg-primary text-on-primary font-label-md text-label-md">
              Try Again
            </button>
          </div>
        )}

        {stage === "review" && detail && <DiscrepancyReview detail={detail} subjectLabel={subjectLabel} onUpdated={setDetail} />}
      </div>
    </div>
  );
}

function DiscrepancyReview({
  detail,
  subjectLabel,
  onUpdated,
}: {
  detail: ClassroomVerificationDetailOut;
  subjectLabel: string;
  onUpdated: (d: ClassroomVerificationDetailOut) => void;
}) {
  const [violationTarget, setViolationTarget] = useState<VerificationResultOut | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  async function refresh() {
    const fresh = await verificationApi.get(detail.verification.id);
    onUpdated(fresh);
  }

  async function decide(result: VerificationResultOut, action: DecisionActionValue) {
    setBusyId(result.id);
    setRowError(null);
    try {
      await verificationApi.decide(result.id, { action });
      await refresh();
    } catch (err) {
      setRowError(err instanceof ApiError ? err.message : "Could not record this decision. Please try again.");
    } finally {
      setBusyId(null);
    }
  }

  async function confirmViolation(payload: {
    reason: ViolationReasonValue;
    notes: string;
    restriction_duration: RestrictionDurationValue;
    custom_restriction_end?: string;
  }) {
    if (!violationTarget) return;
    await verificationApi.decide(violationTarget.id, { action: "violation", ...payload });
    setViolationTarget(null);
    await refresh();
  }

  const discrepancies = detail.results.filter(
    (r) => r.discrepancy_type !== "attended_and_detected" && r.discrepancy_type !== "none"
  );
  const matched = detail.results.filter((r) => r.discrepancy_type === "attended_and_detected");

  return (
    <div>
      <div className="grid grid-cols-3 gap-2 mb-stack-md text-center">
        <div className="bg-surface-container rounded-lg p-3">
          <p className="font-display-lg text-display-lg text-on-surface">{detail.present_count}</p>
          <p className="font-label-sm text-label-sm text-on-surface-variant">Marked Present</p>
        </div>
        <div className="bg-tertiary-container rounded-lg p-3">
          <p className="font-display-lg text-display-lg text-on-tertiary-container">{detail.confirmed_count}</p>
          <p className="font-label-sm text-label-sm text-on-tertiary-container">Confidently Detected</p>
        </div>
        <div className={`rounded-lg p-3 ${discrepancies.length > 0 ? "bg-error-container" : "bg-surface-container"}`}>
          <p className={`font-display-lg text-display-lg ${discrepancies.length > 0 ? "text-on-error-container" : "text-on-surface"}`}>
            {discrepancies.length}
          </p>
          <p className={`font-label-sm text-label-sm ${discrepancies.length > 0 ? "text-on-error-container" : "text-on-surface-variant"}`}>
            Discrepancies
          </p>
        </div>
      </div>

      {detail.students_excluded_no_reference_photo > 0 && (
        <p className="font-label-sm text-label-sm text-on-surface-variant mb-stack-sm flex items-center gap-1.5">
          <span className="material-symbols-outlined text-[16px]">info</span>
          {detail.students_excluded_no_reference_photo} student(s) have no reference photo on file and were not
          covered by this verification.
        </p>
      )}

      <p className="font-label-sm text-label-sm text-on-surface-variant bg-surface-container rounded-md px-3 py-2 mb-stack-md flex items-center gap-1.5">
        <span className="material-symbols-outlined text-[16px]">shield_locked</span>
        AI suggestions require professor verification. Nothing here changes attendance until you decide.
      </p>

      {rowError && <p className="font-body-md text-body-md text-error mb-stack-sm">{rowError}</p>}

      <div className="space-y-2 max-h-[45vh] overflow-y-auto pr-1">
        {discrepancies.map((r) => (
          <DiscrepancyRow
            key={r.id}
            result={r}
            subjectLabel={subjectLabel}
            busy={busyId === r.id}
            onConfirmPresent={() => decide(r, "confirmed_present")}
            onAskToScan={() => decide(r, "asked_to_scan")}
            onDismiss={() => decide(r, "dismissed")}
            onMarkViolation={() => setViolationTarget(r)}
          />
        ))}
        {matched.map((r) => (
          <div key={r.id} className="flex items-center justify-between gap-3 p-3 rounded-lg border border-outline-variant bg-surface-container-low">
            <div>
              <p className="font-label-md text-label-md text-on-surface">{r.full_name}</p>
              <p className="font-label-sm text-label-sm text-on-surface-variant">
                QR: Present · AI: Detected ({Math.round(r.confidence * 100)}%)
              </p>
            </div>
            <span className="material-symbols-outlined text-tertiary filled">check_circle</span>
          </div>
        ))}
        {discrepancies.length === 0 && matched.length === 0 && (
          <p className="font-body-md text-body-md text-on-surface-variant text-center py-6">No covered students to show.</p>
        )}
      </div>

      {violationTarget && (
        <ViolationConfirmDialog
          studentName={violationTarget.full_name}
          subjectLabel={subjectLabel}
          onClose={() => setViolationTarget(null)}
          onConfirm={confirmViolation}
        />
      )}
    </div>
  );
}

function DiscrepancyRow({
  result,
  subjectLabel,
  busy,
  onConfirmPresent,
  onAskToScan,
  onDismiss,
  onMarkViolation,
}: {
  result: VerificationResultOut;
  subjectLabel: string;
  busy: boolean;
  onConfirmPresent: () => void;
  onAskToScan: () => void;
  onDismiss: () => void;
  onMarkViolation: () => void;
}) {
  const isAttendedNotDetected = result.discrepancy_type === "attended_not_detected";
  const decided = Boolean(result.decision_action);
  const confidencePct = Math.round(result.confidence * 100);
  const aiLabel = result.ai_status === "not_detected" ? "Not Detected" : result.ai_status === "uncertain" ? "Uncertain" : "Detected";

  return (
    <div className={`p-3 rounded-lg border border-outline-variant ${isAttendedNotDetected ? "bg-secondary-container/40" : "bg-error-container/40"}`}>
      <div className="flex items-start justify-between gap-3 mb-2 flex-wrap">
        <div>
          <p className="font-label-md text-label-md text-on-surface">{result.full_name}</p>
          <p className="font-label-sm text-label-sm text-on-surface-variant">
            {result.roll_number} · {subjectLabel}
          </p>
        </div>
        <span className="font-label-sm text-label-sm text-on-surface-variant whitespace-nowrap">
          QR: {result.qr_present ? "Present" : "Absent"} · AI: {aiLabel} ({confidencePct}%)
        </span>
      </div>

      {decided ? (
        <p className="font-label-sm text-label-sm text-on-surface-variant italic capitalize">
          Recorded: {result.decision_action?.replace(/_/g, " ")}
        </p>
      ) : isAttendedNotDetected ? (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={onConfirmPresent}
            disabled={busy}
            className="h-9 px-4 rounded-md bg-tertiary text-on-tertiary font-label-sm text-label-sm disabled:opacity-60"
          >
            Confirm Present
          </button>
          <button
            onClick={onMarkViolation}
            disabled={busy}
            className="h-9 px-4 rounded-md border border-error text-error font-label-sm text-label-sm disabled:opacity-60"
          >
            Mark Attendance Violation
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={onAskToScan}
            disabled={busy}
            className="h-9 px-4 rounded-md bg-primary text-on-primary font-label-sm text-label-sm disabled:opacity-60"
          >
            Ask Student to Scan
          </button>
          <button
            onClick={onDismiss}
            disabled={busy}
            className="h-9 px-4 rounded-md border border-outline-variant text-on-surface font-label-sm text-label-sm disabled:opacity-60"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}
