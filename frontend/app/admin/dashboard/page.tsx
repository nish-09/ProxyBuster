"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { RequireRole } from "@/components/route-guard";
import { SideNavBar } from "@/components/layout/SideNavBar";
import { TopNavBar, DesktopTopBar } from "@/components/layout/TopNavBar";
import { BottomMobileNav } from "@/components/layout/BottomMobileNav";
import { useAuth } from "@/lib/auth-context";
import { CardSkeleton } from "@/components/ui/Skeleton";
import { PageError } from "@/components/ui/PageError";
import { adminApi, errorMessage, type AdminSummaryOut } from "@/lib/api";

function initials(name: string) {
  return name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

function DashboardContent() {
  const { user } = useAuth();
  const [counts, setCounts] = useState<AdminSummaryOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setCounts(await adminApi.summary());
    } catch (err) {
      setLoadError(errorMessage(err, "Could not load the dashboard. Please try again."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard fetch-on-mount
    void load();
  }, [load]);

  const tiles = [
    { label: "Students", value: counts?.students, icon: "school", href: "/admin/students" },
    { label: "Professors", value: counts?.professors, icon: "person", href: "/admin/professors" },
    { label: "Subjects", value: counts?.subjects, icon: "menu_book", href: "/admin/subjects" },
    { label: "Class Divisions", value: counts?.divisions, icon: "groups", href: "/admin/divisions" },
  ];

  return (
    <div className="bg-background text-on-background font-body-md antialiased flex min-h-screen">
      <SideNavBar role="admin" />
      <main className="flex-1 min-w-0 md:ml-[280px] min-h-screen bg-surface-container-low">
        <TopNavBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
        <div className="p-container-padding max-w-[1400px] mx-auto space-y-stack-lg pb-24">
          {loadError && <PageError message={loadError} onRetry={() => void load()} />}
          <header className="flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div>
              <h2 className="font-display-lg text-display-lg text-on-surface mb-1">Admin Dashboard</h2>
              <p className="font-body-lg text-body-lg text-on-surface-variant">
                Manage academic data for the pilot{user ? `, ${user.full_name}` : ""}.
              </p>
            </div>
            <DesktopTopBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
          </header>

          <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-gutter">
            {loading
              ? Array.from({ length: 4 }).map((_, i) => <CardSkeleton key={i} />)
              : tiles.map((t) => (
                  <Link
                    key={t.label}
                    href={t.href}
                    className="bg-surface-container-lowest rounded-xl p-5 border border-outline-variant shadow-sm flex flex-col justify-between h-full hover:border-primary transition-colors"
                  >
                    <div className="p-2 bg-primary-container/20 rounded-lg text-primary w-fit mb-4">
                      <span className="material-symbols-outlined">{t.icon}</span>
                    </div>
                    <div>
                      <p className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider mb-1">{t.label}</p>
                      <h3 className="font-display-lg text-display-lg text-on-surface">{t.value}</h3>
                    </div>
                  </Link>
                ))}
          </section>

          <div className="bg-surface-container-lowest rounded-xl border border-outline-variant shadow-sm p-5">
            <h3 className="font-headline-md text-headline-md text-on-surface mb-3">Onboarding checklist</h3>
            <ol className="list-decimal list-inside space-y-2 font-body-md text-body-md text-on-surface-variant">
              <li>Create professor accounts under <Link className="text-primary hover:underline" href="/admin/professors">Professors</Link>.</li>
              <li>Create subjects under <Link className="text-primary hover:underline" href="/admin/subjects">Subjects</Link>.</li>
              <li>Create class divisions and assign a professor under <Link className="text-primary hover:underline" href="/admin/divisions">Divisions</Link>.</li>
              <li>Create student accounts under <Link className="text-primary hover:underline" href="/admin/students">Students</Link>.</li>
              <li>Enroll students into a division from that division&apos;s row on the Divisions page.</li>
              <li>Schedule lectures under <Link className="text-primary hover:underline" href="/admin/lectures">Lectures</Link>.</li>
            </ol>
          </div>
        </div>
      </main>
      <BottomMobileNav role="admin" />
    </div>
  );
}

export default function AdminDashboardPage() {
  return (
    <RequireRole role="admin">
      <DashboardContent />
    </RequireRole>
  );
}
