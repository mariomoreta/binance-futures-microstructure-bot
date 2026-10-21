"use client";
import {useCallback} from "react";
import type {PaperSessionState, PaperTradeResult} from "@/lib/paper-lab-live";
import s from "./PaperLabLive.module.css";

interface ExportPanelProps {
  state: PaperSessionState;
  result: PaperTradeResult | null;
  onDownloadJson: (payload: string, fileName: string) => void;
  onDownloadCsv: (payload: string, fileName: string) => void;
}
export function ExportPanel({state, result, onDownloadJson, onDownloadCsv}: ExportPanelProps) {
  const canExport = !!result || state.status === "cerrada" || state.status === "detenida";

  const downloadJson = useCallback(() => {
    const payload = JSON.stringify({
      session_id: state.session_id,
      created_at_ms: state.created_at_ms,
      updated_at_ms: state.updated_at_ms,
      status: state.status,
      config: state.config,
      result,
      events: state.events,
    }, null, 2);
    const fileName = `paper-lab-session-${state.session_id}.json`;
    onDownloadJson(payload, fileName);
  }, [state, result]);

  const downloadCsv = useCallback(() => {
    if (!result) return;
    const rows = [
      ["session_id", state.session_id],
      ["symbol", result.symbol],
      ["direction", result.direction],
      ["entry_px", result.entry_px],
      ["exit_px", result.exit_px ?? ""],
      ["entry_ms", result.entry_ms],
      ["exit_ms", result.exit_ms ?? ""],
      ["exit_reason", result.exit_reason ?? ""],
      ["exit_executed", result.exit_executed],
      ["qty", result.qty],
      ["filled_cost", result.filled_cost],
      ["gross_pnl", result.gross_pnl],
      ["fees", result.fees],
      ["spread_slip", result.spread_slip],
      ["funding", result.funding],
      ["friction", result.friction],
      ["net_pnl", result.net_pnl],
      ["realized_net", result.realized_net ?? ""],
      ["open_at_end", result.open_at_end],
    ];
    const payload = rows.map((r) => r.join(",")).join("\n");
    const fileName = `paper-lab-trade-${state.session_id}.csv`;
    onDownloadCsv(payload, fileName);
  }, [state, result]);

  return (
    <section className={s.card} aria-label="Exportacion de sesion paper">
      <h3>Exportacion</h3>
      <p className={s.note}>
        Descargue el estado de la sesion y el resultado del trade en formato
        JSON o CSV. Sin exportacion, los datos viven solo en la sesion actual.
      </p>
      <div className={s.exportGrid}>
        <div className={s.exportCard}>
          <h4>Sesion completa (JSON)</h4>
          <button type="button" className={s.live} onClick={downloadJson} disabled={!canExport}>
            Descargar JSON de sesion
          </button>
        </div>
        <div className={s.exportCard}>
          <h4>Resultado del trade (CSV)</h4>
          <button type="button" className={s.live} onClick={downloadCsv} disabled={!canExport}>
            Descargar CSV del trade
          </button>
        </div>
      </div>
      {!canExport && <p className={s.note}>La exportacion queda disponible tras cerrar la posicion o detener la sesion.</p>}
    </section>
  );
}
