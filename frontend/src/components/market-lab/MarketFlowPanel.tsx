// Panel de flujo agresivo comprador/vendedor — contrato `market-flow/v1`.
// Backend Python es la unica autoridad; el frontend solo solicita y presenta.
// Transporte local exclusivamente: sin conexion a Binance publico, sin
// cobertura antes del primer evento de captura, sin reconstruccion desde OHLC.
//
// Delta positivo NO es senal alcista automatica: solo describe el saldo de
// volumen agresor en ventana.

"use client";

import {useEffect, useState, useCallback} from "react";

export interface MarketFlowRow {
  symbol: string;
  as_of_ms: number;
  coverage: string;
  live: boolean;
  trades_total: number;
  freshness_ms: number | null;
  horizons: Record<string, {
    trades: number;
    base_volume: number;
    notional: number;
    buy_base: number;
    sell_base: number;
    buy_notional: number | null;
    sell_notional: number | null;
    signed_delta: number | null;
    delta_ratio: number | null;
    buy_pct: number | null;
    sell_pct: number | null;
    warmup_complete: boolean;
    window_ms: number;
  }>;
  dropped_late: number;
  dropped_invalid: number;
  notes: string[];
}

const FLOW_API = "/api/v1/market-flow";

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  return n.toFixed(decimals);
}

export function MarketFlowPanel({symbol}: {symbol: string}) {
  const [data, setData] = useState<MarketFlowRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchFlow = useCallback(async () => {
    const sym = (symbol || "").trim().toUpperCase();
    if (!sym || !/^[A-Z0-9]{2,32}$/.test(sym)) {
      setData(null);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${FLOW_API}?symbol=${encodeURIComponent(sym)}&as_of_ms=${Date.now()}`,
        {cache: "no-store"},
      );
      if (!res.ok) {
        setError(`HTTP_${res.status}`);
        setData(null);
        return;
      }
      const json = await res.json();
      setData(json as MarketFlowRow);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    (async () => {
      await fetchFlow();
    })();
  }, [fetchFlow]);

  if (!data) {
    return (
      <section aria-labelledby="flow-heading">
        <h2 id="flow-heading">Flujo agresor (comprador / vendedor)</h2>
        <p className="note">
          {loading ? "Consultando flujo de transporte local…" : error ??
            "Sin datos de flujo para este simbolo."}
        </p>
        <p className="note">
          Delta positivo no es senal alcista automatica.
        </p>
      </section>
    );
  }

  const h1m = data.horizons["1m"];
  const coverageLive = data.coverage === "LIVE";

  return (
    <section aria-labelledby="flow-heading">
      <h2 id="flow-heading">Flujo agresor (comprador / vendedor)</h2>
      <p className="note">
        Fuente: aggTrade (transporte local) · {data.trades_total} eventos ·
        cobertura {coverageLive ? "LIVE" : "NINGUNA"} ·
        actualizado {data.as_of_ms}
      </p>
      {data.notes.length > 0 && (
        <p className="note">{data.notes.join(" ")}</p>
      )}
      <table aria-label="Resumen de flujo 1m">
        <thead>
          <tr>
            <th>Compra agresora (notional)</th>
            <th>Venta agresora (notional)</th>
            <th>Delta firmado (buy − sell)</th>
            <th>Delta ratio</th>
            <th>Compra %</th>
            <th>Venta %</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{fmt(h1m?.buy_notional)} USDT</td>
            <td>{fmt(h1m?.sell_notional)} USDT</td>
            <td>{fmt(h1m?.signed_delta)} USDT</td>
            <td>{fmt(h1m?.delta_ratio, 3)}</td>
            <td>{fmt(h1m?.buy_pct)} %</td>
            <td>{fmt(h1m?.sell_pct)} %</td>
          </tr>
        </tbody>
      </table>
      <p className="note">
        {data.dropped_late > 0 ? `${data.dropped_late} evento(s) tardio(s) descartado(s)` : ""}
        {data.dropped_invalid > 0 ? `${data.dropped_invalid} evento(s) invalido(s) descartado(s)` : ""}
      </p>
      <p className="note">
        Sin cobertura antes del inicio de captura: si no hay eventos, no hay
        valores ni ceros inventados.
      </p>
    </section>
  );
}
