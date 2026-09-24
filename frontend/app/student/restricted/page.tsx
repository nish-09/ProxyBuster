"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { RequireRole } from "@/components/route-guard";
import { studentApi, ApiError } from "@/lib/api";

const REASON_LABELS: Record<string, string> = {
  proxy_attendance: "Proxy attendance",
  not_physically_present: "Not physically present",
  unauthorized_attendance: "Unauthorized attendance",
  other: "Policy violation",
};

function RestrictedContent() {
  const router = useRouter();
  const [validUntil, setValidUntil] = useState<string | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    studentApi
      .restriction()
      .then((status) => {
        if (cancelled) return;
        if (!status.active) {
          router.replace("/student/dashboard");
          return;
        }
        setValidUntil(status.valid_until);
        setReason(status.reason);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load restriction status.");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (loading) {
    return (
      <main className="flex-1 flex flex-col justify-center items-center w-full min-h-dvh">
        <span className="material-symbols-outlined animate-spin text-primary text-4xl">progress_activity</span>
      </main>
    );
  }

  if (error) {
    return (
      <main className="flex-1 flex flex-col justify-center items-center w-full min-h-dvh p-container-padding text-center">
        <p className="font-body-md text-body-md text-error mb-4">{error}</p>
        <button onClick={() => router.replace("/student/dashboard")} className="px-4 py-2 rounded-md bg-primary text-on-primary font-body-md">
          Return to Dashboard
        </button>
      </main>
    );
  }

  const formattedDate = validUntil
    ? new Date(validUntil).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })
    : null;

  return (
    <main className="flex-1 flex flex-col justify-center items-center w-full min-h-dvh p-container-padding relative overflow-hidden bg-background">
      <div className="w-full max-w-lg z-10 flex flex-col items-center justify-center animate-fade-in-up">
        <div className="bg-surface rounded-xl clay-glow-red p-stack-lg w-full flex flex-col items-center text-center relative overflow-hidden">
          <div className="w-16 h-16 rounded-lg bg-error-container flex items-center justify-center mb-stack-md mt-2 clay-raised">
            <span className="material-symbols-outlined filled text-on-error-container" style={{ fontSize: 32 }}>
              block
            </span>
          </div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-stack-sm">Attendance Restricted</h1>
          <p className="font-body-md text-body-md text-on-surface-variant mb-stack-lg max-w-sm">
            You currently have an attendance restriction{reason && REASON_LABELS[reason] ? ` (${REASON_LABELS[reason]})` : ""}.
          </p>

          {formattedDate && (
            <div className="bg-surface-dim py-5 px-8 rounded-lg mb-stack-lg w-full flex flex-col items-center clay-recessed">
              <span className="font-label-md text-label-md text-on-surface-variant mb-1">Valid until</span>
              <span className="font-headline-lg text-headline-lg text-on-surface font-bold">{formattedDate}</span>
            </div>
          )}

          <div className="flex items-start gap-3 bg-secondary-container p-4 rounded-md w-full text-left clay-raised">
            <span className="material-symbols-outlined text-on-secondary-container mt-0.5" style={{ fontSize: 20 }}>
              info
            </span>
            <p className="font-label-sm text-label-sm text-on-secondary-container leading-relaxed font-medium">
              Please contact your professor or admin if you believe this was applied incorrectly.
            </p>
          </div>

          <button
            onClick={() => router.push("/student/dashboard")}
            className="mt-stack-lg font-label-md text-label-md text-on-surface border border-outline-variant bg-surface-container-high rounded-md px-6 py-2.5 transition-colors flex items-center gap-2"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
              arrow_back
            </span>
            Return to Dashboard
          </button>
        </div>
        <div className="mt-stack-lg font-label-sm text-label-sm text-on-surface-variant">Proxy Busters Security</div>
      </div>
    </main>
  );
}

export default function StudentRestrictedPage() {
  return (
    <RequireRole role="student">
      <RestrictedContent />
    </RequireRole>
  );
}
