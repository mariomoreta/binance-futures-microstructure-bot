// @vitest-environment node
import {beforeEach, describe, expect, it, vi} from "vitest";
const run = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({spawnSync: run, default: {spawnSync: run}}));
import {POST} from "@/app/api/v1/runtime/stop/route";

const req = (body: unknown, headers: Record<string, string> = {}) =>
  new Request("http://127.0.0.1:3020/api/v1/runtime/stop", {
    method: "POST",
    headers: {origin: "http://127.0.0.1:3020", host: "127.0.0.1:3020",
      "x-v2-action": "observe-only", "sec-fetch-site": "same-origin", ...headers},
    body: JSON.stringify(body),
  });

// The stop preflight is a pure read first; only a verified project-owned
// active run (dashboard/agent/direct) reaches the verified kill. Note
// runtimeAction("stop") runs ONE fixed script (status read + launcher guard
// + conditional stop_probe), so the mock keys on "requester=" (present only
// in that script) and emulates what canonical Python yields on each branch.
// Backend stop_probe remains the authority: PID+image+ctime under lock,
// foreign processes never touched.
const statusOf = (launcher: string | null, running = true) => ({
  status: 0,
  stdout: JSON.stringify({state: running ? "RUNNING" : "STOPPED", running,
    pid: running ? 123 : null, launcher, mode: "observe",
    supervisor: null, sentinel: null}),
});
const isStopScript = (call: unknown[]) =>
  String((call[1] as string[])[1]).includes("requester=");

beforeEach(() => { vi.resetAllMocks(); });
describe("runtime stop route: verified project stop (dashboard/agent/direct)", () => {
  it("keeps FORBIDDEN without origin plus action header", async () => {
    const r = await POST(new Request("http://127.0.0.1:3020/api/v1/runtime/stop", {method: "POST"}));
    expect(r.status).toBe(403);
    expect(run).not.toHaveBeenCalled();
  });
  it("requires the stop confirmation before any status read", async () => {
    const r = await POST(req({confirm: "WRONG"}));
    expect(r.status).toBe(400);
    expect(await r.json()).toMatchObject({error: "CONFIRMATION_REQUIRED"});
    expect(run).not.toHaveBeenCalled();
  });
  it("refuses a truly foreign run with 409 and never kills it", async () => {
    run.mockImplementation((...a: unknown[]) => {
      // Canonical fixed script guard yields not_project_owned before
      // stop_probe ever runs for non-project launchers.
      if (isStopScript(a)) return {status: 0, stdout: JSON.stringify({error: "not_project_owned", launcher: "other-tool"})};
      return statusOf("other-tool");
    });
    const r = await POST(req({confirm: "STOP_DASHBOARD_SESSION"}));
    expect(r.status).toBe(409);
    expect(await r.json()).toMatchObject({error: "not_project_owned"});
    // Fail-closed order inside the fixed script: the launcher guard
    // precedes the verified kill.
    const script = String(run.mock.calls.map(c => String(c[1][1])).find(s => s.includes("requester=")));
    expect(script.indexOf("dashboard") < script.indexOf("stop_probe")).toBe(true);
  });
  it("stops a dashboard-owned run and relays the result", async () => {
    run.mockImplementation((...a: unknown[]) => {
      if (isStopScript(a)) return {status: 0, stdout: JSON.stringify({stopped: true, pid: 123})};
      return statusOf("dashboard");
    });
    const r = await POST(req({confirm: "STOP_DASHBOARD_SESSION"}));
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({stopped: true});
  });
  it("stops a verified agent run (launcher=agent) without treating it as foreign", async () => {
    run.mockImplementation((...a: unknown[]) => {
      if (isStopScript(a)) return {status: 0, stdout: JSON.stringify({stopped: true, pid: 456})};
      return statusOf("agent");
    });
    const r = await POST(req({confirm: "STOP_DASHBOARD_SESSION"}));
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({stopped: true, pid: 456});
    const script = String(run.mock.calls.map(c => String(c[1][1])).find(s => s.includes("requester=")));
    expect(script).toContain("('dashboard','agent','direct')");
  });
  it("maps a failed stop to 409 without claiming it", async () => {
    run.mockImplementation((...a: unknown[]) => {
      if (isStopScript(a)) return {status: 0, stdout: JSON.stringify({stopped: false, error: "stale-probe-record-recovered", state: "FAILED"})};
      return statusOf("dashboard");
    });
    const r = await POST(req({confirm: "STOP_DASHBOARD_SESSION"}));
    expect(r.status).toBe(409);
    expect(await r.json()).toMatchObject({stopped: false});
  });
});
