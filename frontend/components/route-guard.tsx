"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import type { UserRole } from "@/lib/api";

export function RequireRole({ role, children }: { role: UserRole; children: React.ReactNode }) {
  const { user, loading, authError, refresh } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      // A transient failure to verify the session is NOT a reason to sign the user out.
      if (authError) return;
      router.replace("/login");
      return;
    }
    if (user.role !== role) {
      router.replace(
        user.role === "student" ? "/student/dashboard" : user.role === "admin" ? "/admin/dashboard" : "/professor/dashboard"
      );
    }
  }, [loading, user, authError, role, router]);

  if (!loading && !user && authError) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-surface p-container-padding text-center">
        <span className="material-symbols-outlined text-error text-5xl">cloud_off</span>
        <p className="font-body-md text-body-md text-on-surface max-w-sm">{authError}</p>
        <button
          onClick={() => {
            void refresh();
          }}
          className="h-11 px-6 rounded-lg bg-primary text-on-primary font-label-md text-label-md"
        >
          Try again
        </button>
      </div>
    );
  }

  if (loading || !user || user.role !== role) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-surface" role="status" aria-label="Loading">
        <span className="material-symbols-outlined animate-spin text-primary text-4xl">progress_activity</span>
      </div>
    );
  }

  return <>{children}</>;
}
