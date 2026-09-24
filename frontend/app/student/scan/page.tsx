"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { RequireRole } from "@/components/route-guard";
import { attendanceApi, studentApi, ApiError } from "@/lib/api";
import { cacheScanResult } from "@/lib/scan-cache";

/**
 * Explicit scanner state machine. Every state has a way out, so the UI can never sit in one
 * forever:
 *   IDLE        checking status / starting the camera (or camera unavailable — has "Try again")
 *   SCANNING    camera live, waiting for a QR
 *   VALIDATING  a QR was decoded; sanity-checking its shape locally
 *   MARKING     request in flight (has a hard deadline in lib/api.ts, cancelled on leave)
 *   SUCCESS     attendance marked -> navigates to the dedicated success screen
 *   ERROR       recoverable problem; returns to SCANNING by itself after a short delay
 *   COOLDOWN    server says the student is in cooldown -> navigates to the cooldown screen
 *   EXPIRED     the attendance session itself is over; user must choose to scan again
 */
type ScanState = "IDLE" | "SCANNING" | "VALIDATING" | "MARKING" | "SUCCESS" | "ERROR" | "COOLDOWN" | "EXPIRED";

interface Notice {
  title: string;
  subtitle?: string;
}

// Same code submitted again within this window is ignored client-side: the camera re-decodes the
// same QR ~10x/second, and re-sending a code the server just rejected only earns 429s.
const SAME_CODE_IGNORE_MS = 4000;
const ERROR_AUTO_RESUME_MS = 2500;
const QR_USED_RESUME_MS = 1200;

/** Attendance QRs are base64url("session.nonce.issued.expires.signature"). Cheap local filter so a
 * random poster/website QR never costs a network round trip. */
function looksLikeAttendanceQr(text: string): boolean {
  try {
    const decoded = atob(text.replace(/-/g, "+").replace(/_/g, "/"));
    return decoded.split(".").length === 5;
  } catch {
    return false;
  }
}

function describeCameraError(err: unknown): string {
  const name = err instanceof Error ? err.name : "";
  const message = err instanceof Error ? err.message : String(err ?? "");
  if (name === "NotAllowedError" || /permission|denied/i.test(message)) {
    return "Camera access is blocked. Allow camera permission for this site in your browser settings, then tap Try again.";
  }
  if (name === "NotFoundError" || /no camera/i.test(message)) return "No camera found on this device.";
  if (name === "NotReadableError") return "The camera is being used by another app. Close it and tap Try again.";
  if (!window.isSecureContext) return "The camera needs a secure (https) connection.";
  return "Unable to start the camera. Tap Try again.";
}

