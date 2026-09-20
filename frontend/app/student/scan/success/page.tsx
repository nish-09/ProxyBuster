"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { RequireRole } from "@/components/route-guard";
import { useAuth } from "@/lib/auth-context";
import { ApiError, studentApi, type LastScanOut } from "@/lib/api";
import { readCachedScanResult } from "@/lib/scan-cache";

interface View {
  status: string;
  subject: string;
  division: string;
  topic: string | null;
  markedAt: string;
  /** Milliseconds since epoch at which the cooldown ends, or null if none. Server-derived. */
  cooldownEndsAt: number | null;
  authoritative: boolean;
}

function fromServer(last: LastScanOut): View {
  return {
    status: last.attendance_status,
    subject: last.subject_name,
    division: last.division_name,
    topic: last.session_topic,
    markedAt: last.marked_at,
    // Anchor on the server's own remaining-seconds figure, not on comparing the server timestamp
    // with this device's clock (which may be wrong).
    cooldownEndsAt: last.cooldown_active ? Date.now() + last.cooldown_remaining_seconds * 1000 : null,
    authoritative: true,
  };
}

function formatMarkedAt(iso: string) {
  const d = new Date(iso);
  return {
    date: d.toLocaleDateString([], { day: "numeric", month: "long", year: "numeric" }),
    time: d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" }),
  };
}

function formatMmSs(totalSeconds: number) {
  const s = Math.max(0, totalSeconds);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function SuccessContent() {
  const router = useRouter();
  const { user } = useAuth();
  const [view, setView] = useState<View | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "none" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(async () => {
    setState((s) => (s === "ready" ? s : "loading"));
    try {
      const last = await studentApi.lastScan();
      setView(fromServer(last));
      setState("ready");
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setState((s) => (s === "ready" ? s : "none"));
      } else {
        setErrorMessage(err instanceof ApiError ? err.message : "Couldn't load your attendance details.");
        setState((s) => (s === "ready" ? s : "error"));
      }
    }
  }, []);

  useEffect(() => {
    // Paint immediately from the scan response we just received, then replace it with the
    // authoritative record from the database (this is what a refresh/reopen will show too).
    const cached = readCachedScanResult();
    if (cached && cached.marked_at && cached.subject_name) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time hand-off from the scanner
      setView({
        status: cached.attendance_status ?? "present",
        subject: cached.subject_name,
        division: cached.division_name ?? "",
        topic: cached.session_topic,
        markedAt: cached.marked_at,
        cooldownEndsAt: cached.cooldown_seconds ? Date.now() + cached.cooldown_seconds * 1000 : null,
        authoritative: false,
      });
      setState("ready");
    }
    void load();
  }, [load]);

  useEffect(() => {
    if (!view?.cooldownEndsAt) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [view?.cooldownEndsAt]);

  if (state === "loading") {
    return (
      <main className="flex-1 w-full min-h-dvh flex items-center justify-center bg-surface" role="status" aria-label="Loading attendance details">
        <span className="material-symbols-outlined animate-spin text-primary text-4xl">progress_activity</span>
      </main>
    );
  }

  if (state === "none" || state === "error" || !view) {
    return (
      <main className="flex-1 w-full min-h-dvh flex items-center justify-center bg-surface p-container-padding">
        <div className="w-full max-w-md bg-surface-container-lowest rounded-xl card-shadow p-stack-lg flex flex-col items-center text-center border border-outline">
          <span className="material-symbols-outlined text-5xl text-on-surface-variant mb-3">{state === "error" ? "cloud_off" : "history"}</span>
          <h1 className="font-headline-md text-headline-md text-on-surface mb-1">
            {state === "error" ? "Couldn't load the details" : "No recent attendance"}
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant mb-stack-md">
            {state === "error" ? errorMessage : "You haven't marked attendance recently. Scan a QR code to mark it."}
          </p>
          <div className="flex gap-2 w-full">
            {state === "error" && (
              <button onClick={() => void load()} className="flex-1 h-11 rounded-lg bg-primary text-on-primary font-label-md text-label-md">
                Try again
              </button>
            )}
            <button
              onClick={() => router.replace("/student/dashboard")}
              className="flex-1 h-11 rounded-lg border border-outline-variant bg-surface-container text-on-surface font-label-md text-label-md"
            >
              Dashboard
            </button>
          </div>
        </div>
      </main>
    );
  }

  const { date, time } = formatMarkedAt(view.markedAt);
  const cooldownLeft = view.cooldownEndsAt ? Math.max(0, Math.ceil((view.cooldownEndsAt - now) / 1000)) : 0;

  return (
    <main className="flex-1 w-full min-h-dvh flex items-center justify-center bg-surface p-container-padding">
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl clay-glow-green p-stack-lg flex flex-col items-center text-center">
        <div className="w-16 h-16 rounded-full bg-tertiary-container flex items-center justify-center mb-stack-md clay-glow-green animate-clay-pop">
          <span className="material-symbols-outlined filled text-on-tertiary-container" style={{ fontSize: 36 }}>
            check_circle
          </span>
        </div>
        <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">Attendance Marked Successfully</h1>
        <p className="font-body-md text-body-md text-on-surface-variant mb-stack-lg">
          {user ? `Thanks, ${user.full_name.split(" ")[0]}. ` : ""}You&apos;re marked {view.status === "late" ? "late" : "present"}.
        </p>

        <dl className="w-full bg-surface-container border border-outline-variant rounded-md divide-y divide-outline-variant text-left">
          <Row label="Subject" value={`${view.subject}${view.division ? ` (${view.division})` : ""}`} />
          {view.topic && <Row label="Session" value={view.topic} />}
          <Row label="Date" value={date} />
          <Row label="Time" value={time} />
          <Row label="Status" value={view.status} valueClass="text-tertiary capitalize" />
          {user && <Row label="Student" value={user.full_name} />}
        </dl>

        {view.cooldownEndsAt !== null && (
          <div
            className="mt-stack-md w-full flex items-center justify-between gap-3 bg-secondary-container text-on-secondary-container rounded-md px-4 py-3"
            role="status"
          >
            <span className="flex items-center gap-2 font-label-md text-label-md">
              <span className="material-symbols-outlined text-[20px]">lock_clock</span>
              {cooldownLeft > 0 ? "Next scan available in" : "You can scan again"}
            </span>
            {cooldownLeft > 0 && <span className="font-headline-md text-headline-md tabular-nums">{formatMmSs(cooldownLeft)}</span>}
          </div>
        )}

        <button
          onClick={() => router.replace("/student/dashboard")}
          className="mt-stack-lg w-full h-12 px-6 rounded-lg bg-primary text-on-primary font-label-md text-label-md hover:bg-primary/90 transition-colors"
        >
          Back to Dashboard
        </button>
      </div>
    </main>
  );
}

function Row({ label, value, valueClass = "text-on-surface" }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex justify-between items-center gap-4 px-4 py-3">
      <dt className="font-label-md text-label-md text-on-surface-variant shrink-0">{label}</dt>
      <dd className={`font-body-md text-body-md font-semibold text-right break-words min-w-0 ${valueClass}`}>{value}</dd>
    </div>
  );
}

export default function StudentScanSuccessPage() {
  return (
    <RequireRole role="student">
      <SuccessContent />
    </RequireRole>
  );
}
