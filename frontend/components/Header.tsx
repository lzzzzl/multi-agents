"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/tasks", label: "任务" },
  { href: "/tasks/new", label: "新建任务" },
];

export function Header() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-background/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-5">
        <Link href="/tasks" className="group flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent text-white">
            <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2">
              <path d="M12 3v18M3 12h18" strokeLinecap="round" />
            </svg>
          </span>
          <span className="font-display text-[17px] font-semibold tracking-tight">
            Multi&nbsp;Agents
          </span>
        </Link>

        <nav className="flex items-center gap-1 rounded-full border border-line bg-surface p-1 text-sm">
          {navItems.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-full px-4 py-1.5 font-medium transition-colors ${
                  active
                    ? "bg-ink text-background"
                    : "text-muted hover:bg-zinc-bg hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}