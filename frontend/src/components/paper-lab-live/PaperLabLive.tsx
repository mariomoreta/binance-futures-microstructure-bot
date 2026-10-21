"use client";
import {useCallback, useEffect, useMemo, useRef, useState} from "react";
import {
  createPaperSession, stepForward, manualExit, restartSession, stopSession,
  selectOperation, sessionView, formatMoneyPL, formatPricePL, formatPctPL,
  fmtUtcPL, type PaperSessionState, type PaperSessionConfig,
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
  const [fixtureId, setFixtureId] = useState<string | null>(null);
  const [savedSessions, setSavedSessions] = useState<PaperSessionState[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const autoPlayingRef = useRef(false);

  // Cargar sesiones guardadas al montar.
  useEffect(() => {
    fetch("/api/v1/paper-lab/sessions", {cache: "no-store"})
      .then(async (r) => {
        if (!r.ok) return [];
        return r.json();
      })
      .then((data: unknown) => {
        const arr = Array.isArray(data) ? data : [];
        setSavedSessions(arr as PaperSessionState[]);
      })
      .catch(() => {/* ignore: persistencia opcional */});
  }, []);

  // Bucle de avance automatico (play): avanza un paso cada `stepMs` mientras
  // la sesion este abierta y no haya salido.
  const stepMs = 1200;
  useEffect(() => {
    return () => {
      if (intervalRef.current != null) clearInterval(intervalRef.current);
    };
  }, []);

  const view = useMemo(() => state ? sessionView(state) : null, [state]);

  const handleSelectFixture = useCallback((id: string, entry: typeof PAPER_FIXTURES[string] & {candles: any[]; context: any[]}) => {
    if (intervalRef.current != null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
      autoPlayingRef.current = false;
    }
    setFixtureId(id);
    setState(selectOperation(entry.config, entry.candles, entry.context));
  }, []);

  const handleSaveSession = useCallback(async (session: PaperSessionState) => {
    const r = await fetch("/api/v1/paper-lab/sessions", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(session),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json() as {sessions: PaperSessionState[]};
    setSavedSessions(data.sessions ?? []);
  }, []);

  const handleLoadSession = useCallback((session: PaperSessionState) => {
    if (intervalRef.current != null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
      autoPlayingRef.current = false;
    }
    setState(session);
    setFixtureId(null);
  }, []);

  const handleEnter = useCallback(() => {
    if (!state || state.status !== "en_espera") return;
    const next = { ...state, status: "abierta" as const, updated_at_ms: Date.now() };
    // stepForward ejecuta la entrada en el paso actual y avanza la gestion.
    const entered = stepForward(next);
    if (entered.kind === "step" || entered.kind === "exit_executed" || entered.kind === "finished") {
      setState(entered.state);
    }
  }, [state]);

  const handleStep = useCallback(() => {
    if (!state) return;
    const next = stepForward(state);
    if (next.kind === "step" || next.kind === "exit_executed" || next.kind === "finished") {
      setState(next.state);
    }
  }, [state]);

  const handleExit = useCallback(() => {
    if (!state) return;
    const next = manualExit(state);
    if (next.kind === "exit_executed" || next.kind === "finished") {
      setState(next.state);
    }
  }, [state]);

  const handleRestart = useCallback(() => {
    if (!state) return;
    setState(restartSession(state));
  }, [state]);

  const handleStop = useCallback(() => {
    if (!state) return;
    setState(stopSession(state));
  }, [state]);

  if (!state) {
    return (
      <section className={s.root} aria-label="Paper Lab en caliente (ingenieria)">
        <div className={s.labelStrip}>
          <span className={s.badge}><span className={s.dot} aria-hidden="true"></span>PAPER LAB EN CALIENTE</span>
          <span className={s.chip}>Ingenieria — fixtures, sin Binance en vivo</span>
        </div>
        <h1 className={s.title}>Paper Lab — simulacion en caliente</h1>
        <p className={s.subtitle}>
          Seleccione una operacion de fixture para simular entrada, gestion y
          salida con P&L en tiempo real. Los datos son sinteticos; no hay
          capital real ni ordenes Binance.
        </p>
        <FixtureSelector onSelect={handleSelectFixture} selectedId={null} />
      </section>
    );
  }

  const {config, status, position, costs, events, result, clock_ms, cursor} = state;
  const v = view!;
  const open = position.open === true;
  const finished = status === "cerrada" || status === "detenida";
  const entryPx = config.entry_px;
  const stopPx = config.stop_px;
  const exitPx = result?.exit_px ?? position.mark_px ?? null;
  const exitShown = finished && !!exitPx;
  const gross = result?.gross_pnl ?? position.unrealized_gross ?? null;
  const net = result?.net_pnl ?? position.unrealized_net ?? null;

  return (
    <section className={s.root} aria-label="Paper Lab en caliente — simulacion paper">
      <div className={s.labelStrip}>
        <span className={s.badge}><span className={s.dot} aria-hidden="true"></span>PAPER LAB EN CALIENTE</span>
        <span className={s.chip}>Ingenieria — fixtures, sin Binance en vivo</span>
      </div>
      <h1 className={s.title}>Paper Lab — simulacion en caliente</h1>
      <p className={s.subtitle}>
        Simulacion de entrada, gestion y salida sobre velas de fixture. El
        frontend no decide operaciones; solo ejecuta la simulacion que usted pide.
      </p>

      <FixtureSelector onSelect={handleSelectFixture} selectedId={fixtureId} />

      <div className={s.statusRow}>
        <span className={s.chip}>{config.symbol}</span>
        <span className={s.chip}>{config.direction} · familia {config.interval}</span>
        <span className={s.chip} data-state={status}>Sesion: {status === "sin_iniciar" ? "SIN INICIAR" : status === "en_espera" ? "EN ESPERA" : status === "abierta" ? "ABIERTA" : status === "cerrada" ? "CERRADA" : "DETENIDA"}</span>
        <span className={s.chip}>Paso {v.cursor} de {v.n}</span>
        <span className={s.clock}>{v.clockUtc ?? "—"}</span>
      </div>

      <div className={s.identStrip}>
        <span className={s.chip}>Notional {config.notional_usdt} USDT</span>
        <span className={s.chip}>Entrada {formatPricePL(entryPx)}</span>
        <span className={s.chip}>Stop {formatPricePL(stopPx)}</span>
        <span className={s.chip}>Horizonte {Math.round(config.horizon_ms / 60000)} min</span>
        <span className={s.chip}>Fees {config.fee_bps} bps · spread+slip {(config.spread_bps + config.slippage_bps)} bps</span>
        <span className={s.mono}>{state.session_id}</span>
      </div>

      <SessionControls
        status={status}
        canEnter={v.canEnter}
        canStep={v.canStep}
        canExit={v.canExit}
        canRestart={v.canRestart}
        canStop={v.canStop}
        onEnter={handleEnter}
        onStep={handleStep}
        onExit={handleExit}
        onRestart={handleRestart}
        onStop={handleStop}
        stepMs={stepMs}
      />

      <div className={s.grid}>
        <section className={s.card} style={{gridColumn: "1 / -1"}} aria-label="Grafico paper">
          <div className={s.chartHead}>
            <h3>Grafico — velas y niveles ({config.interval}, cerrado)</h3>
          </div>
          <div className={s.chartLegend} aria-label="Leyenda del grafico">
            <span><i className={s.swContext} aria-hidden="true"></i>contexto previo (atenuado)</span>
            <span><i className={s.swReplay} aria-hidden="true"></i>velas de operacion</span>
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
            Solo velas cerradas conocidas hasta el cursor; sin ticks ni recorrido
            intrabar inventado. Los niveles aparecen cuando son relevantes.
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
          <h3>Resumen final (sesion cerrada)</h3>
          <div className={s.row}><span className={s.k}>Simbolo</span><span className={s.v}>{result.symbol}</span></div>
          <div className={s.row}><span className={s.k}>Direccion</span><span className={s.v}>{result.direction}</span></div>
          <div className={s.row}><span className={s.k}>Entrada</span><span className={s.v}>{formatPricePL(result.entry_px)}</span></div>
          <div className={s.row}><span className={s.k}>Salida</span><span className={s.v}>{result.exit_px != null ? formatPricePL(result.exit_px) : "—"}</span></div>
          <div className={s.row}><span className={s.k}>Motivo de salida</span><span className={s.v}>{result.exit_reason ?? "—"}</span></div>
          <div className={s.row}><span className={s.k}>P&L bruto</span><span className={`${s.v} ${result.gross_pnl >= 0 ? s.pos : s.neg}`}>{formatMoneyPL(result.gross_pnl)}</span></div>
          <div className={s.row}><span className={s.k}>Costes totales</span><span className={s.v}>{formatMoneyPL(result.friction)}</span></div>
          <div className={s.row}><span className={s.k}>P&L neto realizado</span><span className={`${s.v} ${result.net_pnl >= 0 ? s.pos : s.neg}`}>{formatMoneyPL(result.net_pnl)}</span></div>
          <div className={s.row}><span className={s.k}>Salida ejecutada</span><span className={s.v}>{result.exit_executed ? "Si" : "No"}</span></div>
          <p className={s.note}>Resultado congelado al cierre. Puede exportarlo o iniciar una nueva sesion.</p>
        </section>
      )}
    </section>
  );
}
