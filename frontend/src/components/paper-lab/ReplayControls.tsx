"use client";
import type {ReplayStatus, PlayerState} from "@/lib/paper-lab-replay";
import s from "./PaperLab.module.css";

interface ReplayControlsProps {
  status: ReplayStatus;
  playerState: PlayerState;
  playerLabel: string;
  speed: number;
  onPlay: () => void;
  onPause: () => void;
  onRestart: () => void;
  onStepForward: () => void;
  onSetSpeed: (s: number) => void;
  stepMs: number;
  canStepForward: boolean;
}

export function ReplayControls({status, playerState, playerLabel, speed, onPlay, onPause, onRestart, onStepForward, onSetSpeed, stepMs, canStepForward}: ReplayControlsProps) {
  const playing = status === "playing";
  const finished = playerState === "terminado";
  const paused = playerState === "pausado";
  const notStarted = playerState === "sin_iniciar";
  // El botón principal reanuda o pausa según el estado real del reproductor.
  const primaryLabel = finished ? "Finalizado" : playing ? "Pausar" : paused ? "Reanudar" : "Reproducir";
  return (
    <div className={s.controls} aria-label="Controles de reproduccion del replay">
      <div className={s.controlGroup}>
        <label>Replay</label>
        <button type="button" className={`${s.replay} ${s.primary}`} onClick={playing ? onPause : onPlay} disabled={finished} aria-label={primaryLabel}>
          {primaryLabel}
        </button>
        <button type="button" className={s.replay} onClick={onStepForward} disabled={!canStepForward}>
          Paso a paso
        </button>
        <button type="button" className={s.replay} onClick={onRestart} disabled={notStarted}>
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
        <label>Estado del reproductor</label>
        <span className={`${s.chip} ${playerState === "terminado" ? s.pos : playerState === "reproduciendo" ? s.warn : playerState === "pausado" ? s.info : ""}`} data-player={playerState}>
          {playerLabel}
        </span>
      </div>
    </div>
  );
}
