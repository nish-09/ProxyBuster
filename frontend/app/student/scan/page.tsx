"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { RequireRole } from "@/components/route-guard";
import { attendanceApi, studentApi, ApiError, type ScanResult } from "@/lib/api";

type ToastState = { kind: "error"; title: string; subtitle?: string } | null;

function formatMarkedAt(iso: string | null) {
  if (!iso) return { date: "", time: "" };
  const d = new Date(iso);
  return {
    date: d.toLocaleDateString([], { day: "numeric", month: "long", year: "numeric" }),
    time: d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
  };
}

function ScannerContent() {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const scannerRef = useRef<import("html5-qrcode").Html5Qrcode | null>(null);
  const camerasRef = useRef<{ id: string; label: string }[]>([]);
  const cameraIndexRef = useRef(0);
  const processingRef = useRef(false);

  const [checkingCooldown, setCheckingCooldown] = useState(true);
  const [toast, setToast] = useState<ToastState>(null);
  const [successResult, setSuccessResult] = useState<ScanResult | null>(null);
  const [torchOn, setTorchOn] = useState(false);
  const [torchSupported, setTorchSupported] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [cameraCount, setCameraCount] = useState(0);

  const showToast = useCallback((t: ToastState, durationMs = 3500) => {
    setToast(t);
    if (t) window.setTimeout(() => setToast((cur) => (cur === t ? null : cur)), durationMs);
  }, []);

  const startCamera = useCallback(async (cameraId: string) => {
    const { Html5Qrcode } = await import("html5-qrcode");
    if (!containerRef.current) return;
    if (!scannerRef.current) {
      scannerRef.current = new Html5Qrcode("qr-reader");
    }
    const scanner = scannerRef.current;
    try {
      await scanner.start(
        cameraId,
        { fps: 10, qrbox: { width: 250, height: 250 } },
        async (decodedText) => {
          if (processingRef.current) return;
          processingRef.current = true;
          try {
            await scanner.pause(true);
          } catch {
            /* ignore */
          }
          try {
            const result = await attendanceApi.scan(decodedText);
            try {
              await scanner.stop();
            } catch {
              /* ignore */
            }
            setScanning(false);
            setSuccessResult(result);
          } catch (err) {
            if (err instanceof ApiError) {
              if (err.status === 423) {
                // Cooldown is server-enforced (see settings.scan_cooldown_seconds) — hand off
                // to the dedicated cooldown screen, which fetches the authoritative remaining
                // time from the server rather than trusting a client-guessed duration.
                router.replace("/student/cooldown");
                return;
              } else if (err.status === 409) {
                showToast({ kind: "error", title: "Already marked", subtitle: err.message });
              } else if (err.status === 410) {
                // Both an expired 10s QR rotation and an expired attendance session return 410;
                // the backend's message text (see attendance_service) tells them apart.
                if (/session/i.test(err.message)) {
                  showToast({ kind: "error", title: "Attendance session has expired", subtitle: "Ask your professor to start a new session." });
                } else {
                  showToast({ kind: "error", title: "QR expired — rescan", subtitle: undefined });
                }
              } else if (err.status === 403) {
                showToast({ kind: "error", title: "Not enrolled in this class" });
              } else {
                showToast({ kind: "error", title: "Scan failed", subtitle: err.message });
              }
            } else {
              showToast({ kind: "error", title: "Scan failed. Try again." });
            }
            try {
              await scanner.resume();
            } catch {
              /* ignore */
            }
          } finally {
            processingRef.current = false;
          }
        },
        () => {
          /* per-frame decode failure — expected while no QR is in view, ignore */
        }
      );
      setScanning(true);
      setCameraError(null);
      try {
        const capabilities = scanner.getRunningTrackCapabilities();
        setTorchSupported(Boolean((capabilities as unknown as { torch?: boolean }).torch));
      } catch {
        setTorchSupported(false);
      }
    } catch (err) {
      setCameraError(err instanceof Error ? err.message : "Unable to access camera.");
    }
  }, [showToast, router]);

  useEffect(() => {
    let cancelled = false;
    studentApi
      .cooldown()
      .then((status) => {
        if (cancelled) return;
        if (status.active) {
          router.replace("/student/cooldown");
          return;
        }
        setCheckingCooldown(false);
      })
      .catch(() => {
        if (!cancelled) setCheckingCooldown(false);
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  useEffect(() => {
    if (checkingCooldown) return;
    let cancelled = false;

    (async () => {
      try {
        const { Html5Qrcode } = await import("html5-qrcode");
        const cameras = await Html5Qrcode.getCameras();
        if (cancelled) return;
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
        if (!cancelled) setCameraError(err instanceof Error ? err.message : "Camera permission denied.");
      }
    })();

    return () => {
      cancelled = true;
      const scanner = scannerRef.current;
      if (scanner) {
        scanner.stop().catch(() => {}).finally(() => {
          scanner.clear();
        });
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkingCooldown]);

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
    if (cameras.length < 2 || !scannerRef.current) return;
    try {
      await scannerRef.current.stop();
    } catch {
      /* ignore */
    }
    cameraIndexRef.current = (cameraIndexRef.current + 1) % cameras.length;
    await startCamera(cameras[cameraIndexRef.current].id);
  }, [startCamera]);

  const retry = useCallback(async () => {
    setToast(null);
    if (!scanning && camerasRef.current.length > 0) {
      await startCamera(camerasRef.current[cameraIndexRef.current].id);
    }
  }, [scanning, startCamera]);

  if (checkingCooldown) {
    return (
      <main className="flex-1 relative w-full h-screen flex items-center justify-center bg-black/90">
        <span className="material-symbols-outlined animate-spin text-tertiary text-4xl">progress_activity</span>
      </main>
    );
  }

  if (successResult) {
    const { date, time } = formatMarkedAt(successResult.marked_at);
    return (
      <main className="flex-1 w-full min-h-screen flex items-center justify-center bg-surface p-container-padding">
        <div className="w-full max-w-md bg-surface-container-lowest rounded-xl clay-glow-green p-stack-lg flex flex-col items-center text-center">
          <div className="w-16 h-16 rounded-full bg-tertiary-container flex items-center justify-center mb-stack-md clay-glow-green animate-clay-pop">
            <span className="material-symbols-outlined filled text-on-tertiary-container" style={{ fontSize: 36 }}>
              check_circle
            </span>
          </div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">Attendance Marked Successfully</h1>
          <p className="font-body-md text-body-md text-on-surface-variant mb-stack-lg">{successResult.message}</p>

          <div className="w-full bg-surface-container border border-outline-variant rounded-md divide-y divide-outline-variant text-left">
            {successResult.subject_name && (
              <div className="flex justify-between items-center px-4 py-3">
                <span className="font-label-md text-label-md text-on-surface-variant">Subject</span>
                <span className="font-body-md text-body-md font-semibold text-on-surface">
                  {successResult.subject_name}
                  {successResult.division_name ? ` (${successResult.division_name})` : ""}
                </span>
              </div>
            )}
            {date && (
              <div className="flex justify-between items-center px-4 py-3">
                <span className="font-label-md text-label-md text-on-surface-variant">Date</span>
                <span className="font-body-md text-body-md font-semibold text-on-surface">{date}</span>
              </div>
            )}
            {time && (
              <div className="flex justify-between items-center px-4 py-3">
                <span className="font-label-md text-label-md text-on-surface-variant">Time</span>
                <span className="font-body-md text-body-md font-semibold text-on-surface">{time}</span>
              </div>
            )}
            <div className="flex justify-between items-center px-4 py-3">
              <span className="font-label-md text-label-md text-on-surface-variant">Status</span>
              <span className="font-body-md text-body-md font-semibold text-tertiary capitalize">
                {successResult.attendance_status ?? "Present"}
              </span>
            </div>
            {successResult.session_topic && (
              <div className="flex justify-between items-center px-4 py-3">
                <span className="font-label-md text-label-md text-on-surface-variant">Session</span>
                <span className="font-body-md text-body-md font-semibold text-on-surface">{successResult.session_topic}</span>
              </div>
            )}
          </div>

          <button
            onClick={() => router.push("/student/dashboard")}
            className="mt-stack-lg w-full px-6 py-3 rounded-lg bg-primary text-on-primary font-label-md text-label-md hover:bg-primary/90 transition-colors"
          >
            Back to Dashboard
          </button>
        </div>
      </main>
    );
  }

  return (
    <div className="bg-surface min-h-screen text-on-surface flex flex-col md:flex-row m-0 p-0 overflow-hidden">
      <header className="hidden md:flex justify-between items-center w-full px-container-padding h-16 bg-surface border-b border-outline sticky top-0 z-40">
        <span className="font-headline-md text-headline-md font-bold text-on-surface">Proxy Busters</span>
        <span className="font-label-md text-label-md text-on-surface-variant">Scanner</span>
      </header>
      <header className="md:hidden flex justify-between items-center p-4 bg-surface border-b border-outline">
        <button onClick={() => router.back()} className="material-symbols-outlined text-on-surface">
          arrow_back
        </button>
        <span className="font-headline-md text-headline-md font-bold text-on-surface">Scan Code</span>
        <div className="w-6" />
      </header>

      <main className="flex-1 relative w-full flex flex-col items-center justify-center bg-black min-h-[calc(100vh-64px)]">
        <div className="absolute top-8 left-0 right-0 z-10 flex flex-col items-center justify-center px-6 text-center">
          <div className="bg-surface/90 backdrop-blur-sm rounded-xl p-4 border border-outline card-shadow max-w-sm w-full">
            <span className="material-symbols-outlined text-tertiary mb-2 text-[32px]">qr_code_scanner</span>
            <p className="font-body-md text-body-md text-on-surface mb-1">Point your camera at the QR code on the professor&apos;s screen.</p>
            <p className="font-label-md text-label-md text-tertiary animate-pulse">
              {cameraError ? cameraError : scanning ? "Scanning for Session..." : "Starting camera..."}
            </p>
          </div>
        </div>

        <div className="relative w-[300px] h-[300px] md:w-[400px] md:h-[400px] rounded-xl overflow-hidden bg-black border-4 border-surface shadow-[0_16px_40px_rgba(0,0,0,0.45),0_0_16px_rgba(59,130,246,0.15)]">
          <div id="qr-reader" ref={containerRef} className="absolute inset-0 [&_video]:object-cover [&_video]:w-full [&_video]:h-full" />
          <div className="absolute top-0 left-0 w-12 h-12 border-t-4 border-l-4 border-tertiary rounded-tl-xl m-4 pointer-events-none" />
          <div className="absolute top-0 right-0 w-12 h-12 border-t-4 border-r-4 border-tertiary rounded-tr-xl m-4 pointer-events-none" />
          <div className="absolute bottom-0 left-0 w-12 h-12 border-b-4 border-l-4 border-tertiary rounded-bl-xl m-4 pointer-events-none" />
          <div className="absolute bottom-0 right-0 w-12 h-12 border-b-4 border-r-4 border-tertiary rounded-br-xl m-4 pointer-events-none" />
          {scanning && <div className="scanner-line z-20" />}
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

        {toast && (
          <div className="absolute bottom-40 md:bottom-24 left-1/2 -translate-x-1/2 px-6 py-3 rounded-lg shadow-lg border flex items-center gap-3 z-50 toast-enter bg-error-container text-on-error-container border-error/20">
            <span className="material-symbols-outlined filled">error</span>
            <div>
              <p className="font-body-md text-body-md font-semibold">{toast.title}</p>
              {toast.subtitle && <p className="font-label-sm text-label-sm opacity-80">{toast.subtitle}</p>}
            </div>
            {!scanning && (
              <button onClick={retry} className="ml-2 font-label-md text-label-md underline">
                Retry
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
