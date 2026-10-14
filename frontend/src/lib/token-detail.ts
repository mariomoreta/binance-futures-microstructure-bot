import type { Capability, Tier } from "./types";

export type MarketState = "NORMAL" | "IGNITION" | "EXPANSION" | "EXHAUSTION" | "REVERSAL" | "UNKNOWN";
export type Direction = "UP" | "DOWN" | "NONE" | "UNKNOWN";
export interface DetailMetric { label: string; value: string | null; context: string; }
export interface TokenDetail {
  featureSections?:{title:string;source:string;asOf:string|null;freshness:"STALE"|"UNKNOWN";rows:{label:string;value:string|null}[]}[];
  source?: "PERSISTED_SQLITE_READONLY";
  priceSource?:string;
  discoveryAsOf?:string|null;
  evaluationAsOf?:string|null;
  symbol: string;
  market: "Binance USD-M Futures";
  tier: Tier;
  capability: Capability;
  price: number | null;
  change24h: number | null;
  asOf: string | null;
  state: MarketState;
  direction: Direction;
  ruleVersion: string | null;
  previousState: MarketState | null;
  evidence: string[];
  counterevidence: string[];
  missing: string[];
  metrics: DetailMetric[];
}
const FIXTURES: Record<string, TokenDetail> = {
  BTCUSDT: {
    symbol: "BTCUSDT", market: "Binance USD-M Futures", tier: "CORE",
    capability: "WARMING", price: 97500, change24h: 2.4,
    asOf: "2026-10-07T12:00:00Z",
    state: "UNKNOWN", direction: "UNKNOWN", ruleVersion: "v0.1.0",
    previousState: null,
    evidence: [], counterevidence: [],
    missing: ["Verified as-of classifier state", "Live feature freshness", "Transition history"],
    metrics: [
      { label: "1m Return", value: "+0.04%", context: "Demonstration only" },
      { label: "Velocity 1m", value: "0.0000011 /s", context: "Demonstration only" },
      { label: "Aggressive flow", value: "+250,000 USDT", context: "Demonstration only" },
      { label: "Order book", value: null, context: "Not available in fixture" },
      { label: "Open interest", value: null, context: "Not available in fixture" },
      { label: "Volatility", value: null, context: "Not available in fixture" },
    ],
  },
};
export function getDemoTokenDetail(symbol: string): TokenDetail {
  const key = symbol.toUpperCase();
  return FIXTURES[key] ?? {
    symbol: key, market: "Binance USD-M Futures", tier: "DISCOVERY",
    capability: "UNKNOWN", price: null, change24h: null, asOf: null,
    state: "UNKNOWN", direction: "UNKNOWN", ruleVersion: null, previousState: null,
    evidence: [], counterevidence: [],
    missing: ["Symbol-specific demo fixture is not provided", "Authoritative Python classification unavailable"],
    metrics: [
      { label: "Returns", value: null, context: "No demo observation" },
      { label: "Aggressive flow", value: null, context: "No demo observation" },
      { label: "Order book", value: null, context: "No demo observation" },
      { label: "Open interest", value: null, context: "No demo observation" },
    ],
  };
}
