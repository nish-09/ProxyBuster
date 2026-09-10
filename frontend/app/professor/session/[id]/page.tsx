"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import QRCode from "qrcode";
import { RequireRole } from "@/components/route-guard";
import { ManualEntryModal } from "@/components/professor/ManualEntryModal";
import {
  attendanceApi,
  attendanceSocketUrl,
  professorApi,
  type LiveFeedEntry,
  type StudentListItem,
} from "@/lib/api";

const QR_TTL_SECONDS = 10; // mirrors backend settings.qr_token_ttl_seconds

function SessionContent({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const subject = searchParams.get("subject") ?? "Attendance Session";
  const division = searchParams.get("division") ?? "";
  const room = searchParams.get("room") ?? "";
  const classDivisionId = searchParams.get("cd") ?? "";

  const [lectureId, setLectureId] = useState<string | null>(null);
  const [status, setStatus] = useState<"active" | "closed" | "loading" | "error">("loading");
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(QR_TTL_SECONDS);
  const [presentCount, setPresentCount] = useState(0);
  const [totalEnrolled, setTotalEnrolled] = useState(0);
  const [feed, setFeed] = useState<LiveFeedEntry[]>([]);
  const [connection, setConnection] = useState<"live" | "polling" | "connecting">("connecting");
  const [showManual, setShowManual] = useState(false);
  const [rosterStudents, setRosterStudents] = useState<StudentListItem[]>([]);
  const [stopping, setStopping] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const expiresAtRef = useRef<number | null>(null);

  const renderQr = useCallback(async (payload: string) => {
    try {
      const url = await QRCode.toDataURL(payload, { width: 256, margin: 1, color: { dark: "#191c1e", light: "#ffffff" } });
      setQrDataUrl(url);
    } catch {
      setQrDataUrl(null);
    }
  }, []);

  const applyQr = useCallback(
    (token: string, expiresAtIso: string) => {
      renderQr(token);
      expiresAtRef.current = new Date(expiresAtIso).getTime();
    },
    [renderQr]
  );

  // Tick the countdown from expiresAtRef every second, independent of transport.
  useEffect(() => {
    countdownRef.current = setInterval(() => {
      if (!expiresAtRef.current) return;
      const remaining = Math.max(0, Math.round((expiresAtRef.current - Date.now()) / 1000));
      setSecondsLeft(remaining);
    }, 1000);
    return () => {
      if (countdownRef.current) clearInterval(countdownRef.current);
    };
  }, []);

  const startPolling = useCallback(() => {
    setConnection("polling");
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      try {
        const live = await attendanceApi.liveSession(sessionId);
        setPresentCount(live.present_count);
        setTotalEnrolled(live.total_enrolled);
        setFeed(live.feed);
        if (live.status === "closed") {
          setStatus("closed");
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          return;
        }
        if (live.qr_payload && live.current_token_expires_at) {
          applyQr(live.qr_payload, live.current_token_expires_at);
        }
      } catch {
        // keep polling; a transient error shouldn't kill the fallback loop
      }
    }, 3500);
  }, [sessionId, applyQr]);

  // Initial load: confirm ownership/lecture id, seed state from the live endpoint.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const session = await attendanceApi.getSession(sessionId);
        if (cancelled) return;
        setLectureId(session.lecture_id);
        setStatus(session.status);
        const live = await attendanceApi.liveSession(sessionId);
        if (cancelled) return;
        setPresentCount(live.present_count);
        setTotalEnrolled(live.total_enrolled);
        setFeed(live.feed);
        if (live.qr_payload && live.current_token_expires_at) {
          applyQr(live.qr_payload, live.current_token_expires_at);
        }
      } catch {
        if (!cancelled) setStatus("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, applyQr]);

  // WebSocket connection with polling fallback.
  useEffect(() => {
    if (status !== "active" && status !== "loading") return;
    const ws = new WebSocket(attendanceSocketUrl(sessionId));
    wsRef.current = ws;

    ws.onopen = () => setConnection("live");
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "qr") {
          applyQr(msg.token, msg.expires_at);
        } else if (msg.type === "checkin") {
          setPresentCount(msg.present_count);
          setTotalEnrolled(msg.total_enrolled);
          setFeed((prev) => [
            { id: crypto.randomUUID(), student_name: msg.student_name, roll_number: msg.roll_number, status: msg.status, marked_at: msg.marked_at },
            ...prev,
          ].slice(0, 20));
        } else if (msg.type === "manual") {
          setPresentCount(msg.present_count);
          setTotalEnrolled(msg.total_enrolled);
        } else if (msg.type === "closed") {
          setStatus("closed");
        }
      } catch {
        // ignore malformed frames
      }
    };
    ws.onerror = () => startPolling();
    ws.onclose = () => {
      if (wsRef.current === ws) startPolling();
    };

    return () => {
      ws.close();
      if (wsRef.current === ws) wsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, status]);

  useEffect(
    () => () => {
      if (pollRef.current) clearInterval(pollRef.current);
    },
    []
  );

  async function handleStop() {
    setStopping(true);
    try {
      await attendanceApi.closeSession(sessionId);
      setStatus("closed");
      if (wsRef.current) wsRef.current.close();
      if (pollRef.current) clearInterval(pollRef.current);
    } finally {
      setStopping(false);
    }
  }

  async function openManualEntry() {
    if (classDivisionId) {
      try {
        const res = await professorApi.students({ class_division_id: classDivisionId });
        setRosterStudents(res.items);
      } catch {
        setRosterStudents([]);
      }
    }
    setShowManual(true);
  }

  async function submitManual(payload: { student_id: string; status: "present" | "absent" | "late"; reason: string }) {
    if (!lectureId) return;
    await attendanceApi.manual({ ...payload, lecture_id: lectureId });
    setShowManual(false);
  }

  const percent = totalEnrolled > 0 ? Math.round((presentCount / totalEnrolled) * 100) : 0;

  if (status === "error") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface p-6">
        <div className="text-center">
          <p className="font-headline-md text-headline-md text-error mb-2">Could not open this session</p>
          <p className="font-body-md text-body-md text-on-surface-variant mb-4">
            It may not exist, or you may not have access to it.
          </p>
          <button onClick={() => router.push("/professor/dashboard")} className="text-primary font-label-md text-label-md hover:underline">
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-background text-on-background font-body-md min-h-screen">
      <header className="sticky top-0 z-40 bg-surface border-b-2 border-outline flex justify-between items-center w-full px-container-padding h-16">
        <button onClick={() => router.push("/professor/dashboard")} className="flex items-center gap-2 text-on-surface-variant hover:text-primary transition-colors">
          <span className="material-symbols-outlined">arrow_back</span>
          <span className="font-label-md text-label-md hidden sm:inline">Dashboard</span>
        </button>
        <span className="font-headline-md text-headline-md font-extrabold text-primary">Proxy Busters</span>
        <span className="w-20" />
      </header>

      <div className="flex-1 p-container-padding flex flex-col gap-gutter max-w-5xl mx-auto w-full">
        <div className="bg-surface rounded-lg border-2 border-outline shadow-[4px_4px_0_#111111] p-stack-md flex flex-col sm:flex-row justify-between items-start sm:items-center gap-stack-sm">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className={`w-2.5 h-2.5 rounded-full border border-outline ${status === "active" ? "bg-primary pulse-ring" : "bg-outline"}`} />
              <span className="font-label-sm text-label-sm text-primary uppercase tracking-widest font-bold">
                {status === "active" ? "Live Session" : status === "closed" ? "Session Closed" : "Loading..."}
              </span>
            </div>
            <h2 className="font-display-lg text-display-lg text-on-surface">
              {subject} {division && <span className="text-on-surface-variant font-headline-lg">({division})</span>}
            </h2>
            <p className="font-body-md text-body-md text-on-surface-variant flex items-center gap-1 mt-1">
              <span className="material-symbols-outlined text-sm">schedule</span>
              {room ? `${room} • ` : ""}
              {connection === "live" ? "Live updates" : connection === "polling" ? "Reconnecting (polling)" : "Connecting..."}
            </p>
          </div>
          <div className="bg-primary text-on-primary border-2 border-outline px-3 py-1.5 rounded-md flex items-center gap-2">
            <span className="material-symbols-outlined text-sm filled">shield_locked</span>
            <span className="font-label-md text-label-md font-bold">Secure Mode Enabled</span>
          </div>
        </div>

        {status === "closed" ? (
          <div className="bg-surface rounded-lg border-2 border-outline shadow-[4px_4px_0_#111111] p-stack-lg text-center">
            <span className="material-symbols-outlined text-5xl text-primary mb-3">task_alt</span>
            <h3 className="font-headline-lg text-headline-lg text-on-surface mb-1">Session Closed</h3>
            <p className="font-body-md text-body-md text-on-surface-variant mb-4">
              Final attendance: {presentCount} / {totalEnrolled} ({percent}%)
            </p>
            <button
              onClick={() => router.push("/professor/dashboard")}
              className="px-5 py-2 bg-primary text-on-primary border-2 border-outline rounded-md font-label-md text-label-md transition-colors"
            >
              Back to Dashboard
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter flex-1">
            <div className="lg:col-span-2 bg-surface rounded-lg border-2 border-outline shadow-[6px_6px_0_#111111] flex flex-col relative overflow-hidden min-h-[420px]">
              <div className="p-stack-md flex justify-between items-center z-10 border-b-2 border-outline">
                <h3 className="font-headline-md text-headline-md text-on-surface">Scan to Mark Attendance</h3>
              </div>
              <div className="flex-1 flex flex-col items-center justify-center p-stack-lg z-10 bg-surface-container-low">
                <div className="bg-surface p-4 rounded-lg border-2 border-outline shadow-[4px_4px_0_#111111] relative">
                  <div className="w-64 h-64 bg-white border-2 border-outline rounded-md flex items-center justify-center relative overflow-hidden">
                    {qrDataUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={qrDataUrl} alt="Attendance QR code" className="w-full h-full object-contain" />
                    ) : (
                      <span className="material-symbols-outlined text-6xl text-primary opacity-50 animate-pulse">qr_code_2</span>
                    )}
                  </div>
                  <div className="absolute -bottom-4 left-1/2 -translate-x-1/2 bg-secondary border-2 border-outline shadow-[2px_2px_0_#111111] rounded-md px-4 py-1.5 flex items-center gap-2 whitespace-nowrap">
                    <span className="material-symbols-outlined text-on-secondary text-sm animate-spin" style={{ animationDuration: "3s" }}>
                      refresh
                    </span>
                    <span className="font-label-sm text-label-sm text-on-secondary font-bold">
                      Refreshing in <span>{secondsLeft}</span>s
                    </span>
                  </div>
                </div>
              </div>
              <div className="h-2 w-full bg-surface-container-high z-10 relative border-t-2 border-outline">
                <div className="h-full bg-primary progress-bar-animated" style={{ width: `${(secondsLeft / QR_TTL_SECONDS) * 100}%` }} />
              </div>
            </div>

            <div className="flex flex-col gap-gutter h-full">
              <div className="bg-tertiary-container rounded-lg border-2 border-outline shadow-[4px_4px_0_#111111] p-stack-md flex-shrink-0">
                <h4 className="font-label-md text-label-md text-on-tertiary-container uppercase tracking-wider mb-2">Attendance Status</h4>
                <div className="flex items-baseline gap-2">
                  <span className="font-display-lg text-display-lg text-on-tertiary-container">{presentCount}</span>
                  <span className="font-headline-md text-headline-md text-on-tertiary-container">/ {totalEnrolled}</span>
                </div>
                <div className="mt-4 w-full bg-surface border-2 border-outline rounded-md h-3 overflow-hidden">
                  <div className="bg-primary h-full" style={{ width: `${percent}%` }} />
                </div>
                <p className="font-label-sm text-label-sm text-on-tertiary-container mt-2 text-right font-bold">{percent}% Present</p>
              </div>

              <div className="bg-surface rounded-lg border-2 border-outline shadow-[4px_4px_0_#111111] p-stack-md flex-1 flex flex-col min-h-[200px]">
                <div className="flex justify-between items-center mb-stack-sm">
                  <h4 className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Live Feed</h4>
                  <span className="flex h-2 w-2 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
                  </span>
                </div>
                <div className="flex-1 overflow-y-auto space-y-2 pr-2 custom-scrollbar">
                  {feed.length === 0 && (
                    <p className="font-body-md text-body-md text-on-surface-variant text-center py-6">No check-ins yet.</p>
                  )}
                  {feed.map((entry, idx) => (
                    <div
                      key={entry.id}
                      className="flex items-center gap-3 p-2 rounded-lg bg-surface-container-low border border-outline-variant/30"
                      style={{ opacity: Math.max(0.4, 1 - idx * 0.05) }}
                    >
                      <div className="w-8 h-8 rounded-full bg-tertiary-container flex items-center justify-center flex-shrink-0 text-on-tertiary-container font-label-md">
                        {entry.student_name.slice(0, 1)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-label-sm text-label-sm text-on-surface truncate">{entry.student_name}</p>
                        <p className="font-body-md text-xs text-on-surface-variant truncate">{entry.roll_number}</p>
                      </div>
                      <span className="material-symbols-outlined text-primary text-sm filled">check_circle</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-surface rounded-xl border border-outline-variant shadow-sm p-stack-sm flex flex-col gap-2 flex-shrink-0">
                <button
                  onClick={handleStop}
                  disabled={stopping}
                  className="w-full flex items-center justify-center gap-2 bg-error text-on-error py-2.5 rounded-lg font-label-md text-label-md hover:bg-error/90 transition-colors shadow-sm disabled:opacity-60"
                >
                  <span className="material-symbols-outlined text-sm filled">stop_circle</span>
                  {stopping ? "Stopping..." : "Stop Session"}
                </button>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={openManualEntry}
                    className="flex items-center justify-center gap-1 bg-surface-container text-on-surface py-2 rounded-lg font-label-sm text-label-sm border border-outline-variant hover:bg-surface-container-high transition-colors"
                  >
                    <span className="material-symbols-outlined text-[16px]">edit_note</span>
                    Manual Entry
                  </button>
                  <button
                    disabled
                    title="Sessions don't auto-expire — they stay active until you press Stop Session, so there's nothing to extend."
                    className="flex items-center justify-center gap-1 bg-surface-container text-on-surface-variant py-2 rounded-lg font-label-sm text-label-sm border border-outline-variant opacity-50 cursor-not-allowed"
                  >
                    <span className="material-symbols-outlined text-[16px]">more_time</span>
                    Extend Timer
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {showManual && (
        <ManualEntryModal students={rosterStudents} onClose={() => setShowManual(false)} onSubmit={submitManual} />
      )}
    </div>
  );
}

export default function ProfessorSessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequireRole role="professor">
      <SessionContent sessionId={id} />
    </RequireRole>
  );
}
