// Paper Lab — fixtures de operaciones para simulacion en caliente (ingenieria).
// Datos sintéticos determinísticos, SIN Binance en vivo, SIN capital real.
// Cada fixture incluye: configuracion, velas de la ventana de operacion y
// contexto previo. Sirven para probar el flujo completo (seleccion, entrada,
// gestion, salida, P&L, persistencia, exportacion) sin depender de feed vivo.
//
// NOTA: estos datos son fixtures de ingeniería. No son señales de trading ni
// resultados backtestados sobre datos reales.

import type {PaperCandle, PaperSessionConfig} from "./paper-lab-live";

export type PaperFixtureEntry = {
  config: PaperSessionConfig;
  candles: PaperCandle[];
  context: PaperCandle[];
  label: string;
};

function candle(openTime: number, open: number, high: number, low: number, close: number): PaperCandle {
  return {
    open_time_ms: openTime,
    open,
    high,
    low,
    close,
    close_time_ms: openTime + 15 * 60 * 1000 - 1,
  };
}

// Genera una serie de velas 15m contiguas desde un instante inicial.
function series(startMs: number, n: number, basePx: number, driftPctPerCandle: number, volatilityPct: number): PaperCandle[] {
  const out: PaperCandle[] = [];
  let px = basePx;
  for (let i = 0; i < n; i += 1) {
    const open = px;
    const drift = 1 + driftPctPerCandle / 100;
    const close = open * drift;
    const range = open * (volatilityPct / 100);
    const high = Math.max(open, close) + range * 0.5;
    const low = Math.min(open, close) - range * 0.5;
    out.push(candle(startMs + i * 15 * 60 * 1000, open, high, low, close));
    px = close;
  }
  return out;
}

// Contexto previo: 48 velas cerradas antes de la ventana de operacion.
function contextBefore(startMs: number, n: number, basePx: number): PaperCandle[] {
  return series(startMs - n * 15 * 60 * 1000, n, basePx, 0, 0.3);
}

// ---------- Fixture 1: BTCUSDT 15m LONG, salida por horizonte (leve pérdida) ----------
export const FIXTURE_BTC_LONG_HORIZON: {
  config: PaperSessionConfig;
  candles: PaperCandle[];
  context: PaperCandle[];
} = (() => {
  const start = 1788904800000; // 2026-09-08T22:00:00Z
  const base = 78458.7;
  const candles = series(start, 12, base, 0.05, 0.4); // 3h de velas
  const config: PaperSessionConfig = {
    symbol: "BTCUSDT",
    interval: "15m",
    direction: "LONG",
    notional_usdt: 1000,
    entry_px: base,
    stop_px: base * 0.995, // -0.5%
    stop_distance_pct: 0.5,
    horizon_ms: 3 * 60 * 60 * 1000, // 3h
    fee_bps: 5,
    spread_bps: 1,
    slippage_bps: 2,
  };
  return {config, candles, context: contextBefore(start, 48, base)};
})();

// ---------- Fixture 2: ETHUSDT 15m SHORT, salida por stop (pérdida controlada) ----------
export const FIXTURE_ETH_SHORT_STOP: {
  config: PaperSessionConfig;
  candles: PaperCandle[];
  context: PaperCandle[];
} = (() => {
  const start = 1788912000000; // 2026-09-09T00:00:00Z
  const base = 3450.0;
  // Velas que suben (contra un SHORT) hasta tocar el stop.
  const candles = series(start, 8, base, 0.35, 0.5);
  const config: PaperSessionConfig = {
    symbol: "ETHUSDT",
    interval: "15m",
    direction: "SHORT",
    notional_usdt: 1000,
    entry_px: base,
    stop_px: base * 1.008, // +0.8% stop para SHORT
    stop_distance_pct: 0.8,
    horizon_ms: 2 * 60 * 60 * 1000, // 2h
    fee_bps: 5,
    spread_bps: 1,
    slippage_bps: 2,
  };
  return {config, candles, context: contextBefore(start, 48, base)};
})();

