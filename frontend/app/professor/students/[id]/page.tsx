"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { RequireRole } from "@/components/route-guard";
import { SideNavBar } from "@/components/layout/SideNavBar";
import { TopNavBar, DesktopTopBar } from "@/components/layout/TopNavBar";
import { BottomMobileNav } from "@/components/layout/BottomMobileNav";
import { useAuth } from "@/lib/auth-context";
import { professorApi, type StudentDetailOut } from "@/lib/api";

function initials(name: string) {
  return name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

function StudentDetailContent({ studentId }: { studentId: string }) {
  const { user } = useAuth();
  const [detail, setDetail] = useState<StudentDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await professorApi.student(studentId);
      setDetail(res);
    } catch {
      setError("Could not load this student's profile.");
    } finally {
      setLoading(false);
    }
  }, [studentId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard fetch-on-mount
    load();
  }, [load]);

  async function handleForceDisconnect() {
    if (!confirm("Force this student's active device to log out immediately?")) return;
    setDisconnecting(true);
    try {
      await professorApi.forceLogout(studentId);
      await load();
    } finally {
      setDisconnecting(false);
    }
  }

  return (
    <div className="bg-background text-on-background font-body-md min-h-screen flex antialiased">
      <SideNavBar role="professor" />
      <main className="flex-1 md:ml-[280px] flex flex-col min-h-screen">
        <TopNavBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
        <div className="flex-1 p-container-padding max-w-7xl mx-auto w-full pb-24">
          <div className="mb-stack-lg flex flex-col sm:flex-row sm:items-end justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <Link href="/professor/students" className="text-on-surface-variant hover:text-primary text-label-sm font-label-sm transition-colors">
                  Students
                </Link>
                <span className="material-symbols-outlined text-[16px] text-outline">chevron_right</span>
                <span className="text-primary text-label-sm font-label-sm">Profile</span>
              </div>
              <h2 className="font-display-lg text-display-lg text-on-surface">Student Profile</h2>
            </div>
            <DesktopTopBar userName={user?.full_name ?? ""} avatarInitials={user ? initials(user.full_name) : ""} />
          </div>

          {loading && <div className="p-8 text-center font-body-md text-body-md text-on-surface-variant">Loading...</div>}
          {error && <div className="p-8 text-center font-body-md text-body-md text-error">{error}</div>}

          {detail && !loading && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter">
              <div className="lg:col-span-2 bg-surface-container-lowest border border-outline-variant rounded-xl p-6 soft-shadow relative overflow-hidden">
                <div className="absolute top-0 right-0 w-64 h-64 bg-primary/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/4 pointer-events-none" />
                <div className="flex flex-col sm:flex-row gap-6 items-start relative z-10">
                  <div className="w-24 h-24 sm:w-32 sm:h-32 rounded-xl bg-tertiary-container text-on-tertiary-container flex items-center justify-center text-3xl font-bold border-2 border-surface-container shadow-sm">
                    {initials(detail.full_name)}
                  </div>
                  <div className="flex-1 w-full">
                    <div className="flex justify-between items-start mb-2 flex-wrap gap-2">
                      <div>
                        <h3 className="font-headline-lg text-headline-lg text-on-surface">{detail.full_name}</h3>
                        <p className="font-body-md text-body-md text-on-surface-variant">
                          {detail.program} • Semester {detail.semester}
                        </p>
                      </div>
                      <div className="bg-surface-container-low px-3 py-1 rounded-full border border-outline-variant flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full ${detail.standing === "good" ? "bg-[#10b981]" : "bg-error"}`} />
                        <span className={`font-label-sm text-label-sm font-bold ${detail.standing === "good" ? "text-[#065f46]" : "text-error"}`}>
                          {detail.standing === "good" ? "Good Standing" : "Attendance Warning"}
                        </span>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-4 mt-6 pt-4 border-t border-outline-variant">
                      <div>
                        <span className="block font-label-sm text-label-sm text-outline mb-1">ROLL NUMBER</span>
                        <span className="font-body-md text-body-md text-on-surface font-medium">{detail.roll_number}</span>
                      </div>
                      <div>
                        <span className="block font-label-sm text-label-sm text-outline mb-1">EMAIL</span>
                        <span className="font-body-md text-body-md text-on-surface">{detail.email}</span>
                      </div>
                      <div>
                        <span className="block font-label-sm text-label-sm text-outline mb-1">ATTENDANCE</span>
                        <span className="font-body-md text-body-md text-on-surface font-medium">{detail.overall_percentage.toFixed(1)}%</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-6 soft-shadow flex flex-col">
                <h3 className="font-headline-md text-headline-md text-on-surface mb-4 flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary filled">shield_locked</span>
                  Security Status
                </h3>
                <div className="flex-1 flex flex-col justify-center gap-5">
                  <div className="flex items-center gap-4">
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center ${detail.cooldown.active ? "bg-error/10 text-error" : "bg-primary/10 text-primary"}`}>
                      <span className="material-symbols-outlined text-[20px]">{detail.cooldown.active ? "timer" : "check_circle"}</span>
                    </div>
                    <div>
                      <div className="font-label-md text-label-md text-on-surface">
                        {detail.cooldown.active ? "Cooldown Active" : "No Active Cooldown"}
                      </div>
                      <div className="font-label-sm text-label-sm text-outline">
                        {detail.cooldown.active ? `${Math.ceil(detail.cooldown.remaining_seconds / 60)} min remaining` : "Clear to log in"}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-full bg-surface-container-high flex items-center justify-center text-on-surface-variant">
                      <span className="material-symbols-outlined text-[20px]">history</span>
                    </div>
                    <div>
                      <div className="font-label-md text-label-md text-on-surface">Last Login</div>
                      <div className="font-label-sm text-label-sm text-outline">
                        {detail.active_device ? new Date(detail.active_device.login_at).toLocaleString() : "No recorded sessions"}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-full bg-surface-container-high flex items-center justify-center text-on-surface-variant">
                      <span className="material-symbols-outlined text-[20px]">devices</span>
                    </div>
                    <div>
                      <div className="font-label-md text-label-md text-on-surface">
                        {detail.recent_security_events.length} Recent Security Event(s)
                      </div>
                      <div className="font-label-sm text-label-sm text-outline">Last 30 days</div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-0 soft-shadow overflow-hidden flex flex-col lg:col-span-1">
                <div className="p-4 border-b border-outline-variant bg-surface-container-low flex justify-between items-center">
                  <h3 className="font-label-md text-label-md text-on-surface">Active Session</h3>
                  <span className="relative flex h-2 w-2">
                    {detail.active_device && detail.active_device.status === "active" && (
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#10b981] opacity-75" />
                    )}
                    <span className={`relative inline-flex rounded-full h-2 w-2 ${detail.active_device?.status === "active" ? "bg-[#10b981]" : "bg-outline"}`} />
                  </span>
                </div>
                <div className="p-6 flex flex-col items-center text-center">
                  <span className="material-symbols-outlined text-[48px] text-primary mb-3" style={{ fontVariationSettings: "'wght' 200" }}>
                    smartphone
                  </span>
                  {detail.active_device ? (
                    <>
                      <h4 className="font-headline-md text-headline-md text-on-surface mb-1">
                        {detail.active_device.device_id ?? "Unknown device"}
                      </h4>
                      <p className="font-body-md text-body-md text-on-surface-variant mb-4">
                        {detail.active_device.user_agent ?? "No user-agent recorded"}
                      </p>
                      <div className="w-full bg-surface-container rounded p-3 flex items-center justify-center gap-2 border border-outline-variant/50">
                        <span className="material-symbols-outlined text-[16px] text-outline">wifi</span>
                        <span className="font-label-sm text-label-sm text-on-surface">{detail.active_device.ip_address ?? "Unknown IP"}</span>
                      </div>
                      {detail.active_device.status === "active" && (
                        <button
                          onClick={handleForceDisconnect}
                          disabled={disconnecting}
                          className="mt-4 text-error font-label-sm text-label-sm hover:underline disabled:opacity-50"
                        >
                          {disconnecting ? "Disconnecting..." : "Force Disconnect"}
                        </button>
                      )}
                    </>
                  ) : (
                    <p className="font-body-md text-body-md text-on-surface-variant">No active device session.</p>
                  )}
                </div>
              </div>

              <div className="lg:col-span-2 bg-surface-container-lowest border border-outline-variant rounded-xl p-6 soft-shadow">
                <h3 className="font-headline-md text-headline-md text-on-surface mb-6">Recent Security Events</h3>
                {detail.recent_security_events.length === 0 ? (
                  <p className="font-body-md text-body-md text-on-surface-variant py-4 text-center">No security events recorded.</p>
                ) : (
                  <div className="space-y-3">
                    {detail.recent_security_events.map((ev) => (
                      <div key={ev.id} className="flex items-start justify-between gap-3 flex-wrap sm:flex-nowrap p-4 border border-outline-variant rounded-lg">
                        <div className="flex items-start gap-4 min-w-0">
                          <div className="w-8 h-8 rounded bg-surface-container-high flex items-center justify-center text-on-surface-variant flex-shrink-0">
                            <span className="material-symbols-outlined text-[18px]">
                              {ev.severity === "high" ? "warning" : "info"}
                            </span>
                          </div>
                          <div className="min-w-0">
                            <div className="font-label-md text-label-md text-on-surface capitalize">{ev.event_type.replace(/_/g, " ")}</div>
                            <div className="font-label-sm text-label-sm text-outline mt-0.5">{ev.description}</div>
                          </div>
                        </div>
                        <span className="font-label-sm text-label-sm text-outline whitespace-nowrap flex-shrink-0">
                          {new Date(ev.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
      <BottomMobileNav role="professor" />
    </div>
  );
}

export default function ProfessorStudentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequireRole role="professor">
      <StudentDetailContent studentId={id} />
    </RequireRole>
  );
}
