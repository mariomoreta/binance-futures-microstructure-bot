"use client";
import {useCallback, useEffect, useMemo, useRef, useState} from "react";
import artifactJson from "@/artifacts/paper-lab-replay-v1.json";
import {parsePaperLabReplay, msPerStep, replayPositionState, directionLabel, closeActionLabel, playerState, playerStateLabel, contextCandlesKnownAt, type ReplayStatus, type ReplayStepView, type ReplayCandle, type ReplayEvent} from "@/lib/paper-lab-replay";
import {formatPrice, formatMoney} from "@/lib/format";
import {ReplayControls} from "./ReplayControls";
import {ReplayChart} from "./ReplayChart";
import {PositionPanel, PnLPanel, EventLog, ProvenancePanel} from "./PaperLabPanels";
import s from "./PaperLab.module.css";

interface ReplayUnavailableProps { message: string; }
export function ReplayUnavailable({message}: ReplayUnavailableProps) {
  return (
    <section className={s.root}>
      <div className={s.labelStrip}>
        <span className={s.badge}><span className={s.dot} aria-hidden="true"></span>REPLAY HISTÓRICO</span>
        <span className={s.chip}>Estado del replay (independiente del monitor)</span>
      </div>
      <h1 className={s.title}>Paper Lab</h1>
      <p className={s.subtitle}>Replay historico de una operacion registrada — no simulacion prospectiva, no senal de trading.</p>
      <div className={s.card} style={{borderColor: "#7a2e3e"}}>
        <h3 style={{margin: "0 0 8px 0", fontSize: "13px", color: "#fb7185"}}>Fuente de replay no disponible</h3>
        <p className={s.note}>{message}</p>
        <p className={s.note}>No se muestran inventos ni mocks: si el artefacto falta o es incompatible, el panel queda en este estado.</p>
      </div>
    </section>
  );
}

function fmtUtc(ms: number | null | undefined): string {
  if (ms == null) return "—";
  return new Date(ms).toISOString().replace(/\.000Z$/, "Z");
}

