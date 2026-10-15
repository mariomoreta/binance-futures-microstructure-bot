import {act, cleanup, render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";
import {RunStatusBar} from "@/components/shell/RunStatusBar";

afterEach(()=>{cleanup();vi.useRealTimers();vi.unstubAllGlobals();});

function mockRuntime(body:unknown){
 vi.useFakeTimers();
 vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>body}));
}

describe("Global run status bar",()=>{
 it("shows recorded state, origin, run, start, plan and remaining on every screen",async()=>{
  mockRuntime({state:"RUNNING",running:true,pid:492,launcher:"dashboard",mode:"observe",
   run_id:"probe-20261015T102519Z",started_at:"2026-10-15T10:25:20+00:00",
   duration_seconds:120,remaining_seconds:60,elapsed_seconds:60,expected_end_at:"2026-10-15T10:27:20+00:00",
   process_state:"owned",process_verified:true,feed_health:"HEALTHY",latest_snapshot_age:5,
   observed_at:new Date().toISOString(),supervisor:{state:"SUPERVISOR_ACTIVE"},sentinel:{state:"SENTINEL_ACTIVE"}});
  render(<RunStatusBar/>);
  await act(async()=>{await vi.advanceTimersByTimeAsync(1);});
  expect(screen.getByTestId("run-status-bar")).toBeInTheDocument();
  expect(screen.getByTestId("rsb-recorded")).toHaveTextContent("RECORDED RUNNING");
  expect(screen.getByTestId("rsb-verified")).toHaveTextContent("OWNED-LIVE");
  expect(screen.getByTestId("rsb-origin")).toHaveTextContent("dashboard");
  expect(screen.getByTestId("rsb-run")).toHaveTextContent("probe-20261015T102519Z");
  expect(screen.getByTestId("rsb-start")).toHaveTextContent("2026-10-15T10:25:20");
  expect(screen.getByTestId("rsb-duration")).toHaveTextContent("120s");
  expect(screen.getByTestId("rsb-remaining")).toHaveTextContent("LEFT");
  expect(screen.getByTestId("rsb-feed")).toHaveTextContent("HEALTHY");
  expect(screen.getByTestId("rsb-supervisor")).toHaveTextContent("SUP");
  expect(screen.getByTestId("rsb-sentinel")).toHaveTextContent("SEN");
  expect(screen.getByText("System →").closest("a")).toHaveAttribute("href","/system");
 });
 it("distinguishes agent origin and unverified liveness without hiding the run",async()=>{
  mockRuntime({state:"RUNNING",running:true,pid:456,launcher:"agent",mode:"observe",
   run_id:"probe-agent",started_at:"2026-10-15T00:07:31+00:00",duration_seconds:120,remaining_seconds:70,
   process_state:"unknown",process_verified:false,feed_health:"DEGRADED",latest_snapshot_age:30,
   observed_at:new Date().toISOString(),supervisor:{state:"SUPERVISOR_STALE"},sentinel:{state:"SENTINEL_STALE"}});
  render(<RunStatusBar/>);
  await act(async()=>{await vi.advanceTimersByTimeAsync(1);});
  expect(screen.getByTestId("rsb-origin")).toHaveTextContent("agent");
  expect(screen.getByTestId("rsb-verified")).toHaveTextContent("NOT-LIVE");
 });
 it("freezes terminal close reason, close time and duration on COMPLETED",async()=>{
  mockRuntime({state:"COMPLETED",running:false,pid:492,launcher:"dashboard",mode:"observe",
   run_id:"probe-20261015T102519Z",duration_seconds:120,elapsed_seconds:133,uptime_seconds:133,
   last_exit_reason:"duration-reached",last_exit_at:"2026-10-15T10:27:33+00:00",
   process_state:"gone",process_verified:false,feed_health:"STALE",latest_snapshot_age:900,
   supervisor:{state:"SUPERVISOR_STALE"},sentinel:{state:"SENTINEL_STALE"}});
  render(<RunStatusBar/>);
  await act(async()=>{await vi.advanceTimersByTimeAsync(1);});
  expect(screen.getByTestId("rsb-terminal")).toHaveTextContent("duration-reached");
  expect(screen.getByTestId("rsb-terminal")).toHaveTextContent("2026-10-15T10:27:33");
  expect(screen.getByTestId("rsb-terminal")).toHaveTextContent("133s");
 });
 it("reports disconnection without claiming a run",async()=>{
  vi.useFakeTimers();
  vi.stubGlobal("fetch",vi.fn().mockRejectedValue(new Error("offline")));
  render(<RunStatusBar/>);
  await act(async()=>{await vi.advanceTimersByTimeAsync(1);});
  expect(screen.getByTestId("rsb-error")).toHaveTextContent("STATUS_UNAVAILABLE");
 });
});
