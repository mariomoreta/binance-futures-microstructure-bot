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
    run.mockReturnValue({status: 0, stdout: JSON.stringify({outcome: "confirmed", reason: "verified", run_id: "r1"})});
    const r = await POST(req({confirm: "START_OBSERVE_2100", preset: "brief"}));
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({outcome: "confirmed", run_id: "r1"});
    const script = String(run.mock.calls[0]?.[1]?.[1]);
    expect(script).toContain("launch_supervised_transaction");
    expect(script).toContain("duration_seconds=120");
  });
  it("maps non-confirmed envelopes to 409 without claiming success", async () => {
    readiness.mockReturnValue({ready: true, reason: "SUPERVISED_CHAIN_VERIFIED", checks: []});
    run.mockReturnValue({status: 0, stdout: JSON.stringify({outcome: "rejected", reason: "registry-unavailable"})});
    const r = await POST(req({confirm: "START_OBSERVE_2100"}));
    expect(r.status).toBe(409);
    expect(await r.json()).toMatchObject({outcome: "rejected"});
  });
  it("binds the fixed call to launcher dashboard so stop wiring applies", async () => {
    readiness.mockReturnValue({ready: true, reason: "SUPERVISED_CHAIN_VERIFIED", checks: []});
    run.mockReturnValue({status: 0, stdout: JSON.stringify({outcome: "confirmed", run_id: "r1"})});
    const r = await POST(req({confirm: "START_OBSERVE_2100", preset: "brief"}));
    expect(r.status).toBe(200);
    const script = String(run.mock.calls[0]?.[1]?.[1]);
    expect(script).toContain("launcher='dashboard'");
    expect(script).toContain("preset='brief'");
  });
  it("relays rollback evidence on rejected launches instead of hiding it", async () => {
    readiness.mockReturnValue({ready: true, reason: "SUPERVISED_CHAIN_VERIFIED", checks: []});
    const envelope = {outcome: "rejected", reason: "sentinel-spawn-failed",
      rollback: {attempted: true, cleaned: [{role: "probe"}], pending: []}};
    run.mockReturnValue({status: 0, stdout: JSON.stringify(envelope)});
    const r = await POST(req({confirm: "START_OBSERVE_2100", preset: "brief"}));
    expect(r.status).toBe(409);
    expect(await r.json()).toMatchObject({reason: "sentinel-spawn-failed", rollback: {attempted: true, pending: []}});
  });
});
