// Monitor de observabilidad del piloto operativo (`scripts/research_pilot.py`).
//
// CONTRATO (sin excepciones):
// - Solo lectura local de artefactos ya persistidos. Ningún fetch, ningún
//   proceso, ninguna conexión a Binance ni a ningún servicio.
// - No calcula decisiones, funding ni P&L: expone exactamente lo que el
//   piloto escribió. El navegador tampoco calcula: recibe estos campos.
// - Ruta de lectura acotada: el cliente NUNCA envía una ruta. Solo un
//   `run_id` validado, resuelto dentro de `PILOT_MONITOR_ROOT`.
//
// Los tiempos se mantienen separados: `decision_ms`/`entry_ms`/`exit_ms` son
// tiempos del evento simulado; `published_at`/`read_at` son tiempos de
// reconstrucción o publicación. Un campo ausente se publica como `null`
// (nunca como cero).

import {
  closeSync,
  existsSync,
  fstatSync,
  openSync,
  readFileSync,
  readSync,
  readdirSync,
} from "node:fs";
import path from "node:path";

const DEFAULT_ROOT = "C:/proyectos/binance-futures-data";

export const PILOT_MONITOR_RUN_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
export const PILOT_SOURCE_PUBLIC = "Binance público — experimento simulado";
export const PILOT_SOURCE_LOCAL = "Proveedor loopback local — experimento simulado";

export type PilotPhase =
  | "captura"
  | "resolucion"
  | "espera_contable"
  | "finalizada"
  | "interrumpida"
  | "desconocida";

export type PilotOperation = {
  observation_id: string;
  symbol: string;
  role: string;
  direction: string | null;
  decision: string;
  decision_ms: number | null;
  entry_px: number | null;
  entry_ms: number | null;
  stop_px: number | null;
  exit_px: number | null;
  exit_ms: number | null;
  exit_reason: string | null;
  exit_executed: boolean;
  open_at_end: boolean;
  qty: number | null;
  gross_pnl: number | null;
  fees: number | null;
  spread_slip: number | null;
  funding: number | null;
  funding_estado: string | null;
  net_pnl: number | null;
  neto_estado: string | null;
  neto_motivo: string | null;
  contabilidad_funding_estado: string | null;
  contabilidad_funding_motivo: string | null;
  funding_sin_cubrir_ms: number | null;
  funding_huecos_ms: number | null;
  funding_settlements_desconocidos: number | null;
  published_at: string | null;
  updates: number;
};

export type PilotSelectionRow = {
  symbol: string;
  side: string | null;
  role: string | null;
  move_24h_pct: number | null;
};

export type PilotMonitorPayload = {
  schema_version: 1;
  run_id: string;
  status_run_id: string | null;
  source: string;
  mode: string | null;
  git_head: string | null;
  phase: PilotPhase;
  phase_raw: string | null;
  status_present: boolean;
  read_at: string;
  updated_at: string | null;
  updated_ms: number | null;
  started_ms: number | null;
  started_at: string | null;
  stop_reason: string | null;
  deadlines: {
    capture_end_ms: number | null;
    settle_end_ms: number | null;
    accounting_end_ms: number | null;
    max_total_ms: number | null;
    accounting_remaining_ms: number | null;
  };
  tokens: { symbol: string; role: string }[];
  cycles: {
    total: number;
    last_cycle_id: string | null;
    last_reference_ms: number | null;
    last_selection: PilotSelectionRow[];
  };
  observations: {
    total: number;
    aptas: number;
    descartadas: number;
    motivos: { motivo: string; count: number }[];
  };
  health: {
    feeds: {
      name: string;
      connected_now: boolean | null;
      connections: number | null;
      messages: number | null;
    }[];
    feeds_closed: boolean | null;
    book: Record<string, number | null>;
    flow: Record<string, number | null>;
  };
  budget: {
    attempts: number | null;
    retries: number | null;
    weight: number | null;
    max_attempts: number | null;
    max_retries: number | null;
    max_weight: number | null;
    blocked: boolean | null;
    reason: string | null;
    funding_rate_attempts_5m: number | null;
    funding_rate_shared_limit_5m: number | null;
    storage: {
      used_bytes: number | null;
      reserved_bytes: number | null;
      accounted_bytes: number | null;
      max_bytes: number | null;
    } | null;
  };
  accounting: {
    pending_operativos: number | null;
    pending_contabilidad: number | null;
    consultas_por_simbolo: { symbol: string; consultas: number }[];
    consultas_totales: number;
    cierre: string | null;
  };
  operations: PilotOperation[];
  counts: {
    filas_publicadas: number;
    operaciones_unicas: number;
    actualizaciones_contables: number;
    entradas_simuladas: number;
    abstenciones: number;
    rechazos_capacidad: number;
    descartes: number;
    abiertas_al_final: number;
    neto_completo: number;
    neto_conditionado: number;
    neto_unknown: number;
    contabilidad_pendiente: number;
    contabilidad_acreditada: number;
    contabilidad_unknown: number;
    por_rol: Record<string, number>;
  };
};

