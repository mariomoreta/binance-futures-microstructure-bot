import Link from "next/link";
import type { ReactNode } from "react";
import { TopNav } from "./TopNav";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="v2-shell">
      <TopNav />
      <main className="v2-main">
        <div className="v2-notice" data-testid="foundation-notice">
          Dashboard V2 foundation (DASH-V2-00). Static shell only — no API
          integration, no live data.
        </div>
        {children}
      </main>
    </div>
  );
}

export function Placeholder({
  title,
  what,
}: {
  title: string;
  what: string;
}) {
  return (
    <section className="v2-card" aria-label={title}>
      <h2>{title}</h2>
      <p className="v2-muted">{what}</p>
      <p className="v2-muted">
        Honest development placeholder. Renders when the owning slice ships;
        until then no values are shown rather than invented ones.
      </p>
    </section>
  );
}

export function DemoDataBanner() {
  return (
    <p className="v2-notice" data-testid="demo-data-banner">
      DEMO DATA — NOT LIVE. Static layout fixture; not an operational value.
    </p>
  );
}

export { Link };
