"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/overview", label: "Overview" },
  { href: "/movers", label: "Movers" },
  { href: "/opportunities", label: "Opportunities" },
  { href: "/system", label: "System" },
];

const FUTURE = [
  { href: "/paper-lab", label: "Paper Lab (future)" },
  { href: "/backtest", label: "Backtest (future)" },
];

export function TopNav() {
  const pathname = usePathname();
  return (
    <nav className="v2-nav" aria-label="Primary">
      <strong>Dashboard V2</strong>
      {ITEMS.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          aria-current={pathname === item.href ? "page" : undefined}
        >
          {item.label}
        </Link>
      ))}
      <span className="v2-muted">Symbol detail: /symbol/[symbol]</span>
      {FUTURE.map((item) => (
        <Link key={item.href} href={item.href}>
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
