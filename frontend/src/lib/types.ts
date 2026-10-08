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
