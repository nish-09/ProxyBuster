"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ApiError, AUTH_EXPIRED_EVENT, authApi, getToken, setToken, type MeResponse, type RegisterRequest } from "@/lib/api";

interface AuthContextValue {
  user: MeResponse | null;
  loading: boolean;
  /** Set when the session could not be verified for a NON-auth reason (offline, server down).
   * The stored token is kept in that case — the user is not logged out. */
  authError: string | null;
  login: (email: string, password: string, deviceId?: string) => Promise<MeResponse>;
  register: (payload: RegisterRequest) => Promise<MeResponse>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const SESSION_ENDED_FLAG = "pb_session_ended";

function deviceId(): string {
  if (typeof window === "undefined") return "server";
  const key = "pb_device_id";
  let id = window.localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    window.localStorage.setItem(key, id);
  }
  return id;
}

function flagSessionEnded() {
  try {
    window.sessionStorage.setItem(SESSION_ENDED_FLAG, "1");
  } catch {
    /* storage unavailable (private mode) — the login page simply won't show the note */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const router = useRouter();

  const refresh = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setUser(null);
      setAuthError(null);
      setLoading(false);
      return;
    }
    try {
      const me = await authApi.me();
      setUser(me);
      setAuthError(null);
    } catch (err) {
      if (err instanceof ApiError && err.isAuthFailure) {
        // Genuinely invalid/expired/revoked session.
        setToken(null);
        setUser(null);
        setAuthError(null);
      } else {
        // Offline, timeout, 5xx: keep the session and let the user retry.
        setAuthError(err instanceof ApiError ? err.message : "Can't reach the server. Check your connection and try again.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional fetch-on-mount session rehydration
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Any authenticated request that comes back 401 (see lib/api.ts) ends the session here, so
  // route guards redirect to /login instead of leaving a dead UI on screen.
  useEffect(() => {
    const onExpired = () => {
      flagSessionEnded();
      setUser(null);
    };
    // Logging out (or being revoked) in another tab must log this tab out too.
    const onStorage = (e: StorageEvent) => {
      if (e.key === "pb_token" && !e.newValue) setUser(null);
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const login = useCallback(async (email: string, password: string, explicitDeviceId?: string) => {
    const res = await authApi.login(email, password, explicitDeviceId ?? deviceId());
    setToken(res.access_token);
    try {
      const me = await authApi.me();
      setUser(me);
      setAuthError(null);
      return me;
    } catch (err) {
      setToken(null);
      throw err;
    }
  }, []);

  const register = useCallback(async (payload: RegisterRequest) => {
    const me = await authApi.register(payload);
    return me;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // The server may be unreachable or the session already gone; either way this device is
      // done. (If the server was unreachable the token simply expires on its own.)
    } finally {
      setToken(null);
      setUser(null);
      router.push("/login");
    }
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, loading, authError, login, register, logout, refresh }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
