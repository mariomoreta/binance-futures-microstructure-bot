"use client";

// Conexión del navegador al servicio local de datos (`market-stream/v1`).
//
// Una sola `EventSource` por gráfico visible. El backend es la autoridad:
// aquí solo se acumulan eventos ya validados. Al cerrar/desmontar se aborta el
// upstream y el servicio libera el consumidor (no se toca el monitor del bot).
//
// Reintentos: `EventSource` reconecta según `retry: 5000` del servidor; aquí se
// cuentan los fallos y tras MAX_ATTEMPTS se deja de fingir conexión y se
// informa "servicio de datos detenido".

import {useEffect, useRef, useState} from "react";
import {
  emptyStreamView, type MarketStreamCandle, type MarketStreamGap,
  type MarketStreamSnapshot, type MarketStreamState, type MarketStreamStatus,
  type MarketStreamView,
} from "./market-stream";

const MAX_ATTEMPTS = 6;
const MAX_UPDATES = 400;
const MAX_GAPS = 10;
const STREAM_URL = "/api/v1/market-stream";
const STATUS_URL = "/api/v1/market-stream/status";
const EMPTY_VIEW: MarketStreamView = emptyStreamView();

export interface UseMarketStreamOptions {
  symbol: string | null;
  interval: string | null;
  fromMs: number | null;
  toMs: number | null;
  enabled: boolean;
}

function parseEvent<T>(event: MessageEvent): T | null {
  try {
    return JSON.parse(String(event.data)) as T;
  } catch {
    return null;
  }
}

