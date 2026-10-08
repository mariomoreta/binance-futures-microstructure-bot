// DEMO DATA — NOT LIVE. Static layout fixtures for DASH-V2-00 only.
// These exist so components can be rendered and tested without any API.
// They must never be presented as operational values and must be replaced
// by versioned /api/v1 view-model data in later slices.

import type {
  ExtremeMoveRow,
  HealthFacts,
  MarketContextFacts,
  MetricPoint,
  MoverRow,
  PulseData,
} from "./types";

export const DEMO_MOVERS: MoverRow[] = [
  {
    symbol: "BTCUSDT",
    tier: "CORE",
    capability: "WARMING",
    subscribed: true,
    price: 97500.0,
    change24hPct: 2.4,
    quoteVolume24h: 1_900_000_000,
    ret1m: 0.0004,
    velocity1m: 1.1e-6,
    accel1m: null,
    flowDelta: 250000,
    volZ1m: null,
    sampleAgeMs: 12000,
  },
  {
    symbol: "ETHUSDT",
    tier: "CORE",
    capability: "UNKNOWN",
    subscribed: true,
    price: null,
    change24hPct: null,
    quoteVolume24h: null,
    ret1m: null,
    velocity1m: null,
    accel1m: null,
    flowDelta: null,
    volZ1m: null,
    sampleAgeMs: null,
  },
];

export const DEMO_ENGINE = {
  state: "STOPPED" as const,
  feed: "UNKNOWN" as const,
  research: "UNKNOWN" as const,
};

const DEMO_ASOF = "2026-10-07T12:00:00Z";
const DEMO_SRC = "demo-fixture";

export const DEMO_METRICS: Record<string, MetricPoint> = {
  discovered: {
    value: 482, unit: "contracts", period: "24h scan",
    asOf: DEMO_ASOF, freshness: "STALE", source: DEMO_SRC,
  },
  deepTracked: {
    value: 3, unit: "symbols", period: "live",
    asOf: DEMO_ASOF, freshness: "STALE", source: DEMO_SRC,
  },
  topGainer: {
    value: 41.2, unit: "% 24h", period: "24h",
    asOf: DEMO_ASOF, freshness: "STALE", source: DEMO_SRC,
  },
  topLoser: {
    value: -25.1, unit: "% 24h", period: "24h",
    asOf: DEMO_ASOF, freshness: "STALE", source: DEMO_SRC,
  },
  activity: {
    value: 918, unit: "msg/s", period: "1m",
    asOf: DEMO_ASOF, freshness: "STALE", source: DEMO_SRC,
  },
  researchCapture: {
    value: null, unit: "buckets", period: "run",
    asOf: null, freshness: "UNKNOWN", source: DEMO_SRC,
    unavailable: "Recorder depth unknown until the research status contract lands.",
  },
};

export const DEMO_PULSE: PulseData = {
  breadthUp: 281,
  breadthDown: 201,
  breadthTotal: 482,
  accelShare: 0.12,
  observedVol: 0.004,
  relativeActivity: 1.3,
  concentrationTop: 0.34,
  coverageNote: "Breadth over the demo discovery set; live depth covers 3 symbols.",
  asOf: DEMO_ASOF,
  freshness: "STALE",
  source: DEMO_SRC,
};

export const DEMO_EXTREMES: ExtremeMoveRow[] = [
  {
    symbol: "BTCUSDT", observedChangePct: 2.4, period: "24h",
    quoteVolume: 1_900_000_000, coverage: "WARMING",
    dataAvailable: "returns, flow, book",
  },
  {
    symbol: "ETHUSDT", observedChangePct: null, period: "24h",
    quoteVolume: null, coverage: "UNKNOWN",
    dataAvailable: "warming",
  },
];

export const DEMO_HEALTH: HealthFacts = {
  recorder: "UNKNOWN",
  persistence: "Example only — no live database read.",
  feedFreshness: "STALE (example, 12m old)",
  wsHealth: "Example only.",
  lastUpdate: DEMO_ASOF,
  errorsGaps: "No live errors observed in this fixture.",
};

export const DEMO_CONTEXT: MarketContextFacts = {
  btcRef: 97500.0,
  ethRef: null,
  categoriesNote: "Category taxonomy arrives with a future provider contract.",
  aggregateNote: "Broad-market aggregates arrive with a future context contract.",
  providerNote: "CoinMarketCap is a future complementary provider — never a Binance mark-price source. No endpoints are called in this slice.",
};
