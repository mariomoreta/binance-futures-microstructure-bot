"use client";
import {useCallback, useEffect, useState} from "react";
import type {PaperSessionState, PaperSessionSummary} from "@/lib/paper-lab-live";
import s from "./PaperLabLive.module.css";

interface SessionPersistenceProps {
  sessions: PaperSessionSummary[];
  onLoad: (sessionId: string) => void;
  onSave: () => Promise<void>;
}
export function SessionPersistence({sessions, onLoad, onSave}: SessionPersistenceProps) {
  const [saving, setSaving] = useState(false);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await onSave();
    } finally {
      setSaving(false);
    }
  }, [onSave]);

  return (
    <section className={s.card} aria-label="Persistencia de sesiones paper">
      <h3>Persistencia</h3>
      <p className={s.note}>
        Las sesiones se persisten en el backend (directorio aislado,
        fuera de datos operacionales) para poder recuperarlas tras un
        refresco sin perder el estado.
      </p>
      <div className={s.controls}>
        <label>Sesiones guardadas</label>
        <select className={s.controlGroup} style={{background:"#0b2334",border:"1px solid #285575",color:"#b9e2ff",padding:"5px 8px",borderRadius:"4px",font:"11px var(--font-mono)"}} onChange={(e) => {
          const id = e.target.value;
          if (!id) return;
          onLoad(id);
        }}>
          <option value="">— seleccionar —</option>
          {sessions.map((s) => (
            <option key={s.session_id} value={s.session_id}>
              {s.session_id} · {s.status} · {new Date(s.created_at_ms).toLocaleString()}
            </option>
          ))}
        </select>
        <button type="button" className={s.live} onClick={handleSave} disabled={saving || sessions.length === 0}>
          {saving ? "Guardando…" : "Refrescar lista"}
        </button>
      </div>
    </section>
  );
}
