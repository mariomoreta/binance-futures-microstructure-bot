import {act, cleanup, render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";
import {BotControl} from "@/components/system/BotControl";

afterEach(() => {cleanup(); vi.useRealTimers(); vi.unstubAllGlobals();});

describe("System runtime presentation", () => {
  it("keeps unavailable client mode UNKNOWN and exposes the error outside the disclosure", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<BotControl />);
    await act(async () => {await vi.advanceTimersByTimeAsync(1);});
    const mode = screen.getByText("Runtime mode").parentElement;
    expect(mode?.querySelector("strong")).toHaveTextContent("UNKNOWN");
    expect(screen.getByRole("alert").closest("details")).toBeNull();
    expect(screen.getByText("Runtime controls & supervisor evidence").closest("details")).not.toHaveAttribute("open");
    expect(screen.getByRole("button", {name: /Start monitor/})).toBeDisabled();
    expect(screen.getByRole("button", {name: /Stop dashboard/})).toBeDisabled();
  });
  it("renders authoritative process and supervisor independently and preserves foreign ownership protection", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok:true, json:async () => ({
      state:"RUNNING", running:true, mode:"observe", launcher:"agent",
      pid:123, uptime_seconds:0, duration_seconds:2100, started_at:null,
      feed_health:"UNKNOWN", supervisor:{state:"SUPERVISOR_UNKNOWN"},
    })}));
    render(<BotControl />);
    await act(async () => {await vi.advanceTimersByTimeAsync(1);});
    expect(screen.getByText("Market engine").parentElement?.querySelector("strong")).toHaveTextContent("RUNNING");
    expect(screen.getByText("Supervisor").parentElement?.querySelector("strong")).toHaveTextContent("UNKNOWN");
    expect(screen.getByRole("button", {name: /Stop dashboard/})).toBeDisabled();
    expect(screen.getByText(/A session launched by agent/)).toBeInTheDocument();
  });
});