// --- utilidades de lectura --------------------------------------------------

function obj(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function flag(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function readJsonSafe(file: string): Record<string, unknown> | null {
  try {
    if (!existsSync(file)) return null;
    const parsed = JSON.parse(readFileSync(file, "utf8")) as unknown;
    return obj(parsed);
  } catch {
    return null;
  }
}

/** Lector incremental de JSONL append-only: solo consume bytes nuevos. */
class JsonlReader {
  private offset = 0;
  private size = 0;
  private tail = "";

  constructor(private readonly file: string) {}

  /**
   * Consume las filas nuevas. `onRestart` se invoca cuando el fichero se
   * reescribe (o desaparece): el estado derivado debe reconstruirse desde
   * cero, porque las filas anteriores ya no pertenecen a la corrida.
   */
  read(onRestart: () => void, onRow: (row: Record<string, unknown>) => void): void {
    if (!existsSync(this.file)) {
      onRestart();
      return;
    }
    const fd = openSync(this.file, "r");
    try {
      const stat = fstatSync(fd);
      if (stat.size < this.size) {
        // El fichero se reescribio: se relee desde el inicio.
        this.offset = 0;
        this.size = 0;
        this.tail = "";
        onRestart();
      }
      if (stat.size === this.offset) return;
      const length = stat.size - this.offset;
      const buffer = Buffer.allocUnsafe(length);
      let read = 0;
      while (read < length) {
        const chunk = readSync(fd, buffer, read, length - read, this.offset + read);
        if (chunk <= 0) break;
        read += chunk;
      }
      this.tail += buffer.subarray(0, read).toString("utf8");
      const parts = this.tail.split("\n");
      this.tail = parts.pop() ?? "";
      for (const line of parts) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const row = obj(JSON.parse(trimmed));
          if (row) onRow(row);
        } catch {
          // Linea no parseable: no se inventa un registro.
        }
      }
      this.offset = stat.size;
      this.size = stat.size;
    } finally {
      closeSync(fd);
    }
  }
}

type ObservationsState = {
  reader: JsonlReader;
  cycles: number;
  observations: number;
  aptas: number;
  descartadas: number;
  motivos: Map<string, number>;
  lastCycle: Record<string, unknown> | null;
  lastSelection: PilotSelectionRow[];
};

type OperationsState = {
  reader: JsonlReader;
  rows: number;
  byId: Map<string, PilotOperation>;
};

const observationsCache = new Map<string, ObservationsState>();
const operationsCache = new Map<string, OperationsState>();

function observationsState(dir: string): ObservationsState {
  const cached = observationsCache.get(dir);
  if (cached) return cached;
  const state: ObservationsState = {
    reader: new JsonlReader(path.join(dir, "observaciones.jsonl")),
    cycles: 0,
    observations: 0,
    aptas: 0,
    descartadas: 0,
    motivos: new Map<string, number>(),
    lastCycle: null,
    lastSelection: [],
  };
  observationsCache.set(dir, state);
  return state;
}

function operationsState(dir: string): OperationsState {
  const cached = operationsCache.get(dir);
  if (cached) return cached;
  const state: OperationsState = {
    reader: new JsonlReader(path.join(dir, "resultado_operativo.jsonl")),
    rows: 0,
    byId: new Map<string, PilotOperation>(),
  };
  operationsCache.set(dir, state);
  return state;
}

