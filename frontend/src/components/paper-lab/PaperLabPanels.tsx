"use client";
import type {ReplayEvent, ReplayPosition, ReplayUnrealized, ReplayStepView} from "@/lib/paper-lab-replay";
import {directionLabel, closeActionLabel} from "@/lib/paper-lab-replay";
import {formatMoney, formatPrice} from "@/lib/format";
import s from "./PaperLab.module.css";

interface PositionPanelProps {
  position: ReplayPosition | null;
  positionState: ReplayStepView;
  tradeDir: string;
  entryPx: number | null;
  stopPx: number | null;
  horizonMs: number | null;
}
export function PositionPanel({position, positionState, tradeDir, entryPx, stopPx, horizonMs}: PositionPanelProps) {
  const open = positionState.state === "ABIERTA";
  const dirTone = tradeDir === "LONG" ? "pos" : tradeDir === "SHORT" ? "neg" : "muted";
  return (
    <section className={s.panel} aria-label="Posicion">
      <h3>Posicion</h3>
      <div className={s.row}><span className={s.k}>Direccion</span><span className={s.v} data-sign={tradeDir==="LONG"?"positive":tradeDir==="SHORT"?"negative":"missing"}>{directionLabel(tradeDir)} <span className={s.mono}>({closeActionLabel(tradeDir)})</span></span></div>
      <div className={s.row}><span className={s.k}>Estado</span><span className={`${s.v} ${open ? s.pos : ""}`} data-state={positionState.state}>{positionState.label}</span></div>
      {entryPx != null && (
        <>
          <div className={s.row}><span className={s.k}>Entrada</span><span className={s.v}>{formatPrice(entryPx)}</span></div>
          <div className={s.row}><span className={s.k}>Tamaño (base)</span><span className={s.v}>{position?.qty == null ? "—" : position.qty.toFixed(8)}</span></div>
          {stopPx != null && <div className={s.row}><span className={s.k}>Stop original</span><span className={`${s.v} ${s.neg}`}>{formatPrice(stopPx)}</span></div>}
          {horizonMs != null && <div className={s.row}><span className={s.k}>Horizonte original</span><span className={`${s.v} ${s.mono}`}>{Math.round(horizonMs / 60000)} min</span></div>}
        </>
      )}
      {open && position?.mark_px != null && <div className={s.row}><span className={s.k}>Marca al cierre conocido</span><span className={s.v}>{formatPrice(position.mark_px)}</span></div>}
      {positionState.state === "CERRADA" && <p className={s.note}>Posición cerrada: la entrada ya no está abierta. El resultado realizado aparece tras el cierre.</p>}
      {positionState.state === "SIN_POSICION" && <p className={s.note}>Sin señal revelada todavía. Nada de la operación se anticipa antes de su instante.</p>}
      {positionState.state === "EN_ESPERA" && <p className={s.note}>Operación seleccionada; la entrada aún no se ejecutó. Nada de la operación se anticipa antes de su instante.</p>}
    </section>
  );
}

