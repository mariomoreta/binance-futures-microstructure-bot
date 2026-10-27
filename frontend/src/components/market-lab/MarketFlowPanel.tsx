// Panel de flujo agresivo comprador/vendedor — contrato `market-flow/v1`.
// Backend como autoridad (FlowEngine en el servicio Python de mercado,
// puerto 8791); el BFF es puro proxy y el frontend solo solicita y presenta.
// Transporte local exclusivamente: mismo origen (puerto 3020), sin conexión
// a Binance público, sin cobertura antes del primer evento de captura, sin
// reconstrucción desde OHLC.
//
// Delta positivo NO es señal alcista automática: solo describe el saldo de
// volumen agresor en ventana.

"use client";

import { useEffect, useState, useRef, useCallback } from "react";

const FLOW_API = "/api/v1/market-flow";
const FLOW_STREAM_API = "/api/v1/market-flow/stream";
const STALE_MS = 60_000; // frescura caduca sin eventos válidos

export interface MarketFlowRow {
  symbol: string;
  identity: { symbol: string; venue: string; market_type: string; source: string };
  as_of_ms: number;
  coverage: string;           // LIVE | NO_COVERAGE_BEFORE_FIRST_EVENT
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
  deduplication: { seen_event_ids: number; max_event_ids: number };
  notes: string[];
}

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  return n.toFixed(decimals);
}

function coverageLabel(coverage: string): string {
  switch (coverage) {
    case "LIVE": return "LIVE";
    case "NO_COVERAGE_BEFORE_FIRST_EVENT": return "DESCONOCIDA";
    default: return coverage;
  }
}

export function MarketFlowPanel({ symbol }: { symbol: string }) {
  const [data, setData] = useState<MarketFlowRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [connectionCause, setConnectionCause] = useState<string | null>(null);
  const symbolRef = useRef<string>("");
  const esRef = useRef<EventSource | null>(null);
  const lastValidDataMs = useRef<number>(0); // última data válida recibida
  const staleTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchFlow = useCallback(async () => {
    const sym = symbolRef.current;
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
        { cache: "no-store" },
      );
      // Solo aplicar si el símbolo no cambió mientras la petición estaba en vuelo
      if (symbolRef.current !== sym) return;
      if (!res.ok) {
        setError(`HTTP_${res.status}`);
        setData(null);
        return;
      }
      const json = await res.json();
      if (symbolRef.current !== sym) return;
      if (!json.ok) {
        setData(json.data as MarketFlowRow);
        setError(json.error ?? "FLOW_SERVICE_ERROR");
        return;
      }
      setData(json.data as MarketFlowRow);
      lastValidDataMs.current = Date.now();
      setConnectionCause(null);
      setError(null);
    } catch (err) {
      if (symbolRef.current !== sym) return;
      setError(err instanceof Error ? err.message : String(err));
      setData(null);
    } finally {
      if (symbolRef.current === sym) setLoading(false);
    }
  }, []);

  // Conexión SSE al flujo (mismo origen)
  useEffect(() => {
    const sym = (symbol || "").trim().toUpperCase();
    symbolRef.current = sym;

    // Cerrar conexión SSE anterior si cambia el símbolo
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }

    if (!sym || !/^[A-Z0-9]{2,32}$/.test(sym)) {
      (async () => {
        setData(null);
        setError(null);
        setConnectionCause(null);
        lastValidDataMs.current = 0;
      })();
      return;
    }

    (async () => {
      setLoading(true);
      setError(null);
      setConnectionCause(null);
    })();

    const url = `${FLOW_STREAM_API}?symbol=${encodeURIComponent(sym)}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => {
      if (symbolRef.current !== sym) return;
      setLoading(false);
      setConnectionCause(null);
    };

    es.onmessage = (evt) => {
      if (symbolRef.current !== sym) return;
      try {
        const parsed = JSON.parse(evt.data);
        if (parsed.event === "snapshot" || parsed.event === "update") {
          const block = parsed.block;
          if (block && block.identity && block.identity.symbol === sym) {
            setData(block as MarketFlowRow);
            lastValidDataMs.current = Date.now();
            setConnectionCause(null);
            setError(null);
          }
        }
      } catch {
        // Ignorar mensajes SSE no parseables
      }
    };

    es.onerror = () => {
      if (symbolRef.current !== sym) return;
      es.close();
      esRef.current = null;
      // Desconexión: retirar LIVE, mostrar causa
      setConnectionCause("desconectado");
      setError("SSE desconectado");
      // Intentar polling de respaldo vía HTTP
      fetchFlow();
    };

    return () => {
      if (esRef.current === es) {
        esRef.current = null;
      }
      es.close();
    };
  }, [symbol, fetchFlow]);

  // Temporizador de frescura: caduca si no llega dato válido en STALE_MS
  useEffect(() => {
    if (staleTimer.current) clearInterval(staleTimer.current);
    staleTimer.current = setInterval(() => {
      const now = Date.now();
      if (lastValidDataMs.current > 0 && now - lastValidDataMs.current > STALE_MS) {
        setConnectionCause("datos obsoletos");
        setData((prev) => prev ? {
          ...prev,
          live: false,
          coverage: "NO_COVERAGE_BEFORE_FIRST_EVENT",
        } : prev);
      }
    }, 5_000);
    return () => {
      if (staleTimer.current) clearInterval(staleTimer.current);
      staleTimer.current = null;
    };
  }, []);

  // Consulta inicial y reconsulta periódica de respaldo
  useEffect(() => {
    fetchFlow();
  }, [fetchFlow]);

  // Render
  return (
    <section aria-labelledby="flow-heading">
      <h2 id="flow-heading">Flujo agresor (comprador / vendedor)</h2>
      {!data ? (
        <>
          <p className="note">
            {loading ? "Conectando al flujo de transporte local…"
              : error ?? "Sin datos de flujo para este símbolo."}
          </p>
          {connectionCause && <p className="note">Causa: {connectionCause}</p>}
          <p className="note">
            Delta positivo no es señal alcista automática.
          </p>
        </>
      ) : (
        <>
          <p className="note">
            Fuente: aggTrade (transporte local, mismo origen) ·
            {data.trades_total} eventos ·
            cobertura {coverageLabel(data.coverage)} ·
            actualizado {data.as_of_ms}
            {connectionCause ? ` · ${connectionCause}` : ""}
          </p>
          {data.notes.length > 0 && (
            <p className="note">{data.notes.join(" ")}</p>
          )}
          <table aria-label="Resumen de flujo">
            <thead>
              <tr>
                <th>Símbolo</th>
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
                <td>{data.live ? "sí" : "no"}</td>
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
            {data.dropped_late > 0 ? `${data.dropped_late} evento(s) tardío(s) descartado(s)` : ""}
            {data.dropped_invalid > 0 ? ` · ${data.dropped_invalid} evento(s) inválido(s) descartado(s)` : ""}
          </p>
          <p className="note">
            Sin cobertura antes del inicio de captura: si no hay eventos, no hay valores ni ceros inventados.
            Valores al cursor requieren cobertura registrada; donde no exista, UNKNOWN.
          </p>
        </>
      )}
    </section>
  );
}
