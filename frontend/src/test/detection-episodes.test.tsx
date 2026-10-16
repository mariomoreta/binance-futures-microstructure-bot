import {act, cleanup, render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";
import {DetectionEpisodes} from "@/components/system/DetectionEpisodes";

afterEach(() => {cleanup(); vi.useRealTimers(); vi.unstubAllGlobals();});

describe("Detection episodes panel", () => {
  it("shows separate event/episode counts with provenance, version and research label", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok: true, json: async () => ({
      available: true, run_id: "probe-test", probe_run_id: "c".repeat(32), grouping_version: "v1",
      events_total: 245, episodes_total: 13, skipped_records: 0, limitation: null,
      episodes: [{episode_id: "BTCUSDT/x", symbol: "BTCUSDT", funding_rate: 0.00005583, repetitions: 9,
        first_observed_at: "2026-10-15T23:09:01+00:00", last_observed_at: "2026-10-15T23:09:09+00:00",
        duration_s: 8, open_reason: "first-event", close_reason: "superseded"}],
      observed_at: new Date().toISOString(),
    })}));
    render(<DetectionEpisodes />);
    await act(async () => {await vi.advanceTimersByTimeAsync(1);});
    expect(screen.getByTestId("ep-events")).toHaveTextContent("245");
    expect(screen.getByTestId("ep-episodes")).toHaveTextContent("13");
    expect(screen.getByText(/probe-test/)).toBeInTheDocument();
    expect(screen.getByText(/never entry signals/)).toBeInTheDocument();
  });
  it("renders UNKNOWN explicitly when evidence is missing", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok: true, json: async () => ({
      available: false, run_id: null, limitation: "no-recorded-run", episodes: [],
    })}));
    render(<DetectionEpisodes />);
    await act(async () => {await vi.advanceTimersByTimeAsync(1);});
    expect(screen.getByText(/UNKNOWN/)).toBeInTheDocument();
    expect(screen.queryByTestId("ep-events")).toBeNull();
  });
  it("expires to UNKNOWN when the read fails", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<DetectionEpisodes />);
    await act(async () => {await vi.advanceTimersByTimeAsync(1);});
    expect(screen.getByText(/UNKNOWN/)).toBeInTheDocument();
  });
});
