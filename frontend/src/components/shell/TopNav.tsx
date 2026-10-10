"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const MAIN = [
  { href: "/overview", label: "Overview", icon: "◉" },
  { href: "/movers", label: "Movers", icon: "▦" },
  { href: "/historical-research", label: "Evidence", icon: "DB" },
  { href: "/market-archive", label: "Market Archive", icon: "MK" },
  { href: "/opportunities", label: "Opportunities", icon: "◈" },
  { href: "/system", label: "System", icon: "⚙" },
];

const FUTURE = [
  { href: "/backtest", label: "Backtest", icon: "◐" },
  { href: "/paper-lab", label: "Paper Lab", icon: "◑" },
];

export function TopNav() {
  const pathname = usePathname();
  return (
    <nav className="v2-nav" aria-label="Primary navigation">
      <div>
        <strong>◆ BINANCE FUTURES</strong>
        <div className="v2-muted" style={{ fontSize: 11 }}>
          market intelligence · read-only
        </div>
      </div>
      <div className="v2-nav-group" aria-hidden="true">
        Terminal
      </div>
      {MAIN.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          aria-current={pathname === item.href ? "page" : undefined}
        >
          <span className="v2-nav-icon" aria-hidden="true">
            {item.icon}
          </span>
          {item.label}
        </Link>
      ))}
      <div className="v2-nav-group" aria-hidden="true">
        Future
      </div>
      {FUTURE.map((item) => (
        <Link key={item.href} href={item.href} aria-current={pathname === item.href ? "page" : undefined}>
          <span className="v2-nav-icon" aria-hidden="true">
            {item.icon}
          </span>
          {item.label} (future)
        </Link>
      ))}
    </nav>
  );
}
