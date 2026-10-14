import { EngineChip, FeedChip, ResearchChip } from "@/components/status/badges";
import type { EngineState, FeedState, ResearchState } from "@/lib/types";

export function DemoPill() {
  return (
    <span className="v2-demo-pill" data-testid="demo-pill">
      DEMO — NOT LIVE
    </span>
  );
}

export function DataFreshnessIndicator({
  freshness,
  age,
}: {
  freshness: "FRESH" | "STALE" | "EXPIRED" | "UNKNOWN";
  age?: string | null;
}) {
  const tone =
    freshness === "FRESH"
      ? "pos"
      : freshness === "UNKNOWN"
        ? "muted"
        : "warn";
  const text =
    freshness === "UNKNOWN" ? "UNKNOWN" : `${freshness}${age ? ` · ${age}` : ""}`;
  return (
    <span className="v2-chip" data-tone={tone} data-testid="freshness">
      {text}
    </span>
  );
}

export function TopBar({
  engine,
  feed,
  research,
  lastData,
  demo=true,
}: {
  engine: EngineState;
  feed: FeedState;
  research: ResearchState;
  lastData: string | null;
  demo?:boolean;
}) {
  return (
    <div className="v2-topbar" data-testid="topbar">
      <div>
        <h1 style={{ margin: "0 0 4px" }}>Overview</h1>
        <div className="v2-market">Binance USD-M Futures · market intelligence</div>
      </div>
      <div className="v2-spacer" />
      <EngineChip state={engine} />
      <FeedChip state={feed} />
      <ResearchChip state={research} />
      <span className="v2-chip" data-tone="muted" data-testid="safety-chip">
        {demo?"OBSERVE ONLY (example)":"READ-ONLY RESEARCH"}
      </span>
      <span className="v2-muted v2-mono" data-testid="last-data" style={{ fontSize: 12 }}>
        {lastData ?? "last data: —"}
      </span>
      {demo?<DemoPill />:<span className="v2-chip" data-tone="warn">PERSISTED · NOT LIVE</span>}
    </div>
  );
}
