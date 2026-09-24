"use client";

import { memo, use, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import { RequireRole } from "@/components/route-guard";
import { ManualEntryModal } from "@/components/professor/ManualEntryModal";
import { ClassroomVerificationModal } from "@/components/professor/ClassroomVerificationModal";
import {
  ApiError,
  attendanceApi,
  attendanceSocketAuthMessage,
  attendanceSocketUrl,
  professorApi,
  type LiveFeedEntry,
  type LiveSessionState,
  type SessionStatus,
  type StudentListItem,
} from "@/lib/api";

type PageStatus = SessionStatus | "loading" | "error";
type Connection = "live" | "polling" | "connecting";

const POLL_INTERVAL_MS = 3500;
const HEARTBEAT_MS = 25_000;
const RECONNECT_DELAYS_MS = [1000, 2000, 4000, 8000, 15000];

function useNow(intervalMs: number) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

/**
 * The QR and its countdown live in their own component, so a rotation (or the 4 Hz countdown tick)
 * re-renders only this panel — never the live feed, counters or the rest of the page.
 */
const QrPanel = memo(function QrPanel({
  payload,
  expiresAtMs,
  ttlSeconds,
  offsetMs,
}: {
  payload: string | null;
  expiresAtMs: number | null;
  ttlSeconds: number;
  offsetMs: number;
}) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  const now = useNow(250);

  useEffect(() => {
    let cancelled = false;
    if (!payload) return;
    // Low error-correction + high resolution keeps modules large, so the code scans from the back
    // of a lecture hall / off a projector.
    QRCode.toDataURL(payload, { width: 640, margin: 2, errorCorrectionLevel: "L", color: { dark: "#191c1e", light: "#ffffff" } })
      .then((url) => {
        if (!cancelled) setDataUrl(url);
      })
      .catch(() => {
        if (!cancelled) setDataUrl(null);
      });
    return () => {
      cancelled = true;
    };
  }, [payload]);

  const msLeft = expiresAtMs === null ? 0 : Math.max(0, expiresAtMs - (now + offsetMs));
  const secondsLeft = Math.ceil(msLeft / 1000);
  const fraction = ttlSeconds > 0 ? Math.min(1, msLeft / (ttlSeconds * 1000)) : 0;

  return (
    <>
      <div className="flex-1 flex flex-col items-center justify-center p-4 sm:p-stack-lg z-10 bg-surface-container-low">
        <div className="bg-surface-container-high p-3 sm:p-5 rounded-xl clay-recessed-glow-blue relative max-w-full">
          <div className="w-full max-w-64 sm:max-w-72 lg:max-w-80 aspect-square bg-white rounded-lg flex items-center justify-center relative overflow-hidden shadow-[0_2px_10px_rgba(23,32,51,0.15)]">
            {payload && dataUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={dataUrl} alt="Attendance QR code" className="w-full h-full object-contain" />
            ) : (
              <span className="material-symbols-outlined text-6xl text-primary opacity-50 animate-pulse">qr_code_2</span>
            )}
          </div>
          <div className="absolute -bottom-4 left-1/2 -translate-x-1/2 bg-secondary rounded-md px-4 py-1.5 flex items-center gap-2 whitespace-nowrap clay-raised">
            <span className="material-symbols-outlined text-on-secondary text-sm animate-spin" style={{ animationDuration: "3s" }}>
              refresh
            </span>
            <span className="font-label-sm text-label-sm text-on-secondary font-semibold">
              Refreshing in <span>{secondsLeft}</span>s
            </span>
          </div>
        </div>
      </div>
      <div className="h-2 w-full bg-surface-container-high z-10 relative border-t border-outline">
        <div className="h-full bg-tertiary" style={{ width: `${fraction * 100}%` }} />
      </div>
    </>
  );
});

function SessionTimer({ endsAtMs, offsetMs }: { endsAtMs: number | null; offsetMs: number }) {
  const now = useNow(1000);
  if (endsAtMs === null) return null;
  const remaining = Math.max(0, Math.ceil((endsAtMs - (now + offsetMs)) / 1000));
  const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
  const ss = String(remaining % 60).padStart(2, "0");
  return (
    <div className="bg-secondary-container text-on-secondary-container px-3 py-1.5 rounded-md flex items-center gap-2 clay-raised">
      <span className="material-symbols-outlined text-sm filled">hourglass_top</span>
      <span className="font-label-md text-label-md font-semibold">{`${mm}:${ss} remaining`}</span>
    </div>
  );
}