function ScannerContent() {
  const router = useRouter();
  const scannerRef = useRef<import("html5-qrcode").Html5Qrcode | null>(null);
  const camerasRef = useRef<{ id: string; label: string }[]>([]);
  const cameraIndexRef = useRef(0);
  const mountedRef = useRef(true);
  const stateRef = useRef<ScanState>("IDLE");
  const abortRef = useRef<AbortController | null>(null);
  const resumeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rejectedRef = useRef<{ text: string; until: number } | null>(null);

  const [state, setStateValue] = useState<ScanState>("IDLE");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [torchOn, setTorchOn] = useState(false);
  const [torchSupported, setTorchSupported] = useState(false);
  const [cameraCount, setCameraCount] = useState(0);

  const setState = useCallback((next: ScanState) => {
    stateRef.current = next;
    setStateValue(next);
  }, []);

  const clearResumeTimer = useCallback(() => {
    if (resumeTimerRef.current) {
      clearTimeout(resumeTimerRef.current);
      resumeTimerRef.current = null;
    }
  }, []);

  const stopCamera = useCallback(async () => {
    const scanner = scannerRef.current;
    scannerRef.current = null;
    if (!scanner) return;
    try {
      if (scanner.isScanning) await scanner.stop(); // releases the MediaStream tracks
    } catch {
      /* already stopped */
    }
    try {
      scanner.clear();
    } catch {
      /* element already gone */
    }
    setTorchOn(false);
    setTorchSupported(false);
  }, []);

  /** Recoverable failure: show why, remember the code so it isn't re-sent, resume scanning soon. */
  const softFail = useCallback(
    (text: string, next: Notice, resumeMs = ERROR_AUTO_RESUME_MS) => {
      rejectedRef.current = { text, until: Date.now() + SAME_CODE_IGNORE_MS };
      setNotice(next);
      setState("ERROR");
      clearResumeTimer();
      resumeTimerRef.current = setTimeout(() => {
        if (!mountedRef.current || stateRef.current !== "ERROR") return;
        setNotice(null);
        setState("SCANNING");
      }, resumeMs);
    },
    [clearResumeTimer, setState]
  );

  const handleDecoded = useCallback(
    async (text: string) => {
      if (stateRef.current !== "SCANNING") return; // one attempt at a time
      const rejected = rejectedRef.current;
      if (rejected && rejected.text === text && Date.now() < rejected.until) return;

      setState("VALIDATING");
      if (!looksLikeAttendanceQr(text)) {
        softFail(text, { title: "That isn't an attendance QR code", subtitle: "Point the camera at the code on your professor's screen." });
        return;
      }

      setState("MARKING");
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const result = await attendanceApi.scan(text, controller.signal);
        if (!mountedRef.current) return;
        setState("SUCCESS");
        cacheScanResult(result);
        await stopCamera();
        router.replace("/student/scan/success");
      } catch (err) {
        if (!mountedRef.current || controller.signal.aborted) return;
        if (!(err instanceof ApiError)) {
          softFail(text, { title: "Something went wrong. Try again." });
          return;
        }
        switch (err.code ?? String(err.status)) {
          case "attendance_restricted":
            setState("COOLDOWN");
            await stopCamera();
            router.replace("/student/restricted");
            return;
          case "cooldown":
          case "423":
            setState("COOLDOWN");
            await stopCamera();
            // The cooldown screen reads the authoritative remaining time from the server.
            router.replace("/student/cooldown");
            return;
          case "already_marked":
            // Nothing to fix — the record exists. Show it (the success screen reads it from the DB).
            setState("SUCCESS");
            await stopCamera();
            router.replace("/student/scan/success");
            return;
          case "qr_used":
            softFail(text, { title: "That code was just used", subtitle: "Hold steady — scanning the new one…" }, QR_USED_RESUME_MS);
            return;
          case "qr_expired":
            softFail(text, { title: "QR expired", subtitle: "Scan the code currently on the screen." });
            return;
          case "invalid_qr":
            softFail(text, { title: "Not a valid attendance QR code" });
            return;
          case "not_enrolled":
            softFail(text, { title: "You're not enrolled in this class", subtitle: "Check with your college admin." }, 4000);
            return;
          case "session_expired":
          case "session_closed":
            clearResumeTimer();
            setNotice({
              title: err.code === "session_closed" ? "Attendance has been closed" : "Attendance session has expired",
              subtitle: "Ask your professor to start a new session.",
            });
            setState("EXPIRED");
            return;
          case "429":
            softFail(text, { title: "Too many attempts", subtitle: "Wait a few seconds and try again." }, 4000);
            return;
          default:
            softFail(text, {
              title: err.status === 0 ? "Connection problem" : "Unable to mark attendance right now",
              subtitle: err.status === 0 || err.status >= 500 ? "Please try again." : err.message,
            });
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [clearResumeTimer, router, setState, softFail, stopCamera]
  );

  const startCamera = useCallback(
    async (cameraId: string) => {
      const { Html5Qrcode } = await import("html5-qrcode");
      if (!mountedRef.current) return;
      await stopCamera();
      const scanner = new Html5Qrcode("qr-reader");
      scannerRef.current = scanner;
      try {
        await scanner.start(
          cameraId,
          { fps: 10, qrbox: { width: 250, height: 250 } },
          (decodedText) => {
            void handleDecoded(decodedText);
          },
          () => {
            /* per-frame decode failure — expected while no QR is in view */
          }
        );
        if (!mountedRef.current) {
          // Left the page while the camera was still starting: release it right away.
          await stopCamera();
          return;
        }
        setCameraError(null);
        if (stateRef.current === "IDLE") setState("SCANNING");
        try {
          const capabilities = scanner.getRunningTrackCapabilities();
          setTorchSupported(Boolean((capabilities as unknown as { torch?: boolean }).torch));
        } catch {
          setTorchSupported(false);
        }
      } catch (err) {
        if (mountedRef.current) {
          setCameraError(describeCameraError(err));
          setState("IDLE");
        }
      }
    },
    [handleDecoded, setState, stopCamera]
  );

  const initCamera = useCallback(async () => {
    setCameraError(null);
    setState("IDLE");
    try {
      const { Html5Qrcode } = await import("html5-qrcode");
      const cameras = await Html5Qrcode.getCameras(); // triggers the permission prompt
      if (!mountedRef.current) return;
      camerasRef.current = cameras;
      setCameraCount(cameras.length);
      if (cameras.length === 0) {
        setCameraError("No camera found on this device.");
        return;
      }
      const backIndex = cameras.findIndex((c) => /back|rear|environment/i.test(c.label));
      cameraIndexRef.current = backIndex >= 0 ? backIndex : 0;
      await startCamera(cameras[cameraIndexRef.current].id);
    } catch (err) {
      if (mountedRef.current) setCameraError(describeCameraError(err));
    }
  }, [setState, startCamera]);

  // Gate on the server-side cooldown, then bring the camera up. Everything is torn down on leave.
  useEffect(() => {
    mountedRef.current = true;
    let cancelled = false;

    (async () => {
      try {
        const restriction = await studentApi.restriction();
        if (cancelled) return;
        if (restriction.active) {
          router.replace("/student/restricted");
          return;
        }
      } catch {
        // Can't check: continue. The server enforces the restriction on the scan itself anyway.
      }
      try {
        const status = await studentApi.cooldown();
        if (cancelled) return;
        if (status.active) {
          router.replace("/student/cooldown");
          return;
        }
      } catch {
        // Can't check: continue. The server enforces the cooldown on the scan itself anyway.
      }
      if (!cancelled) await initCamera();
    })();

    // Don't keep the camera open while the tab is in the background.
    const onVisibility = () => {
      if (document.hidden) {
        if (stateRef.current === "SCANNING" || stateRef.current === "ERROR") {
          clearResumeTimer();
          void stopCamera().then(() => {
            if (mountedRef.current) setState("IDLE");
          });
        }
      } else if (mountedRef.current && stateRef.current === "IDLE" && !cancelled && camerasRef.current.length > 0) {
        void startCamera(camerasRef.current[cameraIndexRef.current].id);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      mountedRef.current = false;
      document.removeEventListener("visibilitychange", onVisibility);
      abortRef.current?.abort(); // cancel any in-flight scan request
      clearResumeTimer();
      void stopCamera();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleFlashlight = useCallback(async () => {
    const scanner = scannerRef.current;
    if (!scanner) return;
    try {
      await scanner.applyVideoConstraints({ advanced: [{ torch: !torchOn } as unknown as MediaTrackConstraintSet] });
      setTorchOn((v) => !v);
    } catch {
      setTorchSupported(false);
    }
  }, [torchOn]);

  const switchCamera = useCallback(async () => {
    const cameras = camerasRef.current;
    if (cameras.length < 2) return;
    cameraIndexRef.current = (cameraIndexRef.current + 1) % cameras.length;
    setState("IDLE");
    await startCamera(cameras[cameraIndexRef.current].id);
  }, [setState, startCamera]);

  const scanAgain = useCallback(() => {
    clearResumeTimer();
    rejectedRef.current = null;
    setNotice(null);
    if (scannerRef.current) setState("SCANNING");
    else void initCamera();
  }, [clearResumeTimer, initCamera, setState]);

  const busy = state === "VALIDATING" || state === "MARKING";
  const statusLine =
    cameraError ??
    (state === "IDLE"
      ? "Starting camera..."
      : state === "SCANNING"
        ? "Scanning for QR code..."
        : busy
          ? "Marking your attendance..."
          : state === "SUCCESS"
            ? "Attendance marked!"
            : state === "COOLDOWN"
              ? "Cooldown active"
              : "Ready when you are");

  return (
    <div className="bg-surface min-h-dvh text-on-surface flex flex-col m-0 p-0 overflow-hidden">
      <header className="hidden md:flex justify-between items-center w-full px-container-padding h-16 bg-surface border-b border-outline sticky top-0 z-40">
        <span className="font-headline-md text-headline-md font-bold text-on-surface">Proxy Busters</span>
        <span className="font-label-md text-label-md text-on-surface-variant">Scanner</span>
      </header>
      <header className="md:hidden flex justify-between items-center p-2 bg-surface border-b border-outline">
        <button
          onClick={() => router.push("/student/dashboard")}
          aria-label="Back to dashboard"
          className="material-symbols-outlined text-on-surface w-11 h-11 flex items-center justify-center"
        >
          arrow_back
        </button>
        <span className="font-headline-md text-headline-md font-bold text-on-surface">Scan Code</span>
        <div className="w-11" />
      </header>

      <main className="flex-1 relative w-full flex flex-col items-center justify-center bg-black min-h-[calc(100dvh-64px)] p-4">
        <div className="absolute top-4 sm:top-8 left-0 right-0 z-10 flex flex-col items-center justify-center px-4 sm:px-6 text-center">
          <div className="bg-surface/90 backdrop-blur-sm rounded-xl p-3 sm:p-4 border border-outline card-shadow max-w-sm w-full">
            <span className="material-symbols-outlined text-tertiary mb-2 text-[32px]">qr_code_scanner</span>
            <p className="font-body-md text-body-md text-on-surface mb-1">Point your camera at the QR code on the professor&apos;s screen.</p>
            <p className={`font-label-md text-label-md ${cameraError ? "text-error" : "text-tertiary animate-pulse"}`} role="status" aria-live="polite">
              {statusLine}
            </p>
            {cameraError && (
              <button
                onClick={() => void initCamera()}
                className="mt-3 h-11 px-5 rounded-lg bg-primary text-on-primary font-label-md text-label-md"
              >
                Try again
              </button>
            )}
          </div>
        </div>

        <div className="relative w-[min(85vw,300px)] h-[min(85vw,300px)] md:w-[400px] md:h-[400px] rounded-xl overflow-hidden bg-black border-4 border-surface shadow-[0_16px_40px_rgba(0,0,0,0.45),0_0_16px_rgba(59,130,246,0.15)]">
          {state === "IDLE" && !cameraError && (
            <div className="absolute inset-0 skeleton-shimmer flex items-center justify-center">
              <span className="material-symbols-outlined text-tertiary text-4xl">qr_code_scanner</span>
            </div>
          )}
          <div id="qr-reader" className="absolute inset-0 [&_video]:object-cover [&_video]:w-full [&_video]:h-full" />
          <div className="absolute top-0 left-0 w-12 h-12 border-t-4 border-l-4 border-tertiary rounded-tl-xl m-4 pointer-events-none" />
          <div className="absolute top-0 right-0 w-12 h-12 border-t-4 border-r-4 border-tertiary rounded-tr-xl m-4 pointer-events-none" />
          <div className="absolute bottom-0 left-0 w-12 h-12 border-b-4 border-l-4 border-tertiary rounded-bl-xl m-4 pointer-events-none" />
          <div className="absolute bottom-0 right-0 w-12 h-12 border-b-4 border-r-4 border-tertiary rounded-br-xl m-4 pointer-events-none" />
          {state === "SCANNING" && <div className="scanner-line z-20" />}
          {busy && (
            <div className="absolute inset-0 z-30 bg-black/55 flex flex-col items-center justify-center gap-2">
              <span className="material-symbols-outlined animate-spin text-on-primary text-4xl">progress_activity</span>
              <span className="font-label-md text-label-md text-on-primary">Marking attendance…</span>
            </div>
          )}
        </div>

        <div className="absolute bottom-24 md:bottom-8 left-0 right-0 z-10 flex justify-center gap-6 px-4">
          <button
            aria-label="Toggle Flashlight"
            onClick={toggleFlashlight}
            disabled={!torchSupported}
            className="bg-surface-container-high rounded-full w-14 h-14 flex items-center justify-center clay-raised text-on-surface hover:bg-surface-container-highest transition-colors disabled:opacity-30"
          >
            <span className="material-symbols-outlined">{torchOn ? "flashlight_on" : "flashlight_off"}</span>
          </button>
          <button
            aria-label="Switch Camera"
            onClick={switchCamera}
            disabled={cameraCount < 2}
            className="bg-surface-container-high rounded-full w-14 h-14 flex items-center justify-center clay-raised text-on-surface hover:bg-surface-container-highest transition-colors disabled:opacity-30"
          >
            <span className="material-symbols-outlined">flip_camera_ios</span>
          </button>
        </div>

        {notice && (state === "ERROR" || state === "EXPIRED") && (
          <div
            role="alert"
            className="absolute bottom-40 md:bottom-24 left-1/2 -translate-x-1/2 w-[min(92vw,26rem)] px-5 py-3 rounded-lg shadow-lg border flex items-center gap-3 z-50 toast-enter bg-error-container text-on-error-container border-error/20"
          >
            <span className="material-symbols-outlined filled">{state === "EXPIRED" ? "timer_off" : "error"}</span>
            <div className="min-w-0 flex-1">
              <p className="font-body-md text-body-md font-semibold">{notice.title}</p>
              {notice.subtitle && <p className="font-label-sm text-label-sm opacity-80">{notice.subtitle}</p>}
            </div>
            {state === "EXPIRED" && (
              <button onClick={scanAgain} className="h-11 px-3 font-label-md text-label-md underline shrink-0">
                Scan again
              </button>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default function StudentScanPage() {
  return (
    <RequireRole role="student">
      <ScannerContent />
    </RequireRole>
  );
}
