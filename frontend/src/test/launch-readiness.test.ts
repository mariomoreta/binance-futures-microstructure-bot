// @vitest-environment node
import {beforeEach, describe, expect, it, vi} from "vitest";
import {spawnSync} from "node:child_process";
import {historicalRead} from "@/lib/historical-db";
import {runtimeStatus} from "@/lib/runtime-control";
import {launchReadiness} from "@/lib/launch-readiness";

vi.mock("node:child_process", () => ({spawnSync: vi.fn()}));
vi.mock("@/lib/historical-db", () => ({historicalRead: vi.fn()}));
vi.mock("@/lib/storage-preflight", () => ({readStorageEvidence: vi.fn()}));
import {readStorageEvidence} from "@/lib/storage-preflight";

const respond = (value: unknown, status = 0) =>
  vi.mocked(spawnSync).mockReturnValue({
    stdout: JSON.stringify(value), status,
  } as ReturnType<typeof spawnSync>);
const check = (name: string) => launchReadiness().checks.find(x => x.name === name)?.status;

const storageOk = () => vi.mocked(readStorageEvidence).mockReturnValue({
  available: true, read_at: "2026-10-14T00:00:00Z", snapshot: null,
  measured: {operational_db: {bytes: 1000, wal_bytes: null, shm_bytes: null},
    historical_db: {bytes: 1000, wal_bytes: null, shm_bytes: null},
    logs: {bytes: 10, files: 1}, disk_free_bytes: 153_000_000_000},
  alerts: [], errors: [], blocked: [], note: "test",
});
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(historicalRead).mockReturnValue(true);
  storageOk();
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
  it("goes ready only with a verified launch path plus every check green", () => {
    vi.mocked(historicalRead).mockReturnValue({quick_check: "ok"});
    vi.mocked(spawnSync).mockImplementation(((...a: unknown[]) => {
      const code = String((a[1] as string[])[1] ?? "");
      if (code.includes("SUPERVISED_LAUNCH_ENABLED")) return {stdout: JSON.stringify({present: true, enabled: true, verify_budget_s: 60, poll_s: 2}), status: 0};
      return {stdout: JSON.stringify({running: false, state: "STOPPED", mode: "observe"}), status: 0};
    }) as typeof spawnSync);
    const r = launchReadiness();
    expect(check("Atomic launch with persistent supervisor and sentinel")).toBe("PASS");
    expect(check("Storage preflight")).toBe("PASS");
    expect(r).toMatchObject({ready: true, reason: "SUPERVISED_CHAIN_VERIFIED"});
  });
  it("treats ABORTED as recorded-terminal, not as an active or unknown run", () => {
    vi.mocked(historicalRead).mockReturnValue({quick_check: "ok"});
    vi.mocked(spawnSync).mockImplementation(((...a: unknown[]) => {
      const code = String((a[1] as string[])[1] ?? "");
      if (code.includes("SUPERVISED_LAUNCH_ENABLED")) return {stdout: JSON.stringify({present: true, enabled: true, verify_budget_s: 60, poll_s: 2}), status: 0};
      return {stdout: JSON.stringify({running: false, state: "ABORTED", mode: "observe"}), status: 0};
    }) as typeof spawnSync);
    expect(check("Registry reports no active run")).toBe("PASS");
    expect(launchReadiness().checks.find(x => x.name === "Registry reports no active run")?.detail).toMatch(/ABORTED.*terminal/);
  });
  it("keeps launch blocked when the capability probe disagrees", () => {
    vi.mocked(spawnSync).mockImplementation(((...a: unknown[]) => {
      const code = String((a[1] as string[])[1] ?? "");
      if (code.includes("SUPERVISED_LAUNCH_ENABLED")) return {stdout: JSON.stringify({present: true, enabled: false, verify_budget_s: 60, poll_s: 2}), status: 0};
      return {stdout: JSON.stringify({running: false, state: "STOPPED", mode: "observe"}), status: 0};
    }) as typeof spawnSync);
    expect(check("Atomic launch with persistent supervisor and sentinel")).toBe("BLOCKED");
    expect(launchReadiness()).toMatchObject({ready: false, reason: "ATOMIC_SUPERVISED_LAUNCH_UNAVAILABLE"});
  });
  it("never certifies the chain by mere callable presence: disabled stays blocked", () => {
    vi.mocked(historicalRead).mockReturnValue({quick_check: "ok"});
    vi.mocked(spawnSync).mockImplementation(((...a: unknown[]) => {
      const code = String((a[1] as string[])[1] ?? "");
      if (code.includes("SUPERVISED_LAUNCH_ENABLED")) return {stdout: JSON.stringify({present: true, enabled: false, verify_budget_s: 60, poll_s: 2}), status: 0};
      return {stdout: JSON.stringify({running: false, state: "STOPPED", mode: "observe"}), status: 0};
    }) as typeof spawnSync);
    expect(check("Atomic launch with persistent supervisor and sentinel")).toBe("BLOCKED");
    expect(launchReadiness().ready).toBe(false);
  });
  it("blocks on a non-finite verification budget even when enabled", () => {
    vi.mocked(historicalRead).mockReturnValue({quick_check: "ok"});
    vi.mocked(spawnSync).mockImplementation(((...a: unknown[]) => {
      const code = String((a[1] as string[])[1] ?? "");
      if (code.includes("SUPERVISED_LAUNCH_ENABLED")) return {stdout: JSON.stringify({present: true, enabled: true, verify_budget_s: null, poll_s: 2}), status: 0};
      return {stdout: JSON.stringify({running: false, state: "STOPPED", mode: "observe"}), status: 0};
    }) as typeof spawnSync);
    expect(check("Atomic launch with persistent supervisor and sentinel")).toBe("BLOCKED");
    expect(launchReadiness().ready).toBe(false);
  });
  it("blocks launch when the operational DB is absent, with measured values", () => {
    vi.mocked(historicalRead).mockReturnValue({quick_check: "ok"});
    vi.mocked(spawnSync).mockImplementation(((...a: unknown[]) => {
      const code = String((a[1] as string[])[1] ?? "");
      if (code.includes("SUPERVISED_LAUNCH_ENABLED")) return {stdout: JSON.stringify({present: true, enabled: true, verify_budget_s: 60, poll_s: 2}), status: 0};
      return {stdout: JSON.stringify({running: false, state: "STOPPED", mode: "observe"}), status: 0};
    }) as typeof spawnSync);
    vi.mocked(readStorageEvidence).mockReturnValue({
      available: false, read_at: "2026-10-14T00:00:00Z", snapshot: null,
      measured: {operational_db: {bytes: null, wal_bytes: null, shm_bytes: null},
        historical_db: {bytes: 1000, wal_bytes: null, shm_bytes: null},
        logs: {bytes: 10, files: 1}, disk_free_bytes: 153_000_000_000},
      alerts: [], errors: ["operational DB absent/unreadable: run state UNKNOWN"], blocked: [], note: "test",
    });
    expect(check("Storage preflight")).toBe("BLOCKED");
    expect(launchReadiness().ready).toBe(false);
  });
  it("blocks launch when disk free is unmeasurable or below the hard floor", () => {
    vi.mocked(historicalRead).mockReturnValue({quick_check: "ok"});
    vi.mocked(spawnSync).mockImplementation(((...a: unknown[]) => {
      const code = String((a[1] as string[])[1] ?? "");
      if (code.includes("SUPERVISED_LAUNCH_ENABLED")) return {stdout: JSON.stringify({present: true, enabled: true, verify_budget_s: 60, poll_s: 2}), status: 0};
      return {stdout: JSON.stringify({running: false, state: "STOPPED", mode: "observe"}), status: 0};
    }) as typeof spawnSync);
    vi.mocked(readStorageEvidence).mockReturnValue({
      available: false, read_at: "2026-10-14T00:00:00Z", snapshot: null,
      measured: {operational_db: {bytes: 1000, wal_bytes: null, shm_bytes: null},
        historical_db: {bytes: 1000, wal_bytes: null, shm_bytes: null},
        logs: {bytes: 10, files: 1}, disk_free_bytes: 100_000_000},
      alerts: [], errors: [], blocked: [], note: "test",
    });
    expect(check("Storage preflight")).toBe("BLOCKED");
  });
  it("keeps historical absence and warn-floor advisory, never blocking", () => {
    vi.mocked(historicalRead).mockReturnValue({quick_check: "ok"});
    vi.mocked(spawnSync).mockImplementation(((...a: unknown[]) => {
      const code = String((a[1] as string[])[1] ?? "");
      if (code.includes("SUPERVISED_LAUNCH_ENABLED")) return {stdout: JSON.stringify({present: true, enabled: true, verify_budget_s: 60, poll_s: 2}), status: 0};
      return {stdout: JSON.stringify({running: false, state: "STOPPED", mode: "observe"}), status: 0};
    }) as typeof spawnSync);
    vi.mocked(readStorageEvidence).mockReturnValue({
      available: false, read_at: "2026-10-14T00:00:00Z", snapshot: null,
      measured: {operational_db: {bytes: 1000, wal_bytes: null, shm_bytes: null},
        historical_db: {bytes: null, wal_bytes: null, shm_bytes: null},
        logs: {bytes: 10, files: 1}, disk_free_bytes: 500_000_000},
      alerts: [{level: "info", text: "No preflight snapshot"}], errors: ["historical DB absent/unreadable: research coverage UNKNOWN"], blocked: [], note: "test",
    });
    expect(check("Storage preflight")).toBe("PASS");
    expect(launchReadiness()).toMatchObject({ready: true, reason: "SUPERVISED_CHAIN_VERIFIED"});
  });
});