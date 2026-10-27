// FlowEngine — módulo compartido (puro, sin red, sin Binance público).
//
// Replica la lógica de `src/microstructure_probe/flow.py` (P1-06) en el
// backend BFF para servir el panel de flujo del mismo origen. No reconstruye
// flujo desde OHLC, no genera operaciones ficticias y no abre conexión
// pública.
//
// Semántica buyer-is-maker (verificada en docs/MARKET_DATA.md):
//  - m=true  -> buyer is maker -> agresor es SELL (side=-1)
//  - m=false -> buyer is taker -> agresor es BUY  (side=+1)
//  - El maker nunca es el agresor; el lado nunca se adivina.
//
// Deduplicación por identidad (symbol + event_id) con presupuesto de
// memoria acotado (LRU). Mismo event_id repetido: no suma volumen.
// Identificadores distintos con igual timestamp: ambos cuentan.
// Eventos tardíos (event_ms < newest seen): se descartan (dropped_late).

export interface FlowEvent {
  symbol: string;
  event_id: string;
  event_ms: number;
  price: number;
  quantity: number;
  buyer_is_maker: boolean;
  normal_quantity?: number;
}

export interface FlowHorizon {
  trades: number;
  base_volume: number;
  notional: number;
  buy_base: number;
  sell_base: number;
  buy_notional: number | null;
  sell_notional: number | null;
  signed_delta: number | null;   // cotizada: buy − sell
  delta_ratio: number | null;    // [-1,+1], + = net agresor BUY
  buy_pct: number | null;
  sell_pct: number | null;
  trade_rate: number;
  notional_rate: number;
  warmup_complete: boolean;
  window_ms: number;
  as_of_ms: number;
  coverage: string;
}

export interface FlowBlock {
  contract_version: string;
  availability: string;
  coverage: string;           // LIVE | NO_COVERAGE_BEFORE_FIRST_EVENT
  identity: { symbol: string; venue: string; market_type: string; source: string };
  as_of_ms: number;
  freshness_ms: number | null;
  live: boolean;
  trades_total: number;
  rpi_base_total: number | null;
  rpi_notional_total: number | null;
  rpi_trades: number | null;
  dropped_late: number;
  dropped_invalid: number;
  horizons: Record<string, FlowHorizon>;
  baselines: Record<string, any>;
  acceleration: any;
  deduplication: { seen_event_ids: number; max_event_ids: number };
  notes: string[];
}

// ---- Presupuesto de memoria para IDs deduplicados (LRU acotado) ----
const MAX_EVENT_IDS = 10_000;

// ---- Horizones (ms) ----
const FLOW_HORIZONS_MS: Record<string, number> = {
  "10s": 10_000,
  "30s": 30_000,
  "1m": 60_000,
  "3m": 180_000,
  "5m": 300_000,
  "15m": 900_000,
};
const FLOW_HORIZON_ORDER: string[] = ["10s", "30s", "1m", "3m", "5m", "15m"];

// ---- Volumen baselines (bucket sizes en segundos) ----
const BASELINE_SIZES_S: number[] = [10, 30, 60, 300];
const BASELINE_LABELS: string[] = ["10s", "30s", "1m", "5m"];
const BASELINE_KEEP_BUCKETS = 600;
const ACCEL_BASELINE_S = 60;

const MARKET_FLOW_CONTRACT_VERSION = "market-flow/v1";
const FLOW_AVAILABILITY = "LIVE_CAPTURE_ONLY";
const NO_COVERAGE = "NO_COVERAGE_BEFORE_FIRST_EVENT";

interface WindowEntry {
  event_ms: number;
  quantity: number;
  notional: number;
  side: number;
}

interface HorizonTotals {
  trades: number;
  base: number;
  notional: number;
  buy_base: number;
  sell_base: number;
  buy_notional: number;
  sell_notional: number;
}

interface OpenBucket {
  bucket_ms: number;
  notional: number;
  base: number;
  trades: number;
  buy_notional: number;
  sell_notional: number;
  first_ms: number;
  last_ms: number;
}

interface CompletedBucket {
  size_s: number;
  bucket_ms: number;
  notional: number;
  base: number;
  trades: number;
  buy_notional: number;
  sell_notional: number;
}