interface PnLPanelProps {
  position: ReplayPosition | null;
  unrealized: ReplayUnrealized | null;
  finished: boolean;
  entered: boolean;
  costs: { entryFees: number; exitFees: number; entrySlip: number; exitSlip: number; funding: number; friction: number };
  trade: { gross: number; net: number; realized: number | null; exitExecuted: boolean };
}
export function PnLPanel({position, unrealized, finished, entered, costs, trade}: PnLPanelProps) {
  const open = position?.open === true;
  const realized = finished && trade.exitExecuted;
  const gross = realized ? trade.gross : unrealized?.gross ?? null;
  return (
    <section className={`${s.panel} ${realized ? s.final : ""}`} aria-label="P&L y costes">
      <h3>{realized ? "Resultado (realizado al cierre)" : "P&L (estimado / no realizado)"}</h3>
      <div className={s.row}><span className={s.k}>P&L bruto</span><span className={`${s.v} ${gross == null ? "" : gross >= 0 ? s.pos : s.neg}`}>{formatMoney(gross)}</span></div>
      <div className={s.row}><span className={s.k}>Comisiones entrada</span><span className={s.v}>{entered ? formatMoney(costs.entryFees) : "— no ejecutadas"}</span></div>
      <div className={s.row}><span className={s.k}>Spread+slippage entrada</span><span className={s.v}>{entered ? formatMoney(costs.entrySlip) : "— no ejecutado"}</span></div>
      {!realized && entered && (
        <>
          <div className={s.row}><span className={s.k}>Salida hipotética</span><span className={`${s.v} ${s.warn}`}>{formatMoney(costs.exitFees + costs.exitSlip)} · no ejecutada</span></div>
          <div className={s.row}><span className={s.k}>Funding devengado</span><span className={s.v}>{formatMoney(costs.funding)}</span></div>
          <div className={s.row}><span className={s.k}>Neto estimado (NO realizado)</span><span className={`${s.v} ${unrealized == null ? "" : unrealized.net_est >= 0 ? s.pos : s.neg}`}>{formatMoney(unrealized?.net_est ?? null)}</span></div>
        </>
      )}
      {realized && (
        <>
          <div className={s.row}><span className={s.k}>Comisiones salida</span><span className={s.v}>{formatMoney(costs.exitFees)}</span></div>
          <div className={s.row}><span className={s.k}>Spread+slippage salida</span><span className={s.v}>{formatMoney(costs.exitSlip)}</span></div>
          <div className={s.row}><span className={s.k}>Funding</span><span className={s.v}>{formatMoney(costs.funding)}</span></div>
          <div className={s.row}><span className={s.k}>Neto REALIZADO</span><span className={`${s.v} ${trade.net >= 0 ? s.pos : s.neg}`}>{formatMoney(trade.net)}</span></div>
        </>
      )}
      {!entered && <p className={s.note}>Sin P&L ni costes ejecutados antes de la entrada.</p>}
      {!realized && open && <p className={s.note}>El neto se confirma solo al cierre; la marca es el cierre OHLC conocido.</p>}
      {realized && <p className={s.note}>Neto reconciliado; la salida se contabiliza solo tras el cierre.</p>}
    </section>
  );
}

interface EventLogProps { events: ReplayEvent[]; }
export function EventLog({events}: EventLogProps) {
  if (events.length === 0) {
    return <section className={s.panel} aria-label="Registro de eventos"><h3>Registro de eventos</h3><div className={s.empty}>Sin eventos revelados aún.</div></section>;
  }
  return (
    <section className={s.panel} aria-label="Registro de eventos">
      <h3>Registro de eventos (hasta el cursor)</h3>
      <div className={s.log}>
        {events.map((e, i) => (
          <div key={i} className={s.logEntry}>
            <span className={s.logTime}>{new Date(e.at_ms).toISOString()}</span>
            <span className={s.logLabel}>{e.label}</span>
            <span className={`${s.logKind} ${s[e.kind]}`}>{e.kind}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

interface ProvenancePanelProps {
  prov: { engine: string; engine_version: string; symbol: string; interval: string; db_sha256: string | null; events_file: string; candles_file: string; manifest_file: string; funding_calendar: string; source_hashes: Record<string, string>; note: string };
  eligibility_rule: string;
  replay_id: string;
  chosen_at_utc: string | null;
  limitations: string[];
  reconciled: Record<string, unknown>;
}
export function ProvenancePanel({prov, eligibility_rule, replay_id, chosen_at_utc, limitations, reconciled}: ProvenancePanelProps) {
  const allOk = prov && Object.keys(reconciled).length > 0 && Object.values(reconciled).every(Boolean);
  return (
    <section className={s.panel} aria-label="Procedencia y limitaciones">
      <h3>Procedencia y limitaciones</h3>
      <div className={s.prov}>
        <div><span className={s.k}>Replay ID:</span> <span className={s.mono}>{replay_id}</span></div>
        <div><span className={s.k}>Elegido:</span> {chosen_at_utc ?? "—"}</div>
        <div><span className={s.k}>Motor:</span> {prov.engine_version} ({prov.engine})</div>
        <div><span className={s.k}>Simbolo / intervalo:</span> {prov.symbol} / {prov.interval}</div>
        <div><span className={s.k}>DB canónica:</span> no leída; paquete versionado</div>
        <div><span className={s.k}>Reconciliacion motor:</span> <span className={`${s.v} ${allOk ? s.pos : s.neg}`}>{allOk ? "OK (rel/abs 1e-9)" : "—"}</span></div>
      </div>
      <div className={s.note}>{eligibility_rule}</div>
      <details className={s.hashes}><summary>Hashes de inputs ({Object.keys(prov.source_hashes).length})</summary>{Object.entries(prov.source_hashes).map(([path, hash]) => <div key={path}><span>{path}</span><code>{hash}</code></div>)}</details>
      <ul className={s.lim}>{limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
    </section>
  );
}
