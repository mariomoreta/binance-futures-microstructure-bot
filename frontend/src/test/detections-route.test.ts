// @vitest-environment node
import {beforeEach, describe, expect, it, vi} from "vitest";
const run = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({spawnSync: run, default: {spawnSync: run}}));
import {GET} from "@/app/api/v1/detections/route";
import {runDetections} from "@/lib/detections";

beforeEach(() => {vi.resetAllMocks();});
describe("detections route: recorded-run evidence only", () => {
  it("surfaces unavailable as UNKNOWN without inventing episodes", async () => {
    run.mockReturnValue({status: 0, stdout: JSON.stringify({schema_version: 1, available: false, run_id: null, probe_run_id: null, limitation: "no-recorded-run", episodes: []})});
    const r = await GET();
    const body = await r.json() as {available: boolean; episodes: unknown[]};
    expect(body.available).toBe(false);
    expect(body.episodes).toEqual([]);
    const x = runDetections();
    expect(x.available).toBe(false);
  });
  it("preserves separate event/episode counts with provenance and version", async () => {
    const payload = {schema_version: 1, available: true, run_id: "probe-test", probe_run_id: "c".repeat(32),
      grouping_version: "v1", events_total: 3, episodes_total: 2, skipped_records: 0, limitation: null,
      episodes: [{episode_id: "BTCUSDT/1/2026", symbol: "BTCUSDT", funding_rate: 0.00005, repetitions: 2, duplicate_records: 0,
        first_observed_at: "2026-10-16T00:00:01Z", last_observed_at: "2026-10-16T00:00:02Z", duration_s: 1,
        samples_first: 100, samples_last: 101, open_reason: "first-event", close_reason: "superseded"}]};
    run.mockReturnValue({status: 0, stdout: JSON.stringify(payload)});
    const r = await GET();
    const body = await r.json() as {events_total: number; episodes_total: number; run_id: string};
    expect(body.events_total).toBe(3);
    expect(body.episodes_total).toBe(2);
    expect(body.run_id).toBe("probe-test");
    const x = runDetections();
    expect(x.episodes[0]?.repetitions).toBe(2);
    expect(Number.isFinite(Date.parse(x.observed_at))).toBe(true);
  });
  it("reports controller failure without claiming evidence", () => {
    run.mockReturnValue({status: 1, stdout: ""});
    const x = runDetections();
    expect(x.available).toBe(false);
    expect(x.error).toBe("CANONICAL_CONTROLLER_UNAVAILABLE");
  });
});