class SymbolFlowSeries {
  private _windows: Map<string, WindowEntry[]> = new Map();
  private _totals: Map<string, HorizonTotals> = new Map();
  private newest_ms: number | null = null;
  private oldest_ms: number | null = null;
  trades_total = 0;
  rpi_base_total = 0;
  rpi_notional_total = 0;
  rpi_trades = 0;
  dropped_late = 0;
  dropped_invalid = 0;

  getNewestMs(): number | null {
    return this.newest_ms;
  }
  private _openBucket: Map<number, OpenBucket | null> = new Map();
  private _completed: Map<number, CompletedBucket[]> = new Map();
  private _dirtyBuckets: CompletedBucket[] = [];
  skipped_buckets: Map<number, number> = new Map();
  completed_buckets = 0;

  constructor(private min_baseline_buckets: number) {
    for (const h of FLOW_HORIZON_ORDER) {
      this._windows.set(h, []);
      this._totals.set(h, {
        trades: 0, base: 0, notional: 0,
        buy_base: 0, sell_base: 0,
        buy_notional: 0, sell_notional: 0,
      });
    }
    for (const s of BASELINE_SIZES_S) {
      this._openBucket.set(s, null);
      this._completed.set(s, []);
      this.skipped_buckets.set(s, 0);
    }
  }

  ingest(event_time_ms: number, price: number, quantity: number,
         buyer_is_maker: boolean, normal_quantity?: number): boolean {
    if (!Number.isFinite(event_time_ms) || event_time_ms <= 0) {
      this.dropped_invalid++;
      return false;
    }
    if (!Number.isFinite(price) || !Number.isFinite(quantity) ||
        price <= 0 || quantity <= 0) {
      this.dropped_invalid++;
      return false;
    }
    if (typeof buyer_is_maker !== "boolean") {
      this.dropped_invalid++;
      return false;
    }
    if (this.newest_ms !== null && event_time_ms < this.newest_ms) {
      this.dropped_late++;
      return false;
    }

    const side = buyer_is_maker ? -1 : 1;
    const notional = price * quantity;

    this.newest_ms = event_time_ms;
    if (this.oldest_ms === null) {
      this.oldest_ms = event_time_ms;
    }
    this.trades_total++;

    if (typeof normal_quantity === "number" && Number.isFinite(normal_quantity) &&
        normal_quantity >= 0 && normal_quantity <= quantity) {
      const rpi_qty = quantity - normal_quantity;
      if (rpi_qty > 0) {
        this.rpi_base_total += rpi_qty;
        this.rpi_notional_total += price * rpi_qty;
        this.rpi_trades++;
      }
    }

    for (const h of FLOW_HORIZON_ORDER) {
      const window = this._windows.get(h)!;
      const totals = this._totals.get(h)!;
      window.push({ event_ms: event_time_ms, quantity, notional, side });
      totals.trades += 1;
      totals.base += quantity;
      totals.notional += notional;
      if (side > 0) {
        totals.buy_base += quantity;
        totals.buy_notional += notional;
      } else {
        totals.sell_base += quantity;
        totals.sell_notional += notional;
      }
    }
    this._evictExpired();
    this._accumulateBaseline(event_time_ms, price, quantity, notional, side);
    return true;
  }

  private _evictExpired(): void {
    if (this.newest_ms === null) return;
    for (const h of FLOW_HORIZON_ORDER) {
      const windowMs = FLOW_HORIZONS_MS[h]!;
      const window = this._windows.get(h)!;
      const totals = this._totals.get(h)!;
      const cutoff = this.newest_ms - windowMs;
      while (window.length > 0 && window[0]!.event_ms <= cutoff) {
        const entry = window.shift()!;
        totals.trades -= 1;
        totals.base -= entry.quantity;
        totals.notional -= entry.notional;
        if (entry.side > 0) {
          totals.buy_base -= entry.quantity;
          totals.buy_notional -= entry.notional;
        } else {
          totals.sell_base -= entry.quantity;
          totals.sell_notional -= entry.notional;
        }
      }
    }
    const longest = this._windows.get("15m")!;
    this.oldest_ms = longest.length > 0 ? longest[0]!.event_ms : this.newest_ms!;
  }

