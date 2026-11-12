// Monitor del piloto — lector local acotado.
//
// Objetivo: el monitor EXPONE lo persistido y nada mas. No calcula economia,
// no inventa ceros, no duplica operaciones cuando la contabilidad actualiza la
// misma observation_id y no lee fuera del directorio autorizado.

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync, appendFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  buildPilotMonitor,
  pilotMonitorRoot,
  resolveRunDir,
} from "@/lib/pilot-monitor";

let root = "";

function runDir(name: string): string {
  const dir = path.join(root, name);
  mkdirSync(dir, { recursive: true });
  return dir;
}

function writeJson(file: string, value: unknown): void {
  writeFileSync(file, JSON.stringify(value, null, 2), "utf8");
}

function writeJsonl(file: string, rows: unknown[]): void {
  writeFileSync(
    file,
    rows.map((row) => JSON.stringify(row)).join("\n") + (rows.length ? "\n" : ""),
    "utf8",
  );
}

const STATUS_CAPTURA = {
  phase: "captura",
  run_id: "exp-v2-ventana-1-test",
  mode: "public",
  activar_publico: true,
  now_ms: 1_700_000_000_000,
  started_ms: 1_699_999_000_000,
  capture_end_ms: 1_700_002_600_000,
  settle_end_ms: 1_700_006_800_000,
  espera_contable_fin_ms: 1_700_039_200_000,
  duracion_maxima_total_ms: 40_200_000,
  espera_contable_plazo_max_ms: 32_400_000,
  followed: ["BTCUSDT", "ETHUSDT"],
  roles: { BTCUSDT: "candidate", ETHUSDT: "comparator" },
  pending: 2,
  stop_reason: null,
  presupuesto: {
    attempts: 120,
    retries: 3,
    weight: 900,
    max_attempts: 2000,
    max_retries: 50,
    max_weight: 5000,
    funding_rate_attempts_5m: 12,
    funding_rate_shared_limit_5m: 500,
    blocked: false,
    reason: null,
  },
  almacenamiento: {
    max_bytes: 134_217_728,
    used_bytes: 1000,
    reserved_bytes: 2000,
    accounted_bytes: 3000,
  },
  book: { BTCUSDT: { event_ms: 1_699_999_999_000, age_event_ms: 1000 } },
  flow: { BTCUSDT: { event_ms: 1_699_999_999_000, age_event_ms: 1000 } },
  feeds: {
    public: { connected_now: false, connections: 1, messages: 10 },
    market: { connected_now: false, connections: 1, messages: 12 },
  },
  espera_contable_pendientes: 1,
  funding_consultas_espera: { BTCUSDT: 2 },
  espera_contable_cierre: null,
};

const OPERATIVA_PENDIENTE = {
  kind: "resultado_operativo",
  observation_id: "BTCUSDT|1700000000000",
  symbol: "BTCUSDT",
  role: "candidate",
  direction: "LONG",
  decision: "ENTRADA_EJECUTADA",
  decision_ms: 1_700_000_000_000,
  entry_px: 100,
  entry_ms: 1_700_000_060_000,
  stop_px: 99.5,
  exit_px: 101,
  exit_ms: 1_700_003_660_000,
  exit_reason: "horizon",
  exit_executed: true,
  open_at_end: false,
  qty: 10,
  gross_pnl: 10,
  fees: 0.4,
  spread_slip: 0.1,
  funding: null,
  funding_estado: "settlement-calendar incompleto (UNKNOWN, no cero)",
  net_pnl: 9.5,
  neto_estado: "CONDICIONADO_SIN_FUNDING_COMPLETO",
  neto_motivo: "funding no acreditado: espera_contable",
  contabilidad_funding_estado: "PENDIENTE",
  contabilidad_funding_motivo: "espera_contable: liquidacion posterior todavia no observada",
  funding_sin_cubrir_ms: 28_800_000,
  ts_utc: "2026-11-12T00:00:00.000Z",
};

beforeEach(() => {
  root = mkdtempSync(path.join(tmpdir(), "pilot-monitor-"));
  process.env.PILOT_MONITOR_ROOT = root;
});

afterEach(() => {
  delete process.env.PILOT_MONITOR_ROOT;
});

describe("ruta de lectura acotada", () => {
  it("solo acepta un run_id simple y lo resuelve dentro de la raiz", () => {
    expect(resolveRunDir("exp-v2-ventana-1-20261112a")).toBe(
      path.join(pilotMonitorRoot(), "exp-v2-ventana-1-20261112a"),
    );
    expect(resolveRunDir("../fuera")).toBeNull();
    expect(resolveRunDir("a/b")).toBeNull();
    expect(resolveRunDir("..\\fuera")).toBeNull();
    expect(resolveRunDir("")).toBeNull();
    expect(resolveRunDir("con espacio")).toBeNull();
  });

  it("una corrida inexistente devuelve null (no un payload vacio)", () => {
    expect(buildPilotMonitor("no-existe")).toBeNull();
  });
});

