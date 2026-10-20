// @vitest-environment node
import {beforeEach, describe, expect, it, vi} from "vitest";
const ctrl = vi.hoisted(() => ({
  startJob: vi.fn(), readJobState: vi.fn(), readRunState: vi.fn(),
  readResults: vi.fn(), readRunResults: vi.fn(), currentRunId: vi.fn((): string | null => null),
  materializeReplay: vi.fn(),
  retentionReport: vi.fn(() => ({dir: "x", exists: false, bytes: 0, files: 0, runs: 0, removed: []})),
}));
const real = await vi.importActual<typeof import("@/lib/backtest-control")>("@/lib/backtest-control");
vi.mock("@/lib/backtest-control", () => ({
  ...real,
  startJob: ctrl.startJob, readJobState: ctrl.readJobState, readRunState: ctrl.readRunState,
  readResults: ctrl.readResults, readRunResults: ctrl.readRunResults,
  currentRunId: ctrl.currentRunId, materializeReplay: ctrl.materializeReplay,
  retentionReport: ctrl.retentionReport,
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
beforeEach(() => {vi.clearAllMocks(); ctrl.currentRunId.mockReturnValue(null);});

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
  it("starts the allowlisted experiment and relays its unique run_id", async () => {
    ctrl.startJob.mockReturnValue({started: true, state: {status: "pendiente"},
      run_id: "bt-eval-census-v2-trio-1-ab", error: undefined});
    const r = await POST(post({experiment: "eval-census-v2-trio"}));
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({started: true, run_id: "bt-eval-census-v2-trio-1-ab"});
    expect(ctrl.startJob).toHaveBeenCalledWith("eval-census-v2-trio");
  });
  it("relays a single-flight refusal without starting a second run", async () => {
    ctrl.startJob.mockReturnValue({started: false, state: {status: "ejecutando"},
      run_id: "bt-active", error: undefined});
    const r = await POST(post({experiment: "eval-census-v2-trio"}));
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({started: false, run_id: "bt-active"});
  });
});

describe("backtest status route", () => {
  it("rejects an unlisted experiment", async () => {
    const r = await statusGET(new Request("http://127.0.0.1:3020/api/v1/backtest/status?experiment=x"));
    expect(r.status).toBe(400);
  });
  it("returns the persisted state, run identity and retention, no-store", async () => {
    ctrl.readJobState.mockReturnValue({status: "completado", n_trades: 15765, run_id: "bt-current"});
    ctrl.currentRunId.mockReturnValue("bt-current");
    const r = await statusGET(new Request("http://127.0.0.1:3020/api/v1/backtest/status?experiment=eval-census-v2-trio"));
    expect(r.status).toBe(200);
    expect(r.headers.get("cache-control")).toBe("no-store");
    expect(await r.json()).toMatchObject({state: {status: "completado"}, run_id: "bt-current"});
  });
  it("targets a specific run when ?run is given (never the current one)", async () => {
    ctrl.readRunState.mockReturnValue({status: "completado", run_id: "bt-specific"});
    const r = await statusGET(new Request("http://127.0.0.1:3020/api/v1/backtest/status?experiment=eval-census-v2-trio&run=bt-specific"));
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({run_id: "bt-specific", state: {run_id: "bt-specific"}});
    expect(ctrl.readRunState).toHaveBeenCalledWith("eval-census-v2-trio", "bt-specific");
    expect(ctrl.readJobState).not.toHaveBeenCalled();
  });
});

describe("backtest results route", () => {
  it("returns 409 with the real status when results are not ready (no mock data)", async () => {
    ctrl.readResults.mockReturnValue({available: false, status: "ejecutando", error: "RESULT_NOT_READY"});
    const r = await resultsGET(new Request("http://127.0.0.1:3020/api/v1/backtest/results?experiment=eval-census-v2-trio"));
    expect(r.status).toBe(409);
    expect(await r.json()).toMatchObject({available: false, status: "ejecutando"});
  });
  it("serves completed results with their verified hashes", async () => {
    ctrl.readResults.mockReturnValue({available: true, experiment_id: "eval-census-v2-trio",
      run_id: "bt-1", summary: {experiment_id: "x"}, trades: [], reconciliation: null,
      result_hashes: {"trades.json": "deadbeef"}});
    const r = await resultsGET(new Request("http://127.0.0.1:3020/api/v1/backtest/results?experiment=eval-census-v2-trio"));
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({available: true, run_id: "bt-1"});
  });
  it("surfaces an integrity failure explicitly (never serves altered results)", async () => {
    ctrl.readResults.mockReturnValue({available: false, status: "fallido",
      error: "RESULT_INTEGRITY_FAILED", run_id: "bt-1"});
    const r = await resultsGET(new Request("http://127.0.0.1:3020/api/v1/backtest/results?experiment=eval-census-v2-trio"));
    expect(r.status).toBe(409);
    expect(await r.json()).toMatchObject({available: false, error: "RESULT_INTEGRITY_FAILED"});
  });
  it("targets a specific run when ?run is given", async () => {
    ctrl.readRunResults.mockReturnValue({available: true, run_id: "bt-2", summary: {}, trades: []});
    const r = await resultsGET(new Request("http://127.0.0.1:3020/api/v1/backtest/results?experiment=eval-census-v2-trio&run=bt-2"));
    expect(r.status).toBe(200);
    expect(ctrl.readRunResults).toHaveBeenCalledWith("eval-census-v2-trio", "bt-2");
    expect(ctrl.readResults).not.toHaveBeenCalled();
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
  it("returns 422 when the operation does not belong to that run", async () => {
    ctrl.materializeReplay.mockReturnValue({ok: false, error: "TARGET_NOT_IN_RUN", run_id: "bt-1"});
    const r = await replayGET(url("experiment=eval-census-v2-trio&event_id=e&group=continuation&segment=dev&scale=1"));
    expect(r.status).toBe(422);
    expect(await r.json()).toMatchObject({error: "TARGET_NOT_IN_RUN"});
  });
  it("serves the linked operation with its backing run identity", async () => {
    ctrl.materializeReplay.mockReturnValue({ok: true, run_id: "bt-1", cached: false,
      artifact: {replay_id: "PLR-ETHUSDT-LONG-1"}});
    const r = await replayGET(url("experiment=eval-census-v2-trio&run=bt-1&event_id=ETHUSDT%3A1%3ALONG%3AH1%3AH1-v1%3A111&group=continuation&segment=dev&scale=1"));
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({run_id: "bt-1", artifact: {replay_id: "PLR-ETHUSDT-LONG-1"}});
    expect(ctrl.materializeReplay).toHaveBeenCalledWith({
      experiment: "eval-census-v2-trio", event_id: "ETHUSDT:1:LONG:H1:H1-v1:111",
      group: "continuation", segment: "dev", scale: 1, run_id: "bt-1"});
  });
});
