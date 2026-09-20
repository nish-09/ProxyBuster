"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { RequireRole } from "@/components/route-guard";
import { SideNavBar } from "@/components/layout/SideNavBar";
import { TopNavBar, DesktopTopBar } from "@/components/layout/TopNavBar";
import { BottomMobileNav } from "@/components/layout/BottomMobileNav";
import { useAuth } from "@/lib/auth-context";
import { professorApi, type CooldownListItem } from "@/lib/api";

function initials(name: string) {
  return name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

/** No dedicated Stitch screen exists for the Cooldown Monitor (linked from SideNavBar/BottomMobileNav) —
 * built with the same Card/list visual language as the rest of the professor console. */
function CooldownsContent() {
  const { user } = useAuth();
  const [items, setItems] = useState<CooldownListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    professorApi
      .cooldowns()
      .then(setItems)
      .catch(() => setError("Could not load cooldowns."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="bg-background text-on-background font-body-md antialiased flex min-h-screen">
      <SideNavBar role="professor" />
      <main className="flex-1 min-w-0 md:ml-[280px] min-h-screen bg-surface-container-low flex flex-col">
        <TopNavBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
        <div className="flex-1 p-container-padding max-w-4xl mx-auto w-full flex flex-col gap-gutter pb-24">
          <div className="flex items-end justify-between gap-gutter">
            <div>
              <h2 className="font-headline-lg text-headline-lg text-on-surface mb-1 flex items-center gap-2">
                <span className="material-symbols-outlined text-primary">timer</span>
                Cooldown Monitor
              </h2>
              <p className="font-body-md text-body-md text-on-surface-variant">
                Students currently locked out after a manual logout (60-minute security window).
              </p>
            </div>
            <DesktopTopBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
          </div>

          <div className="bg-surface-container-lowest border border-outline-variant rounded-xl shadow-sm overflow-hidden">
            {loading ? (
              <div className="p-8 text-center font-body-md text-body-md text-on-surface-variant">Loading...</div>
            ) : error ? (
              <div className="p-8 text-center font-body-md text-body-md text-error">{error}</div>
            ) : items.length === 0 ? (
              <div className="p-8 text-center font-body-md text-body-md text-on-surface-variant">No students are currently on cooldown.</div>
            ) : (
              <div className="divide-y divide-surface-variant">
                {items.map((item) => (
                  <Link
                    key={item.student_id}
                    href={`/professor/students/${item.student_id}`}
                    className="flex items-center gap-4 p-4 hover:bg-surface-container-low transition-colors"
                  >
                    <div className="w-10 h-10 rounded-full bg-tertiary-container text-on-tertiary-container flex items-center justify-center font-label-md">
                      {initials(item.full_name)}
                    </div>
                    <div className="flex-1">
                      <div className="font-medium text-on-surface">{item.full_name}</div>
                      <div className="font-label-sm text-outline">Roll: {item.roll_number} • {item.reason.replace(/_/g, " ")}</div>
                    </div>
                    <div className="text-right">
                      <div className="font-label-md text-label-md text-primary font-bold">
                        {Math.ceil(item.remaining_seconds / 60)} min remaining
                      </div>
                      <div className="font-label-sm text-label-sm text-outline">Until {new Date(item.expires_at).toLocaleTimeString()}</div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
      <BottomMobileNav role="professor" />
    </div>
  );
}

export default function ProfessorCooldownsPage() {
  return (
    <RequireRole role="professor">
      <CooldownsContent />
    </RequireRole>
  );
}
