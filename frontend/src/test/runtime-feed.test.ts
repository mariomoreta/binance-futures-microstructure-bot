// @vitest-environment node
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
const run = vi.hoisted(() => vi.fn());
const readDb = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({spawnSync: run, default: {spawnSync: run}}));
vi.mock("@/lib/historical-db", () => ({historicalRead: readDb}));
import {feedFromStore, runtimeStatus} from "@/lib/runtime-control";

const NOW = Date.parse("2026-10-15T10:30:00Z");
const nowSec = NOW / 1000;
const STARTED = "2026-10-15T10:25:20+00:00";

function quality(patch: Record<string, unknown> = {}) {
  return {
    activeStreams: 11, expectedStreams: 11,
    missingStreams: [], staleStreams: [], silentStreams: ["!forceOrder@arr"],
    messagesByStream: {a: 1000, b: 2000},
    timestampRejected: 0,
    reconnections: {public: 0, market: 0},
    parseErrors: 0, payloadErrors: 0,
    websocketErrors: {public: 0, market: 0},
    ...patch,
  };
}
function controller(patch: Record<string, unknown> = {}) {
  return {
    state: "RUNNING", running: true, pid: 1, launcher: "dashboard",
    mode: "observe", started_at: STARTED, supervisor: null, sentinel: null,
    ...patch,
  };
}
function row(tsSec: number, dq: unknown) {
  return {
    prepare: () => ({get: () => ({timestamp: tsSec, data_quality_json: typeof dq === "string" ? dq : JSON.stringify(dq)})}),
  };
}
function statusWith(tsSec: number, dq: unknown, ctrl: Record<string, unknown> = {}) {
  run.mockReturnValue({status: 0, stdout: JSON.stringify(controller(ctrl))});
  readDb.mockImplementation((fn: (db: unknown) => unknown) => fn(row(tsSec, dq)));
  return runtimeStatus();
}

beforeEach(() => {vi.useFakeTimers(); vi.setSystemTime(new Date(NOW));});
afterEach(() => {vi.resetAllMocks(); vi.useRealTimers();});

describe("Feed health never claims HEALTHY without sufficient attributable evidence", () => {
  it("returns UNKNOWN on invalid quality JSON", () => {
    const x = statusWith(nowSec - 10, "{broken");
    expect(x.feed_health).toBe("UNKNOWN");
    expect(x.feed_attribution).toBe("current");
    expect(x.feed_health).not.toBe("HEALTHY");
  });
  it("returns UNKNOWN on zero messages", () => {
    const x = statusWith(nowSec - 10, quality({messagesByStream: {}}));
    expect(x.feed_health).toBe("UNKNOWN");
  });
  it("returns UNKNOWN when required fields are absent", () => {
    const q = quality(); delete (q as Record<string, unknown>).messagesByStream;
    const x = statusWith(nowSec - 10, q);
    expect(x.feed_health).toBe("UNKNOWN");
    const y = statusWith(nowSec - 10, quality({activeStreams: undefined}));
    expect(y.feed_health).toBe("UNKNOWN");
  });
  it("marks data above the supervisor 0.05 reject gate DEGRADED, never HEALTHY", () => {
    // 180/3000 = 0.06: below the legacy 0.5 dashboard display concept but
    // above the enforced 0.05 supervisor abort gate. The abort threshold is
    // untouched; the BFF only refuses to call such data HEALTHY.
    const x = statusWith(nowSec - 10, quality({messagesByStream: {a: 3000}, timestampRejected: 180}));
    expect(x.feed_health).toBe("DEGRADED");
    expect(x.feed_health).not.toBe("HEALTHY");
  });
  it("reports HEALTHY only for complete fresh attributable evidence", () => {
    const x = statusWith(nowSec - 5, quality());
    expect(x.feed_health).toBe("HEALTHY");
    expect(x.feed_attribution).toBe("current");
    expect(x.latest_snapshot_age).toBe(5);
  });
  it("marks missing streams, foreign silence and parse/payload errors DEGRADED", () => {
    expect(statusWith(nowSec - 5, quality({missingStreams: ["x"]})).feed_health).toBe("DEGRADED");
    expect(statusWith(nowSec - 5, quality({silentStreams: ["!forceOrder@arr", "btcusdt@aggTrade"]})).feed_health).toBe("DEGRADED");
    expect(statusWith(nowSec - 5, quality({parseErrors: 2})).feed_health).toBe("DEGRADED");
    expect(statusWith(nowSec - 5, quality({payloadErrors: 1})).feed_health).toBe("DEGRADED");
    // Event-driven forceOrder silence alone stays HEALTHY.
    expect(statusWith(nowSec - 5, quality()).feed_health).toBe("HEALTHY");
  });
  it("labels fresh evidence from another run as previous-run, never current HEALTHY", () => {
    // Snapshot 90s old (fresh) but predating the current run window:
    // evidence from another run, however recent.
    const x = statusWith(nowSec - 90, quality(), {started_at: new Date(NOW).toISOString()});
    expect(x.feed_health).toBe("UNKNOWN");
    expect(x.feed_attribution).toBe("previous-run");
    expect(x.feed_health).not.toBe("HEALTHY");
  });
  it("returns UNKNOWN without masking when the store is unavailable", () => {
    run.mockReturnValue({status: 0, stdout: JSON.stringify(controller())});
    readDb.mockImplementation(() => {throw new Error("locked");});
    const x = runtimeStatus();
    expect(x.feed_health).toBe("UNKNOWN");
    expect(x.feed_attribution).toBe("none");
  });
  it("attributes the pilot final snapshot to its run window", () => {
    // Real pilot final row shape (10:27:24Z inside 10:25:20-10:27:33Z):
    // stale by clock but attributable to its own run, never to another.
    readDb.mockImplementation((fn: (db: unknown) => unknown) => fn(row(1792060044.4666967, quality({timestampRejected: 0}))));
    const f = feedFromStore({started_at: "2026-10-15T10:25:20+00:00", last_exit_at: "2026-10-15T10:27:33+00:00", expected_end_at: null, state: "COMPLETED"});
    expect(f.feed_attribution).toBe("current");
    expect(f.feed_health).toBe("STALE");
  });
});
