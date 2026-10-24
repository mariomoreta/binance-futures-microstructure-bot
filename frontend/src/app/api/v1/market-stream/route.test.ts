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
  it("reenvia los frames del servicio y declara el cierre del upstream", async () => {
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
    // El servicio cerró: el navegador recibe la causa y el stream termina.
    expect(body).toContain("event: error");
    expect(body).toContain("STREAM_UPSTREAM_CLOSED");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/stream?symbol=BTCUSDT&interval=1m");
    expect(init.cache).toBe("no-store");
  });

  it("declara STREAM_UPSTREAM_ERROR si el cuerpo del servicio falla", async () => {
    const failing = new ReadableStream<Uint8Array>({
      pull() {
        throw new Error("socket hang up");
      },
    });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(failing, {status: 200})));

    const response = await GET(request());
    const body = await response.text();

    expect(body).toContain("event: error");
    expect(body).toContain("STREAM_UPSTREAM_ERROR");
    expect(body).toContain("socket hang up");
  });

  it("aborta el lector del servicio cuando el navegador cancela", async () => {
    const captured: {signal?: AbortSignal} = {};
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init: RequestInit) => {
      captured.signal = init.signal as AbortSignal;
      return new Response(streamOf("event: hello\ndata: {}\n\n"), {status: 200});
    }));
    const browser = new AbortController();
    const req = new Request(
      "http://127.0.0.1:3020/api/v1/market-stream?symbol=BTCUSDT&interval=1m",
      {headers: HOST, signal: browser.signal});

    const response = await GET(req);
    expect(captured.signal?.aborted).toBe(false);
    await response.body?.cancel();

    expect(captured.signal?.aborted).toBe(true);
  });

  it("aborta el upstream si el navegador ya se desconectó al abrir", async () => {
    const captured: {signal?: AbortSignal} = {};
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init: RequestInit) => {
      captured.signal = init.signal as AbortSignal;
      return new Response(streamOf("event: hello\ndata: {}\n\n"), {status: 200});
    }));
    const browser = new AbortController();
    const req = new Request(
      "http://127.0.0.1:3020/api/v1/market-stream?symbol=BTCUSDT&interval=1m",
      {headers: HOST, signal: browser.signal});
    browser.abort();

    await GET(req);

    expect(captured.signal?.aborted).toBe(true);
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
