"use client";

// Sesión de ingeniería — paneles de estado (seis eslabones visibles y
// separados). Todo deriva del estado recibido del backend; este componente no
// calcula decisiones ni estado económico.

import type { PaperSessionState } from "@/lib/paper-lab-live";
import { sessionView } from "@/lib/paper-lab-live";

interface SessionStatusPanelsProps {
  state: PaperSessionState | null;
  marketSymbol: string | null;
  source: string | null;
  /** Evento disparador de la última evaluación (del drive del backend). */
  lastTrigger: {
    frame?: string | null;
    open_time_ms?: number | null;
    close_time_ms?: number | null;
    received_at_ms?: number | null;
  } | null;
  /** Instante de evaluación del último gate (pared del backend). */
  evaluatedAtMs: number | null;
  freshness: {
    received: number;      // velas recibidas en la ventana
    cursor: number;        // reloj de revelación
    total: number;         // velas disponibles
    clockMs: number | null;
    endOfData: boolean;    // sin más velas tras T
    stale: boolean;        // dato obsoleto respecto de T
  };
  indicators: unknown;
  contextBtc: unknown;
  flowCoverage: string;    // p. ej. "NO_COVERAGE" / "LIVE"
  lastError: string | null;
  abstentionReason: string | null;
}

function fmtMs(ms: number | null): string {
  if (ms == null) return "—";
  return new Date(ms).toISOString().replace(/\.000Z$/, "Z");
}

function toneForStatus(status: string): "info" | "pos" | "neg" | "warn" | "muted" {
  switch (status) {
    case "abierta": return "pos";
    case "cerrada": return "info";
    case "en_espera": return "warn";
    case "detenida": return "neg";
    case "evaluando": return "info";
    default: return "muted";
  }
}

