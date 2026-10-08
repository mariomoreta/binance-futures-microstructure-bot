// Shared state vocabulary. Mirrors the Python capability/tier model.
// Null means not measured — never render null as zero.

export type EngineState =
  | "RUNNING"
  | "STOPPED"
  | "STARTING"
  | "STOPPING"
  | "COMPLETED"
  | "FAILED";

export type FeedState = "HEALTHY" | "DEGRADED" | "STALE" | "UNKNOWN";

export type ResearchState = "RUNNING" | "DEGRADED" | "STOPPED" | "UNKNOWN";

export type Tier = "CORE" | "HOT" | "DISCOVERY";

export type Capability =
  | "LIVE"
  | "WARMING"
  | "DISCOVERY ONLY"
  | "STALE"
  | "DEGRADED"
  | "UNKNOWN";

export interface SourceRef {
  provider: string;
  endpoint: string;
  observedAt: string | null;
}

export interface MoverRow {
  symbol: string;
  tier: Tier;
  capability: Capability;
  subscribed: boolean;
  price: number | null;
  change24hPct: number | null;
  quoteVolume24h: number | null;
  ret1m: number | null;
  velocity1m: number | null;
  accel1m: number | null;
  flowDelta: number | null;
  volZ1m: number | null;
  sampleAgeMs: number | null;
}

// Forward-compatible view-model shapes for the future /api/v1 BFF layer.
// Every metric carries provenance; null means not measured (never zero).

export type Freshness = "FRESH" | "STALE" | "EXPIRED" | "UNKNOWN";

export interface MetricPoint {
  value: number | null;
  unit: string;
  period: string;
  asOf: string | null;
  freshness: Freshness;
  source: string;
  unavailable?: string;
}

export interface PulseData {
  breadthUp: number | null;
  breadthDown: number | null;
  breadthTotal: number | null;
  accelShare: number | null;
  observedVol: number | null;
  relativeActivity: number | null;
  concentrationTop: number | null;
  coverageNote: string;
  asOf: string | null;
  freshness: Freshness;
  source: string;
}

export interface ExtremeMoveRow {
  symbol: string;
  observedChangePct: number | null;
  period: string;
  quoteVolume: number | null;
  coverage: Capability;
  dataAvailable: string;
}

export interface HealthFacts {
  recorder: ResearchState;
  persistence: string;
  feedFreshness: string;
  wsHealth: string;
  lastUpdate: string | null;
  errorsGaps: string;
}

export interface MarketContextFacts {
  btcRef: number | null;
  ethRef: number | null;
  categoriesNote: string;
  aggregateNote: string;
  providerNote: string;
}
