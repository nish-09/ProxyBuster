"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { RequireRole } from "@/components/route-guard";
import { studentApi, ApiError } from "@/lib/api";

function formatMMSS(totalSeconds: number) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return { m: m.toString().padStart(2, "0"), s: rem.toString().padStart(2, "0") };
}

function CooldownContent() {
  const router = useRouter();
  const [remaining, setRemaining] = useState<number | null>(null);
  const [reactivatesAt, setReactivatesAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [blink, setBlink] = useState(true);

  useEffect(() => {
    let cancelled = false;
    studentApi
      .cooldown()
      .then((status) => {
        if (cancelled) return;
        if (!status.active) {
          router.replace("/student/dashboard");
          return;
        }
        setRemaining(status.remaining_seconds);
        if (status.expires_at) {
          setReactivatesAt(
            new Date(status.expires_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
          );
        }
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load cooldown status.");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  useEffect(() => {
    if (remaining === null) return;
    if (remaining <= 0) {
      router.replace("/student/dashboard");
      return;
    }
    const tick = setInterval(() => {
      setRemaining((r) => (r === null ? null : Math.max(0, r - 1)));
    }, 1000);
    const blinkTimer = setInterval(() => setBlink((b) => !b), 1000);
    return () => {
      clearInterval(tick);
      clearInterval(blinkTimer);
    };
  }, [remaining, router]);

  if (loading) {
    return (
      <main className="flex-1 flex flex-col justify-center items-center w-full min-h-screen">
        <span className="material-symbols-outlined animate-spin text-primary text-4xl">progress_activity</span>
      </main>
    );
  }

  if (error || remaining === null) {
    return (
      <main className="flex-1 flex flex-col justify-center items-center w-full min-h-screen p-container-padding text-center">
        <p className="font-body-md text-body-md text-error mb-4">{error ?? "Unable to load cooldown status."}</p>
        <button onClick={() => router.replace("/student/dashboard")} className="px-4 py-2 rounded-md bg-primary text-on-primary font-body-md">
          Return to Dashboard
        </button>
      </main>
    );
  }

  const { m, s } = formatMMSS(remaining);
  const progressPct = Math.max(0, Math.min(100, (remaining / 3600) * 100));

  return (
    <main className="flex-1 flex flex-col justify-center items-center w-full min-h-screen p-container-padding relative overflow-hidden bg-background">
      <div className="w-full max-w-lg z-10 flex flex-col items-center justify-center animate-fade-in-up">
        <div className="bg-surface border-2 border-outline rounded-lg shadow-[6px_6px_0_#111111] p-stack-lg w-full flex flex-col items-center text-center relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-2 bg-surface-container-high border-b-2 border-outline">
            <div className="h-full bg-error" style={{ width: `${progressPct}%` }} />
          </div>
          <div className="w-16 h-16 rounded-md bg-error-container border-2 border-outline flex items-center justify-center mb-stack-md mt-2">
            <span className="material-symbols-outlined filled text-on-error-container" style={{ fontSize: 32 }}>
              lock_clock
            </span>
          </div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-stack-sm">Session Lock Active</h1>
          <p className="font-body-md text-body-md text-on-surface-variant mb-stack-lg max-w-sm">
            For security, attendance can only be marked once per 60-minute window from a single device.
          </p>
          <div className="bg-surface-container-low py-6 px-10 rounded-md border-2 border-outline mb-stack-lg w-full flex flex-col items-center">
            <div className="font-display-lg text-display-lg text-on-surface tracking-tight font-extrabold flex items-center gap-1">
              <span>{m}</span>
              <span style={{ opacity: blink ? 1 : 0 }} className="text-primary">
                :
              </span>
              <span>{s}</span>
            </div>
            {reactivatesAt && (
              <div className="font-label-md text-label-md text-on-surface-variant mt-2 uppercase tracking-widest">
                Re-activates at {reactivatesAt}
              </div>
            )}
          </div>
          <div className="flex items-start gap-3 bg-secondary-container p-4 rounded-md border-2 border-outline w-full text-left">
            <span className="material-symbols-outlined text-on-secondary-container mt-0.5" style={{ fontSize: 20 }}>
              security
            </span>
            <p className="font-label-sm text-label-sm text-on-secondary-container leading-relaxed font-semibold">
              Multiple device logins or frequent logouts trigger this protective state. Please wait for the timer to expire before
              attempting to mark attendance again.
            </p>
          </div>
          <button
            onClick={() => router.push("/student/dashboard")}
            className="mt-stack-lg font-label-md text-label-md text-on-surface border border-outline-variant bg-white rounded-md px-6 py-2.5 transition-colors flex items-center gap-2"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
              arrow_back
            </span>
            Return to Dashboard
          </button>
        </div>
        <div className="mt-stack-lg font-label-sm text-label-sm text-on-surface-variant tracking-wider">PROXY BUSTERS SECURITY</div>
      </div>
    </main>
  );
}

export default function StudentCooldownPage() {
  return (
    <RequireRole role="student">
      <CooldownContent />
    </RequireRole>
  );
}
