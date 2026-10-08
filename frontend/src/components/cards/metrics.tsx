import type { ReactNode } from "react";
import { formatCompact, formatPrice, formatSignedPct } from "@/lib/format";

export function MetricCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="v2-card" data-testid="metric-card">
      <div className="v2-muted">{label}</div>
      <div className="v2-mono" style={{ fontSize: 20 }}>
        {value}
      </div>
      {sub ? <div className="v2-muted">{sub}</div> : null}
    </div>
  );
}

export function MetricDelta({
  pct,
  notional,
}: {
  pct: number | null;
  notional?: number | null;
}) {
  const tone =
    pct === null ? "muted" : pct > 0 ? "pos" : pct < 0 ? "neg" : "muted";
  return (
    <span data-testid="metric-delta">
      <span className="v2-chip" data-tone={tone}>
        {formatSignedPct(pct)}
      </span>{" "}
      {notional !== undefined ? (
        <span className="v2-mono v2-muted">{formatCompact(notional)}</span>
      ) : null}
    </span>
  );
}

export function MetricPrice({ value }: { value: number | null }) {
  return (
    <span className="v2-mono" data-testid="metric-price">
      {formatPrice(value)}
    </span>
  );
}
