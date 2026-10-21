"use client";
import type {PaperPosition} from "@/lib/paper-lab-live";
import {formatMoney, formatPrice} from "@/lib/format";
import s from "./PaperLabLive.module.css";

interface PositionPanelProps {
  position: PaperPosition;
  direction: "LONG" | "SHORT" | null;
}
export function PositionPanel({position, direction}: PositionPanelProps) {
  const open = position.open === true;
  return (
    <section className={s.panel} aria-label="Posicion paper">
      <h3>Posicion</h3>
      <div className={s.row}>
        <span className={s.k}>Estado</span>
        <span className={`${s.v} ${open ? s.pos : ""}`} data-state={open ? "abierta" : "cerrada"}>
          {open ? "ABIERTA" : "SIN POSICION"}
        </span>
      </div>
      {direction && (
        <div className={s.row}>
          <span className={s.k}>Direccion</span>
          <span className={s.v} data-sign={direction === "LONG" ? "positive" : "negative"}>
            {direction} ({direction === "LONG" ? "cierre = venta" : "cierre = compra"})
          </span>
        </div>
      )}
      {open && position.entry_px != null && (
        <>
          <div className={s.row}><span className={s.k}>Entrada</span><span className={s.v}>{formatPrice(position.entry_px)}</span></div>
          <div className={s.row}><span className={s.k}>Tamaño (base)</span><span className={s.v}>{position.entry_qty == null ? "—" : position.entry_qty.toFixed(8)}</span></div>
          <div className={s.row}><span className={s.k}>Stop original</span><span className={`${s.v} ${s.neg}`}>{formatPrice(position.stop_px)}</span></div>
          {position.mark_px != null && (
            <div className={s.row}><span className={s.k}>Marca actual</span><span className={s.v}>{formatPrice(position.mark_px)}</span></div>
          )}
          {position.unrealized_gross != null && (
            <div className={s.row}><span className={s.k}>P&L bruto (no realizado)</span><span className={`${s.v} ${position.unrealized_gross >= 0 ? s.pos : s.neg}`}>{formatMoney(position.unrealized_gross)}</span></div>
          )}
          {position.unrealized_net != null && (
            <div className={s.row}><span className={s.k}>P&L neto (no realizado)</span><span className={`${s.v} ${position.unrealized_net >= 0 ? s.pos : s.neg}`}>{formatMoney(position.unrealized_net)}</span></div>
          )}
          {position.mfe_pct != null && (
            <div className={s.row}><span className={s.k}>MFE (maximo favorable)</span><span className={s.v}>{position.mfe_pct.toFixed(2)}%</span></div>
          )}
          {position.mae_pct != null && (
            <div className={s.row}><span className={s.k}>MAE (maximo adverso)</span><span className={s.v}>{position.mae_pct.toFixed(2)}%</span></div>
          )}
        </>
      )}
      {!open && <p className={s.note}>Sin posicion abierta. Ejecute la entrada para iniciar la simulacion.</p>}
    </section>
  );
}