function selectionRows(cycle: Record<string, unknown> | null): PilotSelectionRow[] {
  if (!cycle) return [];
  const out: PilotSelectionRow[] = [];
  for (const key of ["selected", "comparator"] as const) {
    const rows = cycle[key];
    if (!Array.isArray(rows)) continue;
    for (const item of rows) {
      const row = obj(item);
      if (!row) continue;
      out.push({
        symbol: str(row.symbol) ?? "UNKNOWN",
        side: str(row.side),
        role: str(row.role),
        move_24h_pct: num(row.move_24h_pct) ?? num(row.move_24h),
      });
    }
  }
  return out;
}

function operationFromRow(row: Record<string, unknown>, updates: number): PilotOperation {
  return {
    observation_id: str(row.observation_id) ?? "UNKNOWN",
    symbol: str(row.symbol) ?? "UNKNOWN",
    role: str(row.role) ?? "UNKNOWN",
    direction: str(row.direction),
    decision: str(row.decision) ?? "UNKNOWN",
    decision_ms: num(row.decision_ms),
    entry_px: num(row.entry_px),
    entry_ms: num(row.entry_ms),
    stop_px: num(row.stop_px),
    exit_px: num(row.exit_px),
    exit_ms: num(row.exit_ms),
    exit_reason: str(row.exit_reason),
    exit_executed: flag(row.exit_executed) ?? false,
    open_at_end: flag(row.open_at_end) ?? false,
    qty: num(row.qty),
    gross_pnl: num(row.gross_pnl),
    fees: num(row.fees),
    spread_slip: num(row.spread_slip),
    funding: num(row.funding),
    funding_estado: str(row.funding_estado),
    net_pnl: num(row.net_pnl),
    neto_estado: str(row.neto_estado),
    neto_motivo: str(row.neto_motivo),
    contabilidad_funding_estado: str(row.contabilidad_funding_estado),
    contabilidad_funding_motivo: str(row.contabilidad_funding_motivo),
    funding_sin_cubrir_ms: num(row.funding_sin_cubrir_ms),
    funding_huecos_ms: num(row.funding_huecos_ms),
    funding_settlements_desconocidos: num(row.funding_settlements_desconocidos),
    published_at: str(row.ts_utc),
    updates,
  };
}

// --- contrato de lectura ----------------------------------------------------

export function pilotMonitorRoot(): string {
  return path.resolve(process.env.PILOT_MONITOR_ROOT ?? DEFAULT_ROOT);
}

/** Resuelve un `run_id` dentro de la raiz autorizada. `null` si no es valido. */
export function resolveRunDir(runId: string): string | null {
  if (!PILOT_MONITOR_RUN_ID_RE.test(runId)) return null;
  const root = pilotMonitorRoot();
  const dir = path.resolve(root, runId);
  const relative = path.relative(root, dir);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) return null;
  if (path.basename(dir) !== runId) return null;
  return dir;
}

function statusFile(dir: string): string | null {
  const preferred = path.join(dir, "estado.json");
  if (existsSync(preferred)) return preferred;
  try {
    const match = readdirSync(dir)
      .filter((name) => /^estado.*\.json$/i.test(name))
      .sort()[0];
    return match ? path.join(dir, match) : null;
  } catch {
    return null;
  }
}

function classifyPhase(
  raw: string | null,
  stopReason: string | null,
  cierre: string | null,
): PilotPhase {
  if (raw === "captura") return "captura";
  if (raw === "settle") return "resolucion";
  if (raw === "espera_contable") return "espera_contable";
  if (raw !== "fin") return "desconocida";
  const motivo = cierre ?? stopReason ?? "";
  if (
    motivo === "" ||
    motivo === "trabajo_resuelto" ||
    motivo === "duracion" ||
    motivo === "plazo_maximo_de_espera_agotado"
  ) {
    return "finalizada";
  }
  return "interrumpida";
}

function numbersBySymbol(value: unknown): { symbol: string; consultas: number }[] {
  const record = obj(value);
  if (!record) return [];
  return Object.entries(record)
    .map(([symbol, count]) => ({ symbol, consultas: num(count) ?? 0 }))
    .sort((a, b) => (a.symbol < b.symbol ? -1 : a.symbol > b.symbol ? 1 : 0));
}