  private _accumulateBaseline(event_ms: number, price: number, qty: number,
                              notional: number, side: number): void {
    for (const size_s of BASELINE_SIZES_S) {
      const size_ms = size_s * 1000;
      const bucket = event_ms - (event_ms % size_ms);
      const current = this._openBucket.get(size_s);
      if (!current) {
        this._openBucket.set(size_s, {
          bucket_ms: bucket, notional, base: qty, trades: 1,
          buy_notional: side > 0 ? notional : 0,
          sell_notional: side < 0 ? notional : 0,
          first_ms: event_ms, last_ms: event_ms,
        });
        continue;
      }
      if (bucket === current.bucket_ms) {
        current.notional += notional;
        current.base += qty;
        current.trades += 1;
        if (side > 0) current.buy_notional += notional;
        else current.sell_notional += notional;
        current.last_ms = event_ms;
        continue;
      }
      this._closeBucket(size_s);
      if (bucket > current.bucket_ms + size_ms) {
        const skipped = this.skipped_buckets.get(size_s) ?? 0;
        this.skipped_buckets.set(size_s, skipped +
          Math.floor((bucket - current.bucket_ms) / size_ms) - 1);
      }
      this._openBucket.set(size_s, {
        bucket_ms: bucket, notional, base: qty, trades: 1,
        buy_notional: side > 0 ? notional : 0,
        sell_notional: side < 0 ? notional : 0,
        first_ms: event_ms, last_ms: event_ms,
      });
    }
  }

  private _closeBucket(size_s: number): void {
    const current = this._openBucket.get(size_s);
    if (!current) return;
    const record: CompletedBucket = {
      size_s, bucket_ms: current.bucket_ms, notional: current.notional,
      base: current.base, trades: current.trades,
      buy_notional: current.buy_notional, sell_notional: current.sell_notional,
    };
    this._completed.get(size_s)!.push(record);
    this._dirtyBuckets.push(record);
    this.completed_buckets++;
    this._openBucket.set(size_s, null);
  }

  drainCompletedBuckets(): CompletedBucket[] {
    const rows = [...this._dirtyBuckets];
    this._dirtyBuckets = [];
    return rows;
  }

  horizonFeature(horizon: string, as_of_ms: number): FlowHorizon {
    const windowMs = FLOW_HORIZONS_MS[horizon]!;
    const totals = this._totals.get(horizon)!;
    const buy = totals.buy_notional;
    const sell = totals.sell_notional;
    const denom = buy + sell;
    const delta = buy - sell;
    let ratio: number | null = null;
    let buy_pct: number | null = null;
    let sell_pct: number | null = null;
    if (denom > 0) {
      ratio = delta / denom;
      buy_pct = buy / denom * 100;
      sell_pct = sell / denom * 100;
    }
    const span_ms = (this.newest_ms !== null && this.oldest_ms !== null)
      ? this.newest_ms - this.oldest_ms : 0;
    const warmup_complete = span_ms >= windowMs;
    return {
      trades: Math.floor(totals.trades),
      base_volume: totals.base,
      notional: totals.notional,
      buy_base: totals.buy_base,
      sell_base: totals.sell_base,
      buy_notional: buy > 0 ? buy : null,
      sell_notional: sell > 0 ? sell : null,
      signed_delta: delta !== 0 ? delta : null,
      delta_ratio: ratio,
      buy_pct,
      sell_pct,
      trade_rate: totals.trades / (windowMs / 1000),
      notional_rate: totals.notional / (windowMs / 1000),
      warmup_complete,
      window_ms: windowMs,
      as_of_ms,
      coverage: totals.trades > 0 ? "LIVE" : NO_COVERAGE,
    };
  }

  baselineFeature(size_s: number, as_of_ms: number): any {
    const label = BASELINE_LABELS[BASELINE_SIZES_S.indexOf(size_s)];
    const history = this._completed.get(size_s)!.map(r => r.notional);
    const current = this._openBucket.get(size_s);
    const cur_notional = current ? current.notional : 0;
    const cur_base = current ? current.base : 0;
    const cur_trades = current ? current.trades : 0;
    const elapsed_ms = current
      ? current.last_ms - current.bucket_ms + 1
      : 0;
    let mean: number | null = null;
    let std: number | null = null;
    let z: number | null = null;
    const warmed = history.length >= this.min_baseline_buckets;
    if (warmed) {
      const m = history.reduce((a, b) => a + b, 0) / history.length;
      mean = m;
      const variance = history.reduce((a, v) => a + (v - m) ** 2, 0) / history.length;
      if (variance > 0) {
        std = Math.sqrt(variance);
        z = (cur_notional - m) / std;
      }
    }
    return {
      bucket: label, bucket_size_s: size_s,
      current_notional: cur_notional, current_base: cur_base,
      current_trades: cur_trades,
      bucket_start_ms: current ? current.bucket_ms : null,
      elapsed_ms,
      mean_notional: mean, std_notional: std, z_score: z,
      samples: history.length, min_samples: this.min_baseline_buckets,
      warmup: warmed && std !== null,
      skipped_buckets: this.skipped_buckets.get(size_s) ?? 0,
      as_of_ms,
    };
  }

