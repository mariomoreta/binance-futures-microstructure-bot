import { MetricCard } from "@/components/cards/metrics";
import { formatCompact } from "@/lib/format";
import type { MetricPoint } from "@/lib/types";
import { DataFreshnessIndicator } from "./TopBar";

function MetricCell({ point, label }: { point: MetricPoint; label: string }) {
  const shown =
    point.value === null ? (
      <span className="v2-muted">—</span>
    ) : (
      <span>
        {formatCompact(point.value)}{" "}
        <span className="v2-muted" style={{ fontSize: 12 }}>
          {point.unit}
        </span>
      </span>
    );
  return (
    <div style={{ gridColumn: "span 2" }}>
      <MetricCard
        label={label}
        value={shown}
        sub={
          <>
            <div className="v2-muted" style={{ fontSize: 12 }}>
              {point.period} · {point.source}
            </div>
            <DataFreshnessIndicator freshness={point.freshness} />
            {point.unavailable ? (
              <div className="v2-muted" style={{ fontSize: 12 }}>
                {point.unavailable}
              </div>
            ) : null}
          </>
        }
      />
    </div>
  );
}

export function OverviewMetricGrid({
  metrics,
}: {
  metrics: Record<string, MetricPoint>;
}) {
  const order: Array<[string, string]> = [
    ["discovered", "Discovered contracts"],
    ["deepTracked", "Deep-tracked symbols"],
    ["topGainer", "Top gainer"],
    ["topLoser", "Top loser"],
    ["activity", "Market activity"],
    ["researchCapture", "Research capture"],
  ];
  return (
    <section className="v2-section" aria-label="Key metrics">
      <div className="v2-grid" data-testid="metric-grid">
        {order.map(([key, label]) =>
          metrics[key] ? (
            <MetricCell key={key} point={metrics[key] as MetricPoint} label={label} />
          ) : null,
        )}
      </div>
    </section>
  );
}
