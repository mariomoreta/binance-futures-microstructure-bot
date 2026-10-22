import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {act, cleanup, render, screen, waitFor} from "@testing-library/react";
import {livePermitted} from "@/lib/market-stream";
import {useMarketStream} from "@/lib/use-market-stream";

const H = 3_600_000;
const T0 = 1_790_000_000_000;

type Listener = (event: MessageEvent) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  closed = false;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private listeners = new Map<string, Listener[]>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: Listener) {
    const current = this.listeners.get(type) ?? [];
    current.push(listener);
    this.listeners.set(type, current);
  }

  emit(type: string, payload?: unknown) {
    for (const listener of this.listeners.get(type) ?? []) {
      listener({data: payload === undefined ? "" : JSON.stringify(payload)} as MessageEvent);
    }
  }

  close() {
    this.closed = true;
  }
}

function Probe({symbol, interval}: {symbol: string; interval: string}) {
  const view = useMarketStream({
    symbol, interval, fromMs: T0, toMs: T0 + 2 * H, enabled: true,
  });
  return (
    <div>
      <span data-testid="available">{String(view.available)}</span>
      <span data-testid="state">{view.status?.connection.state ?? "none"}</span>
      <span data-testid="live">{livePermitted(view.status) ? "LIVE" : "no"}</span>
      <span data-testid="count">{view.updates.length}</span>
      <span data-testid="last">{view.updates.at(-1)?.close ?? ""}</span>
      <span data-testid="gaps">{view.gaps.length}</span>
      <span data-testid="error">{view.error ?? ""}</span>
    </div>
  );
}

function candle(overrides: Record<string, unknown> = {}) {
  return {
    symbol: "BTCUSDT", interval: "1h",
    open_time_ms: T0 + H, close_time_ms: null,
    open: 100, high: 101, low: 99, close: 100.5,
    base_volume: 1, quote_volume: 100, trade_count: 3,
    closed: false, event_ms: T0 + H + 1000, received_ms: T0 + H + 2000,
    source: "ws_kline", seq: 1,
    ...overrides,
  };
}

const statusEvent = {
  symbol: "BTCUSDT", interval: "1h",
  connection: {state: "RECEIVING", socket_connected: true, fresh_ms: 10_000, stale_ms: 60_000},
  last_message_ms: T0 + H + 2000, last_kline_open_ms: T0 + H,
  closed_through_ms: T0 + H, age_ms: 800, live: true, recovering: false,
  generated_at_ms: T0 + H + 2500,
};

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
    ok: true, json: () => Promise.resolve({available: true}),
  })));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("useMarketStream — conexión y estados", () => {
  it("abre una sola EventSource con identidad y ventana", async () => {
    render(<Probe symbol="BTCUSDT" interval="1h" />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const url = FakeEventSource.instances[0]!.url;
    expect(url).toContain("/api/v1/market-stream?");
    expect(url).toContain("symbol=BTCUSDT");
    expect(url).toContain("interval=1h");
    expect(url).toContain(`from_ms=${T0}`);
  });

  it("acumula candles, reemplaza el tick y acepta el cierre", async () => {
    render(<Probe symbol="BTCUSDT" interval="1h" />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0]!;
    act(() => {
      source.onopen?.();
      source.emit("status", statusEvent);
      source.emit("candle", candle({close: 100.5, seq: 1}));
    });
    await waitFor(() => expect(screen.getByTestId("count").textContent).toBe("1"));
    expect(screen.getByTestId("state").textContent).toBe("RECEIVING");
    expect(screen.getByTestId("live").textContent).toBe("LIVE");
    expect(screen.getByTestId("available").textContent).toBe("true");

    act(() => source.emit("candle", candle({close: 100.9, seq: 2})));
    await waitFor(() => expect(screen.getByTestId("last").textContent).toBe("100.9"));

    act(() => source.emit("closed", candle({
      close: 101.2, closed: true, close_time_ms: T0 + 2 * H - 1, seq: 3,
    })));
    await waitFor(() => expect(screen.getByTestId("count").textContent).toBe("3"));
    expect(screen.getByTestId("last").textContent).toBe("101.2");
  });

  it("no declara LIVE cuando el estado es OBSOLETO", async () => {
    render(<Probe symbol="BTCUSDT" interval="1h" />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    act(() => FakeEventSource.instances[0]!.emit("status", {
      ...statusEvent,
      connection: {...statusEvent.connection, state: "STALE"},
      live: false, age_ms: 30_000,
    }));
    await waitFor(() => expect(screen.getByTestId("state").textContent).toBe("STALE"));
    expect(screen.getByTestId("live").textContent).toBe("no");
  });

  it("registra huecos informados por el backend", async () => {
    render(<Probe symbol="BTCUSDT" interval="1h" />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    act(() => FakeEventSource.instances[0]!.emit("gap", {
      symbol: "BTCUSDT", interval: "1h", reason: "GAP", status: "partial",
      expected_from_ms: T0, expected_to_ms: T0 + H, missing: [[T0, T0 + H]],
      requests: 1,
    }));
    await waitFor(() => expect(screen.getByTestId("gaps").textContent).toBe("1"));
  });

  it("con el servicio detenido no abre socket y lo declara", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({available: false, detail: "ECONNREFUSED"}),
    })));
    render(<Probe symbol="BTCUSDT" interval="1h" />);
    await waitFor(() => expect(screen.getByTestId("available").textContent).toBe("false"));
    expect(FakeEventSource.instances).toHaveLength(0);
    expect(screen.getByTestId("error").textContent).toBe("ECONNREFUSED");
    expect(screen.getByTestId("live").textContent).toBe("no");
  });

  it("cambiar de símbolo cierra la conexión anterior y abre otra", async () => {
    const {rerender} = render(<Probe symbol="BTCUSDT" interval="1h" />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const first = FakeEventSource.instances[0]!;
    rerender(<Probe symbol="ETHUSDT" interval="1h" />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(2));
    expect(first.closed).toBe(true);
    expect(FakeEventSource.instances[1]!.url).toContain("symbol=ETHUSDT");
  });

  it("al desmontar libera la conexión (no deja consumidores)", async () => {
    const {unmount} = render(<Probe symbol="BTCUSDT" interval="1h" />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0]!;
    unmount();
    expect(source.closed).toBe(true);
  });
});