export function SessionStatusPanels({
  state,
  marketSymbol,
  source,
  lastTrigger,
  evaluatedAtMs,
  freshness,
  indicators,
  contextBtc,
  flowCoverage,
  lastError,
  abstentionReason,
}: SessionStatusPanelsProps) {
  const v = state ? sessionView(state) : null;
  const status = state?.status ?? "—";
  const decision = state?.config?.decision ?? null;
  const decisionReason = state?.config?.decision_reason ?? null;
  const config = state?.config;
  const position = state?.position;
  const costs = state?.costs;
  const result = state?.result;

  return (
    <section className="session-panels" aria-label="Estado de la sesión de ingeniería">
      <div className="panelGrid">
        {/* 1. Estado de la sesión */}
        <section className="panel">
          <h3>Estado de la sesión</h3>
          <div className="value big" data-testid="panel-session-status">
            {status === "—" ? "—" : status.replace(/_/g, " ")}
          </div>
          <div className="meta">
            <span>Revisión <span className="mono">{state?.revision ?? "—"}</span></span>
            {state?.session_id && (
              <span className="mono small">{state.session_id}</span>
            )}
          </div>
          <p className="hint">
            {status === "sin_iniciar"
              ? "Creada, sin evidencia evaluada en T."
              : status === "evaluando"
                ? "Evaluando evidencia en T (backend)."
                : status === "en_espera"
                  ? "Entrada simulada pendiente de fill."
                  : status === "abierta"
                    ? "Posición abierta, pendiente de salida."
                    : status === "cerrada"
                      ? "Escenario cerrado (salida ejecutada o fin de datos)."
                      : status === "detenida"
                        ? "Detenida por el usuario (posición congelada)."
                        : "Sin estado."}
          </p>
        </section>

        {/* 2. Fuente de datos (identificada explícitamente) */}
        <section className="panel">
          <h3>Fuente de datos</h3>
          <div className="value" data-testid="panel-source">
            {source ?? "—"}
          </div>
          <div className="meta">
            <span>
              {marketSymbol ? `Símbolo: <span className="mono">{marketSymbol}</span>` : "Símbolo: —"}
            </span>
            <br />
            <span className="muted">{source && source.includes("LIVE")
              ? "Servicio de mercado (SSE, solo loopback) · velas cerradas conducen"
              : "Caché local (klines) · client=None · 0 upstream"}</span>
          </div>
          <p className="hint">
            {source && source.includes("LIVE")
              ? "Fuente: DEMOSTRACIÓN LOCAL (datos simulados, productor WS loopback + servicio de mercado --transport local). Nunca Binance público en este bloque."
              : "Fuente: LOCAL SIMULADA. Los velas son replay de caché local; no se declara Binance LIVE ni se adquieren datos públicos."}
          </p>
        </section>

        {/* 3. Recepción / frescura de datos */}
        <section className="panel">
          <h3>Recepción / frescura</h3>
          <div className="value" data-testid="panel-freshness">
            {freshness.received} / {freshness.total} velas
          </div>
          <div className="meta">
            <span>Paso <span className="mono">{freshness.cursor}</span> de <span className="mono">{freshness.total}</span></span>
            <br />
            <span>Reloj T: {fmtMs(freshness.clockMs)}</span>
          </div>
          <p className="hint">
            {freshness.endOfData
              ? "Fin de datos: no hay más velas tras T (fixture/caché agotada)."
              : freshness.stale
                ? "Dato obsoleto respecto de T."
                : "Datos recibidos al cursor de sesión."}
          </p>
        </section>

        {/* 4. Evaluador */}
        <section className="panel">
          <h3>Evaluador (T)</h3>
          <div className="value" data-testid="panel-evaluator">
            {decision === null ? "—" : decision}
          </div>
          <div className="meta">
            {config?.rule_version && (
              <span>Regla <span className="mono">{config.rule_version}</span></span>
            )}
            <br />
            <span>Velas conocidas: {state ? v?.n ?? 0 : 0}</span>
          </div>
          <p className="hint">
            {decisionReason ?? abstentionReason ?? "Sin evaluación aún."}
          </p>
        </section>

        {/* 5. Última evaluación (evento / T / regla / decisión / motivo) */}
        <section className="panel">
          <h3>Última evaluación</h3>
          <div className="value" data-testid="panel-last-eval-decision">
            {decision === null ? "—" : decision}
          </div>
          <div className="meta">
            {config?.rule_version && (
              <span>Regla <span className="mono">{config.rule_version}</span></span>
            )}
            <br />
            {lastTrigger && (
              <>
                <span>
                  Evento: <span className="mono">{lastTrigger.frame ?? "—"}</span>
                </span>
                <br />
                <span>
                  open {fmtMs(lastTrigger.open_time_ms ?? null)} → close{' '}
                  <span className="mono">{fmtMs(lastTrigger.close_time_ms ?? null)}</span>
                  <br />
                  received {fmtMs(lastTrigger.received_at_ms ?? null)}
                </span>
              </>
            )}
            <br />
            <span>
              T: <span className="mono">{fmtMs(state?.clock_ms ?? null)}</span>{" "}
              {evaluatedAtMs != null && (
                <>
                  · evaluado{' '}
                  <span className="mono">{fmtMs(evaluatedAtMs)}</span>
                </>
              )}
            </span>
          </div>
          <p className="hint">
            {decisionReason ?? abstentionReason ?? "Sin evaluación aún."}
          </p>
        </section>

        {/* 6. Posición paper */}
        <section className="panel">
          <h3>Posición paper</h3>
          <div className="value" data-testid="panel-position">
            {position?.open === true ? "ABIERTA" : "CERRADA / SIN POSICIÓN"}
          </div>
          <div className="meta">
            <span>Entrada {position?.entry_px != null ? position.entry_px.toFixed(4) : "—"}</span>
            <br />
            <span>Stop {position?.stop_px != null ? position.stop_px.toFixed(4) : "—"}</span>
            <br />
            <span>Marca {position?.mark_px != null ? position.mark_px.toFixed(4) : "—"}</span>
          </div>
          <p className="hint">
            {position?.open === true
              ? `No real. ${position.unrealized_net != null ? position.unrealized_net.toFixed(2) : "—"} USDT`
              : result?.exit_executed === true
                ? `Salida ${result.exit_reason ?? "—"} @ ${result.exit_px != null ? result.exit_px.toFixed(4) : "—"}`
                : "Sin posición ejecutada."}
          </p>
        </section>

        {/* 7. Último error / motivo de abstención */}
        <section className="panel">
          <h3>Último error / abstención</h3>
          <div className="value warn" data-testid="panel-error">
            {lastError ?? (abstentionReason ?? "—")}
          </div>
          <div className="meta">
            <span>Flujo: {flowCoverage === "NO_COVERAGE" ? "sin cobertura (UNKNOWN)" : flowCoverage}</span>
            <br />
            <span>
              Contexto BTC:{" "}
              {contextBtc == null || (contextBtc as { unknown?: boolean })?.unknown
                ? "UNKNOWN (motivo BTC_*)"
                : "disponible"}
            </span>
          </div>
          <p className="hint">
            {lastError ? "Error del backend comunicado al cliente." : abstentionReason ? "Abstención por evidencia insuficiente en T." : "Sin errores ni abstenciones."}
          </p>
        </section>
      </div>

      {/* Contexto de mercado (indicadores / BTC / flujo) como referencia informativa */}
      <section className="contextBlock">
        <h3>Contexto de mercado (referencia, no señal)</h3>
        <div className="contextRow">
          <div className="contextItem">
            <div className="label">market-indicators/v1</div>
            <div className="mono small" data-testid="ctx-indicators">
              {indicators == null ? "—" : JSON.stringify(indicators).slice(0, 120)}
            </div>
          </div>
          <div className="contextItem">
            <div className="label">market-btc-context/v1</div>
            <div className="mono small" data-testid="ctx-btc">
              {contextBtc == null ? "—" : JSON.stringify(contextBtc).slice(0, 120)}
            </div>
          </div>
          <div className="contextItem">
            <div className="label">market-flow/v1</div>
            <div className="mono small" data-testid="ctx-flow">
              {flowCoverage === "NO_COVERAGE"
                ? "NO_COVERAGE_BEFORE_FIRST_EVENT (UNKNOWN)"
                : flowCoverage}
            </div>
          </div>
        </div>
        <p className="note">
          Indicadores y contexto BTC son referencia informativa calculada por
          el backend sobre velas cerradas del caché local. No son señal, no son
          filtro de entrada y la diferencia de retornos no es alpha. Sin
          cobertura de flujo histórico → UNKNOWN.
        </p>
      </section>
    </section>
  );
}
