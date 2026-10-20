import {fireEvent, render, screen, waitFor} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";
import BacktestWorkspace from "@/components/backtest/BacktestWorkspace";

afterEach(() => { vi.unstubAllGlobals(); });

const RUN = "bt-eval-census-v2-trio-20261020T120000000-abcdef12";

type CellOver = Record<string, unknown>;

function cell(over: CellOver = {}) {
  return {
    symbol: "BTCUSDT", res: "15m", group: "continuation", label: "H1",
    segment: "dev", scale: 1, n_events: 100, n_trades: 0, n_realized: 0, n_open: 0,
    skipped_overlap: 0, n_expired: 0, n_mismatched: 0, exit_reasons: null,
    expectancy_net: 0, expectancy_gross: 0, total_net: 0, total_net_realized: 0,
    total_fees: 0, total_funding: 0, max_drawdown: 0, max_drawdown_realized: 0,
    mfe_mean: 0, mae_mean: 0, config_hash: "abc", n_trades_1x: 0, status: "ok",
    ...over,
  };
}

function summaryOf(cells: ReturnType<typeof cell>[]) {
  return {
    experiment_id: "eval-census-v2-trio", experiment_version: "EVAL-CENSUS-V2",
    label: "Evaluacion historica", not_label: "NO es un backtest completo",
    engine_version: "backtest-offline/v4.2", executor_version: "dashboard-backtest-executor/v1",
    package: "docs/evidence/eval-census-v2-package", package_version: "EVAL-CENSUS-V2",
    package_files_verified: 33, package_manifest_sha256: "e0c231a771a36322",
    combos: [["BTCUSDT", "15m"]], scales: [1, 2, 3],
    groups: [{group: "continuation", label: "H1"}],
    placebo_note: "Baseline separado de la hipotesis.",
    horizon_rule: "HORIZON-GRID4-V1", mapping: "MAP-CANDIDATE-v2",
    cost_model: "fee 5 bps + spread 1 bps + slippage 2 bps",
    cells, n_trades_total: 9000, n_trades_1x: 5255,
    reconciliation_ok: true, reconciliation_rows: 70, duration_ms: 11057,
    limitations: ["ventana reutilizada"],
  };
}

function tradesOf() {
  return [
    {trade_id: "t1", event_id: "BTCUSDT:1:LONG:H1:H1-v1:5", symbol: "BTCUSDT",
     res: "15m", group: "continuation", segment: "dev", scale: 1, direction: "LONG",
     family: "H1", rules_version: "H1-v1", event_time_ms: 1788903900000,
     entry_ms: 1788904800000, exit_ms: 1788907500000, entry_px: 1, exit_px: 1.1,
     exit_reason: "horizon", exit_executed: true, open_at_end: false, status: "realizada",
     gross_pnl: 1.1, fees: 0.1, funding: 0, net_pnl: 1.0, realized_net: 1.0,
     mfe_pct: 0.1, mae_pct: -0.2, holding_ms: 2700000,
     funding_accounting_complete: true, coverage: "completa"},
    {trade_id: "t2", event_id: "BTCUSDT:2:SHORT:H1:H1-v1:6", symbol: "BTCUSDT",
     res: "15m", group: "baseline", segment: "oos", scale: 1, direction: "SHORT",
     family: "H1", rules_version: "H1-v1", event_time_ms: 1788903600000,
     entry_ms: 1788904800000, exit_ms: 1788906000000, entry_px: 1, exit_px: 0.9,
     exit_reason: "open_at_end", exit_executed: false, open_at_end: true, status: "abierta",
     gross_pnl: 0.5, fees: 0, funding: 0, net_pnl: 0.5, realized_net: null,
     mfe_pct: 0.2, mae_pct: -0.1, holding_ms: 1200000,
     funding_accounting_complete: true, coverage: "completa"},
  ];
}

function respond(body: unknown, ok = true) {
  return {ok, json: async () => body};
}

