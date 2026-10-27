"use client";

import {
  useCallback, useEffect, useRef, useState,
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
  buildEngineeringConfig, splitContextAndOperation, lastContextClose,
  ENGINEERING_RULE_VERSION,
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

// Dos prefijos de datos sobre el MISMO simbolo y la MISMA configuracion de
// sesion. Se usan solo para demostrar que, bajo igual configuracion, un
// prefijo admite entrada y el otro se abstiene (no es un escaner ni una
// estrategia rentable).
const PREFIX_CONTEXT_COUNT: Record<"A" | "B", number> = { A: 20, B: 35 };

interface EngineeringSessionProps {
  symbol?: string;
  interval?: string;
  bars?: number;
}

export default function EngineeringSession({
  symbol = "MINAUSDT",
  interval = "1m",
  bars = 90,
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
  const [prefixOption, setPrefixOption] = useState<"A" | "B">("A");
  // entry_px se fija UNA VEZ (antes de evaluar): cierre de la ultima vela de
  // contexto (precio conocido ANTES de la ventana de operacion). Nunca es el
  // cierre de la vela de entrada, con lo que la regla no garantiza entrada por
  // igualdad automatica. Al cambiar de prefijo se conserva.
  const [entryPxFixed, setEntryPxFixed] = useState<number | null>(null);

  // clock_ms del estado autoritativo aplicado por última vez. Se usa para
  // detectar cambios de T (incluido Entrar) y evitar mostrar valores de un T
  // anterior como si fueran actuales mientras se recarga el contexto.
  const lastClockRef = useRef<number | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const [requestIdCounter, setRequestIdCounter] = useState(0);
  const nextRequestId = useCallback(() => {
    const id = "eng-req-" + Date.now() + "-" + requestIdCounter;
    setRequestIdCounter((n) => n + 1);
    return id;
  }, [requestIdCounter]);

  // Pide indicadores / contexto BTC / flujo al backend con el reloj T de la
  // sesion: solo velas conocidas en T, sin futuros. Fuente solo lectura
  // (--no-fetch: cero upstream). symbol/interval se toman de la identidad
  // autoritativa (config de la sesion recuperada) cuando se pasan; de las
  // props del componente para una sesion nueva.
  const loadContextForClock = useCallback(async (atMs: number | null,
    symbolOverride?: string, intervalOverride?: string) => {
    if (atMs == null) return;
    const sym = symbolOverride ?? symbol;
    const ivl = intervalOverride ?? interval;
    const series = await fetchMarketSeries(sym, ivl, bars, atMs, true);
    if (!series) return;
    const receivedAt = Date.now();
    const all = marketCandlesToPaper(series.candles, receivedAt);
    const { context, operation } = splitContextAndOperation(
      all, PREFIX_CONTEXT_COUNT[prefixOption],
    );
    setMarketSeries({
      candles: operation,
      context,
      indicators: series.indicators,
      contextBtc: series.context_btc,
      coverage: "NO_COVERAGE",
      receivedAt,
    });
  }, [symbol, interval, bars, prefixOption]);

  // Actualizacion centralizada de la vista tras cada respuesta autoritativa.
  // Si clock_ms cambia respecto del T aplicado (incluido Entrar), descarta el
  // contexto anterior (no se muestran valores de otro T como actuales) y
  // recarga indicadores / contexto BTC / flujo para el nuevo T con la
  // identidad autoritativa de la sesion (config.symbol / config.interval).
  const applyAuthoritative = useCallback(async (next: PaperSessionState | null) => {
    if (!next) {
      setState(null);
      setMarketSeries(null);
      lastClockRef.current = null;
      setRefreshing(false);
      return;
    }
    const prevClock = lastClockRef.current;
    const clockChanged = prevClock !== null && prevClock !== next.clock_ms;
    const initialLoad = prevClock === null;
    if (clockChanged) {
      setRefreshing(true);
      setMarketSeries(null); // valores de T anterior no se muestran como actuales
    }
    setState(next);
    lastClockRef.current = next.clock_ms ?? null;
    try {
      if ((initialLoad || clockChanged) && next.clock_ms != null) {
        await loadContextForClock(next.clock_ms, next.config.symbol, next.config.interval);
      }
    } finally {
      setRefreshing(false);
    }
  }, [loadContextForClock]);

  // Recupera el estado autoritativo tras recarga (incluida posicion abierta)
  // y reconstruye el contexto de mercado con el reloj T de la sesion. La
  // identidad (simbolo/intervalo) se toma del config de la sesion recuperada,
  // nunca de las propiedades por defecto del componente.
  const recoverAuthoritative = useCallback(async (sessionId: string) => {
    const loaded = await getSessionApi(sessionId);
    if (loaded.ok && loaded.data) {
      await applyAuthoritative(loaded.data);
      setStarted(true);
      setError(null);
      return loaded.data;
    }
    setError(loaded.error ?? "SESSION_LOAD_FAILED");
    return null;
  }, [applyAuthoritative]);

  useEffect(() => {
    const stored = typeof localStorage !== "undefined"
      ? localStorage.getItem(SESSION_ID_STORAGE_KEY)
      : null;
    if (stored && !state) {
      const handle = setTimeout(() => {
        void recoverAuthoritative(stored).catch(() => { /* persistencia opcional */ });
      }, 0);
      return () => clearTimeout(handle);
    }
  }, [state, recoverAuthoritative]);

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
      const contextCount = PREFIX_CONTEXT_COUNT[prefixOption];
      // Tomar solo las ultimas (contexto + operacion necesaria) velas para
      // mantener el payload de la linea de comandos acotado (evitar
      // WinError 206 / linea de comandos demasiado larga en Windows).
      const operationNeeded = 40; // suficiente para horizonte + pasos
      const window = contextCount + operationNeeded;
      const recent = all.slice(Math.max(0, all.length - window));
      if (recent.length < contextCount + 2) {
        setError("INSUFICIENT_CANDLES: cache local sin suficientes velas para contexto + operacion.");
        setLoading(false);
        return;
      }

      const { context, operation } = splitContextAndOperation(recent, contextCount);
      const firstOp = operation[0];
      if (operation.length === 0 || !firstOp || firstOp.close == null || firstOp.close_time_ms == null) {
        setError("INSUFICIENT_CANDLES: la primera vela de operacion no tiene cierre definido.");
        setLoading(false);
        return;
      }

      // Fijar entry_px UNA VEZ antes de evaluar: cierre de la ultima vela de
      // contexto (precio conocido ANTES de la ventana de operacion). Nunca es
      // el cierre de la vela de entrada, con lo que la regla no garantiza
      // entrada por igualdad automatica. Al cambiar de prefijo se conserva.
      let entryPx = entryPxFixed;
      if (entryPx == null) {
        entryPx = lastContextClose(context);
        if (entryPx == null) {
          setError("CLOCK_REQUIRED: no se pudo establecer el precio de referencia.");
          setLoading(false);
          return;
        }
        setEntryPxFixed(entryPx);
      }

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
      // applyAuthoritative (carga inicial) reconstruye indicadores/contexto
      // para el reloj T con la identidad autoritativa de la sesion.
      await applyAuthoritative(evaluated.data);
      setStarted(true);
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setLoading(false);
    }
  }, [symbol, interval, bars, prefixOption, entryPxFixed, applyAuthoritative, nextRequestId]);

  const changePrefix = useCallback(async (next: "A" | "B") => {
    if (!state) return;
    setPrefixOption(next);
    // Volver a crear y evaluar con la MISMA entry_px fija pero distinto
    // prefijo de datos, para demostrar admision vs abstencion bajo igual
    // configuracion.
    setLoading(true);
    setError(null);
    try {
      const series = await fetchMarketSeries(symbol, interval, bars);
      if (!series || !series.candles || series.candles.length === 0) {
        setError("SERIES_EMPTY: no hay velas en cache local para el simbolo.");
        setLoading(false);
        return;
      }
      const receivedAt = Date.now();
      const all = marketCandlesToPaper(series.candles, receivedAt);
      const contextCount = PREFIX_CONTEXT_COUNT[next];
      const operationNeeded = 40;
      const window = contextCount + operationNeeded;
      const recent = all.slice(Math.max(0, all.length - window));
      if (recent.length < contextCount + 2) {
        setError("INSUFICIENT_CANDLES: cache local sin suficientes velas.");
        setLoading(false);
        return;
      }
      const { context, operation } = splitContextAndOperation(recent, contextCount);
      const firstOp = operation[0];
      if (operation.length === 0 || !firstOp || firstOp.close == null || firstOp.close_time_ms == null) {
        setError("INSUFICIENT_CANDLES: primera vela de operacion sin cierre.");
        setLoading(false);
        return;
      }
      const entryPx = entryPxFixed;
      if (entryPx == null) {
        setError("ENTRY_PX_MISSING: precio de referencia no fijado.");
        setLoading(false);
        return;
      }
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
      // Cambio de prefijo: mismo T pero distinto corte de contexto; se
      // reconstruye el contexto con la nueva cantidad de velas de contexto.
      await applyAuthoritative(evaluated.data);
      await loadContextForClock(evaluated.data.clock_ms ?? null, symbol, interval);
      setStarted(true);
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setLoading(false);
    }
  }, [symbol, interval, bars, entryPxFixed, nextRequestId, applyAuthoritative, loadContextForClock, state]);

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
      if (result.data) await applyAuthoritative(result.data); // Entrar avanza T: contexto al nuevo reloj
    } finally {
      setLoading(false);
    }
  }, [state, nextRequestId, applyAuthoritative, recoverAuthoritative]);

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
        await applyAuthoritative(result.data); // Paso avanza T: contexto al nuevo reloj
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
            await applyAuthoritative(re.data);
          }
        }
      }
    } finally {
      setLoading(false);
    }
  }, [state, nextRequestId, applyAuthoritative, recoverAuthoritative]);

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
      if (result.data) await applyAuthoritative(result.data);
    } finally {
      setLoading(false);
    }
  }, [state, nextRequestId, applyAuthoritative, recoverAuthoritative]);

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
        await applyAuthoritative(result.data); // reinicio reestablece T
        localStorage.setItem(SESSION_ID_STORAGE_KEY, result.data.session_id);
      }
    } finally {
      setLoading(false);
    }
  }, [state, nextRequestId, applyAuthoritative, recoverAuthoritative]);

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
      if (result.data) await applyAuthoritative(result.data);
    } finally {
      setLoading(false);
    }
  }, [state, nextRequestId, applyAuthoritative, recoverAuthoritative]);

  // sessionReady es un objeto combinado que TypeScript puede reducir a
  // no-nulo dentro de la rama correspondiente del condicional JSX.
  const sessionReady = state && marketSeries ? { state, marketSeries } : null;

  const cfg = state?.config;
  const pos = state?.position;
  const csts = state?.costs;
  const evts = state?.events ?? [];
  const res = state?.result;
  const clockMs = state?.clock_ms ?? null;
  const v = state ? sessionView(state) : null;
