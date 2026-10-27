"use client";

import {
  useCallback, useEffect, useState,
} from "react";
import {
  evaluateSessionApi, exitSessionApi, formatMoneyPL,
  formatPricePL, fmtUtcPL, getSessionApi, listSessionsApi,
  restartSessionApi, sessionView, stepSessionApi, stopSessionApi,
  type PaperCandidateDecision, type PaperSessionConfig,
  type PaperSessionState, type PaperCandle,
} from "@/lib/paper-lab-live";
import { buildPaperChartModel } from "@/lib/paper-chart-contract";
import {
  createEngineeringSession, fetchMarketSeries, marketCandlesToPaper,
  buildEngineeringConfig, splitContextAndOperation, contextClock,
  lastContextClose, ENGINEERING_RULE_VERSION,
} from "@/lib/session-lab";
import { PaperChart } from "../paper-lab-live/PaperChart";
import { PositionPanel } from "../paper-lab-live/PositionPanel";
import { PnLPanel } from "../paper-lab-live/PnLPanel";
import { EventLog } from "../paper-lab-live/EventLog";
import { ExportPanel } from "../paper-lab-live/ExportPanel";
import { SessionControls } from "../paper-lab-live/SessionControls";
import { SessionPersistence } from "../paper-lab-live/SessionPersistence";
import { SessionStatusPanels } from "./SessionStatusPanels";
import s from "./EngineeringSession.module.css";

// Clave de persistencia del puntero de sesion (solo un identificador, nunca
// estado economico: el estado autoritativo vive en el backend).
const SESSION_ID_STORAGE_KEY = "paper-lab-sesion-ingenieria-id";

const EMPTY_CANDLES: PaperCandle[] = [];

interface EngineeringSessionProps {
  symbol?: string;
  interval?: string;
  bars?: number;
  contextCount?: number;
}

