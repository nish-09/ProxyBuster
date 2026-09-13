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

const ADMIN_ITEMS: NavItem[] = [
  { href: "/admin/dashboard", label: "Dashboard", icon: "dashboard" },
  { href: "/admin/students", label: "Students", icon: "school" },
  { href: "/admin/professors", label: "Professors", icon: "person" },
  { href: "/admin/subjects", label: "Subjects", icon: "menu_book" },
  { href: "/admin/divisions", label: "Divisions", icon: "groups" },
  { href: "/admin/lectures", label: "Lectures", icon: "event" },
];

export function SideNavBar({ role }: { role: "student" | "professor" | "admin" }) {
  const pathname = usePathname();
  const { logout } = useAuth();
  const items = role === "student" ? STUDENT_ITEMS : role === "admin" ? ADMIN_ITEMS : PROFESSOR_ITEMS;

  return (
    <nav className="hidden md:flex flex-col p-stack-md fixed left-4 top-4 bottom-4 w-[248px] bg-surface rounded-[28px] border border-outline-variant card-shadow z-50">
      <div className="mb-stack-lg flex items-center gap-3 px-3">
        <div className="w-10 h-10 rounded-lg bg-primary flex items-center justify-center text-on-primary clay-raised">
          <span className="material-symbols-outlined filled">security</span>
        </div>
        <div>
          <h1 className="font-headline-lg text-headline-lg font-bold text-on-surface">Proxy Busters</h1>
          <p className="font-label-sm text-label-sm text-on-surface-variant">
            {role === "student" ? "Student Portal" : role === "admin" ? "Admin Portal" : "Faculty Portal"}
          </p>
        </div>
      </div>
      <ul className="flex-1 space-y-1.5">
        {items.map((item) => {
          const active = pathname?.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                className={
                  active
                    ? "flex items-center gap-3 px-4 py-3 text-on-surface font-semibold bg-surface-container-high rounded-md clay-recessed transition-all duration-150"
                    : "flex items-center gap-3 px-4 py-3 text-on-surface-variant hover:text-on-surface hover:bg-surface-container rounded-md transition-colors duration-200"
                }
              >
                <span className={`material-symbols-outlined${active ? " filled text-tertiary" : ""}`}>{item.icon}</span>
                <span className="font-body-md text-body-md font-medium">{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="mt-auto pt-4 border-t border-outline">
        <ul className="space-y-1">
          <li>
            <a
              className="flex items-center gap-3 px-4 py-3 text-on-surface-variant hover:text-on-surface hover:bg-surface-container transition-colors duration-200 rounded-md cursor-pointer"
              href="#"
            >
              <span className="material-symbols-outlined">help</span>
              <span className="font-body-md text-body-md font-medium">Support</span>
            </a>
          </li>
          <li>
            <button
              onClick={() => logout()}
              className="w-full flex items-center gap-3 px-4 py-3 text-error hover:bg-error-container/50 transition-colors duration-200 rounded-md font-medium"
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
