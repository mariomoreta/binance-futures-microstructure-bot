import Link from "next/link";
import { DataStateBadge, TierBadge } from "@/components/status/badges";
import { MetricDelta, MetricPrice } from "@/components/cards/metrics";
import { SymbolLink } from "@/components/cards/SymbolLink";
import { DataTable, type Column } from "@/components/tables/table";
import { formatAgeMs, formatCompact } from "@/lib/format";
import type { MoverRow } from "@/lib/types";

const COLUMNS: Column<MoverRow>[] = [
  {
    key: "symbol",
    header: "Symbol",
    render: (row) => <SymbolLink symbol={row.symbol} />,
  },
  {
    key: "change",
    header: "24h Change",
    numeric: true,
    render: (row) => <MetricDelta pct={row.change24hPct} />,
  },
  {
    key: "qvol",
    header: "Quote Vol 24h",
    numeric: true,
    render: (row) => (
      <span className="v2-mono">{formatCompact(row.quoteVolume24h)}</span>
    ),
  },
  {
    key: "velocity",
    header: "Velocity",
    numeric: true,
    render: (row) => (
      <span className="v2-mono">
        {row.velocity1m !== null ? row.velocity1m.toExponential(1) + "/s" : "—"}
      </span>
    ),
  },
  {
    key: "accel",
    header: "Acceleration",
    numeric: true,
    render: (row) => (
      <span className="v2-mono">
        {row.accel1m !== null ? row.accel1m.toExponential(1) + "/s²" : "—"}
      </span>
    ),
  },
  {
    key: "tier",
    header: "Tier",
    render: (row) => <TierBadge tier={row.tier} />,
  },
  {
    key: "capability",
    header: "Capability",
    render: (row) => <DataStateBadge capability={row.capability} />,
  },
  {
    key: "freshness",
    header: "Freshness",
    render: (row) => (
      <span className="v2-muted v2-mono">{formatAgeMs(row.sampleAgeMs)}</span>
    ),
  },
];

export function MoversSnapshot({ rows }: { rows: MoverRow[] }) {
  return (
    <section className="v2-section" aria-label="Movers snapshot" data-testid="movers-snapshot">
      <h2>
        Movers Snapshot{" "}
        <Link href="/movers" style={{ fontSize: 13 }}>
          Full movers →
        </Link>
      </h2>
      <div className="v2-card">
        <DataTable
          columns={COLUMNS}
          rows={rows.slice(0, 8)}
          caption="Retained historical discovery tops. 24h change is not instantaneous velocity; empty cells mean the source is unavailable."
        />
      </div>
    </section>
  );
}
