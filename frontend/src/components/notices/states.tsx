import type { ReactNode } from "react";

export function ResearchOnlyNotice({ children }: { children?: ReactNode }) {
  return (
    <p className="v2-notice" data-testid="research-only-notice">
      RESEARCH ONLY — NOT A SIGNAL.{" "}
      {children ?? "Descriptive research; no confidence badge, no recommendation."}
    </p>
  );
}

export function EmptyState({
  title,
  hint,
}: {
  title: string;
  hint?: string;
}) {
  return (
    <div className="v2-card" data-testid="empty-state" role="status">
      <strong>{title}</strong>
      {hint ? <p className="v2-muted">{hint}</p> : null}
    </div>
  );
}

export function WarmingState({ what }: { what: string }) {
  return (
    <div className="v2-card" data-testid="warming-state" role="status">
      <strong>WARMING</strong>
      <p className="v2-muted">
        {what} is still warming. Values appear when measured — never as zeros.
      </p>
    </div>
  );
}

export function StaleDataNotice({ age }: { age: string }) {
  return (
    <div className="v2-card" data-testid="stale-notice" role="status">
      <strong>STALE</strong>
      <p className="v2-muted">
        Showing last measured values from {age} ago. Not live.
      </p>
    </div>
  );
}
