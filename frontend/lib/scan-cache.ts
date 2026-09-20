import type { ScanResult } from "@/lib/api";

/**
 * Brief hand-off of the scan response to the success screen so it can paint instantly.
 * It is only a cache: the success screen always re-reads the authoritative record from the
 * server (GET /students/me/last-scan), so nothing here can change or fake the outcome.
 */
const KEY = "pb_last_scan";

export function cacheScanResult(result: ScanResult): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify({ result, cachedAt: Date.now() }));
  } catch {
    /* storage unavailable — the success screen just waits for the server */
  }
}

export function readCachedScanResult(maxAgeMs = 2 * 60_000): ScanResult | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { result: ScanResult; cachedAt: number };
    return Date.now() - parsed.cachedAt <= maxAgeMs ? parsed.result : null;
  } catch {
    return null;
  }
}
