"use client";

import { useEffect, useState } from "react";
import { RequireRole } from "@/components/route-guard";
import { SideNavBar } from "@/components/layout/SideNavBar";
import { TopNavBar, DesktopTopBar } from "@/components/layout/TopNavBar";
import { BottomMobileNav } from "@/components/layout/BottomMobileNav";
import { useAuth } from "@/lib/auth-context";
import { CardSkeleton } from "@/components/ui/Skeleton";
import { adminApi } from "@/lib/api";

function initials(name: string) {
  return name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

function DashboardContent() {
  const { user } = useAuth();
  const [counts, setCounts] = useState<{ students: number; professors: number; subjects: number; divisions: number } | null>(
    null
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [students, professors, subjects, divisions] = await Promise.all([
          adminApi.students(),
          adminApi.professors(),
          adminApi.subjects(),
          adminApi.divisions(),
        ]);
        if (cancelled) return;
        setCounts({
          students: students.length,
          professors: professors.length,
          subjects: subjects.length,
          divisions: divisions.length,
        });
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const tiles = [
    { label: "Students", value: counts?.students, icon: "school", href: "/admin/students" },
    { label: "Professors", value: counts?.professors, icon: "person", href: "/admin/professors" },
    { label: "Subjects", value: counts?.subjects, icon: "menu_book", href: "/admin/subjects" },
    { label: "Class Divisions", value: counts?.divisions, icon: "groups", href: "/admin/divisions" },
  ];

  return (
    <div className="bg-background text-on-background font-body-md antialiased flex min-h-screen">
      <SideNavBar role="admin" />
      <main className="flex-1 md:ml-[280px] min-h-screen bg-surface-container-low">
        <TopNavBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
        <div className="p-container-padding max-w-[1400px] mx-auto space-y-stack-lg pb-24">
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
                  <a
                    key={t.label}
                    href={t.href}
                    className="bg-surface rounded-xl p-5 border border-outline-variant shadow-sm flex flex-col justify-between h-full hover:border-primary transition-colors"
                  >
                    <div className="p-2 bg-primary-container/20 rounded-lg text-primary w-fit mb-4">
                      <span className="material-symbols-outlined">{t.icon}</span>
                    </div>
                    <div>
                      <p className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider mb-1">{t.label}</p>
                      <h3 className="font-display-lg text-display-lg text-on-surface">{t.value}</h3>
                    </div>
                  </a>
                ))}
          </section>

          <div className="bg-surface rounded-xl border border-outline-variant shadow-sm p-5">
            <h3 className="font-headline-md text-headline-md text-on-surface mb-3">Onboarding checklist</h3>
            <ol className="list-decimal list-inside space-y-2 font-body-md text-body-md text-on-surface-variant">
              <li>Create professor accounts under <a className="text-primary hover:underline" href="/admin/professors">Professors</a>.</li>
              <li>Create subjects under <a className="text-primary hover:underline" href="/admin/subjects">Subjects</a>.</li>
              <li>Create class divisions and assign a professor under <a className="text-primary hover:underline" href="/admin/divisions">Divisions</a>.</li>
              <li>Create student accounts under <a className="text-primary hover:underline" href="/admin/students">Students</a> (or let them self-register).</li>
              <li>Enroll students into a division from that division&apos;s row on the Divisions page.</li>
              <li>Schedule lectures under <a className="text-primary hover:underline" href="/admin/lectures">Lectures</a>.</li>
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
