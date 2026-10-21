"use client";
import type {PaperSessionStatus} from "@/lib/paper-lab-live";
import s from "./PaperLabLive.module.css";

interface SessionControlsProps {
  status: PaperSessionStatus;
  canEnter: boolean;
  canStep: boolean;
  canExit: boolean;
  canRestart: boolean;
  canStop: boolean;
  onEnter: () => void;
  onStep: () => void;
  onExit: () => void;
  onRestart: () => void;
  onStop: () => void;
  stepMs: number;
}
export function SessionControls({
  status, canEnter, canStep, canExit, canRestart, canStop,
  onEnter, onStep, onExit, onRestart, onStop, stepMs,
}: SessionControlsProps) {
  const finished = status === "cerrada" || status === "detenida";
  const playing = status === "abierta"; // en este MVP, "abierta" implica reloj corriendo al avanzar
  const primaryLabel = finished ? "Finalizada" : canEnter ? "Entrar" : "Avanzar paso";
  return (
    <div className={s.controls} aria-label="Controles de sesion paper">
      <div className={s.controlGroup}>
        <label>Sesion</label>
        <button type="button" className={`${s.live} ${s.primary}`} onClick={onEnter} disabled={!canEnter || finished} aria-label={primaryLabel}>
          {primaryLabel}
        </button>
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
        <span className={`${s.chip} ${finished ? s.neg : status === "abierta" ? s.pos : status === "en_espera" ? s.warn : s.info}`} data-state={status}>
          {status === "sin_iniciar" ? "SIN INICIAR" : status === "en_espera" ? "EN ESPERA" : status === "abierta" ? "ABIERTA" : status === "cerrada" ? "CERRADA" : "DETENIDA"}
        </span>
      </div>
    </div>
  );
}
