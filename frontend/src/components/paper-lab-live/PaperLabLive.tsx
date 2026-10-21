"use client";
import {useCallback, useEffect, useMemo, useState} from "react";
import {
  createSessionApi, evaluateSessionApi, exitSessionApi, formatMoneyPL,
  formatPricePL, formatPctPL, fmtUtcPL, getSessionApi, listSessionsApi,
  restartSessionApi, sessionView, stepSessionApi, stopSessionApi,
  type PaperCandidateDecision, type PaperSessionConfig,
  type PaperSessionState, type PaperCandle,
} from "@/lib/paper-lab-live";
import {PAPER_FIXTURES, FIXTURE_IDS} from "@/lib/paper-fixtures";
import {FixtureSelector} from "./FixtureSelector";
import {LiveChart} from "./LiveChart";
import {PositionPanel} from "./PositionPanel";
import {PnLPanel} from "./PnLPanel";
import {EventLog} from "./EventLog";
import {SessionControls} from "./SessionControls";
import {ExportPanel} from "./ExportPanel";
import {SessionPersistence} from "./SessionPersistence";
import s from "./PaperLabLive.module.css";

type ApiError = { error: string; detail: string; status: number } | null;

interface PaperLabLiveProps {}
export default function PaperLabLive(): React.JSX.Element {
  const [state, setState] = useState<PaperSessionState | null>(null);
  const [savedSessions, setSavedSessions] = useState<import("@/lib/paper-lab-live").PaperSessionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [fixtureId, setFixtureId] = useState<string | null>(null);
  const [apiError, setApiError] = useState<ApiError>(null);

  // Genera un request_id único por acción lógica (idempotencia entre reintentos).
  const [requestIdCounter, setRequestIdCounter] = useState(0);
  const nextRequestId = useCallback(() => {
    const id = "req-" + Date.now() + "-" + requestIdCounter;
    setRequestIdCounter((n) => n + 1);
    return id;
  }, [requestIdCounter]);

  // Cargar sesiones guardadas al montar (persistencia real, survives refresh).
  useEffect(() => {
    listSessionsApi().then((sessions) => {
      if (sessions.ok) setSavedSessions(sessions.data ?? []);
    }).catch(() => { /* persistencia opcional */ });
  }, []);

  // Recupera el estado autoritativo desde el backend y lo establece.
  const recoverAuthoritative = useCallback(async (sessionId: string) => {
    const loaded = await getSessionApi(sessionId);
    if (loaded.ok && loaded.data) {
      setState(loaded.data);
      setApiError(null);
      return loaded.data;
    }
    return null;
  }, []);

  const createAndEvaluate = useCallback(async (
    id: string,
    ruleVersion: string | null,
  ) => {
    const entry = PAPER_FIXTURES[id];
    if (!entry) return;
    setLoading(true);
    setApiError(null);
    try {
      // 1. Crear sesión en sin_iniciar (sin decisión del cliente).
      const created = await createSessionApi(entry.config, entry.candles,
        entry.context);
      if (!created.ok || !created.data) return;
      setFixtureId(id);
      setState(created.data);

      // 2. Evaluar evidencia en T vía backend (run_backtest como autoridad).
      //    Se envía at_ms = reloj de sesión (created.data.clock_ms) para que el
      //    backend use el reloj de simulación y no la hora actual.
      const evaluated = await evaluateSessionApi(created.data.session_id, null,
        null, ruleVersion, created.data.clock_ms ?? null, nextRequestId());
      if (evaluated.ok && evaluated.data) setState(evaluated.data);
    } finally {
      setLoading(false);
    }
  }, [nextRequestId]);

  const handleSelectFixture = useCallback(async (id: string) => {
    // Regla experimental versionada, fijada antes de ejecutar.
    // Usamos una regla de ingeniería (control, no estrategia aprobada).
    setApiError(null);
    await createAndEvaluate(id, "ENGINEERING-FIXTURE-RULE-v1");
  }, [createAndEvaluate]);

  const handleSaveSession = useCallback(async () => {
    if (!state) return;
    const sessions = await listSessionsApi();
    if (sessions.ok) setSavedSessions(sessions.data ?? []);
  }, [state]);

  const handleLoadSession = useCallback(async (sessionId: string) => {
    setLoading(true);
    setApiError(null);
    try {
      const loaded = await getSessionApi(sessionId);
      if (loaded.ok && loaded.data) {
        setFixtureId(null);
        setState(loaded.data);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const handleEnter = useCallback(async () => {
    if (!state) return;
    setLoading(true);
    setApiError(null);
    try {
      // La entrada se ejecuta al pasar de en_espera a abierta en el backend
      // (step_forward con status en_espera aplica la entrada).
      const result = await stepSessionApi(state.session_id, nextRequestId(), state.revision);
      if (!result.ok) {
        setApiError({ error: result.error ?? "ERROR", detail: result.detail ?? "", status: result.status });
        if (result.status === 409) {
          await recoverAuthoritative(state.session_id);
        }
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
    setApiError(null);
    try {
      const result = await stepSessionApi(state.session_id, nextRequestId(), state.revision);
      if (!result.ok) {
        setApiError({ error: result.error ?? "ERROR", detail: result.detail ?? "", status: result.status });
        if (result.status === 409) {
          await recoverAuthoritative(state.session_id);
        }
        return;
      }
      if (result.data) setState(result.data);
    } finally {
      setLoading(false);
    }
  }, [state, nextRequestId, recoverAuthoritative]);

  const handleExit = useCallback(async () => {
    if (!state) return;
    setLoading(true);
    setApiError(null);
    try {
      const result = await exitSessionApi(state.session_id, nextRequestId(), state.revision);
      if (!result.ok) {
        setApiError({ error: result.error ?? "ERROR", detail: result.detail ?? "", status: result.status });
        if (result.status === 409) {
          await recoverAuthoritative(state.session_id);
        }
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
    setApiError(null);
    try {
      const result = await restartSessionApi(state.session_id, nextRequestId(), state.revision);
      if (!result.ok) {
        setApiError({ error: result.error ?? "ERROR", detail: result.detail ?? "", status: result.status });
        if (result.status === 409) {
          await recoverAuthoritative(state.session_id);
        }
        return;
      }
      if (result.data) setState(result.data);
    } finally {
      setLoading(false);
    }
  }, [state, nextRequestId, recoverAuthoritative]);

  const handleStop = useCallback(async () => {
    if (!state) return;
    setLoading(true);
    setApiError(null);
    try {
      const result = await stopSessionApi(state.session_id, nextRequestId(), state.revision);
      if (!result.ok) {
        setApiError({ error: result.error ?? "ERROR", detail: result.detail ?? "", status: result.status });
        if (result.status === 409) {
          await recoverAuthoritative(state.session_id);
        }
        return;
      }
      if (result.data) setState(result.data);
    } finally {
      setLoading(false);
    }
  }, [state, nextRequestId, recoverAuthoritative]);

  if (!state) {
    return (
      <section className={s.root} aria-label="Paper Lab ingeniería (fixtures)">
        <div className={s.labelStrip}>
          <span className={s.badge}><span className={s.dot} aria-hidden="true"></span>PAPER LAB</span>
          <span className={s.chip}>Ingeniería — backend como fuente de verdad</span>
        </div>
        <h1 className={s.title}>Paper Lab — simulación sobre fixtures</h1>
        <p className={s.subtitle}>
          Backend como fuente de verdad. Seleccione una fixture para iniciar
          un escenario, el backend evalúa la evidencia en T y decide
          (VIGILANDO / SIN_ENTRADA / DESCARTADO / ENTRADA_SIMULADA), luego
          ejecuta entrada, gestión y cierre. Sin capital real ni órdenes Binance.
        </p>
        <FixtureSelector onSelect={handleSelectFixture} selectedId={null} />
      </section>
    );
  }

  const {config, status, position, costs, events, result, clock_ms, cursor} = state;
  const v = sessionView(state);
  const open = position.open === true;
  const finished = status === "cerrada" || status === "detenida";
  const entryPx = config.entry_px;
  const stopPx = config.stop_px;
  // Salida ejecutada SOLO cuando run_backtest confirmó un fill de salida.
  // Nunca se usa position.mark_px como sustituto de precio de salida ejecutado.
  const exitExecuted = result?.exit_executed === true;
  const exitPx = exitExecuted ? (result?.exit_px ?? null) : null;
  const exitShown = finished && exitExecuted && exitPx != null;
  const gross = result?.gross_pnl ?? position.unrealized_gross ?? null;
  // "P&L neto realizado" usa realized_net; si es null (open_at_end), es "No realizado".
  const net = exitExecuted ? (result?.net_pnl ?? null) : null;
  const unrealized = position.unrealized_net;

  const decisionLabel = (d?: PaperCandidateDecision | null): string => {
    if (!d) return "—";
    const map: Record<string, string> = {
      VIGILANDO: "VIGILANDO",
      SIN_ENTRADA: "SIN ENTRADA (abstención)",
      DESCARTADO: "DESCARTADO",
      ENTRADA_SIMULADA: "ENTRADA SIMULADA",
    };
    return map[d] ?? d;
  };

  const fundingLabel = (f: number | null): string =>
    f == null ? "UNKNOWN (sin calendario)" : formatMoneyPL(f);

  // Velas conocidas en T (open_time_ms <= clock_ms) para el gráfico causal.
  const knownCandles = useMemo(() => {
    const T = clock_ms ?? 0;
    return state.candles.filter((c) => c.open_time_ms <= T);
  }, [state.candles, clock_ms]);

  // Velas de contexto conocidas en T.
  const knownContext = useMemo(() => {
    const T = clock_ms ?? 0;
    return state.context_candles.filter((c) => c.open_time_ms <= T);
  }, [state.context_candles, clock_ms]);

  // Clase CSS para el P&L neto realizado.
  let netClass = s.v;
  if (net != null) {
    netClass = net >= 0 ? s.v + " " + s.pos : s.v + " " + s.neg;
  }

  // Mostrar error de API (conflicto de revisión, etc.) si lo hay.
  const errorBanner = apiError ? (
    <div className={s.errorBanner} role="alert">
      <strong>Error del backend:</strong> {apiError.error}
      {apiError.detail && (
        <span> — {apiError.detail}</span>
      )}
      <button type="button" className={s.live} onClick={() => {
        setApiError(null);
        if (state) recoverAuthoritative(state.session_id);
      }}>
        Recuperar estado autoritativo
      </button>
    </div>
  ) : null;

  return (
    <section className={s.root} aria-label="Paper Lab ingeniería — simulación paper">
      <div className={s.labelStrip}>
        <span className={s.badge}><span className={s.dot} aria-hidden="true"></span>PAPER LAB</span>
        <span className={s.chip}>Ingeniería — backend como fuente de verdad</span>
      </div>
      <h1 className={s.title}>Paper Lab — simulación sobre fixtures</h1>
      <p className={s.subtitle}>
        Flujo: fixture → candidato → evaluación → decisión/abstención →
        posición → gestión → cierre/exportación. El backend ejecuta; el
        frontend solo presenta.
      </p>

      {errorBanner}

      {loading && (
        <p className={s.note}>Procesando en el backend…</p>
      )}

      <FixtureSelector onSelect={handleSelectFixture} selectedId={fixtureId} />

      <div className={s.statusRow}>
        <span className={s.chip}>{config.symbol}</span>
        <span className={s.chip}>{config.direction} · familia {config.interval}</span>
        <span className={s.chip} data-state={status}>
          Sesión: {status === "sin_iniciar" ? "SIN INICIAR" :
            status === "evaluando" ? "EVALUANDO" :
            status === "en_espera" ? "EN ESPERA" :
            status === "abierta" ? "ABIERTA" :
            status === "cerrada" ? "CERRADA" : "DETENIDA"}
        </span>
        <span className={s.chip}>Decisión: {decisionLabel(config.decision)}</span>
        <span className={s.chip}>Rev. {state.revision}</span>
        <span className={s.chip}>Paso {v.cursor} de {v.n}</span>
        <span className={s.clock}>{v.clockUtc ?? "—"}</span>
      </div>

      <div className={s.identStrip}>
        <span className={s.chip}>Notional {config.notional_usdt} USDT</span>
        <span className={s.chip}>Entrada {formatPricePL(entryPx)}</span>
        <span className={s.chip}>Stop {formatPricePL(stopPx)}</span>
        <span className={s.chip}>Horizonte {Math.round(config.horizon_ms / 60000)} min</span>
        <span className={s.chip}>Fees {config.fee_bps} bps · spread+slip {(config.spread_bps + config.slippage_bps)} bps</span>
        {config.hypothesis_id && (
          <span className={s.chip}>Hipótesis {config.hypothesis_id} v{config.hypothesis_version ?? "—"}</span>
        )}
        {config.rule_version && (
          <span className={s.chip}>Regla {config.rule_version}</span>
        )}
        <span className={s.mono}>{state.session_id}</span>
        <span className={s.mono}>config={state.config_hash}</span>
      </div>

      <SessionControls
        status={status}
        canEnter={v.canEnter}
        canStep={v.canStep}
        canExit={v.canExit}
        canRestart={v.canRestart}
        canStop={v.canStop}
        canDecide={v.canDecide}
        decision={config.decision ?? null}
        onDecide={() => {
          // La decisión ya se tomó en createAndEvaluate; este botón se muestra
          // solo en estados sin_iniciar/evaluando para re-evaluar.
        }}
        onEnter={handleEnter}
        onStep={handleStep}
        onExit={handleExit}
        onRestart={handleRestart}
        onStop={handleStop}
        stepMs={1200}
      />

      <div className={s.grid}>
        <section className={s.card} style={{gridColumn: "1 / -1"}} aria-label="Gráfico paper">
          <div className={s.chartHead}>
            <h3>Gráfico — velas y niveles ({config.interval}, cerrado)</h3>
          </div>
          <div className={s.chartLegend} aria-label="Leyenda del gráfico">
            <span><i className={s.swContext} aria-hidden="true"></i>contexto previo (atenuado)</span>
            <span><i className={s.swReplay} aria-hidden="true"></i>velas de operación</span>
            {open && <span><i className={s.swEntry} aria-hidden="true"></i>Entrada {formatPricePL(entryPx)}</span>}
            {open && !finished && <span><i className={s.swStop} aria-hidden="true"></i>Stop {formatPricePL(stopPx)}</span>}
            {exitShown && exitPx != null && <span><i className={s.swExit} aria-hidden="true"></i>Cierre {formatPricePL(exitPx)}</span>}
            <span><i className={s.swCursor} aria-hidden="true"></i>cursor</span>
          </div>
          <div className={s.chartWrap}>
            <LiveChart
              candles={knownCandles}
              contextCandles={knownContext}
              entryPx={open ? entryPx : null}
              stopPx={open ? stopPx : null}
              exitPx={exitPx}
              exitShown={exitShown}
              currentTimeMs={clock_ms}
              direction={config.direction}
            />
          </div>
          <p className={s.note}>
            Solo velas conocidas en T (open_time_ms menor o igual al reloj de
            simulación); sin ticks ni recorrido intrabar inventado. Los niveles
            aparecen cuando son relevantes.
          </p>
        </section>

        <section className={s.card}>
          <PositionPanel position={position} direction={config.direction} />
        </section>
        <section className={s.card}>
          <PnLPanel
            finished={finished}
            entered={open}
            costs={costs}
            unrealized={unrealized}
            result={result}
            exitExecuted={exitExecuted}
          />
        </section>
      </div>

      <div className={s.grid}>
        <section className={s.card} style={{gridColumn: "1 / -1"}}>
          <EventLog events={events} />
        </section>
        <section className={s.card}>
          <ExportPanel
            state={state}
            result={result}
            onDownloadJson={(payload, fileName) => {
              const blob = new Blob([payload], {type: "application/json"});
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url; a.download = fileName; a.click();
              URL.revokeObjectURL(url);
            }}
            onDownloadCsv={(payload, fileName) => {
              const blob = new Blob([payload], {type: "text/csv"});
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url; a.download = fileName; a.click();
              URL.revokeObjectURL(url);
            }}
          />
        </section>
      </div>

      <SessionPersistence
        sessions={savedSessions}
        onLoad={handleLoadSession}
        onSave={handleSaveSession}
      />

      {finished && result && (
        <section className={s.card} aria-label="Resumen final">
          <h3>Resumen final (sesión cerrada)</h3>
          <div className={s.row}><span className={s.k}>Símbolo</span><span className={s.v}>{result.symbol}</span></div>
          <div className={s.row}><span className={s.k}>Dirección</span><span className={s.v}>{result.direction}</span></div>
          <div className={s.row}><span className={s.k}>Decisión</span><span className={s.v}>{decisionLabel(config.decision)}</span></div>
          <div className={s.row}><span className={s.k}>Entrada</span><span className={s.v}>{formatPricePL(result.entry_px)}</span></div>
          <div className={s.row}><span className={s.k}>Salida</span><span className={s.v}>{exitPx != null ? formatPricePL(exitPx) : "—"}</span></div>
          <div className={s.row}><span className={s.k}>Motivo de salida</span><span className={s.v}>{result.exit_reason ?? "—"}</span></div>
          <div className={s.row}><span className={s.k}>Salida ejecutada</span><span className={s.v}>{result.exit_executed ? "Sí" : "No"}</span></div>
          <div className={s.row}><span className={s.k}>Posición abierta al final</span><span className={s.v}>{result.open_at_end ? "Sí" : "No"}</span></div>
          <div className={s.row}><span className={s.k}>P&L bruto</span><span className={result.gross_pnl >= 0 ? s.v + " " + s.pos : s.v + " " + s.neg}>{formatMoneyPL(result.gross_pnl)}</span></div>
          <div className={s.row}><span className={s.k}>Costes totales (ejecutados)</span><span className={s.v}>{formatMoneyPL(result.friction)}</span></div>
          <div className={s.row}><span className={s.k}>Funding</span><span className={s.v}>{fundingLabel(result.funding)}</span></div>
          <div className={s.row}><span className={s.k}>P&L neto realizado</span><span className={netClass}>{net != null ? formatMoneyPL(net) : "No realizado"}</span></div>
          <p className={s.note}>
            {result.open_at_end
              ? "Fin de datos: la posición permanece abierta y no realizada (sin comisión de salida inventada)."
              : "Resultado congelado al cierre."}
            Puede exportarlo o iniciar una nueva sesión.
          </p>
        </section>
      )}
    </section>
  );
}
