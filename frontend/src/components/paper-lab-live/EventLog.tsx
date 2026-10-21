"use client";
import type {PaperEvent} from "@/lib/paper-lab-live";
import s from "./PaperLabLive.module.css";

interface EventLogProps { events: PaperEvent[]; }
export function EventLog({events}: EventLogProps) {
  if (events.length === 0) {
    return (
      <section className={s.panel} aria-label="Registro de eventos paper">
        <h3>Registro de eventos</h3>
        <div className={s.empty}>Sin eventos revelados aún.</div>
      </section>
    );
  }
  return (
    <section className={s.panel} aria-label="Registro de eventos paper">
      <h3>Registro de eventos (hasta el cursor)</h3>
      <div className={s.log}>
        {events.map((e, i) => (
          <div key={i} className={s.logEntry}>
            <span className={s.logTime}>{new Date(e.at_ms).toISOString()}</span>
            <span className={s.logLabel}>{e.label}{e.detail ? ` · ${e.detail}` : ""}</span>
            <span className={`${s.logKind} ${s[e.kind]}`}>{e.kind}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
