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

/** 4-tab bottom nav shown below md, mirroring the mobile Stitch exports. */
export function BottomMobileNav({ role }: { role: "student" | "professor" }) {
  const pathname = usePathname();
  const items = role === "student" ? STUDENT_ITEMS : PROFESSOR_ITEMS;

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-surface/95 backdrop-blur-md border-t border-outline-variant flex justify-around items-center h-16">
      {items.map((item) => {
        const active = pathname?.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`flex flex-col items-center justify-center gap-0.5 flex-1 h-full ${
              active ? "text-primary" : "text-on-surface-variant"
            }`}
          >
            <span className={`material-symbols-outlined${active ? " filled" : ""}`}>{item.icon}</span>
            <span className="font-label-sm text-label-sm">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
