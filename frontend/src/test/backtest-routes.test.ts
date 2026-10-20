// @vitest-environment node
import {beforeEach, describe, expect, it, vi} from "vitest";
const ctrl = vi.hoisted(() => ({
  startJob: vi.fn(), readJobState: vi.fn(), readResults: vi.fn(),
  materializeReplay: vi.fn(), retentionReport: vi.fn(() => ({dir: "x", exists: false, bytes: 0, files: 0})),
}));
const real = await vi.importActual<typeof import("@/lib/backtest-control")>("@/lib/backtest-control");
vi.mock("@/lib/backtest-control", () => ({
  ...real,
  startJob: ctrl.startJob, readJobState: ctrl.readJobState, readResults: ctrl.readResults,
  materializeReplay: ctrl.materializeReplay, retentionReport: ctrl.retentionReport,
}));
const {POST} = await import("@/app/api/v1/backtest/run/route");
const {GET: statusGET} = await import("@/app/api/v1/backtest/status/route");
const {GET: resultsGET} = await import("@/app/api/v1/backtest/results/route");
const {GET: replayGET} = await import("@/app/api/v1/backtest/replay/route");

const post = (body: unknown, headers: Record<string, string> = {}) =>
  new Request("http://127.0.0.1:3020/api/v1/backtest/run", {
    method: "POST", headers: {origin: "http://127.0.0.1:3020", host: "127.0.0.1:3020",
      "content-type": "application/json", ...headers},
    body: JSON.stringify(body),
  });
beforeEach(() => vi.clearAllMocks());

describe("backtest run route: allowlisted, no client paths", () => {
  it("rejects a cross-origin/non-local request without starting anything", async () => {
    const r = await POST(new Request("http://127.0.0.1:3020/api/v1/backtest/run", {method: "POST"}));
    expect(r.status).toBe(403);
    expect(ctrl.startJob).not.toHaveBeenCalled();
  });
  it("rejects an experiment outside the allowlist, including a path-shaped id", async () => {
    for (const experiment of ["../etc/passwd", "rm -rf /", "otra-cosa", ""]) {
      const r = await POST(post({experiment}));
      expect(r.status).toBe(400);
      expect(await r.json()).toMatchObject({error: "EXPERIMENT_NOT_ALLOWED"});
    }
    expect(ctrl.startJob).not.toHaveBeenCalled();
  });
  it("starts the allowlisted experiment and relays the state", async () => {
    ctrl.startJob.mockReturnValue({started: true, state: {status: "pendiente"}, error: undefined});
    const r = await POST(post({experiment: "eval-census-v2-trio"}));
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({started: true});
    expect(ctrl.startJob).toHaveBeenCalledWith("eval-census-v2-trio");
  });
  it("relays a single-flight refusal without starting a second run", async () => {
    ctrl.startJob.mockReturnValue({started: false, state: {status: "ejecutando"}, error: undefined});
    const r = await POST(post({experiment: "eval-census-v2-trio"}));
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({started: false});
  });
});

describe("backtest status route", () => {
  it("rejects an unlisted experiment", async () => {
    const r = await statusGET(new Request("http://127.0.0.1:3020/api/v1/backtest/status?experiment=x"));
    expect(r.status).toBe(400);
  });
  it("returns the persisted state and retention, no-store", async () => {
    ctrl.readJobState.mockReturnValue({status: "completado", n_trades: 15765});
    const r = await statusGET(new Request("http://127.0.0.1:3020/api/v1/backtest/status?experiment=eval-census-v2-trio"));
    expect(r.status).toBe(200);
    expect(r.headers.get("cache-control")).toBe("no-store");
    expect(await r.json()).toMatchObject({state: {status: "completado"}});
  });
});

describe("backtest results route", () => {
  it("returns 409 with the real status when results are not ready (no mock data)", async () => {
    ctrl.readResults.mockReturnValue({available: false, status: "ejecutando", error: "RESULT_NOT_READY"});
    const r = await resultsGET(new Request("http://127.0.0.1:3020/api/v1/backtest/results?experiment=eval-census-v2-trio"));
    expect(r.status).toBe(409);
    expect(await r.json()).toMatchObject({available: false, status: "ejecutando"});
  });
  it("serves completed results", async () => {
    ctrl.readResults.mockReturnValue({available: true, experiment_id: "eval-census-v2-trio",
      summary: {experiment_id: "x"}, trades: [], reconciliation: null});
    const r = await resultsGET(new Request("http://127.0.0.1:3020/api/v1/backtest/results?experiment=eval-census-v2-trio"));
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({available: true});
  });
});

describe("backtest replay route (operation -> Paper Lab link)", () => {
  const url = (qs: string) => new Request(`http://127.0.0.1:3020/api/v1/backtest/replay?${qs}`);
  it("requires event_id, group, segment and scale", async () => {
    const r = await replayGET(url("experiment=eval-census-v2-trio"));
    expect(r.status).toBe(400);
    expect(ctrl.materializeReplay).not.toHaveBeenCalled();
  });
  it("returns 409 when results are not ready", async () => {
    ctrl.materializeReplay.mockReturnValue({ok: false, error: "RESULT_NOT_READY"});
    const r = await replayGET(url("experiment=eval-census-v2-trio&event_id=e&group=continuation&segment=dev&scale=1"));
    expect(r.status).toBe(409);
  });
  it("returns 422 for an unsupported operation type without fabricating a replay", async () => {
    ctrl.materializeReplay.mockReturnValue({ok: false, error: "REPLAY_UNSUPPORTED"});
    const r = await replayGET(url("experiment=eval-census-v2-trio&event_id=e&group=continuation&segment=dev&scale=1"));
    expect(r.status).toBe(422);
  });
  it("serves the linked operation artifact with the exact identity", async () => {
    ctrl.materializeReplay.mockReturnValue({ok: true, artifact: {replay_id: "PLR-ETHUSDT-LONG-1"}});
    const r = await replayGET(url("experiment=eval-census-v2-trio&event_id=ETHUSDT%3A1%3ALONG%3AH1%3AH1-v1%3A111&group=continuation&segment=dev&scale=1"));
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({replay_id: "PLR-ETHUSDT-LONG-1"});
    expect(ctrl.materializeReplay).toHaveBeenCalledWith({
      experiment: "eval-census-v2-trio", event_id: "ETHUSDT:1:LONG:H1:H1-v1:111",
      group: "continuation", segment: "dev", scale: 1});
  });
});