  private getSkippedBuckets(size_s: number): number {
    return this.skipped_buckets.get(size_s) ?? 0;
  }

  accelerationFeature(as_of_ms: number): any {
    const size_s = ACCEL_BASELINE_S;
    const current = this._openBucket.get(size_s);
    const completed = this._completed.get(size_s);
    const out: any = {
      baseline: "1m",
      notional_rate: null, notional_rate_change: null,
      trade_rate: null, trade_rate_change: null,
      delta_rate: null, delta_rate_change: null,
    };
    if (!current) return out;
    const elapsed_s = Math.max((current.last_ms - current.bucket_ms + 1) / 1000, 1e-3);
    const cur_notional_rate = current.notional / elapsed_s;
    const cur_trade_rate = current.trades / elapsed_s;
    const cur_delta = current.buy_notional - current.sell_notional;
    const cur_delta_rate = cur_delta / elapsed_s;
    out.notional_rate = cur_notional_rate;
    out.trade_rate = cur_trade_rate;
    out.delta_rate = cur_delta_rate;
    if (!completed || completed.length === 0) return out;
    const prev = completed[completed.length - 1]!;
    const span_s = size_s;
    out.notional_rate_change = cur_notional_rate - prev.notional / span_s;
    out.trade_rate_change = cur_trade_rate - prev.trades / span_s;
    const prev_delta = prev.buy_notional - prev.sell_notional;
    out.delta_rate_change = cur_delta_rate - prev_delta / span_s;
    return out;
  }

  snapshot(symbol: string, as_of_ms: number, subscribed: boolean): FlowBlock {
    const freshness_ms = this.newest_ms !== null
      ? as_of_ms - this.newest_ms : null;
    const span_ms = (this.newest_ms !== null && this.oldest_ms !== null)
      ? this.newest_ms - this.oldest_ms : 0;
    const live = subscribed && this.trades_total > 0;

    const horizons: Record<string, FlowHorizon> = {};
    for (const h of FLOW_HORIZON_ORDER) {
      horizons[h] = this.horizonFeature(h, as_of_ms);
    }
    const baselines: Record<string, any> = {};
    for (let i = 0; i < BASELINE_LABELS.length; i++) {
      const label = BASELINE_LABELS[i]!;
      const size_s = BASELINE_SIZES_S[i]!;
      baselines[label] = this.baselineFeature(size_s, as_of_ms);
    }

    return {
      contract_version: MARKET_FLOW_CONTRACT_VERSION,
      availability: FLOW_AVAILABILITY,
      coverage: this.trades_total > 0 ? "LIVE" : NO_COVERAGE,
      identity: { symbol, venue: "binance", market_type: "usd_m_futures",
                  source: "aggTrade_local_transport" },
      as_of_ms,
      freshness_ms,
      live,
      trades_total: this.trades_total,
      rpi_base_total: this.rpi_base_total > 0 ? this.rpi_base_total : null,
      rpi_notional_total: this.rpi_notional_total > 0 ? this.rpi_notional_total : null,
      rpi_trades: this.rpi_trades > 0 ? this.rpi_trades : null,
      dropped_late: this.dropped_late,
      dropped_invalid: this.dropped_invalid,
      horizons,
      baselines,
      acceleration: this.accelerationFeature(as_of_ms),
      deduplication: {
        seen_event_ids: 0,
        max_event_ids: MAX_EVENT_IDS,
      },
      notes: ["Delta positivo no es señal alcista automática: solo describe "
        + "el saldo de volumen agresor en ventana."],
    };
  }
}

export class FlowEngine {
  private _allowed: Set<string> | null;
  private _series: Map<string, SymbolFlowSeries> = new Map();
  private _seenEventIds: Map<string, string[]> = new Map();
  private _seenEventIdsSet: Map<string, Set<string>> = new Map();
  dropped_unknown = 0;
  events_processed = 0;
  bucket_updates = 0;

  constructor(symbols: string[] = [], min_baseline_buckets = 5) {
    this._allowed = symbols.length > 0
      ? new Set(symbols.map(s => s.toUpperCase()))
      : null;
  }