function stubCompleted(cells: ReturnType<typeof cell>[]) {
  const summary = summaryOf(cells);
  const trades = tradesOf();
  const fetchMock = vi.fn(async (input: unknown) => {
    const url = String(input);
    if (url.includes("/api/v1/backtest/status")) {
      return respond({state: {status: "completado", error: null, detail: null,
        n_trades: 5255, reconciliation_ok: true, run_id: RUN, duration_ms: 11057,
        updated_at_ms: Date.now(), identity: "verified"}, run_id: RUN});
    }
    if (url.includes("/api/v1/backtest/results")) return respond({run_id: RUN, summary, trades});
    return respond({error: "NOT_FOUND"}, false);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("Backtest Workspace: hypothesis vs placebo vs ledger sum", () => {
  it("shows hypothesis and placebo realized results SEPARATELY, plus marks apart", async () => {
    stubCompleted([
      cell({group: "continuation", n_trades: 2991, n_realized: 2986, n_open: 5,
        total_net: 52, total_net_realized: 50}),
      cell({group: "baseline", n_trades: 2264, n_realized: 2262, n_open: 2,
        total_net: 20.5, total_net_realized: 20}),
      // Escenario de coste 2x: NO debe entrar en los agregados @1x.
      cell({group: "continuation", scale: 2, n_trades: 5000, n_realized: 5000,
        n_open: 0, total_net: 999, total_net_realized: 999}),
    ]);
    render(<BacktestWorkspace/>);
    await screen.findByText("3. Resultados del experimento");

    const hypothesis = screen.getByText("Resultado REALIZADO @1x — hipótesis").closest("div")!;
    expect(hypothesis).toHaveTextContent("+50.00");
    const placebo = screen.getByText("Resultado REALIZADO @1x — placebo (referencia)").closest("div")!;
    expect(placebo).toHaveTextContent("+20.00");
    // La marca de abiertas (2.5) se presenta aparte del realizado.
    const marks = screen.getByText("Marcas de abiertas @1x").closest("div")!;
    expect(marks).toHaveTextContent("+2.50");
    expect(marks).toHaveTextContent("NO beneficio realizado");
    // @1x: solo la celda de escala 1 (2991), nunca 2991+5000.
    const counts = screen.getByText("Hipótesis @1x").closest("div")!;
    expect(counts).toHaveTextContent("2991");
    expect(counts).not.toHaveTextContent("7991");
  });

  it("labels the technical sum as an arithmetic ledger sum with NO portfolio meaning", async () => {
    stubCompleted([
      cell({group: "continuation", n_trades: 2991, n_realized: 2986, n_open: 5,
        total_net: 52, total_net_realized: 50}),
      cell({group: "baseline", n_trades: 2264, n_realized: 2262, n_open: 2,
        total_net: 20.5, total_net_realized: 20}),
    ]);
    render(<BacktestWorkspace/>);
    await screen.findByText("3. Resultados del experimento");

    const sums = screen.getAllByText("Suma aritmética de ledgers @1x (control)");
    const metric = sums[0]!.closest("div")!;
    expect(metric).toHaveTextContent("+70.00");
    expect(metric).toHaveTextContent("NO es cartera");
    expect(metric).toHaveTextContent("NO es cartera ni beneficio de una estrategia");
    // No se rotula como beneficio de la estrategia ni como total del portafolio.
    expect(metric.textContent ?? "").not.toMatch(/beneficio de la estrategia/i);
    expect(metric.textContent ?? "").not.toMatch(/total del portafolio/i);
  });

  it("keeps UNKNOWN for missing economic data instead of rendering zero", async () => {
    stubCompleted([
      cell({group: "continuation", n_trades: 10, n_realized: null, n_open: null,
        total_net: 5, total_net_realized: null}),
    ]);
    render(<BacktestWorkspace/>);
    await screen.findByText("3. Resultados del experimento");

    const counts = screen.getByText("Hipótesis @1x").closest("div")!;
    expect(counts).toHaveTextContent("UNKNOWN realizadas");
    expect(counts).not.toHaveTextContent("0 realizadas");
    const realized = screen.getByText("Resultado REALIZADO @1x — hipótesis").closest("div")!;
    expect(realized).toHaveTextContent("UNKNOWN");
  });

  it("marks executor identity UNKNOWN and does not claim the run is verified", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: unknown) => {
      const url = String(input);
      if (url.includes("/api/v1/backtest/status")) {
        return respond({state: {status: "ejecutando", error: "PROCESS_IDENTITY_UNKNOWN",
          detail: "sin evidencia", n_trades: null, reconciliation_ok: null, run_id: RUN,
          duration_ms: null, updated_at_ms: Date.now(), identity: "UNKNOWN"}, run_id: RUN});
      }
      return respond({error: "NOT_FOUND"}, false);
    }));
    render(<BacktestWorkspace/>);
    const alert = await screen.findByRole("status");
    expect(alert).toHaveTextContent("Identidad del ejecutor no verificable (UNKNOWN)");
    expect(alert).toHaveTextContent("no se declara «verificada»");
    expect(screen.queryByText("3. Resultados del experimento")).toBeNull();
  });

  it("surfaces ALREADY_RUNNING as an explicit refusal, never as success", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: unknown, init?: {method?: string}) => {
      const url = String(input);
      if (url.includes("/api/v1/backtest/status")) {
        return respond({state: {status: "fallido", error: "PROCESS_INTERRUPTED",
          detail: null, n_trades: null, reconciliation_ok: null, run_id: RUN,
          duration_ms: null, updated_at_ms: Date.now(), identity: "UNKNOWN"}, run_id: RUN});
      }
      if (url.includes("/api/v1/backtest/run") && init?.method === "POST") {
        return respond({started: false, error: "ALREADY_RUNNING", run_id: RUN}, false);
      }
      return respond({error: "NOT_FOUND"}, false);
    }));
    render(<BacktestWorkspace/>);
    const button = await screen.findByRole("button", {name: "Ejecutar backtest"});
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    await waitFor(() => {
      const alerts = screen.getAllByRole("alert");
      const refusal = alerts.find((a) => (a.textContent ?? "").includes("ALREADY_RUNNING"));
      expect(refusal).toBeTruthy();
      expect(refusal).toHaveTextContent("no se lanzó otra");
    });
  });
});
