"use client";
import {useCallback, useState} from "react";
import type {PaperSessionConfig, PaperCandle} from "@/lib/paper-lab-live";
import {PAPER_FIXTURES, FIXTURE_IDS, type PaperFixtureEntry} from "@/lib/paper-fixtures";
import s from "./PaperLabLive.module.css";

interface FixtureSelectorProps {
  onSelect: (id: string, entry: PaperFixtureEntry) => void;
  selectedId: string | null;
}
export function FixtureSelector({onSelect, selectedId}: FixtureSelectorProps) {
  const [viewAll, setViewAll] = useState(false);

  const handleSelect = useCallback((id: string) => {
    const entry = PAPER_FIXTURES[id];
    if (entry) onSelect(id, entry);
  }, [onSelect]);

  return (
    <section className={s.card} aria-label="Seleccion de operacion (fixtures de ingenieria)">
      <h3>Seleccion de operacion</h3>
      <p className={s.note}>
        Elija una operacion de fixture para simular. Los datos son sinteticos de
        ingenieria (sin Binance en vivo, sin capital real). El frontend no
        decide operaciones: solo ejecuta la simulacion que usted pide.
      </p>
      <div className={s.fixtureGrid}>
        {FIXTURE_IDS.map((id) => {
          const entry = PAPER_FIXTURES[id];
          if (!entry) return null;
          const sel = selectedId === id;
          return (
            <div
              key={id}
              className={`${s.fixtureCard} ${sel ? s.selected : ""}`}
              onClick={() => handleSelect(id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && handleSelect(id)}
            >
              <h4>{entry.label}</h4>
              <p className={s.meta}>
                {entry.config.symbol} · {entry.config.interval} ·
                {entry.config.direction} · notional {entry.config.notional_usdt} USDT
              </p>
              <p className={s.meta}>
                entrada {entry.config.entry_px.toFixed(2)} ·
                stop {entry.config.stop_px.toFixed(2)} ·
                horizonte {Math.round(entry.config.horizon_ms / 60000)} min
              </p>
              <p className={s.meta}>
                velas: {entry.candles.length} · contexto: {entry.context.length}
              </p>
              <span className={s.chip} data-state={sel ? "abierta" : "sin_iniciar"}>
                {sel ? "Seleccionada" : "Seleccionar"}
              </span>
            </div>
          );
        })}
      </div>
      {viewAll ? (
        <button type="button" className={s.live} onClick={() => setViewAll(false)}>
          Ver menos
        </button>
      ) : (
        <button type="button" className={s.live} onClick={() => setViewAll(true)}>
          Ver todas las opciones
        </button>
      )}
    </section>
  );
}