  private _getSeries(symbol: string): SymbolFlowSeries {
    let series = this._series.get(symbol);
    if (!series) {
      series = new SymbolFlowSeries(5);
      this._series.set(symbol, series);
    }
    return series;
  }

  private _isAllowed(symbol: string): boolean {
    if (this._allowed === null) return true;
    return this._allowed.has(symbol);
  }

  private _recordEventId(symbol: string, event_id: string): boolean {
    let set = this._seenEventIdsSet.get(symbol);
    if (!set) {
      set = new Set();
      this._seenEventIdsSet.set(symbol, set);
      this._seenEventIds.set(symbol, []);
    }
    if (set.has(event_id)) return false;
    set.add(event_id);
    const ids = this._seenEventIds.get(symbol)!;
    ids.push(event_id);
    if (ids.length > MAX_EVENT_IDS) {
      const evicted = ids.shift();
      if (evicted !== undefined) set.delete(evicted);
    }
    return true;
  }

  ingest(event: FlowEvent): { ok: boolean; duplicate: boolean; reason?: string } {
    const symbol = event.symbol.toUpperCase();
    if (!this._isAllowed(symbol)) {
      this.dropped_unknown++;
      return { ok: false, duplicate: false, reason: "UNKNOWN_SYMBOL" };
    }
    const isNew = this._recordEventId(symbol, event.event_id);
    if (!isNew) {
      return { ok: false, duplicate: true, reason: "DUPLICATE_EVENT_ID" };
    }
    const series = this._getSeries(symbol);
    const accepted = series.ingest(
      event.event_ms, event.price, event.quantity,
      event.buyer_is_maker, event.normal_quantity,
    );
    if (!accepted) {
      const newest = series.getNewestMs();
      const isLatest = newest !== null && event.event_ms < newest;
      if (isLatest) {
        return { ok: false, duplicate: false, reason: "LATE_EVENT" };
      }
      return { ok: false, duplicate: false, reason: "INVALID_EVENT" };
    }
    this.events_processed++;
    this.bucket_updates += series.completed_buckets;
    return { ok: true, duplicate: false };
  }

  snapshot(symbol: string, as_of_ms: number, subscribed: boolean): FlowBlock {
    const series = this._series.get(symbol);
    if (!series || series.trades_total === 0) {
      return this._emptyBlock(symbol, as_of_ms);
    }
    const block = series.snapshot(symbol, as_of_ms, subscribed);
    block.deduplication = {
      seen_event_ids: this._seenEventIdsSet.get(symbol)!.size,
      max_event_ids: MAX_EVENT_IDS,
    };
    return block;
  }

  private _emptyBlock(symbol: string, as_of_ms: number): FlowBlock {
    const horizons: Record<string, FlowHorizon> = {};
    for (const h of FLOW_HORIZON_ORDER) {
      const windowMs = FLOW_HORIZONS_MS[h]!;
      horizons[h] = {
        trades: 0, base_volume: 0, notional: 0,
        buy_base: 0, sell_base: 0,
        buy_notional: null, sell_notional: null,
        signed_delta: null, delta_ratio: null,
        buy_pct: null, sell_pct: null,
        trade_rate: 0, notional_rate: 0,
        warmup_complete: false,
        window_ms: windowMs,
        as_of_ms,
        coverage: NO_COVERAGE,
      };
    }
    return {
      contract_version: MARKET_FLOW_CONTRACT_VERSION,
      availability: FLOW_AVAILABILITY,
      coverage: NO_COVERAGE,
      identity: { symbol, venue: "binance", market_type: "usd_m_futures",
                  source: "aggTrade_local_transport" },
      as_of_ms,
      freshness_ms: null,
      live: false,
      trades_total: 0,
      rpi_base_total: null,
      rpi_notional_total: null,
      rpi_trades: null,
      dropped_late: 0,
      dropped_invalid: 0,
      horizons,
      baselines: {},
      acceleration: {},
      deduplication: {
        seen_event_ids: this._seenEventIdsSet.get(symbol)?.size || 0,
        max_event_ids: MAX_EVENT_IDS,
      },
      notes: ["Sin eventos de captura para este símbolo: sin cobertura, "
        + "sin valores ni ceros inventados."],
    };
  }

  symbols(): string[] {
    return [...this._series.keys()].sort();
  }
}