function SessionContent({ sessionId }: { sessionId: string }) {
  const router = useRouter();

  const [info, setInfo] = useState<{ subject: string; division: string; room: string; lectureId: string; classDivisionId: string } | null>(null);
  const [status, setStatus] = useState<PageStatus>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [qr, setQr] = useState<{ payload: string | null; expiresAtMs: number | null }>({ payload: null, expiresAtMs: null });
  const [ttlSeconds, setTtlSeconds] = useState(10);
  const [offsetMs, setOffsetMs] = useState(0);
  const [presentCount, setPresentCount] = useState(0);
  const [totalEnrolled, setTotalEnrolled] = useState(0);
  const [feed, setFeed] = useState<LiveFeedEntry[]>([]);
  const [sessionEndsAtMs, setSessionEndsAtMs] = useState<number | null>(null);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [showManual, setShowManual] = useState(false);
  const [showVerification, setShowVerification] = useState(false);
  const [rosterStudents, setRosterStudents] = useState<StudentListItem[]>([]);
  const [stopping, setStopping] = useState(false);
  const [confirmStop, setConfirmStop] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const statusRef = useRef<PageStatus>("loading");
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const updateStatus = useCallback((next: PageStatus) => {
    statusRef.current = next;
    setStatus(next);
  }, []);

  /** Applies a full server snapshot (initial load, polling fallback, and WS resync). */
  const applyLive = useCallback(
    (live: LiveSessionState) => {
      setInfo({
        subject: live.subject_name,
        division: live.division_name,
        room: live.room ?? "",
        lectureId: live.lecture_id,
        classDivisionId: live.class_division_id,
      });
      setTtlSeconds(live.qr_ttl_seconds);
      setOffsetMs(new Date(live.server_time).getTime() - Date.now());
      setPresentCount(live.present_count);
      setTotalEnrolled(live.total_enrolled);
      setFeed(live.feed);
      setSessionEndsAtMs(live.session_expires_at ? new Date(live.session_expires_at).getTime() : null);
      updateStatus(live.status);
      if (live.status !== "active") {
        setQr({ payload: null, expiresAtMs: null });
      } else if (live.qr_payload && live.current_token_expires_at) {
        setQr({ payload: live.qr_payload, expiresAtMs: new Date(live.current_token_expires_at).getTime() });
      }
    },
    [updateStatus]
  );

  const fetchLive = useCallback(async () => {
    const live = await attendanceApi.liveSession(sessionId);
    applyLive(live);
    return live;
  }, [sessionId, applyLive]);

  // Initial load.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const live = await attendanceApi.liveSession(sessionId);
        if (!cancelled) applyLive(live);
      } catch (err) {
        if (cancelled) return;
        setLoadError(err instanceof ApiError && err.status === 0 ? err.message : null);
        updateStatus("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, applyLive, updateStatus]);

  // Realtime: WebSocket first, polling as the fallback, automatic reconnection with backoff.
  useEffect(() => {
    if (status !== "active") return;
    let disposed = false;
    let attempt = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let heartbeat: ReturnType<typeof setInterval> | null = null;

    const stopPolling = () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
    const startPolling = () => {
      setConnection("polling");
      if (pollRef.current) return;
      pollRef.current = setInterval(() => {
        fetchLive().catch(() => {
          /* transient — keep polling */
        });
      }, POLL_INTERVAL_MS);
    };

    const connect = () => {
      if (disposed) return;
      setConnection((c) => (c === "live" ? c : "connecting"));
      const ws = new WebSocket(attendanceSocketUrl(sessionId));
      wsRef.current = ws;
      let ready = false;

      ws.onopen = () => ws.send(attendanceSocketAuthMessage()); // JWT goes in the first frame, not the URL
      ws.onmessage = (event) => {
        let msg: Record<string, unknown>;
        try {
          msg = JSON.parse(event.data as string);
        } catch {
          return;
        }
        if (typeof msg.server_time === "string") setOffsetMs(new Date(msg.server_time).getTime() - Date.now());
        switch (msg.type) {
          case "ready":
            ready = true;
            attempt = 0;
            stopPolling();
            setConnection("live");
            // Re-sync once: anything that happened while disconnected is recovered, and the
            // snapshot REPLACES the feed so events can never be duplicated.
            fetchLive().catch(() => {});
            break;
          case "qr":
            if (typeof msg.token === "string" && typeof msg.expires_at === "string") {
              setQr({ payload: msg.token, expiresAtMs: new Date(msg.expires_at).getTime() });
              if (typeof msg.ttl_seconds === "number") setTtlSeconds(msg.ttl_seconds);
            }
            break;
          case "checkin": {
            setPresentCount(msg.present_count as number);
            setTotalEnrolled(msg.total_enrolled as number);
            const entry: LiveFeedEntry = {
              id: `${msg.roll_number as string}-${msg.marked_at as string}`,
              student_name: msg.student_name as string,
              roll_number: msg.roll_number as string,
              status: msg.status as LiveFeedEntry["status"],
              marked_at: msg.marked_at as string,
            };
            setFeed((prev) => (prev.some((p) => p.roll_number === entry.roll_number) ? prev : [entry, ...prev].slice(0, 20)));
            break;
          }
          case "manual":
            setPresentCount(msg.present_count as number);
            setTotalEnrolled(msg.total_enrolled as number);
            fetchLive().catch(() => {});
            break;
          case "closed":
            updateStatus(msg.status === "expired" ? "expired" : "closed");
            setQr({ payload: null, expiresAtMs: null });
            break;
        }
      };
      const onDown = () => {
        if (disposed || wsRef.current !== ws) return;
        if (heartbeat) clearInterval(heartbeat);
        wsRef.current = null;
        if (statusRef.current !== "active") return;
        startPolling(); // don't lose the QR/counts while we reconnect
        const delay = RECONNECT_DELAYS_MS[Math.min(attempt, RECONNECT_DELAYS_MS.length - 1)];
        attempt += 1;
        reconnectTimer = setTimeout(connect, delay);
      };
      ws.onerror = () => {
        if (!ready) onDown();
      };
      ws.onclose = onDown;

      if (heartbeat) clearInterval(heartbeat);
      heartbeat = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, HEARTBEAT_MS);
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (heartbeat) clearInterval(heartbeat);
      stopPolling();
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
    };
  }, [status, sessionId, fetchLive, updateStatus]);

  useEffect(
    () => () => {
      if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
    },
    []
  );

  async function handleStop() {
    // Two taps: the first arms the button, the second (within 4 s) stops the session — a
    // misplaced tap in front of a class must not end attendance.
    if (!confirmStop) {
      setConfirmStop(true);
      confirmTimerRef.current = setTimeout(() => setConfirmStop(false), 4000);
      return;
    }
    if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
    setConfirmStop(false);
    setStopping(true);
    setActionError(null);
    try {
      await attendanceApi.closeSession(sessionId);
      await fetchLive().catch(() => updateStatus("closed"));
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Already ended (expired, or stopped from another tab): just show the real state.
        await fetchLive().catch(() => {});
      } else {
        setActionError(err instanceof ApiError ? err.message : "Couldn't stop the session. Please try again.");
      }
    } finally {
      setStopping(false);
    }
  }

  async function openManualEntry() {
    setActionError(null);
    if (info?.classDivisionId) {
      try {
        const res = await professorApi.students({ class_division_id: info.classDivisionId });
        setRosterStudents(res.items);
      } catch {
        setRosterStudents([]);
        setActionError("Couldn't load the class list for manual entry.");
        return;
      }
    }
    setShowManual(true);
  }

  async function submitManual(payload: { student_id: string; status: "present" | "absent" | "late"; reason: string }) {
    if (!info) return;
    await attendanceApi.manual({ ...payload, lecture_id: info.lectureId });
    setShowManual(false);
    fetchLive().catch(() => {});
  }

  const percent = totalEnrolled > 0 ? Math.round((presentCount / totalEnrolled) * 100) : 0;
  const ended = status === "closed" || status === "expired";

  if (status === "error") {
    return (
      <div className="min-h-dvh flex items-center justify-center bg-surface p-6">
        <div className="text-center max-w-sm">
          <p className="font-headline-md text-headline-md text-error mb-2">Could not open this session</p>
          <p className="font-body-md text-body-md text-on-surface-variant mb-4">
            {loadError ?? "It may not exist, or you may not have access to it."}
          </p>
          <div className="flex gap-2 justify-center">
            <button
              onClick={() => {
                updateStatus("loading");
                setLoadError(null);
                fetchLive().catch((err) => {
                  setLoadError(err instanceof ApiError && err.status === 0 ? err.message : null);
                  updateStatus("error");
                });
              }}
              className="h-11 px-5 rounded-md bg-primary text-on-primary font-label-md text-label-md"
            >
              Try again
            </button>
            <button onClick={() => router.push("/professor/dashboard")} className="h-11 px-5 text-primary font-label-md text-label-md hover:underline">
              Back to Dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-background text-on-background font-body-md min-h-dvh">
      <header className="sticky top-0 z-40 bg-surface border-b border-outline shadow-[0_6px_20px_rgba(23,32,51,0.08)] flex justify-between items-center w-full px-container-padding h-16">
        <button
          onClick={() => router.push("/professor/dashboard")}
          className="flex items-center gap-2 text-on-surface-variant hover:text-primary transition-colors min-h-11"
        >
          <span className="material-symbols-outlined">arrow_back</span>
          <span className="font-label-md text-label-md hidden sm:inline">Dashboard</span>
        </button>
        <span className="font-headline-md text-headline-md font-bold text-on-surface">Proxy Busters</span>
        <span className="w-20 hidden sm:block" />
      </header>

      <div className="flex-1 p-container-padding flex flex-col gap-gutter max-w-5xl mx-auto w-full">
        <div
          className={`bg-surface rounded-lg p-stack-md flex flex-col sm:flex-row justify-between items-start sm:items-center gap-stack-sm ${
            status === "active" ? "clay-glow-blue" : "border border-outline clay-raised"
          }`}
        >
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className={`w-2.5 h-2.5 rounded-full border border-outline ${status === "active" ? "bg-primary pulse-ring" : "bg-outline"}`} />
              <span className={`font-label-sm text-label-sm font-semibold ${status === "active" ? "text-primary" : "text-on-surface-variant"}`}>
                {status === "active" ? "Session Active" : status === "closed" ? "Session Closed" : status === "expired" ? "Session Expired" : "Loading..."}
              </span>
            </div>
            <h2 className="font-display-lg text-display-lg text-on-surface break-words">
              {info?.subject ?? "Attendance Session"}{" "}
              {info?.division && <span className="text-on-surface-variant font-headline-lg">({info.division})</span>}
            </h2>
            <p className="font-body-md text-body-md text-on-surface-variant flex items-center gap-1 mt-1">
              <span className="material-symbols-outlined text-sm">{connection === "live" ? "sensors" : "sync"}</span>
              {info?.room ? `${info.room} • ` : ""}
              {status !== "active" ? "Not live" : connection === "live" ? "Live updates" : connection === "polling" ? "Reconnecting (polling)" : "Connecting..."}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {status === "active" && <SessionTimer endsAtMs={sessionEndsAtMs} offsetMs={offsetMs} />}
            <div className="bg-primary-container text-on-primary-container px-3 py-1.5 rounded-md flex items-center gap-2 clay-raised">
              <span className="material-symbols-outlined text-sm filled">shield_locked</span>
              <span className="font-label-md text-label-md font-semibold">Secure Mode Enabled</span>
            </div>
          </div>
        </div>

        {ended ? (
          <div className="bg-surface-container-lowest rounded-lg border border-outline card-shadow p-stack-lg text-center">
            <span className="material-symbols-outlined text-5xl text-tertiary mb-3">{status === "expired" ? "timer_off" : "task_alt"}</span>
            <h3 className="font-headline-lg text-headline-lg text-on-surface mb-1">{status === "expired" ? "Session Expired" : "Session Closed"}</h3>
            <p className="font-body-md text-body-md text-on-surface-variant mb-4">
              Final attendance: {presentCount} / {totalEnrolled} ({percent}%)
            </p>
            <div className="flex flex-wrap gap-2 justify-center">
              <button
                onClick={() => setShowVerification(true)}
                className="h-11 px-5 bg-secondary text-on-secondary border border-outline rounded-md font-label-md text-label-md transition-colors flex items-center gap-2"
              >
                <span className="material-symbols-outlined text-[18px]">photo_camera</span>
                Verify Classroom
              </button>
              <button
                onClick={() => router.push("/professor/attendance-sheet")}
                className="h-11 px-5 bg-primary text-on-primary border border-outline rounded-md font-label-md text-label-md transition-colors"
              >
                View Attendance Sheet
              </button>
              <button
                onClick={() => router.push("/professor/dashboard")}
                className="h-11 px-5 bg-surface-container text-on-surface border border-outline rounded-md font-label-md text-label-md transition-colors"
              >
                Back to Dashboard
              </button>
            </div>
          </div>
        ) : status === "loading" ? (
          <div className="bg-surface-container-lowest rounded-lg border border-outline card-shadow p-stack-lg flex items-center justify-center min-h-[320px]" role="status" aria-label="Loading session">
            <span className="material-symbols-outlined animate-spin text-primary text-4xl">progress_activity</span>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter flex-1">
            <div className="lg:col-span-2 bg-surface-container-lowest rounded-lg border border-outline card-shadow flex flex-col relative overflow-hidden min-h-[420px]">
              <div className="p-stack-md flex justify-between items-center z-10 border-b border-outline">
                <h3 className="font-headline-md text-headline-md text-on-surface">Scan to Mark Attendance</h3>
              </div>
              <QrPanel payload={qr.payload} expiresAtMs={qr.expiresAtMs} ttlSeconds={ttlSeconds} offsetMs={offsetMs} />
            </div>

            <div className="flex flex-col gap-gutter h-full">
              <div className="bg-surface-container-lowest rounded-lg border border-outline card-shadow p-stack-md flex-shrink-0">
                <h4 className="font-label-md text-label-md text-on-surface-variant mb-2 flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-tertiary text-[16px] filled">how_to_reg</span>
                  Attendance Status
                </h4>
                <div className="flex items-baseline gap-2">
                  <span className="font-display-lg text-display-lg text-tertiary" aria-live="polite">{presentCount}</span>
                  <span className="font-headline-md text-headline-md text-on-surface-variant">/ {totalEnrolled}</span>
                </div>
                <div className="mt-4 w-full bg-surface-dim rounded-md h-3 overflow-hidden clay-recessed">
                  <div className="bg-tertiary h-full" style={{ width: `${percent}%` }} />
                </div>
                <p className="font-label-sm text-label-sm text-tertiary mt-2 text-right font-semibold">{percent}% Present</p>
              </div>

              <div className="bg-surface rounded-lg border border-outline card-shadow p-stack-md flex-1 flex flex-col min-h-[200px]">
                <div className="flex justify-between items-center mb-stack-sm">
                  <h4 className="font-label-md text-label-md text-on-surface-variant">Live Feed</h4>
                  <span className="flex h-2 w-2 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
                  </span>
                </div>
                <div className="flex-1 overflow-y-auto space-y-2 pr-2 custom-scrollbar max-h-72 lg:max-h-none">
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
                {actionError && (
                  <p className="font-label-sm text-label-sm text-error px-1" role="alert">
                    {actionError}
                  </p>
                )}
                <button
                  onClick={handleStop}
                  disabled={stopping}
                  className={`w-full min-h-11 flex items-center justify-center gap-2 py-2.5 rounded-lg font-label-md text-label-md transition-colors shadow-sm disabled:opacity-60 ${
                    confirmStop ? "bg-error text-on-error ring-4 ring-error/30" : "bg-error text-on-error hover:bg-error/90"
                  }`}
                >
                  <span className="material-symbols-outlined text-sm filled">stop_circle</span>
                  {stopping ? "Stopping..." : confirmStop ? "Tap again to confirm" : "Stop Session"}
                </button>
                <button
                  onClick={openManualEntry}
                  className="min-h-11 flex items-center justify-center gap-1 bg-surface-container text-on-surface py-2 rounded-lg font-label-sm text-label-sm border border-outline-variant hover:bg-surface-container-high transition-colors"
                >
                  <span className="material-symbols-outlined text-[16px]">edit_note</span>
                  Manual Entry
                </button>
                <button
                  onClick={() => setShowVerification(true)}
                  className="min-h-11 flex items-center justify-center gap-1 bg-surface-container text-on-surface py-2 rounded-lg font-label-sm text-label-sm border border-outline-variant hover:bg-surface-container-high transition-colors"
                >
                  <span className="material-symbols-outlined text-[16px]">photo_camera</span>
                  Verify Classroom
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {showManual && (
        <ManualEntryModal students={rosterStudents} onClose={() => setShowManual(false)} onSubmit={submitManual} />
      )}
      {showVerification && info && (
        <ClassroomVerificationModal
          sessionId={sessionId}
          subjectLabel={`${info.subject}${info.division ? ` (${info.division})` : ""}`}
          onClose={() => setShowVerification(false)}
        />
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
