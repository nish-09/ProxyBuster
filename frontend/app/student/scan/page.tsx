"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { RequireRole } from "@/components/route-guard";
import { attendanceApi, studentApi, ApiError } from "@/lib/api";

type ToastState = { kind: "success" | "cooldown" | "error"; title: string; subtitle?: string } | null;

function ScannerContent() {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const scannerRef = useRef<import("html5-qrcode").Html5Qrcode | null>(null);
  const camerasRef = useRef<{ id: string; label: string }[]>([]);
  const cameraIndexRef = useRef(0);
  const processingRef = useRef(false);

  const [checkingCooldown, setCheckingCooldown] = useState(true);
  const [toast, setToast] = useState<ToastState>(null);
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
            showToast({ kind: "success", title: "Attendance Marked", subtitle: result.message });
            try {
              await scanner.stop();
            } catch {
              /* ignore */
            }
            setScanning(false);
          } catch (err) {
            if (err instanceof ApiError) {
              if (err.status === 423) {
                showToast({
                  kind: "cooldown",
                  title: "Cooldown Active",
                  subtitle: err.remainingSeconds !== undefined ? `${Math.ceil(err.remainingSeconds / 60)} min remaining` : undefined,
                });
              } else if (err.status === 409) {
                showToast({ kind: "error", title: "Already marked", subtitle: err.message });
              } else if (err.status === 410) {
                showToast({ kind: "error", title: "QR expired — rescan", subtitle: undefined });
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
  }, [showToast]);

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
        <span className="material-symbols-outlined animate-spin text-inverse-primary text-4xl">progress_activity</span>
      </main>
    );
  }

  return (
    <div className="bg-inverse-surface min-h-screen text-on-surface flex flex-col md:flex-row m-0 p-0 overflow-hidden">
      <header className="hidden md:flex justify-between items-center w-full px-container-padding h-16 backdrop-blur-md bg-inverse-surface/80 border-b border-outline sticky top-0 z-40">
        <span className="font-headline-md text-headline-md font-extrabold text-inverse-primary">Proxy Busters</span>
        <span className="font-label-md text-label-md text-inverse-primary">Scanner</span>
      </header>
      <header className="md:hidden flex justify-between items-center p-4 bg-inverse-surface border-b border-outline">
        <button onClick={() => router.back()} className="material-symbols-outlined text-inverse-primary">
          arrow_back
        </button>
        <span className="font-headline-md text-headline-md font-extrabold text-inverse-primary">Scan Code</span>
        <div className="w-6" />
      </header>

      <main className="flex-1 relative w-full flex flex-col items-center justify-center bg-black/90 min-h-[calc(100vh-64px)]">
        <div className="absolute top-8 left-0 right-0 z-10 flex flex-col items-center justify-center px-6 text-center">
          <div className="bg-inverse-surface/80 backdrop-blur-md rounded-xl p-4 border border-outline max-w-sm w-full">
            <span className="material-symbols-outlined text-inverse-primary mb-2 text-[32px]">qr_code_scanner</span>
            <p className="font-body-md text-body-md text-inverse-on-surface mb-1">Point your camera at the QR code on the professor&apos;s screen.</p>
            <p className="font-label-md text-label-md text-primary-fixed-dim animate-pulse">
              {cameraError ? cameraError : scanning ? "Scanning for Session..." : "Starting camera..."}
            </p>
          </div>
        </div>

        <div className="relative w-[300px] h-[300px] md:w-[400px] md:h-[400px] rounded-xl overflow-hidden shadow-[0_0_40px_rgba(53,37,205,0.2)] bg-black">
          <div id="qr-reader" ref={containerRef} className="absolute inset-0 [&_video]:object-cover [&_video]:w-full [&_video]:h-full" />
          <div className="absolute top-0 left-0 w-12 h-12 border-t-4 border-l-4 border-primary-fixed rounded-tl-xl m-4 pointer-events-none" />
          <div className="absolute top-0 right-0 w-12 h-12 border-t-4 border-r-4 border-primary-fixed rounded-tr-xl m-4 pointer-events-none" />
          <div className="absolute bottom-0 left-0 w-12 h-12 border-b-4 border-l-4 border-primary-fixed rounded-bl-xl m-4 pointer-events-none" />
          <div className="absolute bottom-0 right-0 w-12 h-12 border-b-4 border-r-4 border-primary-fixed rounded-br-xl m-4 pointer-events-none" />
          {scanning && <div className="scanner-line z-20" />}
        </div>

        <div className="absolute bottom-24 md:bottom-8 left-0 right-0 z-10 flex justify-center gap-6 px-4">
          <button
            aria-label="Toggle Flashlight"
            onClick={toggleFlashlight}
            disabled={!torchSupported}
            className="bg-inverse-surface/80 backdrop-blur-md rounded-full w-14 h-14 flex items-center justify-center border border-outline text-inverse-on-surface hover:bg-surface-variant transition-colors disabled:opacity-30"
          >
            <span className="material-symbols-outlined">{torchOn ? "flashlight_on" : "flashlight_off"}</span>
          </button>
          <button
            aria-label="Switch Camera"
            onClick={switchCamera}
            disabled={cameraCount < 2}
            className="bg-inverse-surface/80 backdrop-blur-md rounded-full w-14 h-14 flex items-center justify-center border border-outline text-inverse-on-surface hover:bg-surface-variant transition-colors disabled:opacity-30"
          >
            <span className="material-symbols-outlined">flip_camera_ios</span>
          </button>
        </div>

        {toast && (
          <div
            className={`absolute bottom-40 md:bottom-24 left-1/2 -translate-x-1/2 px-6 py-3 rounded-lg shadow-lg border flex items-center gap-3 z-50 toast-enter ${
              toast.kind === "success"
                ? "bg-surface text-on-surface border-outline-variant"
                : toast.kind === "cooldown"
                  ? "bg-error-container text-on-error-container border-error/20"
                  : "bg-error-container text-on-error-container border-error/20"
            }`}
          >
            <span className="material-symbols-outlined filled">
              {toast.kind === "success" ? "check_circle" : toast.kind === "cooldown" ? "timer" : "error"}
            </span>
            <div>
              <p className="font-body-md text-body-md font-semibold">{toast.title}</p>
              {toast.subtitle && <p className="font-label-sm text-label-sm opacity-80">{toast.subtitle}</p>}
            </div>
            {!scanning && toast.kind !== "success" && (
              <button onClick={retry} className="ml-2 font-label-md text-label-md underline">
                Retry
              </button>
            )}
          </div>
        )}

        {toast?.kind === "success" && (
          <button
            onClick={() => router.push("/student/dashboard")}
            className="absolute bottom-8 md:bottom-4 z-50 px-6 py-2 rounded-lg bg-primary text-on-primary font-label-md text-label-md"
          >
            Back to Dashboard
          </button>
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
