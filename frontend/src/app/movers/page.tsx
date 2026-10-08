"use client";

import { useState } from "react";
import { SectionHeader } from "@/components/shell/SectionHeader";
import { DataStateBadge, TierBadge } from "@/components/status/badges";
import { MetricDelta, MetricPrice } from "@/components/cards/metrics";
import { SymbolLink } from "@/components/cards/SymbolLink";
import { DataTable, FilterTabs, type Column } from "@/components/tables/table";
import { DemoDataBanner } from "@/components/shell/AppShell";
import { DEMO_MOVERS } from "@/lib/fixtures";
import { formatCompact } from "@/lib/format";
import type { MoverRow } from "@/lib/types";

const COLUMNS: Column<MoverRow>[] = [
  {
    key: "symbol",
    header: "Symbol",
    render: (row) => <SymbolLink symbol={row.symbol} />,
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
    key: "price",
    header: "Price",
    numeric: true,
    render: (row) => <MetricPrice value={row.price} />,
  },
  {
    key: "change",
    header: "24h",
    numeric: true,
    render: (row) => <MetricDelta pct={row.change24hPct} />,
  },
  {
    key: "qvol",
    header: "Quote vol 24h",
    numeric: true,
    render: (row) => (
      <span className="v2-mono">{formatCompact(row.quoteVolume24h)}</span>
    ),
  },
];

export default function MoversPage() {
  const [tab, setTab] = useState("All");
  const rows =
    tab === "All" ? DEMO_MOVERS : DEMO_MOVERS.filter((r) => r.tier === tab);
  return (
    <div>
      <SectionHeader title="Movers" />
      <DemoDataBanner />
      <FilterTabs
        tabs={["All", "CORE", "HOT", "DISCOVERY"]}
        active={tab}
        onChange={setTab}
      />
      <DataTable
        columns={COLUMNS}
        rows={rows}
        caption="Venue movers — raw numbers only; display formatting at render time."
      />
    </div>
  );
}