export interface PaperLabReplayProps { source?: unknown; }
export default function PaperLabReplay({source = artifactJson}: PaperLabReplayProps) {
  const [status, setStatus] = useState<ReplayStatus>("idle");
  const [cursor, setCursor] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [zoom, setZoom] = useState(1);
  const intervalRef = useRef<number | null>(null);

  const parsedResult = useMemo(() => {
    try { return {parsed: parsePaperLabReplay(source), error: null}; }
    catch (error) {
      return {parsed: null, error: error instanceof Error ? error.message : "Artefacto de replay incompatible o ausente"};
    }
  }, [source]);
  const parsed = parsedResult.parsed;

  const steps = parsed ? parsed.window.steps : [];
  const n = steps.length;
  const finished = cursor === n;

  // Todos los hooks van antes de cualquier retorno anticipado.
  // Avance por el TEMPORIZADOR: nunca cambia el estado manual del reproductor.
  const tickForward = useCallback(() => {
    setCursor((c) => {
      if (c >= n) return c;
      const nc = Math.min(c + 1, n);
      if (nc === n) setStatus("finished");
      return nc;
    });
  }, [n]);
  // Avance MANUAL (paso a paso): detiene la reproducción en el paso actual.
  const stepForward = useCallback(() => {
    if (finished) return;
    setCursor((c) => {
      const nc = Math.min(c + 1, n);
      if (nc === n) setStatus("finished");
      else setStatus("paused");
      return nc;
    });
  }, [finished, n]);
  const handlePlay = useCallback(() => { if (!finished) setStatus("playing"); }, [finished]);
  const handlePause = useCallback(() => setStatus("paused"), []);
  const handleRestart = useCallback(() => { setCursor(0); setStatus("idle"); }, []);
  const handleSetSpeed = useCallback((sp: number) => setSpeed(sp > 0 ? sp : 1), []);

  // Bucle de reproduccion (solo controles del replay; nunca Start/Stop del monitor).
  useEffect(() => {
    if (status !== "playing") { if (intervalRef.current != null) { clearInterval(intervalRef.current); intervalRef.current = null; } return; }
    const stepMs = msPerStep(speed);
    intervalRef.current = window.setInterval(tickForward, stepMs) as unknown as number;
    return () => { if (intervalRef.current != null) { clearInterval(intervalRef.current); intervalRef.current = null; } };
  }, [status, speed, tickForward]);

  if (!parsed) return <ReplayUnavailable message={parsedResult.error ?? "desconocido"} />;

  const { trade, event, levels, costs, result, window: w, provenance, eligibility_rule, replay_id, chosen_at_utc, limitations } = parsed;
  const revealedSteps = steps.slice(0, cursor);
  const revealedEvents: ReplayEvent[] = revealedSteps.flatMap((s) => s.events);
  const lastStep = cursor > 0 ? steps[cursor - 1]! : null;
  const lastPosition = lastStep?.position_after ?? null;
  const lastExit = lastStep?.exit ?? null;
  const positionState = replayPositionState(revealedEvents, lastPosition, lastExit, finished);
  const view = {
    status: finished ? "finished" : status,
    cursor,
    n,
    finished,
    progress: n === 0 ? 1 : cursor / n,
    step: lastStep,
    clockMs: lastStep?.known_at_ms ?? null,
    clockUtc: fmtUtc(lastStep?.known_at_ms ?? null),
    // Solo los pasos de VELA aportan velas; los de EVENTO no.
    candles: revealedSteps.filter((s) => s.kind === "candle" && s.candle).map((s) => s.candle as ReplayCandle),
    events: revealedEvents,
    position: lastPosition,
    positionState,
    unrealized: lastStep?.unrealized ?? null,
    exit: lastExit,
    canPlay: !finished,
    canPause: status === "playing",
    canRestart: true,
    canStepForward: !finished,
  } as const;

  // Estado del REPRODUCTOR (independiente del estado de posición).
  const pState = playerState(status, cursor, n);
  const pLabel = playerStateLabel(pState);

  // Instante inicial ANTES de la detección: la vista inicial muestra el contexto
  // ya conocido en ese instante. No se simula un reloj sin definir.
  const initialCursorMs = w.initial_cursor_ms;
  // El contexto visible en un instante nunca incluye velas cuyo cierre sea posterior.
  const clockForContext = cursor > 0 ? view.clockMs : initialCursorMs;
  const contextVisible = contextCandlesKnownAt(w.context_candles, clockForContext);

  // Detección revelada (solo cuando el replay la ha descubierto); su hora de
  // formación se muestra como metadata, no como instante de revelación.
  const detection = revealedEvents.find((e) => e.kind === "detection") ?? null;
  const detectionRevealed = detection != null;

  const hasEntered = positionState.entered;
  const hasClosed = positionState.closed;
  const entryPx = levels.entry_px;
  const stopPx = levels.stop_px;
  const exitPx = view.exit?.px ?? null;
  const exitShown = hasClosed && !!view.exit;
  const unrealized = view.unrealized;
  const gross = trade.gross_pnl;
  const net = trade.net_pnl;

  return (
    <section className={s.root} aria-label="Paper Lab — replay historico">
      <div className={s.labelStrip}>
        <span className={s.badge}><span className={s.dot} aria-hidden="true"></span>REPLAY HISTÓRICO</span>
        <span className={s.chip}>Estado del replay (independiente del monitor)</span>
      </div>
      <h1 className={s.title}>Paper Lab</h1>
      <p className={s.subtitle}>
        Replay historico interactivo de una operacion registrada. No es seleccion automatica en vivo ni simulacion prospectiva.
      </p>
      <div className={s.statusRow}>
        <span className={`${s.chip} ${pState === "terminado" ? s.pos : pState === "reproduciendo" ? s.warn : ""}`}>
          Reproducción: {pLabel}
        </span>
        <span className={s.chip}>Paso {view.cursor} de {view.n}</span>
        <span className={s.clock}>{view.clockUtc ?? "—"}</span>
      </div>
      <div className={s.identStrip} aria-label="Identidad de la operación">
        <span className={s.chip}>{trade.symbol}</span>
        <span className={s.chip}>{directionLabel(trade.direction)} · familia {trade.family}</span>
        <span className={s.chip}>{w.interval} · {w.n_candles} velas cerradas</span>
        <span className={s.chip} data-state={positionState.state}>Posición: {positionState.label}</span>
        <span className={s.chip}>Control de mecánica (BTC) — no valida el selector de extremos</span>
        <span className={`${s.chip} ${s.mono}`}>{replay_id}</span>
      </div>
      <p className={s.note}>
        Estos chips describen el <strong>escenario seleccionado offline</strong> (símbolo, familia y dirección del caso elegido por regla fija).
        No son una detección automática: la <strong>detección</strong> se revela en el replay solo cuando es conocida (paso «detección conocida»),
        mostrando entonces su hora original de formación como metadata.
      </p>

      <ReplayControls
        status={view.status}
        playerState={pState}
        playerLabel={pLabel}
        speed={speed}
        onPlay={handlePlay}
        onPause={handlePause}
        onRestart={handleRestart}
        onStepForward={stepForward}
        onSetSpeed={handleSetSpeed}
        stepMs={msPerStep(speed)}
        canStepForward={view.canStepForward}
      />

      <div className={s.grid}>
        <section className={s.card} style={{gridColumn: "1 / -1"}} aria-label="Grafico del replay">
          <div className={s.chartHead}>
            <h3>Grafico — contexto + velas y niveles ({w.interval}, cerrado)</h3>
            <div className={s.zoomGroup} role="group" aria-label="Zoom del grafico">
              <span className={s.mono}>Zoom</span>
              <button type="button" className={s.replay} onClick={() => setZoom((z) => Math.max(1, +(z / 1.5).toFixed(2)))} aria-label="Alejar">−</button>
              <span className={s.mono}>{zoom.toFixed(2)}x</span>
              <button type="button" className={s.replay} onClick={() => setZoom((z) => Math.min(12, +(z * 1.5).toFixed(2)))} aria-label="Acercar">+</button>
              <button type="button" className={s.replay} onClick={() => setZoom(1)}>Reset</button>
            </div>
          </div>
          <div className={s.chartLegend} aria-label="Leyenda del grafico">
            <span><i className={s.swContext} aria-hidden="true"></i>contexto previo (atenuado)</span>
            <span><i className={s.swReplay} aria-hidden="true"></i>velas del replay</span>
            {hasEntered && <span><i className={s.swEntry} aria-hidden="true"></i>Entrada {formatPrice(entryPx)}</span>}
            {hasEntered && !hasClosed && <span><i className={s.swStop} aria-hidden="true"></i>Stop {formatPrice(stopPx)}</span>}
            {exitShown && exitPx != null && <span><i className={s.swExit} aria-hidden="true"></i>Cierre {formatPrice(exitPx)}</span>}
            <span><i className={s.swCursor} aria-hidden="true"></i>cursor</span>
          </div>
          <div className={s.chartWrap}>
            <ReplayChart
              candles={view.candles}
              contextCandles={contextVisible}
              entryPx={hasEntered ? entryPx : null}
              stopPx={hasEntered && !hasClosed ? stopPx : null}
              exitPx={exitPx}
              exitShown={exitShown}
              currentTimeMs={view.clockMs}
              zoom={zoom}
            />
          </div>
          <p className={s.note}>
            Vista inicial: cursor en <span className={s.mono}>{fmtUtc(initialCursorMs)}</span>, anterior a la detección; solo se muestran las velas de contexto ya
            conocidas hasta ese instante. Las {w.n_context_candles} velas atenuadas a la izquierda son contexto previo REAL (mismo paquete), solo informativo: no forman
            parte de la reproducción ni de posiciones/P&L, y su cierre nunca supera el cursor. Solo se muestran velas cerradas conocidas hasta el cursor; sin ticks ni
            recorrido intrabar inventado. Los niveles de cierre aparecen solo tras el cierre.
          </p>
        </section>

        <section className={s.card}>
          <PositionPanel
            position={view.position ?? null}
            positionState={positionState}
            tradeDir={trade.direction}
            entryPx={hasEntered ? entryPx : null}
            stopPx={hasEntered ? stopPx : null}
            horizonMs={hasEntered ? levels.horizon_ms : null}
          />
        </section>

        <section className={s.card}>
          <PnLPanel
            position={view.position ?? null}
            unrealized={unrealized}
            finished={hasClosed}
            entered={hasEntered}
            costs={{
              entryFees: costs.entry_fees,
              exitFees: costs.exit_fees,
              entrySlip: costs.entry_spread_slip,
              exitSlip: costs.exit_spread_slip,
              funding: costs.funding,
              friction: costs.friction,
            }}
            trade={{ gross, net, realized: result.realized_net, exitExecuted: trade.exit_executed }}
          />
        </section>
      </div>

      <div className={s.grid}>
        <section className={s.card} style={{gridColumn: "1 / -1"}}>
          <EventLog events={view.events} />
        </section>
        <section className={s.card}>
          <ProvenancePanel
            prov={{
              engine: provenance.engine,
              engine_version: provenance.engine_version,
              symbol: provenance.symbol,
              interval: provenance.interval,
              db_sha256: provenance.db_sha256,
              events_file: provenance.events_file,
              candles_file: provenance.candles_file,
              manifest_file: provenance.manifest_file,
              funding_calendar: provenance.funding_calendar,
              source_hashes: provenance.source_hashes,
              note: provenance.note,
            }}
            eligibility_rule={eligibility_rule}
            replay_id={replay_id}
            chosen_at_utc={chosen_at_utc}
            limitations={limitations}
            reconciled={result.reconciled_to_engine}
          />
        </section>
      </div>

      <section className={s.card} aria-label="Revelación de la detección">
        <h3>Revelación de la detección (formación vs disponibilidad)</h3>
        <div className={s.row}><span className={s.k}>Hora de formación (metadata)</span><span className={`${s.v} ${s.mono}`}>{fmtUtc(event.event_time_ms)}</span></div>
        <div className={s.row}><span className={s.k}>Disponible a partir de</span><span className={`${s.v} ${s.mono}`}>{fmtUtc(event.available_at_ms)}</span></div>
        <div className={s.row}><span className={s.k}>Ejecución (entrada)</span><span className={`${s.v} ${s.mono}`}>{fmtUtc(trade.entry_ms)}</span></div>
        <div className={s.row}><span className={s.k}>Estado en el replay</span><span className={s.v} data-revealed={detectionRevealed}>{detectionRevealed ? "Detección revelada" : "Detección aún no conocida"}</span></div>
        <p className={s.note}>
          La formación pertenece a un momento del patrón, pero <strong>no autoriza a revelar la detección</strong>: el patrón solo puede conocerse en su instante de
          disponibilidad. La cinta lo revela en ese instante ({fmtUtc(event.available_at_ms)}) y muestra entonces su hora original de formación. La entrada es posterior.
        </p>
      </section>

      {hasClosed && (
        <section className={s.card} aria-label="Resumen final">
          <h3>Resumen final (tras el cierre)</h3>
          <div className={s.row}><span className={s.k}>Motivo de cierre</span><span className={s.v}>{trade.exit_reason}</span></div>
          <div className={s.row}><span className={s.k}>Dirección</span><span className={s.v}>{directionLabel(trade.direction)} · {closeActionLabel(trade.direction)}</span></div>
          <div className={s.row}><span className={s.k}>Entrada</span><span className={s.v}>{formatPrice(trade.entry_px)}</span></div>
          <div className={s.row}><span className={s.k}>Cierre</span><span className={s.v}>{formatPrice(trade.exit_px)}</span></div>
          <div className={s.row}><span className={s.k}>P&L bruto realizado</span><span className={`${s.v} ${gross >= 0 ? s.pos : s.neg}`}>{formatMoney(gross)}</span></div>
          <div className={s.row}><span className={s.k}>Costes totales</span><span className={s.v}>{formatMoney(costs.friction)}</span></div>
          <div className={s.row}><span className={s.k}>P&L neto realizado</span><span className={`${s.v} ${net >= 0 ? s.pos : s.neg}`}>{formatMoney(net)}</span></div>
          <p className={s.note}>{result.note}</p>
        </section>
      )}
    </section>
  );
}