/** Construye el payload de monitor. `null` si la corrida no existe. */
export function buildPilotMonitor(runId: string): PilotMonitorPayload | null {
  const dir = resolveRunDir(runId);
  if (!dir || !existsSync(dir)) return null;

  const statusFilePath = statusFile(dir);
  const status = statusFilePath ? readJsonSafe(statusFilePath) : null;
  const resumen = readJsonSafe(path.join(dir, "resumen.json"));
  const manifiesto = readJsonSafe(path.join(dir, "manifiesto.json"));

  const obs = observationsState(dir);
  obs.reader.read(
    () => {
      obs.cycles = 0;
      obs.observations = 0;
      obs.aptas = 0;
      obs.descartadas = 0;
      obs.motivos.clear();
      obs.lastCycle = null;
      obs.lastSelection = [];
    },
    (row) => {
      const kind = str(row.kind);
      if (kind === "ciclo") {
        obs.cycles += 1;
        obs.lastCycle = row;
        obs.lastSelection = selectionRows(row);
        return;
      }
      if (kind !== "observacion") return;
      obs.observations += 1;
      if (flag(row.apto_para_evaluacion) === true) obs.aptas += 1;
      else obs.descartadas += 1;
      const motivos = row.motivos;
      if (Array.isArray(motivos)) {
        for (const motivo of motivos) {
          const key = str(motivo);
          if (!key) continue;
          obs.motivos.set(key, (obs.motivos.get(key) ?? 0) + 1);
        }
      }
    },
  );

  const ops = operationsState(dir);
  ops.reader.read(
    () => {
      ops.rows = 0;
      ops.byId.clear();
    },
    (row) => {
      if (str(row.kind) !== "resultado_operativo") return;
      ops.rows += 1;
      const id = str(row.observation_id) ?? `sin-id-${ops.rows}`;
      const previous = ops.byId.get(id);
      ops.byId.set(id, operationFromRow(row, (previous?.updates ?? 0) + 1));
    },
  );

  const operations = [...ops.byId.values()].sort((a, b) => {
    const left = a.decision_ms ?? 0;
    const right = b.decision_ms ?? 0;
    if (left !== right) return left - right;
    return a.observation_id < b.observation_id ? -1 : 1;
  });

  const mode = str(status?.mode);
  const phaseRaw = str(status?.phase);
  const stopReason = str(status?.stop_reason);
  const cierre = str(status?.espera_contable_cierre);
  const nowMs = num(status?.now_ms);
  const accountingEnd = num(status?.espera_contable_fin_ms);
  const followed = Array.isArray(status?.followed) ? status.followed : [];
  const roles = obj(status?.roles) ?? {};
  const feedsRecord = obj(status?.feeds) ?? {};
  const presupuesto = obj(status?.presupuesto);
  const almacenamiento = obj(status?.almacenamiento);
  const consultas = numbersBySymbol(status?.funding_consultas_espera);

  const counts = {
    filas_publicadas: ops.rows,
    operaciones_unicas: ops.byId.size,
    actualizaciones_contables: Math.max(0, ops.rows - ops.byId.size),
    entradas_simuladas: operations.filter((op) => op.decision === "ENTRADA_EJECUTADA").length,
    abstenciones: operations.filter((op) => op.decision === "SIN_ENTRADA").length,
    rechazos_capacidad: operations.filter((op) => op.decision === "RECHAZADA_CAPACIDAD").length,
    descartes: operations.filter((op) => op.decision === "DESCARTADO").length,
    abiertas_al_final: operations.filter((op) => op.open_at_end).length,
    neto_completo: operations.filter((op) => op.neto_estado === "COMPLETO").length,
    neto_conditionado: operations.filter(
      (op) => op.neto_estado === "CONDICIONADO_SIN_FUNDING_COMPLETO",
    ).length,
    neto_unknown: operations.filter((op) => op.neto_estado === "UNKNOWN").length,
    contabilidad_pendiente: operations.filter(
      (op) => op.contabilidad_funding_estado === "PENDIENTE",
    ).length,
    contabilidad_acreditada: operations.filter(
      (op) => op.contabilidad_funding_estado === "ACREDITADA",
    ).length,
    contabilidad_unknown: operations.filter(
      (op) => op.contabilidad_funding_estado === "UNKNOWN",
    ).length,
    por_rol: operations.reduce<Record<string, number>>((acc, op) => {
      acc[op.role] = (acc[op.role] ?? 0) + 1;
      return acc;
    }, {}),
  };

  const feeds = Object.entries(feedsRecord).map(([name, value]) => {
    const feed = obj(value) ?? {};
    return {
      name,
      connected_now: flag(feed.connected_now),
      connections: num(feed.connections),
      messages: num(feed.messages),
    };
  });

  return {
    schema_version: 1,
    run_id: runId,
    status_run_id: str(status?.run_id),
    source: mode === "public" ? PILOT_SOURCE_PUBLIC : PILOT_SOURCE_LOCAL,
    mode,
    git_head: str(manifiesto?.git_head),
    phase: classifyPhase(phaseRaw, stopReason, cierre),
    phase_raw: phaseRaw,
    status_present: status !== null,
    read_at: new Date().toISOString(),
    updated_at: nowMs === null ? null : new Date(nowMs).toISOString(),
    updated_ms: nowMs,
    started_ms: num(status?.started_ms),
    started_at: num(status?.started_ms) === null ? null : new Date(Number(status?.started_ms)).toISOString(),
    stop_reason: stopReason,
    deadlines: {
      capture_end_ms: num(status?.capture_end_ms),
      settle_end_ms: num(status?.settle_end_ms),
      accounting_end_ms: accountingEnd,
      max_total_ms: num(status?.duracion_maxima_total_ms),
      accounting_remaining_ms:
        accountingEnd !== null && nowMs !== null ? accountingEnd - nowMs : null,
    },
    tokens: followed
      .map((symbol) => str(symbol))
      .filter((symbol): symbol is string => symbol !== null)
      .map((symbol) => ({ symbol, role: str(roles[symbol]) ?? "UNKNOWN" })),
    cycles: {
      total: obs.cycles,
      last_cycle_id: str(obs.lastCycle?.cycle_id),
      last_reference_ms: num(obs.lastCycle?.reference_ms),
      last_selection: obs.lastSelection,
    },
    observations: {
      total: obs.observations,
      aptas: obs.aptas,
      descartadas: obs.descartadas,
      motivos: [...obs.motivos.entries()]
        .map(([motivo, count]) => ({ motivo, count }))
        .sort((a, b) => b.count - a.count),
    },
    health: {
      feeds,
      feeds_closed: feeds.length
        ? feeds.every((feed) => feed.connected_now === false)
        : null,
      book: (obj(status?.book) ?? {}) as Record<string, number | null>,
      flow: (obj(status?.flow) ?? {}) as Record<string, number | null>,
    },
    budget: {
      attempts: num(presupuesto?.attempts),
      retries: num(presupuesto?.retries),
      weight: num(presupuesto?.weight),
      max_attempts: num(presupuesto?.max_attempts),
      max_retries: num(presupuesto?.max_retries),
      max_weight: num(presupuesto?.max_weight),
      blocked: flag(presupuesto?.blocked),
      reason: str(presupuesto?.reason),
      funding_rate_attempts_5m: num(presupuesto?.funding_rate_attempts_5m),
      funding_rate_shared_limit_5m: num(presupuesto?.funding_rate_shared_limit_5m),
      storage: almacenamiento
        ? {
            used_bytes: num(almacenamiento.used_bytes),
            reserved_bytes: num(almacenamiento.reserved_bytes),
            accounted_bytes: num(almacenamiento.accounted_bytes),
            max_bytes: num(almacenamiento.max_bytes),
          }
        : null,
    },
    accounting: {
      pending_operativos: num(status?.pending),
      pending_contabilidad: num(status?.espera_contable_pendientes),
      consultas_por_simbolo: consultas,
      consultas_totales: consultas.reduce((acc, item) => acc + item.consultas, 0),
      cierre: cierre ?? str(obj(resumen?.espera_contable)?.cierre),
    },
    operations,
    counts,
  };
}
