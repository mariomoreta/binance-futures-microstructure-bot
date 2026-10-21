"use client";
import {useCallback, useEffect, useMemo, useState} from "react";
import {
  createSessionApi, exitSessionApi, formatMoneyPL, formatPricePL,
  formatPctPL, fmtUtcPL, getSessionApi, listSessionsApi,
  restartSessionApi, sessionView, stepSessionApi, stopSessionApi,
  type PaperCandidateDecision, type PaperSessionConfig,
  type PaperSessionState, type PaperCandle,
  type PaperSessionSummary,
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

interface PaperLabLiveProps {}
export default function PaperLabLive(): React.JSX.Element {
  const [state, setState] = useState<PaperSessionState | null>(null);
  const [savedSessions, setSavedSessions] = useState<PaperSessionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [fixtureId, setFixtureId] = useState<string | null>(null);

  // Cargar sesiones guardadas al montar (persistencia real, survives refresh).
  useEffect(() => {
    listSessionsApi().then((sessions) => {
      setSavedSessions(sessions);
    }).catch(() => {/* persistencia opcional */});
  }, []);

  const createWithDecision = useCallback(async (
    id: string,
    decision: PaperCandidateDecision | null,
  ) => {
    const entry = PAPER_FIXTURES[id];
    if (!entry) return;
    setLoading(true);
    try {
      const created = await createSessionApi(entry.config, entry.candles,
        entry.context);
      if (created) {
        // Si se especifica decision, recrear con la decision fijada
        if (decision) {
          const decided = await createSessionApi({
            ...created.config,
            decision,
            hypothesis_id: "ENGINEERING-FIXTURE-v1",
            hypothesis_version: "1.0",
          }, created.candles, created.context_candles);
          if (decided) {
            setFixtureId(id);
            setState(decided);
          }
        } else {
          setFixtureId(id);
          setState(created);
        }
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSelectFixture = useCallback(async (id: string) => {
    await createWithDecision(id, null);
  }, [createWithDecision]);

  const handleDecide = useCallback(async (decision: PaperCandidateDecision) => {
    if (!fixtureId) return;
    await createWithDecision(fixtureId, decision);
  }, [fixtureId, createWithDecision]);

  const handleSaveSession = useCallback(async () => {
    const sessions = await listSessionsApi();
    setSavedSessions(sessions);
  }, [state]);

  const handleLoadSession = useCallback(async (sessionId: string) => {
    setLoading(true);
    try {
      const loaded = await getSessionApi(sessionId);
      if (loaded) {
        setFixtureId(null);
        setState(loaded);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const handleEnter = useCallback(async () => {
    if (!state) return;
    setLoading(true);
    try {
      const next = await stepSessionApi(state.session_id);
      if (next) setState(next);
    } finally {
      setLoading(false);
    }
  }, [state]);

  const handleStep = useCallback(async () => {
    if (!state) return;
    setLoading(true);
    try {
      const next = await stepSessionApi(state.session_id);
      if (next) setState(next);
    } finally {
      setLoading(false);
    }
  }, [state]);

  const handleExit = useCallback(async () => {
    if (!state) return;
    setLoading(true);
    try {
      const next = await exitSessionApi(state.session_id);
      if (next) setState(next);
    } finally {
      setLoading(false);
    }
  }, [state]);

  const handleRestart = useCallback(async () => {
    if (!state) return;
    setLoading(true);
    try {
      const next = await restartSessionApi(state.session_id);
      if (next) setState(next);
    } finally {
      setLoading(false);
    }
  }, [state]);

  const handleStop = useCallback(async () => {
    if (!state) return;
    setLoading(true);
    try {
      const next = await stopSessionApi(state.session_id);
      if (next) setState(next);
    } finally {
      setLoading(false);
    }
  }, [state]);

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
          un escenario, luego decida (VIGILANDO / SIN_ENTRADA / DESCARTADO /
          ENTRADA_SIMULADA) y el backend ejecuta entrada, gestión y cierre.
          Sin capital real ni órdenes Binance.
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
  const exitPx = result?.exit_px ?? position.mark_px ?? null;
  const exitShown = finished && !!exitPx;
  const gross = result?.gross_pnl ?? position.unrealized_gross ?? null;
  const net = result?.net_pnl ?? position.unrealized_net ?? null;

  const decisionLabel = (d?: PaperCandidateDecision | null) => {
    if (!d) return "—";
    const map: Record<string, string> = {
      VIGILANDO: "VIGILANDO",
      SIN_ENTRADA: "SIN ENTRADA (abstención)",
      DESCARTADO: "DESCARTADO",
      ENTRADA_SIMULADA: "ENTRADA SIMULADA",
    };
    return map[d] ?? d;
  };

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
        onDecide={handleDecide}
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
              candles={state.candles}
              contextCandles={state.context_candles}
              entryPx={open ? entryPx : null}
              stopPx={open ? stopPx : null}
              exitPx={exitPx}
              exitShown={exitShown}
              currentTimeMs={clock_ms}
              direction={config.direction}
            />
          </div>
          <p className={s.note}>
            Solo velas cerradas conocidas hasta el cursor; sin ticks ni
            recorrido intrabar inventado. Los niveles aparecen cuando son relevantes.
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
            unrealized={position.unrealized_net}
            result={result}
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
          <div className={s.row}><span className={s.k}>Salida</span><span className={s.v}>{result.exit_px != null ? formatPricePL(result.exit_px) : "—"}</span></div>
          <div className={s.row}><span className={s.k}>Motivo de salida</span><span className={s.v}>{result.exit_reason ?? "—"}</span></div>
          <div className={s.row}><span className={s.k}>P&L bruto</span><span className={`${s.v} ${result.gross_pnl >= 0 ? s.pos : s.neg}`}>{formatMoneyPL(result.gross_pnl)}</span></div>
          <div className={s.row}><span className={s.k}>Costes totales</span><span className={s.v}>{formatMoneyPL(result.friction)}</span></div>
          <div className={s.row}><span className={s.k}>P&L neto realizado</span><span className={`${s.v} ${result.net_pnl >= 0 ? s.pos : s.neg}`}>{formatMoneyPL(result.net_pnl)}</span></div>
          <div className={s.row}><span className={s.k}>Salida ejecutada</span><span className={s.v}>{result.exit_executed ? "Sí" : "No"}</span></div>
          <p className={s.note}>Resultado congelado al cierre. Puede exportarlo o iniciar una nueva sesión.</p>
        </section>
      )}
    </section>
  );
}
