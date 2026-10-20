"use client";
import type {ReplayStatus} from "@/lib/paper-lab-replay";
import s from "./PaperLab.module.css";

interface ReplayControlsProps {
  status: ReplayStatus;
  speed: number;
  onPlay: () => void;
  onPause: () => void;
  onRestart: () => void;
  onStepForward: () => void;
  onSetSpeed: (s: number) => void;
  stepMs: number;
  canStepForward: boolean;
}

export function ReplayControls({status, speed, onPlay, onPause, onRestart, onStepForward, onSetSpeed, stepMs, canStepForward}: ReplayControlsProps) {
  const playing = status === "playing";
  const finished = status === "finished";
  const paused = status === "paused";
  return (
    <div className={s.controls} aria-label="Controles de reproduccion del replay">
      <div className={s.controlGroup}>
        <label>Replay</label>
        <button type="button" className={`${s.replay} ${s.primary}`} onClick={playing ? onPause : onPlay} disabled={finished}>
          {finished ? "Finalizado" : playing ? "Pausar" : paused ? "Reanudar" : "Reproducir"}
        </button>
        <button type="button" className={s.replay} onClick={onStepForward} disabled={!canStepForward}>
          Paso a paso
        </button>
        <button type="button" className={s.replay} onClick={onRestart} disabled={status === "idle"}>
          Reiniciar
        </button>
      </div>
      <div className={s.controlGroup}>
        <label htmlFor="pl-speed">Velocidad</label>
        <select id="pl-speed" value={String(speed)} onChange={e => onSetSpeed(parseFloat(e.target.value))}>
          <option value="0.25">0.25x</option>
          <option value="0.5">0.5x</option>
          <option value="1">1x</option>
          <option value="2">2x</option>
          <option value="4">4x</option>
        </select>
        <span className={s.mono}>{speed}x · {(stepMs / 1000).toFixed(2)} s de reloj por paso</span>
      </div>
      <div className={s.controlGroup}>
        <label>Estado</label>
        <span className={`${s.chip} ${finished ? s.pos : playing ? s.warn : ""}`}>
          {finished ? "TERMINADO" : playing ? "REPRODUCIENDO" : paused ? "PAUSADO" : "REPOSO"}
        </span>
      </div>
    </div>
  );
}
