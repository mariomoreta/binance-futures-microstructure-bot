"use client";
import type {PaperCandidateDecision, PaperSessionStatus} from "@/lib/paper-lab-live";
import s from "./PaperLabLive.module.css";

interface SessionControlsProps {
  status: PaperSessionStatus;
  canEnter: boolean;
  canStep: boolean;
  canExit: boolean;
  canRestart: boolean;
  canStop: boolean;
  canDecide: boolean;
  decision: PaperCandidateDecision | null;
  onDecide: (decision: PaperCandidateDecision) => void;
  onEnter: () => void;
  onStep: () => void;
  onExit: () => void;
  onRestart: () => void;
  onStop: () => void;
  stepMs: number;
}
export function SessionControls({
  status, canEnter, canStep, canExit, canRestart, canStop, canDecide,
  decision, onDecide, onEnter, onStep, onExit, onRestart, onStop, stepMs,
}: SessionControlsProps) {
  const finished = status === "cerrada" || status === "detenida";
  const decided = decision != null;
  return (
    <div className={s.controls} aria-label="Controles de sesion paper">
      <div className={s.controlGroup}>
        <label>Sesion</label>
        {canDecide && !decided && (
          <>
            <button type="button" className={s.live} onClick={() => onDecide("VIGILANDO")} disabled={finished}>
              Vigilando
            </button>
            <button type="button" className={s.live} onClick={() => onDecide("SIN_ENTRADA")} disabled={finished}>
              Sin entrada
            </button>
            <button type="button" className={s.live} onClick={() => onDecide("DESCARTADO")} disabled={finished}>
              Descartado
            </button>
            <button type="button" className={`${s.live} ${s.primary}`} onClick={() => onDecide("ENTRADA_SIMULADA")} disabled={finished || !canEnter}>
              Entrada simulada
            </button>
          </>
        )}
        {(!canDecide || decided) && canEnter && !finished && (
          <button type="button" className={`${s.live} ${s.primary}`} onClick={onEnter} aria-label="Entrar">
            Entrar
          </button>
        )}
        <button type="button" className={s.live} onClick={onStep} disabled={!canStep || finished}>
          Paso a paso
        </button>
        <button type="button" className={`${s.live} ${s.danger}`} onClick={onExit} disabled={!canExit || finished}>
          Cerrar posicion
        </button>
        <button type="button" className={s.live} onClick={onRestart} disabled={!canRestart}>
          Reiniciar
        </button>
        <button type="button" className={s.live} onClick={onStop} disabled={!canStop || finished}>
          Detener sesion
        </button>
      </div>
      <div className={s.controlGroup}>
        <label>Reloj</label>
        <span className={s.mono}>{(stepMs / 1000).toFixed(2)} s por paso</span>
      </div>
      <div className={s.controlGroup}>
        <label>Estado</label>
        <span className={`${s.chip} ${finished ? s.neg : status === "abierta" ? s.pos : status === "en_espera" ? s.warn : status === "evaluando" ? s.info : s.info}`} data-state={status}>
          {status === "sin_iniciar" ? "SIN INICIAR" : status === "evaluando" ? "EVALUANDO" : status === "en_espera" ? "EN ESPERA" : status === "abierta" ? "ABIERTA" : status === "cerrada" ? "CERRADA" : "DETENIDA"}
        </span>
      </div>
      {decided && (
        <div className={s.controlGroup}>
          <label>Decision</label>
          <span className={s.chip} data-decision={decision}>
            {decision === "VIGILANDO" ? "VIGILANDO" : decision === "SIN_ENTRADA" ? "SIN ENTRADA" : decision === "DESCARTADO" ? "DESCARTADO" : "ENTRADA SIMULADA"}
          </span>
        </div>
      )}
    </div>
  );
}