describe("exposicion del estado persistido", () => {
  it("publica identidad, fase, plazos y presupuesto sin recalcular", () => {
    const dir = runDir("exp-v2-ventana-1-20261112a");
    writeJson(path.join(dir, "estado.json"), STATUS_CAPTURA);
    const payload = buildPilotMonitor("exp-v2-ventana-1-20261112a");
    expect(payload).not.toBeNull();
    expect(payload?.source).toBe("Binance público — experimento simulado");
    expect(payload?.phase).toBe("captura");
    expect(payload?.run_id).toBe("exp-v2-ventana-1-20261112a");
    expect(payload?.status_run_id).toBe("exp-v2-ventana-1-test");
    expect(payload?.tokens).toEqual([
      { symbol: "BTCUSDT", role: "candidate" },
      { symbol: "ETHUSDT", role: "comparator" },
    ]);
    expect(payload?.budget.attempts).toBe(120);
    expect(payload?.budget.max_attempts).toBe(2000);
    expect(payload?.budget.storage?.accounted_bytes).toBe(3000);
    expect(payload?.deadlines.max_total_ms).toBe(40_200_000);
    expect(payload?.health.feeds_closed).toBe(true);
    expect(payload?.accounting.consultas_totales).toBe(2);
  });

  it("cuenta ciclos, observaciones aptas, descartadas y sus motivos", () => {
    const dir = runDir("exp-v2-ventana-1-20261112a");
    writeJson(path.join(dir, "estado.json"), STATUS_CAPTURA);
    writeJsonl(path.join(dir, "observaciones.jsonl"), [
      {
        kind: "ciclo",
        cycle_id: "ciclo-1",
        reference_ms: 1_700_000_000_000,
        selected: [{ symbol: "BTCUSDT", side: "UP", move_24h_pct: 12.5 }],
        comparator: [{ symbol: "ETHUSDT", side: "DOWN", move_24h: -8.25 }],
      },
      {
        kind: "observacion",
        observation_id: "BTCUSDT|1700000000000",
        symbol: "BTCUSDT",
        apto_para_evaluacion: true,
        motivos: [],
      },
      {
        kind: "observacion",
        observation_id: "ETHUSDT|1700000000000",
        symbol: "ETHUSDT",
        apto_para_evaluacion: false,
        motivos: ["sin_libro", "dato_obsoleto_flujo"],
      },
    ]);
    const payload = buildPilotMonitor("exp-v2-ventana-1-20261112a");
    expect(payload?.cycles.total).toBe(1);
    expect(payload?.cycles.last_cycle_id).toBe("ciclo-1");
    expect(payload?.cycles.last_selection).toHaveLength(2);
    expect(payload?.observations.total).toBe(2);
    expect(payload?.observations.aptas).toBe(1);
    expect(payload?.observations.descartadas).toBe(1);
    expect(payload?.observations.motivos).toEqual([
      { motivo: "sin_libro", count: 1 },
      { motivo: "dato_obsoleto_flujo", count: 1 },
    ]);
  });

  it("la actualizacion contable de una observation_id no crea una operacion nueva", () => {
    const dir = runDir("exp-v2-ventana-1-20261112a");
    writeJson(path.join(dir, "estado.json"), {
      ...STATUS_CAPTURA,
      phase: "espera_contable",
      espera_contable_cierre: "trabajo_resuelto",
    });
    const file = path.join(dir, "resultado_operativo.jsonl");
    writeJsonl(file, [OPERATIVA_PENDIENTE]);
    const primera = buildPilotMonitor("exp-v2-ventana-1-20261112a");
    expect(primera?.counts.operaciones_unicas).toBe(1);
    expect(primera?.counts.filas_publicadas).toBe(1);
    expect(primera?.operations[0]?.contabilidad_funding_estado).toBe("PENDIENTE");
    expect(primera?.operations[0]?.funding).toBeNull();

    appendFileSync(
      file,
      JSON.stringify({
        ...OPERATIVA_PENDIENTE,
        contabilidad_funding_estado: "ACREDITADA",
        contabilidad_funding_motivo: "liquidaciones observadas; cobertura completa",
        funding: -0.12,
        neto_estado: "COMPLETO",
        neto_motivo: "funding acreditado y cobertura completa",
        funding_sin_cubrir_ms: 0,
        ts_utc: "2026-11-12T01:00:00.000Z",
      }) + "\n",
      "utf8",
    );
    const segunda = buildPilotMonitor("exp-v2-ventana-1-20261112a");
    expect(segunda?.counts.operaciones_unicas).toBe(1);
    expect(segunda?.counts.filas_publicadas).toBe(2);
    expect(segunda?.counts.actualizaciones_contables).toBe(1);
    expect(segunda?.operations).toHaveLength(1);
    expect(segunda?.operations[0]?.contabilidad_funding_estado).toBe("ACREDITADA");
    expect(segunda?.operations[0]?.neto_estado).toBe("COMPLETO");
    expect(segunda?.operations[0]?.funding).toBe(-0.12);
    expect(segunda?.operations[0]?.updates).toBe(2);
  });

  it("distingue abstencia, rechazo por capacidad y posicion abierta al final", () => {
    const dir = runDir("exp-v2-ventana-1-20261112a");
    writeJson(path.join(dir, "estado.json"), STATUS_CAPTURA);
    writeJsonl(path.join(dir, "resultado_operativo.jsonl"), [
      {
        ...OPERATIVA_PENDIENTE,
        observation_id: "A|1",
        decision: "SIN_ENTRADA",
        entry_px: null,
        entry_ms: null,
        stop_px: null,
        exit_px: null,
        exit_ms: null,
        exit_executed: false,
        gross_pnl: 0,
        fees: 0,
        spread_slip: 0,
        net_pnl: null,
        neto_estado: "UNKNOWN",
      },
      {
        ...OPERATIVA_PENDIENTE,
        observation_id: "B|2",
        decision: "RECHAZADA_CAPACIDAD",
        exit_px: null,
        exit_ms: null,
        exit_executed: false,
        net_pnl: null,
        neto_estado: "UNKNOWN",
      },
      {
        ...OPERATIVA_PENDIENTE,
        observation_id: "C|3",
        exit_px: null,
        exit_ms: null,
        exit_executed: false,
        open_at_end: true,
        net_pnl: null,
        neto_estado: "UNKNOWN",
      },
    ]);
    const payload = buildPilotMonitor("exp-v2-ventana-1-20261112a");
    expect(payload?.counts.abstenciones).toBe(1);
    expect(payload?.counts.rechazos_capacidad).toBe(1);
    expect(payload?.counts.abiertas_al_final).toBe(1);
    expect(payload?.operations[0]?.entry_px).toBeNull();
    expect(payload?.operations[0]?.funding).toBeNull();
  });

  it("si el fichero de la corrida se recrea, el estado se reconstruye", () => {
    const dir = runDir("exp-v2-ventana-1-20261112a");
    writeJson(path.join(dir, "estado.json"), STATUS_CAPTURA);
    writeJsonl(path.join(dir, "observaciones.jsonl"), [
      {
        kind: "observacion",
        observation_id: "BTCUSDT|1700000000000",
        symbol: "BTCUSDT",
        apto_para_evaluacion: false,
        motivos: ["sin_libro"],
      },
    ]);
    writeJsonl(path.join(dir, "resultado_operativo.jsonl"), [OPERATIVA_PENDIENTE]);
    const primera = buildPilotMonitor("exp-v2-ventana-1-20261112a");
    expect(primera?.observations.total).toBe(1);
    expect(primera?.counts.operaciones_unicas).toBe(1);

    // Corrida nueva en el mismo directorio: los artefactos anteriores ya no
    // pertenecen a la corrida y no pueden seguir publicados.
    writeJsonl(path.join(dir, "observaciones.jsonl"), []);
    writeJsonl(path.join(dir, "resultado_operativo.jsonl"), []);
    const segunda = buildPilotMonitor("exp-v2-ventana-1-20261112a");
    expect(segunda?.observations.total).toBe(0);
    expect(segunda?.observations.motivos).toEqual([]);
    expect(segunda?.counts.operaciones_unicas).toBe(0);
    expect(segunda?.counts.filas_publicadas).toBe(0);
    expect(segunda?.operations).toEqual([]);
  });

  it("una espera cerrada por plazo no es una interrupcion del operador", () => {    const dir = runDir("exp-v2-ventana-1-20261112a");
    writeJson(path.join(dir, "estado.json"), {
      ...STATUS_CAPTURA,
      phase: "fin",
      espera_contable_cierre: "plazo_maximo_de_espera_agotado",
      stop_reason: "duracion",
    });
    expect(buildPilotMonitor("exp-v2-ventana-1-20261112a")?.phase).toBe("finalizada");
  });

  it("una parada por presupuesto se marca como interrumpida", () => {
    const dir = runDir("exp-v2-ventana-1-20261112a");
    writeJson(path.join(dir, "estado.json"), {
      ...STATUS_CAPTURA,
      phase: "fin",
      stop_reason: "presupuesto_bytes",
      espera_contable_cierre: "presupuesto_bytes",
    });
    const payload = buildPilotMonitor("exp-v2-ventana-1-20261112a");
    expect(payload?.phase).toBe("interrumpida");
    expect(payload?.stop_reason).toBe("presupuesto_bytes");
  });
});
