"use client";
// Monitor del piloto operativo: lectura de estado ya persistido.
//
// El navegador NO calcula: recibe los campos del BFF y los presenta. No
// presenta como realized el P&L de una posicion abierta, no inventa ceros
// para campos ausentes y separa los tiempos del evento simulado de los
// tiempos de publicacion/reconstruccion.

import { useEffect, useState } from "react";
import type { PilotMonitorPayload, PilotOperation } from "@/lib/pilot-monitor";
import s from "./PilotMonitor.module.css";

const POLL_MS = 3000;

function fmtTime(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms)) return "—";
  return new Date(ms).toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

function fmtNum(value: number | null, digits = 4): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

function fmtMoney(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `${value.toFixed(4)} USDT`;
}

function fmtDuration(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms)) return "—";
  const total = Math.max(0, Math.round(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

const PHASE_LABEL: Record<string, string> = {
  captura: "Captura",
  resolucion: "Resolución",
  espera_contable: "Espera contable",
  finalizada: "Finalizada",
  interrumpida: "Interrumpida",
  desconocido: "Desconocida",
};

function phaseTone(phase: string): string {
  if (phase === "finalizada") return "pos";
  if (phase === "interrumpida") return "neg";
  if (phase === "espera_contable") return "warn";
  return "info";
}

function decisionLabel(decision: string): string {
  if (decision === "ENTRADA_EJECUTADA") return "Entrada simulada ejecutada";
  if (decision === "RECHAZADA_CAPACIDAD") return "Rechazo por capacidad";
  if (decision === "SIN_ENTRADA") return "Abstención";
  if (decision === "DESCARTADO") return "Descarte";
  if (decision === "ENTRADA_SIMULADA") return "Entrada simulada (sin fill)";
  if (decision === "PENDIENTE") return "Pendiente";
  return decision;
}

function accountingLabel(state: string | null): string {
  if (state === "PENDIENTE") return "PENDIENTE";
  if (state === "ACREDITADA") return "ACREDITADA";
  if (state === "UNKNOWN") return "UNKNOWN";
  return "—";
}

function accountingTone(state: string | null): string {
  if (state === "ACREDITADA") return "pos";
  if (state === "UNKNOWN") return "neg";
  if (state === "PENDIENTE") return "warn";
  return "muted";
}

function netTone(state: string | null): string {
  if (state === "COMPLETO") return "pos";
  if (state === "CONDICIONADO_SIN_FUNDING_COMPLETO") return "warn";
  return "muted";
}

function OperationRow({ op }: { op: PilotOperation }) {
  const abierta = op.open_at_end;
  const salida = op.exit_executed
    ? `${fmtNum(op.exit_px, 6)} @ ${fmtTime(op.exit_ms)}`
    : abierta
      ? "Posición abierta al final (sin salida ejecutada)"
      : "—";
  const pnl = abierta
    ? "No realizado (posición abierta)"
    : op.net_pnl === null
      ? "—"
      : fmtMoney(op.net_pnl);
  return (
    <tr data-testid={`pilot-op-${op.observation_id}`}>
      <td className={s.mono}>{op.observation_id}</td>
      <td>
        <strong>{op.symbol}</strong>
        <small>{op.role}</small>
      </td>
      <td>{op.direction ?? "—"}</td>
      <td data-testid={`pilot-decision-${op.observation_id}`}>
        {decisionLabel(op.decision)}
      </td>
      <td>
        {op.entry_px === null ? "—" : `${fmtNum(op.entry_px, 6)} @ ${fmtTime(op.entry_ms)}`}
      </td>
      <td>{fmtNum(op.stop_px, 6)}</td>
      <td>
        {salida}
        {op.exit_reason ? <small>motivo: {op.exit_reason}</small> : null}
      </td>
      <td>
        {fmtMoney(op.gross_pnl)}
        <small>costes: {fmtMoney((op.fees ?? 0) + (op.spread_slip ?? 0))}</small>
      </td>
      <td>
        {op.funding === null ? "—" : fmtMoney(op.funding)}
        {op.funding_estado ? <small>{op.funding_estado}</small> : null}
      </td>
      <td data-testid={`pilot-net-${op.observation_id}`}>
        <span className={s.chip} data-tone={netTone(op.neto_estado)}>
          {op.neto_estado ?? "—"}
        </span>
        <small>{pnl}</small>
        {op.neto_motivo ? <small>{op.neto_motivo}</small> : null}
      </td>
      <td data-testid={`pilot-accounting-${op.observation_id}`}>
        <span className={s.chip} data-tone={accountingTone(op.contabilidad_funding_estado)}>
          {accountingLabel(op.contabilidad_funding_estado)}
        </span>
        {op.contabilidad_funding_motivo ? (
          <small>{op.contabilidad_funding_motivo}</small>
        ) : null}
        {op.funding_sin_cubrir_ms ? (
          <small>sin cubrir: {op.funding_sin_cubrir_ms} ms</small>
        ) : null}
      </td>
      <td className={s.mono}>
        {fmtTime(op.published_at ? Date.parse(op.published_at) : null)}
        <small>{op.updates > 1 ? `${op.updates} publicaciones` : "1 publicación"}</small>
      </td>
    </tr>
  );
}

export function PilotMonitor({ runId }: { runId: string }) {
  const [data, setData] = useState<PilotMonitorPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    let alive = true;
    async function load() {
      try {
        const response = await fetch(`/api/v1/pilot-monitor?run=${encodeURIComponent(runId)}`, {
          cache: "no-store",
        });
        const body = (await response.json()) as {
          ok?: boolean;
          error?: string;
          data?: PilotMonitorPayload;
        };
        if (!alive) return;
        if (!response.ok || !body.ok || !body.data) {
          setError(body.error ?? `HTTP_${response.status}`);
          return;
        }
        setData(body.data);
        setError(null);
      } catch {
        if (alive) setError("LECTURA_LOCAL_NO_DISPONIBLE");
      }
    }
    void load();
    const timer = setInterval(() => void load(), POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [runId]);

  if (!runId) {
    return (
      <section className={s.root} data-testid="pilot-monitor">
        <p className={s.warn} role="alert">
          Monitor sin corrida: falta el identificador <code>run</code> en la URL.
        </p>
      </section>
    );
  }
  if (error && !data) {
    return (
      <section className={s.root} data-testid="pilot-monitor">
        <p className={s.warn} role="alert">
          No se pudo leer la corrida <strong>{runId}</strong>: {error}. Sin datos, sin ceros
          inventados.
        </p>
      </section>
    );
  }
  if (!data) {
    return (
      <section className={s.root} data-testid="pilot-monitor">
        <p className={s.muted}>Leyendo estado local de la corrida…</p>
      </section>
    );
  }

  const phase = data.phase;
  const esperaActiva = phase === "espera_contable";
  const feedsCerrados = data.health.feeds_closed === true;

  return (
    <section className={s.root} data-testid="pilot-monitor">
      <header className={s.header}>
        <div>
          <small>PILOTO OPERATIVO · MONITOR DE SOLO LECTURA</small>
          <h1>Monitor del piloto — {data.source}</h1>
          <p className={s.muted}>
            Lectura local de los artefactos de la corrida. El navegador no calcula
            decisiones, funding ni P&L.
          </p>
        </div>
        <div className={s.identity}>
          <span className={s.chip} data-tone="info" data-testid="pilot-run-id">
            run_id {data.run_id}
          </span>
          {data.status_run_id && data.status_run_id !== data.run_id ? (
            <span className={s.chip} data-tone="muted" data-testid="pilot-status-run-id">
              artefactos: {data.status_run_id}
            </span>
          ) : null}
          <span className={s.chip} data-tone={phaseTone(phase)} data-testid="pilot-phase">
            {PHASE_LABEL[phase] ?? phase}
          </span>
          <span className={s.chip} data-tone="muted" data-testid="pilot-source">
            {data.source}
          </span>
          {data.git_head ? (
            <span className={s.chip} data-tone="muted">
              sha {data.git_head.slice(0, 12)}
            </span>
          ) : null}
        </div>
      </header>

      {error ? (
        <p className={s.warn} role="status" data-testid="pilot-monitor-error">
          Última lectura fallida: {error}. Se conserva el último estado conocido.
        </p>
      ) : null}

      {esperaActiva || feedsCerrados ? (
        <p className={s.notice} data-testid="pilot-feeds-closed">
          <strong>Feeds cerrados.</strong> La captura terminó: no hay nuevas selecciones ni
          entradas y el mercado no está LIVE. Solo continúa la contabilidad de funding.
        </p>
      ) : null}

      <section className={s.card} aria-label="Identidad y progreso">
        <h2>Identidad y progreso</h2>
        <div className={s.metrics}>
          <Metric label="Fuente real" value={data.source} testid="pilot-metric-source" />
          <Metric label="Fase" value={PHASE_LABEL[phase] ?? phase} testid="pilot-metric-phase" />
          <Metric label="Inicio" value={fmtTime(data.started_ms)} testid="pilot-metric-start" />
          <Metric
            label="Última actualización del piloto"
            value={fmtTime(data.updated_ms)}
            testid="pilot-metric-updated"
          />
          <Metric label="Lectura del monitor" value={fmtTime(Date.parse(data.read_at))} />
          <Metric
            label="Fin de captura"
            value={fmtTime(data.deadlines.capture_end_ms)}
          />
          <Metric label="Fin de resolución" value={fmtTime(data.deadlines.settle_end_ms)} />
          <Metric
            label="Fin de espera contable"
            value={fmtTime(data.deadlines.accounting_end_ms)}
          />
          <Metric
            label="Plazo restante de contabilidad"
            value={fmtDuration(data.deadlines.accounting_remaining_ms)}
            testid="pilot-metric-remaining"
          />
          <Metric
            label="Duración máxima total"
            value={fmtDuration(data.deadlines.max_total_ms)}
            testid="pilot-metric-max-total"
          />
        </div>
        {data.stop_reason ? (
          <p className={s.muted}>
            Motivo de parada registrado: <code>{data.stop_reason}</code>
          </p>
        ) : null}
      </section>

      <section className={s.card} aria-label="Selección y observación">
        <h2>Selección, ciclos y observaciones</h2>
        <div className={s.metrics}>
          <Metric label="Ciclos" value={String(data.cycles.total)} testid="pilot-metric-cycles" />
          <Metric label="Observaciones" value={String(data.observations.total)} />
          <Metric label="Aptas" value={String(data.observations.aptas)} testid="pilot-metric-aptas" />
          <Metric
            label="Descartadas"
            value={String(data.observations.descartadas)}
            testid="pilot-metric-descartadas"
          />
          <Metric label="Último ciclo" value={data.cycles.last_cycle_id ?? "—"} />
          <Metric
            label="Referencia del último ciclo"
            value={fmtTime(data.cycles.last_reference_ms)}
          />
        </div>
        <div className={s.split}>
          <div>
            <h3>Motivos de descarte</h3>
            {data.observations.motivos.length === 0 ? (
              <p className={s.muted}>Sin descartes registrados.</p>
            ) : (
              <ul className={s.list}>
                {data.observations.motivos.map((item) => (
                  <li key={item.motivo}>
                    <span>{item.motivo}</span>
                    <b>{item.count}</b>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3>Tokens seguidos y rol</h3>
            {data.tokens.length === 0 ? (
              <p className={s.muted}>Sin tokens seguidos todavía.</p>
            ) : (
              <ul className={s.list}>
                {data.tokens.map((token) => (
                  <li key={token.symbol}>
                    <span>{token.symbol}</span>
                    <b>{token.role}</b>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        {data.cycles.last_selection.length > 0 ? (
          <>
            <h3>Última selección registrada</h3>
            <table className={s.table}>
              <thead>
                <tr>
                  <th>Símbolo</th>
                  <th>Rol</th>
                  <th>Lado</th>
                  <th>Movimiento 24h</th>
                </tr>
              </thead>
              <tbody>
                {data.cycles.last_selection.map((row, index) => (
                  <tr key={`${row.symbol}-${index}`}>
                    <td>{row.symbol}</td>
                    <td>{row.role ?? "—"}</td>
                    <td>{row.side ?? "—"}</td>
                    <td>{row.move_24h_pct === null ? "—" : `${row.move_24h_pct.toFixed(2)} %`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : null}
      </section>

      <section className={s.card} aria-label="Salud de fuentes">
        <h2>Salud y frescura de libro y flujo</h2>
        <div className={s.metrics}>
          {data.health.feeds.map((feed) => (
            <Metric
              key={feed.name}
              label={`Feed ${feed.name}`}
              value={
                feed.connected_now === null
                  ? "—"
                  : feed.connected_now
                    ? "Conectado"
                    : "Cerrado"
              }
              testid={`pilot-feed-${feed.name}`}
            />
          ))}
          <Metric
            label="Estado de feeds"
            value={data.health.feeds_closed === null ? "—" : data.health.feeds_closed ? "Cerrados" : "Abiertos"}
            testid="pilot-feeds-state"
          />
        </div>
        <div className={s.split}>
          <FreshnessTable title="Libro (edad del último evento)" rows={data.health.book} />
          <FreshnessTable title="Flujo (edad del último evento)" rows={data.health.flow} />
        </div>
      </section>

      <section className={s.card} aria-label="Presupuesto consumido">
        <h2>Presupuesto consumido y límites</h2>
        <div className={s.metrics}>
          <Metric
            label="Intentos HTTP"
            value={
              data.budget.attempts === null
                ? "—"
                : `${data.budget.attempts} / ${data.budget.max_attempts ?? "—"}`
            }
            testid="pilot-budget-attempts"
          />
          <Metric
            label="Reintentos"
            value={
              data.budget.retries === null
                ? "—"
                : `${data.budget.retries} / ${data.budget.max_retries ?? "—"}`
            }
          />
          <Metric
            label="Peso reservado"
            value={
              data.budget.weight === null
                ? "—"
                : `${data.budget.weight} / ${data.budget.max_weight ?? "—"}`
            }
            testid="pilot-budget-weight"
          />
          <Metric
            label="Consultas funding (5 min)"
            value={
              data.budget.funding_rate_attempts_5m === null
                ? "—"
                : `${data.budget.funding_rate_attempts_5m} / ${
                    data.budget.funding_rate_shared_limit_5m ?? "—"
                  }`
            }
          />
          <Metric
            label="Almacenamiento contabilizado"
            value={
              data.budget.storage?.accounted_bytes === null ||
              data.budget.storage?.accounted_bytes === undefined
                ? "—"
                : `${data.budget.storage.accounted_bytes} / ${data.budget.storage.max_bytes ?? "—"} B`
            }
            testid="pilot-budget-storage"
          />
          <Metric
            label="Puerta de presupuesto"
            value={
              data.budget.blocked === null
                ? "—"
                : data.budget.blocked
                  ? `Bloqueada (${data.budget.reason ?? "sin motivo"})`
                  : "Abierta"
            }
            testid="pilot-budget-blocked"
          />
        </div>
      </section>

      <section className={s.card} aria-label="Contabilidad de funding">
        <h2>Contabilidad de funding</h2>
        <div className={s.metrics}>
          <Metric
            label="Posiciones pendientes de contabilidad"
            value={data.accounting.pending_contabilidad === null ? "—" : String(data.accounting.pending_contabilidad)}
            testid="pilot-accounting-pending"
          />
          <Metric label="Consultas de funding" value={String(data.accounting.consultas_totales)} />
          <Metric label="Cierre" value={data.accounting.cierre ?? "—"} testid="pilot-accounting-closure" />
        </div>
        {data.accounting.consultas_por_simbolo.length > 0 ? (
          <ul className={s.list}>
            {data.accounting.consultas_por_simbolo.map((item) => (
              <li key={item.symbol}>
                <span>{item.symbol}</span>
                <b>{item.consultas}</b>
              </li>
            ))}
          </ul>
        ) : (
          <p className={s.muted}>Sin consultas de funding registradas todavía.</p>
        )}
      </section>

      <section className={s.card} aria-label="Operaciones simuladas">
        <h2>Operaciones simuladas</h2>
        <div className={s.metrics}>
          <Metric label="Filas publicadas" value={String(data.counts.filas_publicadas)} />
          <Metric
            label="Operaciones únicas"
            value={String(data.counts.operaciones_unicas)}
            testid="pilot-ops-unique"
          />
          <Metric
            label="Actualizaciones contables"
            value={String(data.counts.actualizaciones_contables)}
            testid="pilot-ops-updates"
          />
          <Metric label="Entradas simuladas" value={String(data.counts.entradas_simuladas)} />
          <Metric label="Abstenciones" value={String(data.counts.abstenciones)} />
          <Metric
            label="Rechazos por capacidad"
            value={String(data.counts.rechazos_capacidad)}
            testid="pilot-ops-capacity"
          />
          <Metric label="Descartes" value={String(data.counts.descartes)} />
          <Metric
            label="Posiciones abiertas al final"
            value={String(data.counts.abiertas_al_final)}
            testid="pilot-ops-open"
          />
          <Metric label="Neto completo" value={String(data.counts.neto_completo)} />
          <Metric label="Neto condicionado" value={String(data.counts.neto_conditionado)} />
        </div>
        {data.operations.length === 0 ? (
          <p className={s.muted}>
            Sin operaciones publicadas todavía. Las entradas y salidas se reconstruyen
            después de la captura.
          </p>
        ) : (
          <div className={s.tableWrap}>
            <table className={`${s.table} ${s.opsTable}`} data-testid="pilot-operations">
              <thead>
                <tr>
                  <th>observation_id</th>
                  <th>Símbolo</th>
                  <th>Dirección</th>
                  <th>Decisión</th>
                  <th>Entrada simulada</th>
                  <th>Stop</th>
                  <th>Salida simulada</th>
                  <th>Bruto y costes</th>
                  <th>Funding</th>
                  <th>Neto</th>
                  <th>Contabilidad</th>
                  <th>Publicado</th>
                </tr>
              </thead>
              <tbody>
                {data.operations.map((op) => (
                  <OperationRow key={op.observation_id} op={op} />
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className={s.muted}>
          Las entradas y salidas son simulaciones reconstruidas con sus tiempos
          históricos; no son órdenes enviadas. Un registro contable posterior actualiza la
          misma observation_id y no crea una operación nueva.
        </p>
      </section>
    </section>
  );
}

function Metric({
  label,
  value,
  testid,
}: {
  label: string;
  value: string;
  testid?: string;
}) {
  return (
    <section>
      <small>{label}</small>
      <strong data-testid={testid}>{value}</strong>
    </section>
  );
}

function FreshnessTable({
  title,
  rows,
}: {
  title: string;
  rows: Record<string, number | null>;
}) {
  const entries = Object.entries(rows);
  return (
    <div>
      <h3>{title}</h3>
      {entries.length === 0 ? (
        <p className={s.muted}>Sin datos de esta fuente.</p>
      ) : (
        <table className={s.table}>
          <thead>
            <tr>
              <th>Símbolo</th>
              <th>Edad</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([symbol, age]) => (
              <tr key={symbol}>
                <td>{symbol}</td>
                <td>{age === null ? "—" : fmtDuration(age)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
