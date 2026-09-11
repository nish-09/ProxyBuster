"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  href: string;
  label: string;
  icon: string;
}

const STUDENT_ITEMS: NavItem[] = [
  { href: "/student/dashboard", label: "Home", icon: "dashboard" },
  { href: "/student/attendance", label: "History", icon: "fact_check" },
  { href: "/student/scan", label: "Scan", icon: "qr_code_scanner" },
  { href: "/student/cooldown", label: "Status", icon: "timer" },
];

const PROFESSOR_ITEMS: NavItem[] = [
  { href: "/professor/dashboard", label: "Dashboard", icon: "dashboard" },
  { href: "/professor/students", label: "Students", icon: "group" },
  { href: "/professor/attendance-sheet", label: "Sheet", icon: "fact_check" },
  { href: "/professor/cooldowns", label: "Cooldowns", icon: "timer" },
];

const ADMIN_ITEMS: NavItem[] = [
  { href: "/admin/dashboard", label: "Home", icon: "dashboard" },
  { href: "/admin/students", label: "Students", icon: "school" },
  { href: "/admin/divisions", label: "Divisions", icon: "groups" },
  { href: "/admin/lectures", label: "Lectures", icon: "event" },
];

/** 4-tab bottom nav shown below md, mirroring the mobile Stitch exports. */
export function BottomMobileNav({ role }: { role: "student" | "professor" | "admin" }) {
  const pathname = usePathname();
  const items = role === "student" ? STUDENT_ITEMS : role === "admin" ? ADMIN_ITEMS : PROFESSOR_ITEMS;

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-surface border-t border-outline shadow-[0_-2px_10px_rgba(0,0,0,0.35)] flex justify-around items-center h-16">
      {items.map((item) => {
        const active = pathname?.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`flex flex-col items-center justify-center gap-0.5 flex-1 h-full mx-1 my-2 rounded-md border transition-all ${
              active
                ? "text-on-surface font-semibold border-outline bg-surface-container-high shadow-[inset_0_2px_4px_rgba(0,0,0,0.4)]"
                : "text-on-surface-variant border-transparent"
            }`}
          >
            <span className={`material-symbols-outlined${active ? " filled text-tertiary" : ""}`}>{item.icon}</span>
            <span className="font-label-sm text-label-sm">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
