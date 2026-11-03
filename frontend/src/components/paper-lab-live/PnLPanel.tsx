"use client";
import type {PaperCosts, PaperTradeResult} from "@/lib/paper-lab-live";
import {formatCost, formatCostEstimate, formatFunding, formatMoney} from "@/lib/format";
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

  // Estimación de salida: ambos componentes deben estar presentes para evitar
  // convertir null en cero al sumar.
  const feeEst = costs.exit_fees_estimated;
  const slipEst = costs.exit_spread_slip_estimated;
  const estimateAvailable = feeEst != null && slipEst != null;
  const estimateValue = estimateAvailable ? feeEst + slipEst : null;

  return (
    <section className={`${s.panel} ${realized ? s.final : ""}`} aria-label="P&L y costes paper">
      <h3>{realized ? "Resultado (realizado al cierre)" : "P&L (estimado / no realizado)"}</h3>
      <div className={s.row}><span className={s.k}>P&L bruto</span><span className={`${s.v} ${gross == null ? "" : gross >= 0 ? s.pos : s.neg}`}>{formatMoney(gross)}</span></div>
      {/* Costes de entrada: siempre visibles; UNKNOWN si no hubo fill de entrada. */}
      <div className={s.row}><span className={s.k}>Comisiones entrada</span><span className={s.v}>{formatCost(costs.entry_fees, entered, "sin fill de entrada")}</span></div>
      <div className={s.row}><span className={s.k}>Spread+slippage entrada</span><span className={s.v}>{formatCost(costs.entry_spread_slip, entered, "sin fill de entrada")}</span></div>
      {!realized ? (
        <>
          {/* Costes de salida: siempre visibles; UNKNOWN si no hubo salida ejecutada. */}
          <div className={s.row}><span className={s.k}>Comisiones salida</span><span className={s.v}>{formatCost(costs.exit_fees, exitExecuted, "sin salida ejecutada")}</span></div>
          <div className={s.row}><span className={s.k}>Spread+slippage salida</span><span className={s.v}>{formatCost(costs.exit_spread_slip, exitExecuted, "sin salida ejecutada")}</span></div>
          <div className={s.row}><span className={s.k}>Salida hipotetica (costes)</span><span className={`${s.v} ${s.warn}`}>{formatCostEstimate(estimateValue, estimateAvailable)}</span></div>
          <div className={s.row}><span className={s.k}>Funding devengado</span><span className={s.v}>{formatFunding(costs.funding)}</span></div>
          <div className={s.row}><span className={s.k}>Neto estimado (NO realizado)</span><span className={`${s.v} ${unrealized == null ? "" : unrealized >= 0 ? s.pos : s.neg}`}>{formatMoney(unrealized ?? null)}</span></div>
        </>
      ) : (
        <>
          <div className={s.row}><span className={s.k}>Comisiones salida</span><span className={s.v}>{formatCost(costs.exit_fees, exitExecuted, "sin salida ejecutada")}</span></div>
          <div className={s.row}><span className={s.k}>Spread+slippage salida</span><span className={s.v}>{formatCost(costs.exit_spread_slip, exitExecuted, "sin salida ejecutada")}</span></div>
          <div className={s.row}><span className={s.k}>Funding</span><span className={s.v}>{formatFunding(costs.funding)}</span></div>
          <div className={s.row}><span className={s.k}>Neto REALIZADO</span><span className={`${s.v} ${net != null && net >= 0 ? s.pos : s.neg}`}>{formatMoney(net)}</span></div>
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
