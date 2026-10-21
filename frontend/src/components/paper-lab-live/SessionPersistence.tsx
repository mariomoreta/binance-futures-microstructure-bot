"use client";
import {useCallback, useEffect, useState} from "react";
import type {PaperSessionState} from "@/lib/paper-lab-live";
import s from "./PaperLabLive.module.css";

interface SessionPersistenceProps {
  sessions: PaperSessionState[];
  onLoad: (session: PaperSessionState) => void;
  onSave: (session: PaperSessionState) => Promise<void>;
}
export function SessionPersistence({sessions, onLoad, onSave}: SessionPersistenceProps) {
  const [saving, setSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<string | null>(null);

  const handleSave = useCallback(async (session: PaperSessionState) => {
    setSaving(true);
    try {
      await onSave(session);
      setLastSaved(session.session_id);
    } finally {
      setSaving(false);
    }
  }, [onSave]);

  return (
    <section className={s.card} aria-label="Persistencia de sesiones paper">
      <h3>Persistencia</h3>
      <p className={s.note}>
        Guarde y cargue sesiones de paper. Las sesiones se persisten en disco
        (directorio aislado, fuera de datos operacionales) para poder revisarlas
        despues sin perder el estado.
      </p>
      <div className={s.controls}>
        <label>Sesiones guardadas</label>
        <select className={s.controlGroup} style={{background:"#0b2334",border:"1px solid #285575",color:"#b9e2ff",padding:"5px 8px",borderRadius:"4px",font:"11px var(--font-mono)"}} onChange={(e) => {
          const id = e.target.value;
          if (!id) return;
          const s = sessions.find((x) => x.session_id === id);
          if (s) onLoad(s);
        }}>
          <option value="">— seleccionar —</option>
          {sessions.map((s) => (
            <option key={s.session_id} value={s.session_id}>
              {s.session_id} · {s.status} · {new Date(s.created_at_ms).toLocaleString()}
            </option>
          ))}
        </select>
        <button type="button" className={s.live} onClick={() => handleSave(sessions[sessions.length - 1]!)} disabled={saving || sessions.length === 0}>
          {saving ? "Guardando…" : "Guardar sesion actual"}
        </button>
        {lastSaved && <span className={s.mono} style={{marginLeft:8}}>Ultimo guardado: {lastSaved.slice(0, 20)}…</span>}
      </div>
    </section>
  );
}
