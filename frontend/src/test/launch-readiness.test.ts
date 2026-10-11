// @vitest-environment node
import {beforeEach, describe, expect, it, vi} from "vitest";
import {spawnSync} from "node:child_process";
import {historicalRead} from "@/lib/historical-db";
import {runtimeStatus} from "@/lib/runtime-control";
import {launchReadiness} from "@/lib/launch-readiness";

vi.mock("node:child_process", () => ({spawnSync: vi.fn()}));
vi.mock("@/lib/historical-db", () => ({historicalRead: vi.fn()}));

const respond = (value: unknown, status = 0) =>
  vi.mocked(spawnSync).mockReturnValue({
    stdout: JSON.stringify(value), status,
  } as ReturnType<typeof spawnSync>);
const check = (name: string) => launchReadiness().checks.find(x => x.name === name)?.status;

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(historicalRead).mockReturnValue(true);
});

describe("runtime readiness requires controller evidence", () => {
  it("keeps unavailable mode and concurrency UNKNOWN", () => {
    vi.mocked(spawnSync).mockReturnValue({
      error: new Error("unavailable"), stdout: "", status: null,
    } as ReturnType<typeof spawnSync>);
    expect(runtimeStatus()).toMatchObject({mode: "UNKNOWN", state: "UNKNOWN"});
    expect(check("Canonical controller")).toBe("UNKNOWN");
    expect(check("Observe-only mode")).toBe("UNKNOWN");
    expect(check("Registry reports no active run")).toBe("UNKNOWN");
  });
  it.each([null, [], "observe", 1])("rejects non-object JSON %j without throwing", value => {
    respond(value);
    expect(runtimeStatus()).toMatchObject({error: "INVALID_CONTROLLER_RESPONSE", mode: "UNKNOWN"});
    expect(check("Observe-only mode")).toBe("UNKNOWN");
  });
  it("does not infer observe mode from missing fields", () => {
    respond({running: false, state: "STOPPED"});
    expect(runtimeStatus().mode).toBe("UNKNOWN");
    expect(check("Observe-only mode")).toBe("UNKNOWN");
  });
  it.each(["UNKNOWN", "RUNNING", "FUTURE_STATE"])("does not clear concurrency for %s", state => {
    respond({running: false, state, mode: "observe"});
    expect(check("Registry reports no active run")).toBe("UNKNOWN");
  });
  it("requires an explicit boolean running field", () => {
    respond({state: "STOPPED", mode: "observe"});
    expect(check("Registry reports no active run")).toBe("UNKNOWN");
  });
  it.each(["STOPPED", "COMPLETED", "FAILED"])("recognizes recorded inactive %s", state => {
    respond({running: false, state, mode: "observe"});
    expect(check("Registry reports no active run")).toBe("PASS");
    expect(check("Observe-only mode")).toBe("PASS");
    expect(launchReadiness()).toMatchObject({
      ready: false, reason: "ATOMIC_SUPERVISED_LAUNCH_UNAVAILABLE",
    });
    expect(check("Atomic launch with persistent supervisor and sentinel")).toBe("BLOCKED");
  });
  it.each(["STARTING", "STOPPING"])("blocks concurrent %s", state => {
    respond({running: false, state, mode: "observe"});
    expect(check("Registry reports no active run")).toBe("BLOCKED");
  });
  it("blocks explicit active runs and non-observe mode", () => {
    respond({running: true, state: "RUNNING", mode: "execution"});
    expect(check("Registry reports no active run")).toBe("BLOCKED");
    expect(check("Observe-only mode")).toBe("BLOCKED");
  });
  it("does not report a controller error as verified observe mode", () => {
    respond({running: false, state: "STOPPED", mode: "observe", error: "STATUS_FAILED"});
    expect(check("Canonical controller")).toBe("UNKNOWN");
    expect(check("Observe-only mode")).toBe("UNKNOWN");
    expect(check("Registry reports no active run")).toBe("UNKNOWN");
  });
  it("keeps failed commands unknown even when stdout resembles success", () => {
    respond({running: false, state: "STOPPED", mode: "observe"}, 1);
    expect(runtimeStatus()).toMatchObject({mode: "UNKNOWN", error: "CANONICAL_CONTROLLER_UNAVAILABLE"});
    expect(check("Observe-only mode")).toBe("UNKNOWN");
  });
});