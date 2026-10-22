// @vitest-environment node
import {afterEach, describe, expect, it, vi} from "vitest";
import {GET} from "./route";

const HOST = {host: "127.0.0.1:3020"};

function request(query = "symbol=BTCUSDT&interval=1m",
                 headers: Record<string, string> = HOST): Request {
  return new Request(`http://127.0.0.1:3020/api/v1/market-stream?${query}`, {headers});
}

function streamOf(...frames: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame));
      controller.close();
    },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("BFF /api/v1/market-stream (cadena servicio -> navegador)", () => {
  it("reenvia el SSE del servicio sin transformarlo", async () => {
    const fetchMock = vi.fn(async () => new Response(
      streamOf("event: hello\ndata: {\"contract_version\":\"market-stream/v1\"}\n\n",
        "event: candle\ndata: {\"open_time_ms\":1}\n\n"),
      {status: 200, headers: {"Content-Type": "text/event-stream"}}));
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(request());

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("text/event-stream");
    expect(response.headers.get("cache-control")).toContain("no-store");
    const body = await response.text();
    expect(body).toContain("event: hello");
    expect(body).toContain("event: candle");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/stream?symbol=BTCUSDT&interval=1m");
    expect(init.cache).toBe("no-store");
  });

  it("declara 503 STREAM_SERVICE_DOWN si el servicio no responde", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("fetch failed", {cause: {code: "ECONNREFUSED"}});
    }));

    const response = await GET(request());
    const payload = await response.json() as {error?: string; detail?: string};

    expect(response.status).toBe(503);
    expect(payload.error).toBe("STREAM_SERVICE_DOWN");
    expect(payload.detail).toContain("ECONNREFUSED");
  });

  it("declara 503 si el servicio responde error HTTP", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", {status: 429})));

    const response = await GET(request());
    const payload = await response.json() as {error?: string; detail?: string};

    expect(response.status).toBe(503);
    expect(payload.detail).toContain("429");
  });

  it("rechaza identidad o ventana invalida antes de llamar al servicio", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    for (const query of ["symbol=BTCUSDT&interval=7m", "interval=1m",
                         "symbol=BTC-USDT&interval=1m", "symbol=BTCUSDT&interval=1m&bars=0",
                         "symbol=BTCUSDT&interval=1m&from_ms=10&to_ms=5"]) {
      const response = await GET(request(query));
      expect(response.status).toBe(400);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rechaza origenes ajenos al dashboard local", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(request("symbol=BTCUSDT&interval=1m",
      {host: "127.0.0.1:3020", origin: "http://evil.example"}));

    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