export default function EngineeringSession({
  symbol = "MINAUSDT",
  interval = "1m",
  bars = 80,
  contextCount = 20,
}: EngineeringSessionProps) {
  const [state, setState] = useState<PaperSessionState | null>(null);
  const [marketSeries, setMarketSeries] = useState<{
    candles: PaperCandle[];
    context: PaperCandle[];
    indicators: unknown;
    contextBtc: unknown;
    coverage: string;
    receivedAt: number;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);

  const [requestIdCounter, setRequestIdCounter] = useState(0);
  const nextRequestId = useCallback(() => {
    const id = "eng-req-" + Date.now() + "-" + requestIdCounter;
    setRequestIdCounter((n) => n + 1);
    return id;
  }, [requestIdCounter]);

  const recoverAuthoritative = useCallback(async (sessionId: string) => {
    const loaded = await getSessionApi(sessionId);
    if (loaded.ok && loaded.data) {
      setState(loaded.data);
      setStarted(true);
      setError(null);
      return loaded.data;
    }
    setError(loaded.error ?? "SESSION_LOAD_FAILED");
    return null;
  }, []);

  useEffect(() => {
    const stored = typeof localStorage !== "undefined"
      ? localStorage.getItem(SESSION_ID_STORAGE_KEY)
      : null;
    if (stored && !state) {
      getSessionApi(stored).then((loaded) => {
        if (loaded.ok && loaded.data) {
          setState(loaded.data);
          setStarted(true);
          setError(null);
        } else {
          setError(loaded.error ?? "SESSION_LOAD_FAILED");
        }
      }).catch(() => { /* persistencia opcional */ });
    }
  }, [state]);

  const startSession = useCallback(async () => {
    setLoading(true);
    setError(null);
    setStarted(false);
    try {
      const series = await fetchMarketSeries(symbol, interval, bars);
      if (!series || !series.candles || series.candles.length === 0) {
        setError("SERIES_EMPTY: no hay velas en cache local para el simbolo.");
        setLoading(false);
        return;
      }

      const receivedAt = Date.now();
      const all = marketCandlesToPaper(series.candles, receivedAt);
      if (all.length < contextCount + 2) {
        setError("INSUFICIENT_CANDLES: cache local sin suficientes velas para contexto + operacion.");
        setLoading(false);
        return;
      }

      const { context, operation } = splitContextAndOperation(all, contextCount);
      const firstOp = operation[0];
      if (operation.length === 0 || !firstOp || firstOp.close == null || firstOp.close_time_ms == null) {
        setError("INSUFICIENT_CANDLES: la primera vela de operacion no tiene cierre definido.");
        setLoading(false);
        return;
      }

      // Regla de ingeniería: T = cierre de la primera vela de operacion; el
      // precio de referencia de entrada es ese mismo cierre. La senal
      // RULE-CAUSAL-V1 se evalua sobre velas de operación conocidas en T.
      const entryPx = firstOp.close;
      const clock = firstOp.close_time_ms;

      const config: PaperSessionConfig = buildEngineeringConfig({
        symbol, interval, entryPx,
        horizonMs: 30 * 60 * 1000,
      });

      const created = await createEngineeringSession({
        config, candles: operation, context,
      });
      if (!created.ok || !created.session) {
        setError(created.error ?? "CREATE_FAILED");
        setLoading(false);
        return;
      }
      setState(created.session);
      localStorage.setItem(SESSION_ID_STORAGE_KEY, created.session.session_id);

      const evaluated = await evaluateSessionApi(
        created.session.session_id, null, null,
        ENGINEERING_RULE_VERSION, clock, nextRequestId(),
      );
      if (!evaluated.ok || !evaluated.data) {
        setError(evaluated.error ?? "EVALUATE_FAILED");
        setLoading(false);
        return;
      }
      setState(evaluated.data);

      setMarketSeries({
        candles: operation,
        context,
        indicators: series.indicators,
        contextBtc: series.context_btc,
        coverage: "NO_COVERAGE",
        receivedAt,
      });
      setStarted(true);
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setLoading(false);
    }
  }, [symbol, interval, bars, contextCount, nextRequestId]);

  const stopSession = useCallback(async () => {
    if (!state) return;
    setLoading(true);
    setError(null);
    try {
      const result = await stopSessionApi(state.session_id, nextRequestId(), state.revision);
      if (!result.ok) {
        setError(result.error ?? "STOP_FAILED");
        if (result.status === 409) await recoverAuthoritative(state.session_id);
        setLoading(false);
        return;
      }
      if (result.data) setState(result.data);
    } finally {
      setLoading(false);
    }
  }, [state, nextRequestId, recoverAuthoritative]);

  const handleEnter = useCallback(async () => {
    if (!state) return;
    setLoading(true);
    setError(null);
    try {
      const result = await stepSessionApi(state.session_id, nextRequestId(), state.revision);
      if (!result.ok) {
        setError(result.error ?? "ENTER_FAILED");
        if (result.status === 409) await recoverAuthoritative(state.session_id);
        setLoading(false);
        return;
      }
      if (result.data) setState(result.data);
    } finally {
      setLoading(false);
    }
  }, [state, nextRequestId, recoverAuthoritative]);

  const handleStep = useCallback(async () => {
    if (!state) return;
    setLoading(true);
    setError(null);
    try {
      const result = await stepSessionApi(state.session_id, nextRequestId(), state.revision);
      if (!result.ok) {
        setError(result.error ?? "STEP_FAILED");
        if (result.status === 409) await recoverAuthoritative(state.session_id);
        setLoading(false);
        return;
      }
      if (result.data) {
        setState(result.data);
        const advanced = result.data as PaperSessionState;
        if (advanced.status === "sin_iniciar" || advanced.status === "en_espera") {
          const re = await evaluateSessionApi(
            advanced.session_id, null, null, null,
            advanced.clock_ms ?? null, nextRequestId(), advanced.revision,
          );
          if (!re.ok) {
            setError(re.error ?? "REEVALUATE_FAILED");
            if (re.status === 409) await recoverAuthoritative(advanced.session_id);
          } else if (re.data) {
            setState(re.data);
          }
        }
      }
    } finally {
      setLoading(false);
    }
  }, [state, nextRequestId, recoverAuthoritative]);

  const handleExit = useCallback(async () => {
    if (!state) return;
    setLoading(true);
    setError(null);
    try {
      const result = await exitSessionApi(state.session_id, nextRequestId(), state.revision);
      if (!result.ok) {
        setError(result.error ?? "EXIT_FAILED");
        if (result.status === 409) await recoverAuthoritative(state.session_id);
        setLoading(false);
        return;
      }
      if (result.data) setState(result.data);
    } finally {
      setLoading(false);
    }
  }, [state, nextRequestId, recoverAuthoritative]);

  const handleRestart = useCallback(async () => {
    if (!state) return;
    setLoading(true);
    setError(null);
    try {
      const result = await restartSessionApi(state.session_id, nextRequestId(), state.revision);
      if (!result.ok) {
        setError(result.error ?? "RESTART_FAILED");
        if (result.status === 409) await recoverAuthoritative(state.session_id);
        setLoading(false);
        return;
      }
      if (result.data) {
        setState(result.data);
        localStorage.setItem(SESSION_ID_STORAGE_KEY, result.data.session_id);
      }
    } finally {
      setLoading(false);
    }
  }, [state, nextRequestId, recoverAuthoritative]);

  const handleDecide = useCallback(async (decision: PaperCandidateDecision) => {
    if (!state) return;
    setLoading(true);
    setError(null);
    try {
      const result = await evaluateSessionApi(
        state.session_id, null, null, null,
        state.clock_ms ?? null, nextRequestId(), state.revision,
      );
      if (!result.ok) {
        setError(result.error ?? "DECIDE_FAILED");
        if (result.status === 409) await recoverAuthoritative(state.session_id);
        setLoading(false);
        return;
      }
      if (result.data) setState(result.data);
    } finally {
      setLoading(false);
    }
  }, [state, nextRequestId, recoverAuthoritative]);

  const candlesForView = state?.candles ?? EMPTY_CANDLES;
  const contextForView = state?.context_candles ?? EMPTY_CANDLES;
  const clockForView = state?.clock_ms ?? 0;

  const chartModel = state
    ? buildPaperChartModel(
      {
        ...state,
        candles: candlesForView.filter((c) => c.open_time_ms <= clockForView),
        context_candles: contextForView.filter((c) => c.open_time_ms <= clockForView),
      },
      { fixtureId: null },
    )
    : null;

  return (
    <section className={s.root} aria-label="Sesion de ingenieria - transporte local">
      <header className={s.header}>
        <div className={s.titleBlock}>
          <h1>Sesion de ingenieria - transporte local</h1>
          <p className={s.subtitle}>
            Flujo: datos (cache local, 0 upstream), grafico,
            indicadores / contexto BTC / flujo, candidato, decision,
            posicion paper, gestion, cierre, exportacion. El backend es la
            autoridad; el navegador solo solicita acciones y presenta estados.
          </p>
        </div>
        <div className={s.actions}>
          <button
            type="button"
            className={s.startButton}
            disabled={loading || started}
            onClick={startSession}
            data-testid="btn-iniciar-sesion"
          >
            {loading ? "Iniciando..." : "Iniciar sesion"}
          </button>
          <button
            type="button"
            className={s.stopButton}
            disabled={loading || !started || !state}
            onClick={stopSession}
            data-testid="btn-detener-sesion"
          >
            Detener sesion
          </button>
        </div>
      </header>

      {error && (
        <div className={s.errorBanner} role="alert" data-testid="session-error">
          <strong>Error:</strong> {error}
          {state && (
            <button type="button" className={s.recoverButton} onClick={() => recoverAuthoritative(state.session_id)}>
              Recuperar estado autoritativo
            </button>
          )}
        </div>
      )}

      {started && state && marketSeries && (
        <div>
          {(() => {
            const view = sessionView(state);
            const cfg = state.config;
            const pos = state.position;
            const csts = state.costs;
            const evts = state.events;
            const res = state.result;
            const opn = pos.open === true;
            const fin = state.status === "cerrada" || state.status === "detenida";
            return (
              <>
                <SessionStatusPanels
                  state={state}
                  marketSymbol={cfg.symbol}
                  source="LOCAL SIMULADA - cache local (klines), client=None, 0 upstream"
                  freshness={{
                    received: view.cursor,
                    cursor: view.cursor,
                    total: view.n,
                    clockMs: state.clock_ms,
                    endOfData: fin && opn && res?.open_at_end === true,
                    stale: false,
                  }}
                  indicators={marketSeries.indicators}
                  contextBtc={marketSeries.contextBtc}
                  flowCoverage={marketSeries.coverage}
                  lastError={error}
                  abstentionReason={
                    (cfg.decision === "SIN_ENTRADA" || cfg.decision === "DESCARTADO")
                      ? cfg.decision_reason ?? null
                      : null
                  }
                />

                <SessionControls
                  status={state.status}
                  canEnter={view.canEnter}
                  canStep={view.canStep}
                  canExit={view.canExit}
                  canRestart={view.canRestart}
                  canStop={view.canStop}
                  canDecide={view.canDecide}
                  decision={cfg.decision ?? null}
                  onDecide={handleDecide}
                  onEnter={handleEnter}
                  onStep={handleStep}
                  onExit={handleExit}
                  onRestart={handleRestart}
                  onStop={stopSession}
                  stepMs={1200}
                />

                <div className={s.grid}>
                  <section className={s.cardFull} aria-label="Grafico de operacion">
                    <div className={s.chartHead}>
                      <h3>
                        Grafico - velas, niveles y eventos ({cfg.interval}, simulacion)
                      </h3>
                      <span className={s.sourceChip}>Fuente: LOCAL SIMULADA ({cfg.symbol})</span>
                    </div>
                    <div className={s.chartLegend} aria-label="Leyenda del grafico">
                      <span><i className={s.swContext} aria-hidden="true"></i> contexto conocido</span>
                      <span><i className={s.swReplay} aria-hidden="true"></i> velas reveladas</span>
                      <span><i className={s.swOpen} aria-hidden="true"></i> solo-open (open, sin OHLC)</span>
                      {chartModel?.operation.signal && (
                        <span><i className={s.swSignal} aria-hidden="true"></i> senal</span>
                      )}
                      {chartModel?.operation.pending_entry && (
                        <span><i className={s.swPending} aria-hidden="true"></i> entrada pendiente (no ejecutada)</span>
                      )}
                      {chartModel?.operation.entry && (
                        <span><i className={s.swEntry} aria-hidden="true"></i> Entrada {formatPricePL(chartModel.operation.entry.px)}</span>
                      )}
                      {chartModel?.operation.stop_effective_px != null && (
                        <span><i className={s.swStop} aria-hidden="true"></i> Stop efectivo {formatPricePL(chartModel.operation.stop_effective_px)}</span>
                      )}
                      {chartModel?.operation.exit && (
                        <span><i className={s.swExit} aria-hidden="true"></i> Salida {formatPricePL(chartModel.operation.exit.px)} ({chartModel.operation.exit.reason ?? "-"})</span>
                      )}
                    </div>
                    <div className={s.chartWrap}>
                      {chartModel && <PaperChart model={chartModel} />}
                    </div>
                    <p className={s.note}>
                      Solo velas conocidas en T; la vela solo-open se marca como punto
                      ambar (open conocido, high/low/close UNKNOWN) y no se interpola.
                      Entrada y stop salen de position.entry_px/stop_px efectivos; la
                      salida solo se dibuja con exit_executed=true. Volumen e
                      indicadores no los produce el backend en esta fase: se muestran
                      como UNKNOWN.
                    </p>
                  </section>
                </div>

                <div className={s.grid}>
                  <section className={s.card}>
                    <PositionPanel position={pos} direction={cfg.direction} />
                  </section>
                  <section className={s.card}>
                    <PnLPanel
                      finished={fin}
                      entered={opn}
                      costs={csts}
                      unrealized={pos.unrealized_net}
                      result={res}
                      exitExecuted={res?.exit_executed === true}
                    />
                  </section>
                </div>

                <div className={s.grid}>
                  <section className={s.cardFull}>
                    <h3>Historial de eventos</h3>
                    <EventLog events={evts} />
                  </section>
                </div>

                <div className={s.grid}>
                  <section className={s.card}>
                    <h3>Exportacion</h3>
                    <ExportPanel
                      state={state}
                      result={res ?? null}
                      onDownloadJson={(payload: string, fileName: string) => {
                        const blob = new Blob([payload], { type: "application/json" });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement("a");
                        a.href = url; a.download = fileName; a.click();
                        URL.revokeObjectURL(url);
                      }}
                      onDownloadCsv={(payload: string, fileName: string) => {
                        const blob = new Blob([payload], { type: "text/csv" });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement("a");
                        a.href = url; a.download = fileName; a.click();
                        URL.revokeObjectURL(url);
                      }}
                    />
                    <div className={s.exportMeta}>
                      <div className={s.row}>
                        <span className={s.k}>session_id</span>
                        <span className={s.v + " " + s.mono}>{state.session_id}</span>
                      </div>
                      <div className={s.row}>
                        <span className={s.k}>simbolo</span>
                        <span className={s.v}>{cfg.symbol}</span>
                      </div>
                      <div className={s.row}>
                        <span className={s.k}>intervalo</span>
                        <span className={s.v}>{cfg.interval}</span>
                      </div>
                      <div className={s.row}>
                        <span className={s.k}>config_hash</span>
                        <span className={s.v + " " + s.mono}>{state.config_hash}</span>
                      </div>
                      <div className={s.row}>
                        <span className={s.k}>motor</span>
                        <span className={s.v + " " + s.mono}>{state.engine_version}</span>
                      </div>
                      <div className={s.row}>
                        <span className={s.k}>regla</span>
                        <span className={s.v + " " + s.mono}>{cfg.rule_version}</span>
                      </div>
                      <div className={s.row}>
                        <span className={s.k}>reloj T</span>
                        <span className={s.v}>{fmtUtcPL(state.clock_ms)}</span>
                      </div>
                      <div className={s.row}>
                        <span className={s.k}>revision</span>
                        <span className={s.v}>{state.revision}</span>
                      </div>
                    </div>
                  </section>
                </div>

                <SessionPersistence
                  sessions={[]}
                  onLoad={recoverAuthoritative}
                  onSave={async () => {
                    const s = await listSessionsApi();
                    if (s.ok) {
                      // refrescar lista sin efectos
                    }
                  }}
                />
              </>
            );
          })()}
        </div>
      )}

      {!started && !error && (
        <section className={s.empty}>
          <p>Sesion no iniciada. Abrir el dashboard no inicia servicios ni operaciones.</p>
          <p className={s.emptyNote}>
            Pulsa Iniciar sesion para cargar {symbol} desde cache local,
            evaluar la evidencia en T y abrir la sesion de ingenieria.
          </p>
        </section>
      )}
    </section>
  );
}
