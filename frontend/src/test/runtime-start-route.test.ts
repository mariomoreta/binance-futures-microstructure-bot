// @vitest-environment node
import {beforeEach, describe, expect, it, vi} from "vitest";
const run = vi.hoisted(() => vi.fn());
const readiness = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({spawnSync: run, default: {spawnSync: run}}));
vi.mock("@/lib/launch-readiness", () => ({launchReadiness: readiness}));
import {POST} from "@/app/api/v1/runtime/start/route";

const req = (body: unknown, headers: Record<string, string> = {}) =>
  new Request("http://127.0.0.1:3020/api/v1/runtime/start", {
    method: "POST",
    headers: {origin: "http://127.0.0.1:3020", host: "127.0.0.1:3020",
      "x-v2-action": "observe-only", "sec-fetch-site": "same-origin", ...headers},
    body: JSON.stringify(body),
  });

// runtimeAction("start") runs a status pre-check BEFORE any spawn, so the
// mock routes by script content: launch code (contains
// "launch_supervised_transaction") vs status/capability reads. Helpers
// below emulate canonical Python on each branch with isolated fakes.
const stoppedFree = {status: 0, stdout: JSON.stringify({state: "STOPPED", running: false, pid: null, launcher: null, mode: "observe", supervisor: null, sentinel: null})};
const runningDashboard = {status: 0, stdout: JSON.stringify({state: "RUNNING", running: true, pid: 123, launcher: "dashboard", mode: "observe", supervisor: null, sentinel: null})};
const runningForeign = {status: 0, stdout: JSON.stringify({state: "RUNNING", running: true, pid: 456, launcher: "agent", mode: "observe", supervisor: null, sentinel: null})};
const isLaunch = (call: unknown[]) => String((call[1] as string[])[1]).includes("launch_supervised_transaction");
const launchCalls = () => run.mock.calls.filter(isLaunch);
beforeEach(() => { vi.resetAllMocks(); });
describe("runtime start route: gated supervised chain", () => {
  it("keeps FORBIDDEN without origin plus confirmation header", async () => {
    const r = await POST(new Request("http://127.0.0.1:3020/api/v1/runtime/start", {method: "POST"}));
    expect(r.status).toBe(403);
  });
  it("requires confirmation before touching readiness", async () => {
    const r = await POST(req({preset: "brief"}));
    expect(r.status).toBe(400);
    expect(readiness).not.toHaveBeenCalled();
    expect(run).not.toHaveBeenCalled();
  });
  it("rejects unknown presets without spawning anything", async () => {
    const r = await POST(req({confirm: "START_OBSERVE_2100", preset: "turbo"}));
    expect(r.status).toBe(400);
    expect(await r.json()).toMatchObject({error: "INVALID_PRESET"});
    expect(run).not.toHaveBeenCalled();
  });
  it("blocks on readiness without launching and relays checks", async () => {
    readiness.mockReturnValue({ready: false, reason: "READINESS_BLOCKED", checks: [{name: "X", status: "BLOCKED", detail: "d"}]});
    const r = await POST(req({confirm: "START_OBSERVE_2100", preset: "brief"}));
    expect(r.status).toBe(409);
    expect(await r.json()).toMatchObject({error: "READINESS_BLOCKED"});
    expect(run).not.toHaveBeenCalled();
  });
  it("relays the canonical envelope on the green path with fixed allowlisted code", async () => {
    readiness.mockReturnValue({ready: true, reason: "SUPERVISED_CHAIN_VERIFIED", checks: []});
    run.mockImplementation((...a: unknown[]) => {
      if (isLaunch(a)) return {status: 0, stdout: JSON.stringify({outcome: "confirmed", reason: "verified", run_id: "r1"})};
      return stoppedFree;
    });
    const r = await POST(req({confirm: "START_OBSERVE_2100", preset: "brief"}));
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({outcome: "confirmed", run_id: "r1"});
    expect(launchCalls()).toHaveLength(1);
    const script = String(launchCalls()[0]?.[1]?.[1]);
    expect(script).toContain("launch_supervised_transaction");
    expect(script).toContain("duration_seconds=120");
  });
  it("maps non-confirmed envelopes to 409 without claiming success", async () => {
    readiness.mockReturnValue({ready: true, reason: "SUPERVISED_CHAIN_VERIFIED", checks: []});
    run.mockImplementation((...a: unknown[]) => {
      if (isLaunch(a)) return {status: 0, stdout: JSON.stringify({outcome: "rejected", reason: "registry-unavailable"})};
      return stoppedFree;
    });
    const r = await POST(req({confirm: "START_OBSERVE_2100"}));
    expect(r.status).toBe(409);
    expect(await r.json()).toMatchObject({outcome: "rejected"});
  });
  it("binds the fixed call to launcher dashboard so stop wiring applies", async () => {
    readiness.mockReturnValue({ready: true, reason: "SUPERVISED_CHAIN_VERIFIED", checks: []});
    run.mockImplementation((...a: unknown[]) => {
      if (isLaunch(a)) return {status: 0, stdout: JSON.stringify({outcome: "confirmed", run_id: "r1"})};
      return stoppedFree;
    });
    const r = await POST(req({confirm: "START_OBSERVE_2100", preset: "brief"}));
    expect(r.status).toBe(200);
    const script = String(launchCalls()[0]?.[1]?.[1]);
    expect(script).toContain("launcher='dashboard'");
    expect(script).toContain("preset='brief'");
  });
  it("relays rollback evidence on rejected launches instead of hiding it", async () => {
    readiness.mockReturnValue({ready: true, reason: "SUPERVISED_CHAIN_VERIFIED", checks: []});
    const envelope = {outcome: "rejected", reason: "sentinel-spawn-failed",
      rollback: {attempted: true, cleaned: [{role: "probe"}], pending: []}};
    run.mockImplementation((...a: unknown[]) => {
      if (isLaunch(a)) return {status: 0, stdout: JSON.stringify(envelope)};
      return stoppedFree;
    });
    const r = await POST(req({confirm: "START_OBSERVE_2100", preset: "brief"}));
    expect(r.status).toBe(409);
    expect(await r.json()).toMatchObject({reason: "sentinel-spawn-failed", rollback: {attempted: true, pending: []}});
  });
  it("refuses a second start while a dashboard run is active without spawning", async () => {
    readiness.mockReturnValue({ready: false, reason: "READINESS_BLOCKED", checks: []});
    run.mockImplementation((...a: unknown[]) => {
      if (isLaunch(a)) return {status: 0, stdout: JSON.stringify({outcome: "confirmed", run_id: "late"})};
      return runningDashboard;
    });
    // Readiness itself blocks here, but the unit under test is the
    // no-double-spawn pre-check inside runtimeAction: call the route
    // green and prove zero launch spawns on retry state.
    readiness.mockReturnValue({ready: true, reason: "SUPERVISED_CHAIN_VERIFIED", checks: []});
    const r = await POST(req({confirm: "START_OBSERVE_2100", preset: "brief"}));
    expect(r.status).toBe(409);
    expect(await r.json()).toMatchObject({error: "ALREADY_RUNNING"});
    expect(launchCalls()).toHaveLength(0);
  });
  it("refuses to take over a foreign-owned run without spawning", async () => {
    readiness.mockReturnValue({ready: true, reason: "SUPERVISED_CHAIN_VERIFIED", checks: []});
    run.mockImplementation((...a: unknown[]) => {
      if (isLaunch(a)) return {status: 0, stdout: JSON.stringify({outcome: "confirmed", run_id: "late"})};
      return runningForeign;
    });
    const r = await POST(req({confirm: "START_OBSERVE_2100", preset: "brief"}));
    expect(r.status).toBe(409);
    expect(await r.json()).toMatchObject({error: "ALREADY_RUNNING_FOREIGN"});
    expect(launchCalls()).toHaveLength(0);
  });
  it("reconciles a start timeout as 202 uncertain with the live record, never as failure", async () => {
    readiness.mockReturnValue({ready: true, reason: "SUPERVISED_CHAIN_VERIFIED", checks: []});
    const timeoutErr = Object.assign(new Error("spawnSync ETIMEDOUT"), {code: "ETIMEDOUT"});
    // Sequence: pre-check sees a free registry, the spawn exceeds its
    // budget, the reconcile read finds the late-confirmed dashboard run.
    let statusCalls = 0;
    run.mockImplementation((...a: unknown[]) => {
      if (isLaunch(a)) return {error: timeoutErr, stdout: "", status: null};
      statusCalls++;
      return statusCalls <= 1 ? stoppedFree : runningDashboard;
    });
    const r = await POST(req({confirm: "START_OBSERVE_2100", preset: "brief"}));
    expect(r.status).toBe(202);
    const body = await r.json();
    expect(body).toMatchObject({error: "START_TIMEOUT_UNCERTAIN", retry: "reconcile-before-retry"});
    expect(body.status).toMatchObject({state: "RUNNING", pid: 123, launcher: "dashboard"});
    expect(launchCalls()).toHaveLength(1);
  });
  it("late confirmation needs no retry: a follow-up start reconciles without respawning", async () => {
    readiness.mockReturnValue({ready: true, reason: "SUPERVISED_CHAIN_VERIFIED", checks: []});
    run.mockImplementation((...a: unknown[]) => runningDashboard);
    const r = await POST(req({confirm: "START_OBSERVE_2100", preset: "brief"}));
    expect(r.status).toBe(409);
    expect(await r.json()).toMatchObject({error: "ALREADY_RUNNING"});
    expect(launchCalls()).toHaveLength(0);
  });
});
