// @vitest-environment jsdom
// Monitor del piloto — presentacion.
//
// Objetivo: el panel PRESENTA lo que el BFF entrego. No calcula economia, no
// inventa ceros, no presenta como realizado el P&L de una posicion abierta,
// separa abstencia de rechazo por capacidad y refleja los cambios de fase sin
// recargar la pagina.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { PilotMonitor } from "@/components/pilot-monitor/PilotMonitor";
import type { PilotMonitorPayload, PilotOperation } from "@/lib/pilot-monitor";

const BASE: PilotMonitorPayload = {
  schema_version: 1,
  run_id: "exp-v2-ventana-1-20261112a",
  status_run_id: "exp-v2-ventana-1-20261112a",
  source: "Binance público — experimento simulado",
  mode: "public",
  git_head: "ea984c235eb5234d508bf46f52d794321cfc6ab4",
  phase: "captura",
  phase_raw: "captura",
  status_present: true,
  read_at: "2026-11-12T00:00:00.000Z",
  updated_at: "2026-11-12T00:00:00.000Z",
  updated_ms: 1_794_441_600_000,
  started_ms: 1_794_440_400_000,
  started_at: "2026-11-11T23:53:20.000Z",
  stop_reason: null,
  deadlines: {
    capture_end_ms: 1_794_445_200_000,
    settle_end_ms: 1_794_449_400_000,
    accounting_end_ms: null,
    max_total_ms: 40_200_000,
    accounting_remaining_ms: null,
  },
  tokens: [{ symbol: "BTCUSDT", role: "candidate" }],
  cycles: {
    total: 2,
    last_cycle_id: "ciclo-2",
    last_reference_ms: 1_794_441_600_000,
    last_selection: [
      { symbol: "BTCUSDT", side: "UP", role: "candidate", move_24h_pct: 12.5 },
    ],
  },
  observations: {
    total: 5,
    aptas: 3,
    descartadas: 2,
    motivos: [{ motivo: "sin_libro", count: 2 }],
  },
  health: {
    feeds: [{ name: "public", connected_now: false, connections: 1, messages: 10 }],
    feeds_closed: true,
    book: {},
    flow: {},
  },
  budget: {
    attempts: 120,
    retries: 3,
    weight: 900,
    max_attempts: 2000,
    max_retries: 50,
    max_weight: 5000,
    blocked: false,
    reason: null,
    funding_rate_attempts_5m: 12,
    funding_rate_shared_limit_5m: 500,
    storage: {
      used_bytes: 1,
      reserved_bytes: 2,
      accounted_bytes: 3,
      max_bytes: 134_217_728,
    },
  },
  accounting: {
    pending_operativos: 1,
    pending_contabilidad: 1,
    consultas_por_simbolo: [{ symbol: "BTCUSDT", consultas: 2 }],
    consultas_totales: 2,
    cierre: null,
  },
  operations: [],
  counts: {
    filas_publicadas: 0,
    operaciones_unicas: 0,
    actualizaciones_contables: 0,
    entradas_simuladas: 0,
    abstenciones: 0,
    rechazos_capacidad: 0,
    descartes: 0,
    abiertas_al_final: 0,
    neto_completo: 0,
    neto_conditionado: 0,
    neto_unknown: 0,
    contabilidad_pendiente: 0,
    contabilidad_acreditada: 0,
    contabilidad_unknown: 0,
    por_rol: {},
  },
};

function operacion(overrides: Partial<PilotOperation>): PilotOperation {
  return {
    observation_id: "BTCUSDT|1794441600000",
    symbol: "BTCUSDT",
    role: "candidate",
    direction: "LONG",
    decision: "ENTRADA_EJECUTADA",
    decision_ms: 1_794_441_600_000,
    entry_px: 100,
    entry_ms: 1_794_441_660_000,
    stop_px: 99.5,
    exit_px: 101,
    exit_ms: 1_794_445_260_000,
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
    funding_huecos_ms: 0,
    funding_settlements_desconocidos: 0,
    published_at: "2026-11-12T00:00:00.000Z",
    updates: 1,
    ...overrides,
  };
}

