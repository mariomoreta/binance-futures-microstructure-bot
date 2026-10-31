// @vitest-environment node
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {fetchMarketSeries, INTERVAL_STEP_MS} from "@/lib/session-lab";

function jsonResponse(body: unknown, status = 200) {
  return {ok: status >= 200 && status < 300, status, json: async () => body};
}

// Reloj fijo dentro de un minuto (no cae en frontera de rejilla), para que la
// ventana calculada sea determinista.
const NOW_MS = 1_790_000_037_000;

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(NOW_MS));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

function urlOf(mock: ReturnType<typeof vi.fn>): string {
  return String(mock.mock.calls[0]![0]);
}

describe("sesión de ingeniería — fuente solo lectura (--no-fetch)", () => {
  it("fetchMarketSeries pide ventana explícita de velas cerradas (nunca 0→9999999999999)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({candles: []}));
    vi.stubGlobal("fetch", fetchMock);
    await fetchMarketSeries("MINAUSDT", "1m", 90);
    const url = urlOf(fetchMock);
    expect(url.startsWith("/api/v1/market-series?")).toBe(true);
    expect(url).toContain("symbol=MINAUSDT");
    expect(url).toContain("interval=1m");
    expect(url).toContain("bars=90");
    expect(url).toContain("pages=1");
    // Opción de solo lectura controlada por backend: cero upstream.
    expect(url).toContain("read_only=1");
    // Rango explícito y cerrado: nunca el rango abierto al futuro.
    expect(url).not.toContain("from_ms=0");
    expect(url).not.toContain("to_ms=9999999999999");
    const stepMs = INTERVAL_STEP_MS["1m"] ?? 60_000;
    const lastClosedOpen = Math.floor(NOW_MS / stepMs) * stepMs - stepMs;
    expect(url).toContain(`to_ms=${lastClosedOpen}`);
    expect(url).toContain(`from_ms=${lastClosedOpen - (90 - 1) * stepMs}`);
    expect(lastClosedOpen).toBeLessThanOrEqual(NOW_MS);
  });

  it("fetchMarketSeries con reloj T usa to_ms=atMs y read_only=1", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({candles: []}));
    vi.stubGlobal("fetch", fetchMock);
    const T = 1_790_000_000_000;
    await fetchMarketSeries("BTCUSDT", "5m", 200, T);
    const url = urlOf(fetchMock);
    expect(url).toContain(`to_ms=${T}`);
    expect(url).toContain("read_only=1");
    expect(url).toContain("symbol=BTCUSDT");
    expect(url).toContain("interval=5m");
    const stepMs = INTERVAL_STEP_MS["5m"] ?? 60_000;
    expect(url).toContain(`from_ms=${T - (200 - 1) * stepMs}`);
  });

  it("sin read_only no se agrega (reserva del explorador normal)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({candles: []}));
    vi.stubGlobal("fetch", fetchMock);
    await fetchMarketSeries("ETHUSDT", "1h", 300, null, false);
    const url = urlOf(fetchMock);
    expect(url).not.toContain("read_only=1");
    // El explorador normal conserva la adquisición bajo demanda con sus
    // presupuestos existentes (el backend defaulta --page-limit 300, pages <= 2,
    // ledger compartido, 30 req/min).
    expect(url).toContain("pages=1");
    expect(url).not.toContain("from_ms=0");
    expect(url).not.toContain("to_ms=9999999999999");
    const stepMs = INTERVAL_STEP_MS["1h"] ?? 60_000;
    const lastClosedOpen = Math.floor(NOW_MS / stepMs) * stepMs - stepMs;
    expect(url).toContain(`to_ms=${lastClosedOpen}`);
    expect(url).toContain(`from_ms=${lastClosedOpen - (300 - 1) * stepMs}`);
  });

  it("ausencia en caché devuelve datos vacíos sin activar fetch adicional", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({candles: [], coverage: {state: "NO_COVERAGE"}}));
    vi.stubGlobal("fetch", fetchMock);
    const result = await fetchMarketSeries("NOEXISTUSDT", "1m", 50);
    expect(result).not.toBeNull();
    expect(result!.candles).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(1); // cero reintentos ni fetch encadenado
  });
});
