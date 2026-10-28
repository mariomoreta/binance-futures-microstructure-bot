// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { MarketFlowPanel } from "@/components/market-lab/MarketFlowPanel";

// Objetivo: el panel de flujo NO queda muerto ante la caída del SSE sin
// cambio de identidad (re-render duplicado, corte del transporte) — reintenta
// con la MISMA identidad tras un retardo fijo; y al desmontar NO reintenta
// (libera su consumidor). El BFF con bodyTimeout 0 evita el corte de 30 s.
// El servicio Python (8792, preexistente) es la autoridad del flujo.

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  closed = false;
  onopen: (() => void) | null = null;
  onmessage: ((evt: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  close() { this.closed = true; }
}

const g = globalThis as unknown as { EventSource: unknown };
g.EventSource = FakeEventSource;

function snapshotUrl() {
  return FakeEventSource.instances.map((e) => e.url);
}

afterEach(() => {
  FakeEventSource.instances = [];
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("MarketFlowPanel — reconexión SSE sin cambio de identidad", () => {
  beforeEach(() => {
    // Sin Datos HTTP reales: el respaldo HTTP falla inmediatamente (mock)
    // para que la causa visible quede en "desconectado — reintentando".
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(
      new TypeError("respaldo mock caído"))));
  });
  it("ante onerror del SSE: reintenta con la MISMA identidad (mismo símbolo) y no desarma el panel", () => {
    vi.useFakeTimers();
    let unmount: () => void;
    act(() => {
      const r = render(<MarketFlowPanel symbol="BTCUSDT" />);
      unmount = r.unmount;
    });
    // conexión inicial
    expect(FakeEventSource.instances.length).toBe(1);
    expect(snapshotUrl()[0]).toContain("/api/v1/market-flow/stream?symbol=BTCUSDT");
    // la conexión cae SIN cambio de identidad
    const first = FakeEventSource.instances[0]!;
    act(() => {
      first.onerror?.();
      vi.advanceTimersByTime(2600);
    });
    // nueva suscripción con la misma identidad (reconexión, no panel muerto)
    expect(FakeEventSource.instances.length).toBe(2);
    expect(snapshotUrl()[1]).toContain("symbol=BTCUSDT");
    expect(first.closed).toBe(true);
    // la causa es visible mientras no hay datos
    const bodyText = document.body.textContent ?? "";
    expect(bodyText).toMatch(/reintentando/i);
    unmount!();
    vi.useRealTimers();
  });

  it("al desmontar NO reabre la suscripción: libera su consumidor", () => {
    vi.useFakeTimers();
    const { unmount } = render(<MarketFlowPanel symbol="BTCUSDT" />);
    const first = FakeEventSource.instances[0]!;
    first.onerror?.();
    unmount();
    vi.advanceTimersByTime(10_000);
    // sin reintento después de desmontar: consumidor liberado
    expect(FakeEventSource.instances.length).toBe(1);
    expect(first.closed).toBe(true);
    vi.useRealTimers();
  });

  it("cambio de símbolo: cierra la suscripción previa y abre la nueva identidad", () => {
    vi.useFakeTimers();
    const { rerender } = render(<MarketFlowPanel symbol="BTCUSDT" />);
    expect(FakeEventSource.instances.length).toBe(1);
    rerender(<MarketFlowPanel symbol="ETHUSDT" />);
    expect(FakeEventSource.instances.length).toBe(2);
    expect(FakeEventSource.instances[0]!.closed).toBe(true);
    expect(snapshotUrl()[1]).toContain("symbol=ETHUSDT");
    vi.advanceTimersByTime(10_000);
    expect(FakeEventSource.instances.length).toBe(2); // sin resurrección previa
    vi.useRealTimers();
  });
});
