import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PnLPanel } from "@/components/paper-lab-live/PnLPanel";
import type { PaperCosts, PaperTradeResult } from "@/lib/paper-lab-live";

const baseCosts: PaperCosts = {
  fee_bps: 5,
  spread_bps: 1,
  entry_fees: 0,
  exit_fees: 0,
  entry_spread_slip: 0,
  exit_spread_slip: 0,
  funding: null,
  friction: 0,
  entry_fees_executed: 0,
  exit_fees_executed: 0,
  entry_spread_slip_executed: 0,
  exit_spread_slip_executed: 0,
  exit_fees_estimated: 0,
  exit_spread_slip_estimated: 0,
};

const filledResult: PaperTradeResult = {
  symbol: "MINAUSDT",
  direction: "LONG",
  entry_px: 0.05564,
  exit_px: 0.056,
  entry_ms: 1793718120000,
  exit_ms: 1793718180000,
  exit_reason: "stop",
  exit_executed: true,
  qty: 17972.68,
  filled_cost: 1000,
  gross_pnl: 60,
  fees: 0,
  spread_slip: 0,
  funding: null,
  friction: 0,
  net_pnl: 60,
  realized_net: 60,
  open_at_end: false,
  entry_fees_executed: 1,
  exit_fees_executed: 1,
  entry_spread_slip_executed: 1,
  exit_spread_slip_executed: 1,
  exit_fees_estimated: 0,
  exit_spread_slip_estimated: 0,
};

function renderPanel(overrides: {
  entered?: boolean;
  exitExecuted?: boolean;
  costs?: Partial<PaperCosts>;
  result?: PaperTradeResult | null;
}) {
  const costs: PaperCosts = { ...baseCosts, ...overrides.costs };
  return render(
    <PnLPanel
      finished={false}
      entered={overrides.entered ?? false}
      costs={costs}
      unrealized={null}
      result={overrides.result ?? null}
      exitExecuted={overrides.exitExecuted ?? false}
    />,
  );
}

describe("PnLPanel cost semantics", () => {
  it("entrada ejecutada con comisiones y slippage cero muestra 0.00, no guion", () => {
    const screen = renderPanel({
      entered: true,
      costs: {
        entry_fees: 0,
        entry_spread_slip: 0,
        entry_fees_executed: 1,
        entry_spread_slip_executed: 1,
      },
    });
    expect(
      screen.getByText(/Comisiones entrada/).parentElement?.textContent,
    ).toContain("0.00");
    expect(
      screen.getByText(/Spread\+slippage entrada/).parentElement?.textContent,
    ).toContain("0.00");
  });

  it("salida ejecutada con costes cero muestra 0.00", () => {
    const screen = renderPanel({
      entered: true,
      exitExecuted: true,
      result: filledResult,
      costs: {
        exit_fees: 0,
        exit_spread_slip: 0,
        exit_fees_executed: 1,
        exit_spread_slip_executed: 1,
      },
    });
    expect(
      screen.getByText(/Comisiones salida/).parentElement?.textContent,
    ).toContain("0.00");
    expect(
      screen.getByText(/Spread\+slippage salida/).parentElement?.textContent,
    ).toContain("0.00");
  });

  it("fill ejecutado con coste desconocido muestra guion, no cero", () => {
    const screen = renderPanel({
      entered: true,
      costs: {
        entry_fees: null as unknown as number,
        entry_spread_slip: null as unknown as number,
        entry_fees_executed: 1,
        entry_spread_slip_executed: 1,
      },
    });
    expect(
      screen.getByText(/Comisiones entrada/).parentElement?.textContent,
    ).toContain("—");
    expect(
      screen.getByText(/Spread\+slippage entrada/).parentElement?.textContent,
    ).toContain("—");
  });

  it("sin fill de entrada muestra UNKNOWN con motivo (no cero)", () => {
    const screen = renderPanel({
      entered: false,
      costs: {
        entry_fees: 0,
        entry_spread_slip: 0,
        entry_fees_executed: 0,
        entry_spread_slip_executed: 0,
      },
    });
    expect(
      screen.getByText(/Comisiones entrada/).parentElement?.textContent,
    ).toContain("UNKNOWN (sin fill de entrada)");
    expect(
      screen.getByText(/Spread\+slippage entrada/).parentElement?.textContent,
    ).toContain("UNKNOWN (sin fill de entrada)");
  });

  it("salida ejecutada con coste ausente muestra guion (no cero ni inventado)", () => {
    const screen = renderPanel({
      entered: true,
      exitExecuted: true,
      result: filledResult,
      costs: {
        exit_fees: null as unknown as number,
        exit_spread_slip: null as unknown as number,
        exit_fees_executed: 1,
        exit_spread_slip_executed: 1,
      },
    });
    expect(
      screen.getByText(/Comisiones salida/).parentElement?.textContent,
    ).toContain("—");
    expect(
      screen.getByText(/Spread\+slippage salida/).parentElement?.textContent,
    ).toContain("—");
  });

  it("estimación conocida cero muestra 0.00 (estimación, no ejecutada)", () => {
    const screen = renderPanel({
      entered: true,
      exitExecuted: false,
      costs: {
        exit_fees_estimated: 0,
        exit_spread_slip_estimated: 0,
      },
    });
    const el = screen.getByText(/Salida hipotetica/).parentElement;
    expect(el?.textContent).toContain(
      "0.00 (estimación, no ejecutada)",
    );
  });

  it("estimación conocida positiva muestra importe y 'estimación, no ejecutada'", () => {
    const screen = renderPanel({
      entered: true,
      exitExecuted: false,
      costs: {
        exit_fees_estimated: 3.2,
        exit_spread_slip_estimated: 1.5,
      },
    });
    const el = screen.getByText(/Salida hipotetica/).parentElement;
    expect(el?.textContent).toContain("+4.70 (estimación, no ejecutada)");
  });

  it("estimación ausente muestra UNKNOWN sin convertir null en cero", () => {
    const screen = renderPanel({
      entered: true,
      exitExecuted: false,
      costs: {
        exit_fees_estimated: null as unknown as number,
        exit_spread_slip_estimated: null as unknown as number,
      },
    });
    const el = screen.getByText(/Salida hipotetica/).parentElement;
    expect(el?.textContent).toContain("UNKNOWN (sin estimación disponible)");
  });
});