const vForReady = state ? sessionView(state) : null;
  const opn = pos?.open === true;
  const fin = state ? (state.status === "cerrada" || state.status === "detenida") : false;

  const chartModel = sessionReady
    ? buildPaperChartModel(
      {
        ...sessionReady.state,
        candles: sessionReady.state.candles.filter(
          (c) => c.open_time_ms <= (sessionReady.state.clock_ms ?? 0),
        ),
        context_candles: sessionReady.state.context_candles.filter(
          (c) => c.open_time_ms <= (sessionReady.state.clock_ms ?? 0),
        ),
      },
      { fixtureId: null },
    )
    : null;

  const abstentionReason =
    (cfg?.decision === "SIN_ENTRADA" || cfg?.decision === "DESCARTADO")
      ? cfg?.decision_reason ?? null
      : null;

  // sessionReady garantiza que state es no-nulo, por tanto v y chartModel
  // también lo son dentro de la rama correspondiente.
  const vReady = v!;
  const chartModelReady = chartModel!;

  return (
    <section className={s.root} aria-label="Sesion de ingenieria - transporte local">
      <header className={s.header}>
        <div className={s.titleBlock}>
          <h1>Sesion de ingenieria - transporte local</h1>
          <p className={s.subtitle}>
            Flujo: datos (cache local, 0 upstream) → grafico →
            indicadores / contexto BTC / flujo (recalculados en el backend con
            el reloj T de la sesion) → candidato → decision →
            posicion paper → gestion → cierre → exportacion. El backend es
            la autoridad; el navegador solo solicita acciones y presenta
            estados.
          </p>
        </div>
        <div className={s.actions}>
          <label className={s.prefixLabel}>Prefijo de datos:</label>
          <select
            value={prefixOption}
            onChange={(e) => changePrefix((e.target.value as "A" | "B") ?? "A")}
            disabled={loading || !!sessionReady || refreshing}
            className={s.prefixSelect}
          >
            <option value="A">A (admite entrada)</option>
            <option value="B">B (se abstiene)</option>
          </select>
          <button
            type="button"
            className={s.startButton}
            disabled={loading || started || !!sessionReady}
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
          <button
            type="button"
            className={s.recoverButton}
            onClick={() => state && recoverAuthoritative(state.session_id)}
          >
            Recuperar estado autoritativo
          </button>
        </div>
      )}

      {state ? (
        <div>
          {refreshing && marketSeries == null ? (
            <p className={s.note} role="status">
              Actualizando indicadores y contexto al reloj T de la sesión…
            </p>
          ) : null}
          {sessionReady ? (
            <div>
              <SessionStatusPanels
            state={sessionReady.state}
            marketSymbol={sessionReady.state.config.symbol}
            source="LOCAL SIMULADA - cache local (klines), client=None, 0 upstream"
            freshness={{
              received: vReady.cursor,
              cursor: vReady.cursor,
              total: vReady.n,
              clockMs: sessionReady.state.clock_ms,
              endOfData: fin && opn && res?.open_at_end === true,
              stale: false,
            }}
            indicators={sessionReady.marketSeries.indicators}
            contextBtc={sessionReady.marketSeries.contextBtc}
            flowCoverage={sessionReady.marketSeries.coverage}
            lastError={error}
            abstentionReason={abstentionReason}
          />

          <SessionControls
            status={sessionReady.state.status}
            canEnter={vReady.canEnter}
            canStep={vReady.canStep}
            canExit={vReady.canExit}
            canRestart={vReady.canRestart}
            canStop={vReady.canStop}
            canDecide={vReady.canDecide}
            decision={sessionReady.state.config.decision ?? null}
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
                  Grafico - velas, niveles y eventos (
                  {sessionReady.state.config.interval}, simulacion)
                </h3>
                <span className={s.sourceChip}>
                  Fuente: LOCAL SIMULADA ({sessionReady.state.config.symbol})
                </span>
              </div>
              <div className={s.chartLegend} aria-label="Leyenda del grafico">
                <span><i className={s.swContext} aria-hidden="true"></i> contexto conocido</span>
                <span><i className={s.swReplay} aria-hidden="true"></i> velas reveladas</span>
                <span><i className={s.swOpen} aria-hidden="true"></i> solo-open (open, sin OHLC)</span>
                {chartModelReady.operation.signal && (
                  <span><i className={s.swSignal} aria-hidden="true"></i> senal</span>
                )}
                {chartModelReady.operation.pending_entry && (
                  <span><i className={s.swPending} aria-hidden="true"></i> entrada pendiente (no ejecutada)</span>
                )}
                {chartModelReady.operation.entry && (
                  <span><i className={s.swEntry} aria-hidden="true"></i> Entrada {formatPricePL(chartModelReady.operation.entry.px)}</span>
                )}
                {chartModelReady.operation.stop_effective_px != null && (
                  <span><i className={s.swStop} aria-hidden="true"></i> Stop efectivo {formatPricePL(chartModelReady.operation.stop_effective_px)}</span>
                )}
                {chartModelReady.operation.exit && (
                  <span><i className={s.swExit} aria-hidden="true"></i> Salida {formatPricePL(chartModelReady.operation.exit.px)} ({chartModelReady.operation.exit.reason ?? "-"})</span>
                )}
              </div>
              <div className={s.chartWrap}>
                {chartModel && <PaperChart model={chartModel} />}
              </div>
              <p className={s.note}>
                Solo velas conocidas en T; open conocido al abrir y OHLC completo
                solo al cierre. La vela solo-open se marca como punto ambar y no
                se interpola. Entrada y stop salen de position.entry_px /
                position.stop_px efectivos; la salida solo se dibuja con
                exit_executed=true. Los indicadores y el contexto BTC se
                recalculan en el backend con el reloj T de la sesion (sin
                futuros); sin cobertura de flujo para el instante, se muestra
                UNKNOWN. Volumen e indicadores de negociacion no los produce el
                backend en esta fase: se muestran como UNKNOWN.
              </p>
            </section>
          </div>

          <div className={s.grid}>
            <section className={s.card}>
              <PositionPanel position={sessionReady.state.position} direction={sessionReady.state.config.direction} />
            </section>
            <section className={s.card}>
              <PnLPanel
                finished={fin}
                entered={opn}
                costs={csts!}
                unrealized={sessionReady.state.position.unrealized_net}
                result={res!}
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
                state={sessionReady.state}
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
                  <span className={s.v + " " + s.mono}>{sessionReady.state.session_id}</span>
                </div>
                <div className={s.row}>
                  <span className={s.k}>simbolo</span>
                  <span className={s.v}>{sessionReady.state.config.symbol}</span>
                </div>
                <div className={s.row}>
                  <span className={s.k}>intervalo</span>
                  <span className={s.v}>{sessionReady.state.config.interval}</span>
                </div>
                <div className={s.row}>
                  <span className={s.k}>config_hash</span>
                  <span className={s.v + " " + s.mono}>{sessionReady.state.config_hash}</span>
                </div>
                <div className={s.row}>
                  <span className={s.k}>motor</span>
                  <span className={s.v + " " + s.mono}>{sessionReady.state.engine_version}</span>
                </div>
                <div className={s.row}>
                  <span className={s.k}>regla</span>
                  <span className={s.v + " " + s.mono}>{sessionReady.state.config.rule_version}</span>
                </div>
                <div className={s.row}>
                  <span className={s.k}>reloj T</span>
                  <span className={s.v}>{fmtUtcPL(clockMs)}</span>
                </div>
                <div className={s.row}>
                  <span className={s.k}>revision</span>
                  <span className={s.v}>{sessionReady.state.revision}</span>
                </div>
                <div className={s.row}>
                  <span className={s.k}>prefijo</span>
                  <span className={s.v}>{prefixOption}</span>
                </div>
                <div className={s.row}>
                  <span className={s.k}>entry_px fijo</span>
                  <span className={s.v}>{entryPxFixed != null ? entryPxFixed.toFixed(4) : "-"}</span>
                </div>
              </div>
            </section>
          </div>

          </div>
          ) : (
            <p className={s.note}>
              Contexto de mercado sin cobertura para el reloj T actual (UNKNOWN).
            </p>
          )}
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
        </div>
      ) : (
        <section className={s.empty}>
          <p>Sesion no iniciada. Abrir el dashboard no inicia servicios ni operaciones.</p>
          <p className={s.emptyNote}>
            Seleccione un prefijo de datos y pulse Iniciar sesion para cargar
            {symbol} desde cache local, evaluar la evidencia en T y abrir la
            sesion de ingenieria.
          </p>
        </section>
      )}
    </section>
  );
}
