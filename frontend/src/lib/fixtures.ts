// DEMO DATA — NOT LIVE. Static layout fixtures for DASH-V2-00 only.
// These exist so components can be rendered and tested without any API.
// They must never be presented as operational values and must be replaced
// by versioned /api/v1 view-model data in later slices.

import type { MoverRow } from "./types";

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