// ---------- Fixture 3: SOLUSDT 15m LONG, salida manual en beneficio ----------
export const FIXTURE_SOL_LONG_MANUAL: {
  config: PaperSessionConfig;
  candles: PaperCandle[];
  context: PaperCandle[];
} = (() => {
  const start = 1788919200000; // 2026-09-09T02:00:00Z
  const base = 142.50;
  // Velas que suben claramente (favorable para LONG).
  const candles = series(start, 10, base, 0.6, 0.5);
  const config: PaperSessionConfig = {
    symbol: "SOLUSDT",
    interval: "15m",
    direction: "LONG",
    notional_usdt: 1000,
    entry_px: base,
    stop_px: base * 0.985, // -1.5%
    stop_distance_pct: 1.5,
    horizon_ms: 4 * 60 * 60 * 1000, // 4h
    fee_bps: 5,
    spread_bps: 1,
    slippage_bps: 2,
  };
  return {config, candles, context: contextBefore(start, 48, base)};
})();

// ---------- Fixture 4: BTCUSDT 15m LONG, stop de la vela de entrada ----------
// Regresión de orden temporal: la vela de entrada (V2) toca el stop efectivo
// (low 90 < 95.95) y la siguiente abre con gap por debajo (80). La salida debe
// resolverse en el stop efectivo 95.95 al conocerse el cierre de V2, no en el
// gap posterior de V3.
export const FIXTURE_BTC_LONG_STOP_ORDER: {
  config: PaperSessionConfig;
  candles: PaperCandle[];
  context: PaperCandle[];
} = (() => {
  const start = 1788926400000; // 2026-09-09T04:00:00Z
  const base = 100.0;
  const step = 15 * 60 * 1000;
  const candles = [
    candle(start + 0 * step, 100, 102, 99, 101),  // V0: señal (close >= 100)
    candle(start + 1 * step, 101, 103, 100, 102), // V1: decisión en su open
    candle(start + 2 * step, 101, 103, 90, 102),  // V2: fill @101, low 90
    candle(start + 3 * step, 80, 85, 75, 82),     // V3: gap @80
    candle(start + 4 * step, 82, 86, 81, 84),
  ];
  const config: PaperSessionConfig = {
    symbol: "BTCUSDT",
    interval: "15m",
    direction: "LONG",
    notional_usdt: 1000,
    entry_px: base,
    stop_px: 95, // referencia de la señal; el stop efectivo es 101 * 0.95
    stop_distance_pct: 5,
    horizon_ms: 3 * 60 * 60 * 1000,
    fee_bps: 5,
    spread_bps: 1,
    slippage_bps: 2,
  };
  return {config, candles, context: contextBefore(start, 48, base)};
})();

// ---------- Catalogo de fixtures disponibles ----------
export const PAPER_FIXTURES: Record<string, {
  config: PaperSessionConfig;
  candles: PaperCandle[];
  context: PaperCandle[];
  label: string;
}> = {
  btc_long_horizon: {
    ...FIXTURE_BTC_LONG_HORIZON,
    label: "BTCUSDT 15m LONG — salida por horizonte (leve pérdida)",
  },
  eth_short_stop: {
    ...FIXTURE_ETH_SHORT_STOP,
    label: "ETHUSDT 15m SHORT — salida por stop (pérdida controlada)",
  },
  sol_long_manual: {
    ...FIXTURE_SOL_LONG_MANUAL,
    label: "SOLUSDT 15m LONG — cierre manual en beneficio",
  },
  btc_long_stop_order: {
    ...FIXTURE_BTC_LONG_STOP_ORDER,
    label: "BTCUSDT 15m LONG — stop de la vela de entrada (orden temporal)",
  },
};

export const FIXTURE_IDS = Object.keys(PAPER_FIXTURES);
