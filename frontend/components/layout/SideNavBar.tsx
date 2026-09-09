"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

interface NavItem {
  href: string;
  label: string;
  icon: string;
}

/**
 * Every Stitch desktop export (student_dashboard, professor_analytics_dashboard,
 * detailed_attendance_sheet, student_profile, live_attendance_session, my_attendance_history)
 * embeds the exact same literal sidebar markup/classes regardless of which role the screen is
 * for (a Stitch export quirk — see design/student_dashboard/code.html). The markup/classes below
 * are copied verbatim; only the item set is switched per role, which is required for the app to
 * be functional (a student must not see links to professor-only pages that would 403).
 */
const STUDENT_ITEMS: NavItem[] = [
  { href: "/student/dashboard", label: "Dashboard", icon: "dashboard" },
  { href: "/student/attendance", label: "My Attendance", icon: "fact_check" },
  { href: "/student/scan", label: "Scan Attendance", icon: "qr_code_scanner" },
];

const PROFESSOR_ITEMS: NavItem[] = [
  { href: "/professor/dashboard", label: "Dashboard", icon: "dashboard" },
  { href: "/professor/attendance-sheet", label: "Attendance Sheet", icon: "fact_check" },
  { href: "/professor/students", label: "Students", icon: "group" },
  { href: "/professor/cooldowns", label: "Cooldown Monitor", icon: "timer" },
];

export function SideNavBar({ role }: { role: "student" | "professor" }) {
  const pathname = usePathname();
  const { logout } = useAuth();
  const items = role === "student" ? STUDENT_ITEMS : PROFESSOR_ITEMS;

  return (
    <nav className="hidden md:flex flex-col h-full p-stack-md fixed left-0 top-0 h-full w-[280px] bg-surface border-r border-outline-variant shadow-sm z-50">
      <div className="mb-stack-lg flex items-center gap-3 px-3">
        <div className="w-10 h-10 rounded-lg bg-primary-container flex items-center justify-center text-on-primary-container">
          <span className="material-symbols-outlined filled">security</span>
        </div>
        <div>
          <h1 className="font-headline-lg text-headline-lg font-bold text-primary">Proxy Busters</h1>
          <p className="font-label-sm text-label-sm text-on-surface-variant">
            {role === "student" ? "Student Portal" : "College Admin Portal"}
          </p>
        </div>
      </div>
      <ul className="flex-1 space-y-1">
        {items.map((item) => {
          const active = pathname?.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                className={
                  active
                    ? "flex items-center gap-3 px-4 py-3 text-primary font-bold bg-secondary-container/30 rounded-lg transition-transform duration-150"
                    : "flex items-center gap-3 px-4 py-3 text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high transition-colors duration-200 rounded-lg"
                }
              >
                <span className={`material-symbols-outlined${active ? " filled" : ""}`}>{item.icon}</span>
                <span className="font-body-md text-body-md">{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="mt-auto pt-4 border-t border-surface-variant">
        <ul className="space-y-1">
          <li>
            <a
              className="flex items-center gap-3 px-4 py-3 text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high transition-colors duration-200 rounded-lg cursor-pointer"
              href="#"
            >
              <span className="material-symbols-outlined">help</span>
              <span className="font-body-md text-body-md">Support</span>
            </a>
          </li>
          <li>
            <button
              onClick={() => logout()}
              className="w-full flex items-center gap-3 px-4 py-3 text-error hover:bg-error-container/20 transition-colors duration-200 rounded-lg"
            >
              <span className="material-symbols-outlined">logout</span>
              <span className="font-body-md text-body-md">Logout</span>
            </button>
          </li>
        </ul>
      </div>
    </nav>
  );
}