export function useMarketStream(options: UseMarketStreamOptions): MarketStreamView {
  const {symbol, interval, fromMs, toMs, enabled} = options;
  const [view, setView] = useState<MarketStreamView>(emptyStreamView);
  const windowRef = useRef<{fromMs: number | null; toMs: number | null}>({fromMs, toMs});
  // Instante local del ultimo evento SSE recibido. La frescura se calcula aqui
  // para retirar LIVE aunque el stream se quede mudo sin cerrar.
  const lastEventAt = useRef<number | null>(null);

  // La ventana solo se usa al abrir la conexión: paginar hacia atrás no debe
  // reabrir el feed ni duplicar suscripciones.
  useEffect(() => {
    windowRef.current = {fromMs, toMs};
  }, [fromMs, toMs]);

  // Reloj local de frescura: si no llega ningun evento (ni heartbeat), el panel
  // pasa a OBSOLETO y luego a DESCONECTADO con la causa, sin depender de que se
  // agoten los reintentos del EventSource.
  useEffect(() => {
    if (!enabled) return;
    const timer = setInterval(() => {
      const last = lastEventAt.current;
      if (last === null) return;
      const age = Math.max(0, Date.now() - last);
      setView((previous) => {
        // El aviso de servicio detenido es terminal: no se sobrescribe con la
        // causa de frescura mientras el EventSource sigue reintentando.
        if (previous.available === false) return previous;
        const status = previous.status;
        if (!status) return previous;
        const fresh = status.connection.fresh_ms;
        const stale = status.connection.stale_ms;
        const state: MarketStreamState = age > stale
          ? "DISCONNECTED"
          : age > fresh ? "STALE" : status.connection.state;
        const cause = age > stale
          ? `sin mensajes del feed desde hace ${Math.round(age / 1000)} s: desconectado`
          : age > fresh
            ? `sin mensajes del feed desde hace ${Math.round(age / 1000)} s: LIVE retirado por frescura`
            : previous.error;
        if (status.age_ms === age && status.connection.state === state
            && previous.error === cause) {
          return previous;
        }
        return {
          ...previous,
          error: cause,
          status: {
            ...status,
            age_ms: age,
            live: status.live && age <= fresh,
            connection: {...status.connection, state},
          },
        };
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [enabled]);

  useEffect(() => {
    if (!enabled || !symbol || !interval) {
      return;
    }
    let disposed = false;
    let source: EventSource | null = null;
    let attempts = 0;
    const controller = new AbortController();
    lastEventAt.current = Date.now();
    const touch = () => { lastEventAt.current = Date.now(); };

    const fail = (detail: string) => {
      if (disposed) return;
      setView((previous) => ({
        ...previous, available: false, error: detail,
        status: previous.status ? {...previous.status,
          connection: {...previous.status.connection, state: "DISCONNECTED"},
          live: false, age_ms: previous.status.age_ms} : null,
      }));
    };

    const pushUpdate = (candle: MarketStreamCandle) => {
      setView((previous) => {
        const updates = [...previous.updates, candle];
        return {...previous, updates: updates.slice(-MAX_UPDATES)};
      });
    };

    const open = () => {
      if (disposed) return;
      if (typeof EventSource === "undefined") {
        // Entorno sin SSE: se declara la ausencia en vez de fingir conexión.
        setView({...emptyStreamView(), available: false,
          error: "EventSource no disponible en este entorno"});
        return;
      }
      const params = new URLSearchParams({symbol, interval});
      const window = windowRef.current;
      if (window.fromMs !== null) params.set("from_ms", String(window.fromMs));
      if (window.toMs !== null) params.set("to_ms", String(window.toMs));
      const es = new EventSource(`${STREAM_URL}?${params.toString()}`);
      source = es;

      es.addEventListener("hello", () => {
        if (disposed) return;
        touch();
        setView((previous) => ({...previous, available: true, error: null}));
      });
      es.addEventListener("snapshot", (event) => {
        const payload = parseEvent<MarketStreamSnapshot>(event);
        if (!payload || disposed) return;
        touch();
        setView((previous) => ({
          ...previous, snapshot: payload, available: true,
          // El snapshot ya trae el bloque versionado calculado por el
          // backend (market-indicators/v1) sobre velas cerradas;
          // los eventos `indicators` posteriores lo reemplazan.
          indicators: payload.indicators ?? previous.indicators,
          // market-btc-context/v1 aditivo del snapshot; los eventos
          // `context` posteriores lo reemplazan.
          btc_context: payload.context_btc ?? previous.btc_context,
        }));
      });
      // Recalculo incremental por cierre: el backend publica el bloque
      // versionado al confirmarse una vela; solo se acepta el mismo
      // símbolo/intervalo de esta conexión.
      es.addEventListener("indicators", (event) => {
        const block = parseEvent<Record<string, unknown>>(event);
        if (!block || disposed) return;
        const identity = block["identity"] as
          {symbol?: unknown; interval?: unknown} | undefined;
        if (identity?.symbol !== symbol || identity?.interval !== interval) {
          return;
        }
        touch();
        setView((previous) => ({...previous, indicators: block}));
      });
      es.addEventListener("context", (event) => {
        // market-btc-context/v1: recalculado en el backend al cerrar la
        // vela del token o la de BTC; solo misma identidad de la conexión.
        const block = parseEvent<Record<string, unknown>>(event);
        if (!block || disposed) return;
        const identity = block["identity"] as
          {symbol?: unknown; interval?: unknown} | undefined;
        if (identity?.symbol !== symbol || identity?.interval !== interval) {
          return;
        }
        touch();
        setView((previous) => ({...previous, btc_context: block}));
      });
      es.addEventListener("candle", (event) => {
        const candle = parseEvent<MarketStreamCandle>(event);
        if (!candle || disposed) return;
        touch();
        pushUpdate(candle);
      });
      es.addEventListener("closed", (event) => {
        const candle = parseEvent<MarketStreamCandle>(event);
        if (!candle || disposed) return;
        touch();
        pushUpdate({...candle, closed: true});
      });
      es.addEventListener("status", (event) => {
        const status = parseEvent<MarketStreamStatus>(event);
        if (!status || disposed) return;
        touch();
        setView((previous) => ({...previous, status, available: true, error: null}));
      });
      es.addEventListener("gap", (event) => {
        const gap = parseEvent<MarketStreamGap>(event);
        if (!gap || disposed) return;
        touch();
        setView((previous) => ({
          ...previous, available: true,
          gaps: [...previous.gaps, gap].slice(-MAX_GAPS),
        }));
      });
      es.addEventListener("heartbeat", (event) => {
        const beat = parseEvent<{
          connection?: MarketStreamStatus["connection"];
          age_ms?: number | null; live?: boolean;
          last_message_ms?: number | null; last_kline_open_ms?: number | null;
          now_ms?: number;
        }>(event);
        if (!beat || disposed) return;
        touch();
        setView((previous) => {
          if (!previous.status) return previous;
          return {
            ...previous,
            available: true,
            error: null,
            status: {
              ...previous.status,
              connection: beat.connection ?? previous.status.connection,
              age_ms: beat.age_ms ?? previous.status.age_ms,
              live: beat.live === true,
              last_message_ms: beat.last_message_ms ?? previous.status.last_message_ms,
              last_kline_open_ms: beat.last_kline_open_ms ?? previous.status.last_kline_open_ms,
              generated_at_ms: beat.now_ms ?? previous.status.generated_at_ms,
            },
          };
        });
      });
      es.addEventListener("error", (event) => {
        // Evento `error` del propio stream (p. ej. MAX_CONSUMERS, upstream
        // cerrado) o de red. Se declara la causa y se retira LIVE al instante.
        if (disposed) return;
        const payload = parseEvent<{code?: string; detail?: string}>(event as MessageEvent);
        if (payload?.code) {
          setView((previous) => ({
            ...previous, available: true,
            error: payload.detail ?? payload.code ?? "error del feed",
            status: previous.status ? {
              ...previous.status, live: false,
              connection: {...previous.status.connection, state: "DISCONNECTED"},
            } : null,
          }));
        }
      });

      es.onopen = () => {
        if (disposed) return;
        attempts = 0;
        touch();
        setView((previous) => ({...previous, available: true, attempts: 0}));
      };
      es.onerror = () => {
        if (disposed) return;
        attempts += 1;
        if (attempts >= MAX_ATTEMPTS) {
          es.close();
          source = null;
          fail("servicio de datos detenido o inaccesible tras varios intentos");
          return;
        }
        // La causa no espera al ultimo reintento: si el backend ya la declaro
        // (p. ej. upstream cerrado) se conserva; si no, se informa del reintento.
        setView((previous) => ({
          ...previous, attempts,
          error: previous.error
            ?? `conexión con el feed interrumpida; reintentando (${attempts}/${MAX_ATTEMPTS})`,
          status: previous.status ? {
            ...previous.status, live: false,
            connection: {...previous.status.connection, state: "DISCONNECTED"},
          } : null,
        }));
        // El BFF responde 503 (JSON) cuando el servicio esta detenido. Para
        // EventSource eso es un fallo fatal y no reintenta: sin esta consulta
        // `attempts` se queda en 1 y el aviso de servicio detenido nunca
        // aparece. Se pregunta al endpoint de estado, que si responde 200 con
        // `available:false` declara la causa real y cierra el stream.
        void (async () => {
          try {
            const response = await fetch(STATUS_URL, {
              cache: "no-store", signal: controller.signal,
            });
            const data = await response.json() as {
              available?: boolean; detail?: string | null;
            };
            if (disposed) return;
            if (data.available === false) {
              es.close();
              if (source === es) source = null;
              fail(data.detail ?? "servicio de datos detenido");
            }
          } catch {
            // Sin estado disponible: se mantiene el reintento normal.
          }
        })();
      };
    };

    if (typeof fetch !== "function") {
      open();
      return () => {
        disposed = true;
        controller.abort();
        source?.close();
      };
    }

    fetch(STATUS_URL, {cache: "no-store", signal: controller.signal})      .then((response) => response.json())
      .then((data: {available?: boolean; detail?: string | null}) => {
        if (disposed) return;
        if (data.available === false) {
          fail(data.detail ?? "servicio de datos detenido");
          return;
        }
        open();
      })
      .catch(() => {
        if (disposed) return;
        // El endpoint de estado no respondió: se intenta el stream igualmente.
        open();
      });

    return () => {
      disposed = true;
      controller.abort();
      source?.close();
    };
  }, [enabled, interval, symbol]);

  // Si el estado acumulado no pertenece al símbolo/intervalo actual (cambio
  // rápido) se devuelve vacío: nunca se presenta un feed de otro contrato.
  const matches = view.status === null
    || (view.status.symbol === symbol && view.status.interval === interval);
  return enabled && matches ? view : EMPTY_VIEW;
}
