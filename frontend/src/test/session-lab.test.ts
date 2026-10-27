// @vitest-environment node
import {afterEach, describe, expect, it, vi} from "vitest";
import {fetchMarketSeries} from "@/lib/session-lab";

function jsonResponse(body: unknown, status = 200) {
  return {ok: status >= 200 && status < 300, status, json: async () => body};
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("sesión de ingeniería — fuente solo lectura (--no-fetch)", () => {
  it("fetchMarketSeries fuerza read_only=1 (cero upstream, caché solo)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({candles: []}));
    vi.stubGlobal("fetch", fetchMock);
    await fetchMarketSeries("MINAUSDT", "1m", 90);
    const url = String(fetchMock.mock.calls[0]![0]);
    expect(url.startsWith("/api/v1/market-series?")).toBe(true);
    expect(url).toContain("symbol=MINAUSDT");
    expect(url).toContain("interval=1m");
    expect(url).toContain("bars=90");
    expect(url).toContain("pages=1");
    expect(url).toContain("from_ms=0");
    // Opción de solo lectura controlada por backend: cero upstream.
    expect(url).toContain("read_only=1");
    // Nunca fecha de vencimiento fija del reloj de pared: rango amplio al caché.
    expect(url).toContain("to_ms=9999999999999");
  });

  it("fetchMarketSeries con reloj T usa to_ms=atMs y read_only=1", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({candles: []}));
    vi.stubGlobal("fetch", fetchMock);
    const T = 1_790_000_000_000;
    await fetchMarketSeries("BTCUSDT", "5m", 200, T);
    const url = String(fetchMock.mock.calls[0]![0]);
    expect(url).toContain(`to_ms=${T}`);
    expect(url).toContain("read_only=1");
    expect(url).toContain("symbol=BTCUSDT");
    expect(url).toContain("interval=5m");
  });

  it("sin read_only no se agrega (reserva del explorador normal)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({candles: []}));
    vi.stubGlobal("fetch", fetchMock);
    await fetchMarketSeries("ETHUSDT", "1h", 300, null, false);
    const url = String(fetchMock.mock.calls[0]![0]);
    expect(url).not.toContain("read_only=1");
    // El explorador normal conserva la adquisición bajo demanda con sus
    // presupuestos existentes (el backend defaulta --page-limit 300, pages <= 2,
    // ledger compartido, 30 req/min).
    expect(url).toContain("pages=1");
    expect(url).toContain("from_ms=0");
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