function responder(payload: PilotMonitorPayload) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ ok: true, data: payload }),
  } as unknown as Response;
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => responder(BASE)),
  );
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("PilotMonitor — identidad y progreso", () => {
  it("muestra run_id, fuente real y fase", async () => {
    render(<PilotMonitor runId="exp-v2-ventana-1-20261112a" />);
    expect(await screen.findByTestId("pilot-run-id")).toHaveTextContent(
      "exp-v2-ventana-1-20261112a",
    );
    expect(screen.getByTestId("pilot-source")).toHaveTextContent(
      "Binance público — experimento simulado",
    );
    expect(screen.getByTestId("pilot-phase")).toHaveTextContent("Captura");
    expect(screen.getByTestId("pilot-budget-attempts")).toHaveTextContent("120 / 2000");
  });

  it("distingue espera contable con feeds cerrados de mercado vivo", async () => {
    const enEspera: PilotMonitorPayload = {
      ...BASE,
      phase: "espera_contable",
      phase_raw: "espera_contable",
      accounting: { ...BASE.accounting, cierre: null },
    };
    vi.stubGlobal("fetch", vi.fn(async () => responder(enEspera)));
    render(<PilotMonitor runId="exp-v2-ventana-1-20261112a" />);
    const notice = await screen.findByTestId("pilot-feeds-closed");
    expect(notice).toHaveTextContent("Feeds cerrados");
    expect(notice).toHaveTextContent("Solo continúa la contabilidad de funding");
    expect(notice).toHaveTextContent("no está LIVE");
  });
});

describe("PilotMonitor — operaciones", () => {
  it("conserva los tiempos historicos y no inventa ceros", async () => {
    const conOperacion: PilotMonitorPayload = {
      ...BASE,
      operations: [operacion({})],
      counts: { ...BASE.counts, filas_publicadas: 1, operaciones_unicas: 1, entradas_simuladas: 1 },
    };
    vi.stubGlobal("fetch", vi.fn(async () => responder(conOperacion)));
    render(<PilotMonitor runId="exp-v2-ventana-1-20261112a" />);
    const row = await screen.findByTestId("pilot-op-BTCUSDT|1794441600000");
    expect(row).toHaveTextContent("2026-11-12 00:01:00 UTC");
    expect(row).toHaveTextContent("2026-11-12 01:01:00 UTC");
    expect(row).toHaveTextContent("99.500000");
    expect(row).toHaveTextContent("PENDIENTE");
    expect(row).toHaveTextContent("CONDICIONADO_SIN_FUNDING_COMPLETO");
    // Funding ausente: no se presenta como cero.
    expect(row).toHaveTextContent("—");
  });

  it("una posicion abierta al final no se presenta con P&L realizado", async () => {
    const abierta: PilotMonitorPayload = {
      ...BASE,
      operations: [
        operacion({
          exit_px: null,
          exit_ms: null,
          exit_executed: false,
          open_at_end: true,
          net_pnl: null,
          neto_estado: "UNKNOWN",
          neto_motivo: "posicion abierta: la salida no esta ejecutada y el P&L no es realizado",
        }),
      ],
      counts: { ...BASE.counts, abiertas_al_final: 1 },
    };
    vi.stubGlobal("fetch", vi.fn(async () => responder(abierta)));
    render(<PilotMonitor runId="exp-v2-ventana-1-20261112a" />);
    const row = await screen.findByTestId("pilot-op-BTCUSDT|1794441600000");
    expect(row).toHaveTextContent("Posición abierta al final");
    expect(row).toHaveTextContent("No realizado (posición abierta)");
    expect(row).not.toHaveTextContent("9.5000 USDT");
  });

  it("separa el rechazo por capacidad de la abstinencia", async () => {
    const conAmbos: PilotMonitorPayload = {
      ...BASE,
      operations: [
        operacion({
          observation_id: "A|1",
          symbol: "AAAUSDT",
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
        }),
        operacion({
          observation_id: "B|2",
          symbol: "BBBUSDT",
          decision: "RECHAZADA_CAPACIDAD",
          exit_px: null,
          exit_ms: null,
          exit_executed: false,
          net_pnl: null,
          neto_estado: "UNKNOWN",
        }),
      ],
      counts: { ...BASE.counts, abstenciones: 1, rechazos_capacidad: 1 },
    };
    vi.stubGlobal("fetch", vi.fn(async () => responder(conAmbos)));
    render(<PilotMonitor runId="exp-v2-ventana-1-20261112a" />);
    expect(await screen.findByTestId("pilot-decision-A|1")).toHaveTextContent("Abstención");
    expect(screen.getByTestId("pilot-decision-B|2")).toHaveTextContent("Rechazo por capacidad");
    expect(screen.getByTestId("pilot-ops-capacity")).toHaveTextContent("1");
  });

  it("refleja el cambio de fase sin recargar la pagina", async () => {
    vi.useFakeTimers();
    const espera: PilotMonitorPayload = {
      ...BASE,
      phase: "espera_contable",
      phase_raw: "espera_contable",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(responder(BASE))
      .mockResolvedValue(responder(espera));
    vi.stubGlobal("fetch", fetchMock);
    render(<PilotMonitor runId="exp-v2-ventana-1-20261112a" />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByTestId("pilot-phase")).toHaveTextContent("Captura");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(screen.getByTestId("pilot-phase")).toHaveTextContent("Espera contable");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
