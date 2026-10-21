"use client";
import type {PaperCosts, PaperTradeResult} from "@/lib/paper-lab-live";
import {formatMoney} from "@/lib/format";
import s from "./PaperLabLive.module.css";

interface PnLPanelProps {
  finished: boolean;
  entered: boolean;
  costs: PaperCosts;
  unrealized: number | null;
  result: PaperTradeResult | null;
  exitExecuted: boolean;
}
export function PnLPanel({finished, entered, costs, unrealized, result, exitExecuted}: PnLPanelProps) {
  const realized = exitExecuted && !!result;
  const gross = realized ? result?.gross_pnl ?? null : unrealized ?? null;
  const net = realized ? result?.net_pnl ?? null : null;
  return (
    <section className={`${s.panel} ${realized ? s.final : ""}`} aria-label="P&L y costes paper">
      <h3>{realized ? "Resultado (realizado al cierre)" : "P&L (estimado / no realizado)"}</h3>
      <div className={s.row}><span className={s.k}>P&L bruto</span><span className={`${s.v} ${gross == null ? "" : gross >= 0 ? s.pos : s.neg}`}>{formatMoney(gross)}</span></div>
      {entered && (
        <>
          <div className={s.row}><span className={s.k}>Comisiones entrada</span><span className={s.v}>{formatMoney(costs.entry_fees)}</span></div>
          <div className={s.row}><span className={s.k}>Spread+slippage entrada</span><span className={s.v}>{formatMoney(costs.entry_spread_slip)}</span></div>
          {!realized && (
            <>
              <div className={s.row}><span className={s.k}>Salida hipotetica (costes)</span><span className={`${s.v} ${s.warn}`}>{formatMoney(costs.exit_fees + costs.exit_spread_slip)} · no ejecutada</span></div>
              <div className={s.row}><span className={s.k}>Funding devengado</span><span className={s.v}>{formatMoney(costs.funding)}</span></div>
              <div className={s.row}><span className={s.k}>Neto estimado (NO realizado)</span><span className={`${s.v} ${unrealized == null ? "" : unrealized >= 0 ? s.pos : s.neg}`}>{formatMoney(unrealized ?? null)}</span></div>
            </>
          )}
          {realized && (
            <>
              <div className={s.row}><span className={s.k}>Comisiones salida</span><span className={s.v}>{formatMoney(costs.exit_fees)}</span></div>
              <div className={s.row}><span className={s.k}>Spread+slippage salida</span><span className={s.v}>{formatMoney(costs.exit_spread_slip)}</span></div>
              <div className={s.row}><span className={s.k}>Funding</span><span className={s.v}>{formatMoney(costs.funding)}</span></div>
              <div className={s.row}><span className={s.k}>Neto REALIZADO</span><span className={`${s.v} ${net != null && net >= 0 ? s.pos : s.neg}`}>{formatMoney(net)}</span></div>
            </>
          )}
        </>
      )}
      {!entered && <p className={s.note}>Sin costes ejecutados antes de la entrada.</p>}
      {!realized && entered && <p className={s.note}>El neto se confirma solo al cierre; la marca es el cierre OHLC conocido.</p>}
      {realized && result && (
        <>
          <div className={s.row}><span className={s.k}>Motivo de salida</span><span className={s.v}>{result.exit_reason ?? "—"}</span></div>
          <div className={s.row}><span className={s.k}>Salida ejecutada</span><span className={s.v}>{result.exit_executed ? "Si" : "No"}</span></div>
          <p className={s.note}>El neto realizado se congela al cierre; no se modifica con pasos posteriores.</p>
        </>
      )}
    </section>
  );
}
