// Panel de flujo agresivo comprador/vendedor — contrato `market-flow/v1`.
// Backend Python es la unica autoridad (FlowEngine compartido via
// market_flow_service); el frontend solo solicita y presenta. Transporte
// local exclusivamente: sin conexion a Binance publico, sin cobertura antes
// del primer evento de captura, sin reconstruccion desde OHLC.
//
// Delta positivo NO es senal alcista automatica: solo describe el saldo de
// volumen agresor en ventana.

"use client";

import {useEffect, useState, useRef, useCallback} from "react";

const FLOW_API = "/api/v1/market-flow";
const FLOW_HOST = "127.0.0.1";
const FLOW_PORT = 8799;

export interface MarketFlowRow {
  symbol: string;
  identity: {symbol: string; venue: string; market_type: string; source: string};
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
    coverage: string;
  }>;
  dropped_late: number;
  dropped_invalid: number;
  deduplication: {seen_event_ids: number};
  notes: string[];
}

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  return n.toFixed(decimals);
}

function coverageLabel(coverage: string): string {
  switch (coverage) {
    case "LIVE": return "LIVE";
    case "NO_COVERAGE_BEFORE_FIRST_EVENT": return "SIN COBERTURA";
    default: return coverage;
  }
}

export function MarketFlowPanel({symbol}: {symbol: string}) {
  const [data, setData] = useState<MarketFlowRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [freshnessStale, setFreshnessStale] = useState(false);
  const symbolRef = useRef(symbol);
  const eventSourceRef = useRef<EventSource | null>(null);
  const lastResponseMs = useRef<number>(0);

  const fetchFlow = useCallback(async () => {
    const sym = (symbol || "").trim().toUpperCase();
    if (!sym || !/^[A-Z0-9]{2,32}$/.test(sym)) {
      setData(null);
      setError(null);
      return;
    }
    // Descartar si el simbolo cambio mientras la peticion estaba en vuelo
    if (sym !== symbolRef.current) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${FLOW_API}?symbol=${encodeURIComponent(sym)}&as_of_ms=${Date.now()}`,
        {cache: "no-store"},
      );
      if (sym !== symbolRef.current) return;
      if (!res.ok) {
        setError(`HTTP_${res.status}`);
        setData(null);
        return;
      }
      const json = await res.json();
      if (sym !== symbolRef.current) return;
      if (!json.ok) {
        // Servicio no alcanzado o error: SIN COBERTURA, sin sinteticos
        setData(json.data as MarketFlowRow);
        setError(json.error ?? "FLOW_SERVICE_ERROR");
        return;
      }
      setData(json.data as MarketFlowRow);
      lastResponseMs.current = Date.now();
      setFreshnessStale(false);
    } catch (err) {
      if (sym !== symbolRef.current) return;
      setError(err instanceof Error ? err.message : String(err));
      setData(null);
    } finally {
      if (sym === symbolRef.current) setLoading(false);
    }
  }, [symbol]);

  // Conexion SSE al servicio de flujo para actualizaciones incrementales
  useEffect(() => {
    const sym = (symbol || "").trim().toUpperCase();
    if (!sym || !/^[A-Z0-9]{2,32}$/.test(sym)) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      return;
    }
    // Cerrar conexion anterior si el simbolo cambio
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    symbolRef.current = sym;
    lastResponseMs.current = Date.now();

    const url = `http://${FLOW_HOST}:${FLOW_PORT}/flow/stream?symbol=${encodeURIComponent(sym)}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onopen = () => {
      setError(null);
      setLoading(false);
    };

    es.onmessage = (evt) => {
      try {
        const parsed = JSON.parse(evt.data);
        if (parsed.event === "snapshot" || parsed.event === "update") {
          const block = parsed.block;
          if (block && block.symbol === sym) {
            setData(block as MarketFlowRow);
            lastResponseMs.current = Date.now();
            setFreshnessStale(false);
          }
        }
      } catch {
        // Ignorar mensajes SSE no parseables
      }
    };

    es.onerror = () => {
      // El servicio puede no estar alcanzado: usar polling de respaldo
      es.close();
      eventSourceRef.current = null;
      fetchFlow();
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [symbol, fetchFlow]);

  // Temporizador de frescura: caduca aunque no lleguen eventos
  useEffect(() => {
    const timer = setInterval(() => {
      const now = Date.now();
      // Si no hay respuesta/actualizacion en 60s, la frescura caduca
      if (lastResponseMs.current > 0 && now - lastResponseMs.current > STALE_MS) {
        setFreshnessStale(true);
        setData((prev) => prev ? {...prev, live: false, coverage: "NO_COVERAGE_BEFORE_FIRST_EVENT"} : prev);
      }
    }, 5000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    (async () => {
      await fetchFlow();
    })();
  }, [fetchFlow]);

  // Render
  return (
    <section aria-labelledby="flow-heading">
      <h2 id="flow-heading">Flujo agresor (comprador / vendedor)</h2>
      {!data ? (
        <>
          <p className="note">
            {loading ? "Consultando flujo de transporte local…" : error ??
              "Sin datos de flujo para este simbolo."}
          </p>
          <p className="note">
            Delta positivo no es senal alcista automatica.
          </p>
        </>
      ) : (
        <>
          <p className="note">
            Fuente: aggTrade (transporte local) · {data.trades_total} eventos ·
            cobertura {coverageLabel(data.coverage)} ·
            actualizado {data.as_of_ms}
            {freshnessStale ? " · FRESCURA CADUCADA" : ""}
          </p>
          {data.notes.length > 0 && (
            <p className="note">{data.notes.join(" ")}</p>
          )}
          <table aria-label="Resumen de flujo 1m">
            <thead>
              <tr>
                <th>Simbolo</th>
                <th>Cobertura</th>
                <th>Eventos totales</th>
                <th>Visto (IDs)</th>
                <th>Live</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{data.identity.symbol}</td>
                <td>{coverageLabel(data.coverage)}</td>
                <td>{data.trades_total}</td>
                <td>{data.deduplication?.seen_event_ids ?? 0}</td>
                <td>{data.live ? "si" : "no"}</td>
              </tr>
            </tbody>
          </table>
          <h3>Ventana 1m</h3>
          <table aria-label="Detalle de flujo 1m">
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
                <td>{fmt(data.horizons["1m"]?.buy_notional)} USDT</td>
                <td>{fmt(data.horizons["1m"]?.sell_notional)} USDT</td>
                <td>{fmt(data.horizons["1m"]?.signed_delta)} USDT</td>
                <td>{fmt(data.horizons["1m"]?.delta_ratio, 3)}</td>
                <td>{fmt(data.horizons["1m"]?.buy_pct)} %</td>
                <td>{fmt(data.horizons["1m"]?.sell_pct)} %</td>
              </tr>
            </tbody>
          </table>
          <p className="note">
            {data.dropped_late > 0 ? `${data.dropped_late} evento(s) tardio(s) descartado(s)` : ""}
            {data.dropped_invalid > 0 ? ` · ${data.dropped_invalid} evento(s) invalido(s) descartado(s)` : ""}
          </p>
          <p className="note">
            Sin cobertura antes del inicio de captura: si no hay eventos, no
            hay valores ni ceros inventados. Valores al cursor requieren
            cobertura registrada; donde no exista, UNKNOWN.
          </p>
        </>
      )}
    </section>
  );
}

const STALE_MS = 60_000;
