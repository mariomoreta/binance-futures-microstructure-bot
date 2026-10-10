import Link from "next/link";
import type { ReactNode } from "react";
import { TopNav } from "./TopNav";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="v2-shell">
      <a className="v2-skip-link" href="#main-content">Skip to main content</a>
      <TopNav />
      <main className="v2-main" id="main-content" tabIndex={-1}>
        <div className="v2-source-strip" data-testid="shell-demo-strip"><span className="v2-source-label">SOURCE PER PANEL</span><span>DEMO previews and recorded evidence are explicitly labeled.</span></div>
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
