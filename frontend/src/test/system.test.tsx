import {describe,expect,it,vi} from "vitest";
import {render,screen} from "@testing-library/react";
import SystemPage from "@/app/system/page";

vi.mock("@/components/notices/SnapshotRefresh",()=>({SnapshotRefresh:()=>null}));
vi.mock("@/lib/runtime-control",()=>({runtimeStatus:()=>({
  running:false,state:"UNKNOWN",pid:null,launcher:null,mode:"UNKNOWN",
  uptime_seconds:null,duration_seconds:null,started_at:null,
  feed_health:"UNKNOWN",latest_snapshot_age:null,error:"CONTROLLER_UNAVAILABLE",
}),controllerHasLaunch:()=>false}));
vi.mock("@/lib/historical-db",()=>({historicalRead:()=>{throw Error("No unit-test database");}}));

describe("System V2 truthful shell",()=>{it("shows unknown, not invented operational health",()=>{
  render(<SystemPage/>);
  expect(screen.getByTestId("system-v2")).toBeInTheDocument();
  expect(screen.getAllByText("UNKNOWN").length).toBeGreaterThan(4);
  expect(screen.getByText(/No real operational events loaded/)).toBeInTheDocument();
  expect(screen.queryByText("99.98%")).not.toBeInTheDocument();
  expect(screen.queryByText(/CONTROL CONNECTED/)).not.toBeInTheDocument();
  expect(screen.getByRole("region",{name:"Host & service coverage"})).toBeInTheDocument();
});});
