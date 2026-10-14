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
    expect(screen.getByText("Recorded process").parentElement?.querySelector("strong")).toHaveTextContent("RUNNING");
    expect(screen.getByText("Supervisor").parentElement?.querySelector("strong")).toHaveTextContent("UNKNOWN");
    expect(screen.getByText(/current process liveness is not reported/)).toBeInTheDocument();
    expect(screen.getByRole("button", {name: /Stop dashboard/})).toBeDisabled();
    expect(screen.getByText(/A session launched by agent/)).toBeInTheDocument();
  });
});

describe("System launch through the supervised chain",()=>{
  it("enables start only on readiness-green and posts the bounded preset",async()=>{
    vi.useFakeTimers();
    const posted:{url:string,init:RequestInit}[]=[];
    vi.stubGlobal("fetch",vi.fn().mockImplementation(async(url:string,init?:RequestInit)=>{
      if(String(url).endsWith("/runtime/readiness"))return {ok:true,json:async()=>({ready:true,reason:"SUPERVISED_CHAIN_VERIFIED",checks:[]})};
      if(String(url).endsWith("/runtime/start")){posted.push({url:String(url),init:init!});return {ok:true,json:async()=>({outcome:"confirmed",run_id:"r1"})}};
      return {ok:true,json:async()=>({state:"STOPPED",running:false,pid:null,launcher:null,mode:"observe",supervisor:{state:"SUPERVISOR_UNKNOWN"},sentinel:{state:"SENTINEL_UNKNOWN"}})};
    }));
    render(<BotControl/>);
    await act(async()=>{await vi.advanceTimersByTimeAsync(1);});
    const start=screen.getByRole("button",{name:/Start monitor/});
    expect(start).toBeEnabled();
    await act(async()=>{start.click();});
    await act(async()=>{screen.getByRole("button",{name:"Confirm start"}).click();await vi.advanceTimersByTimeAsync(10);});
    expect(posted).toHaveLength(1);
    expect(JSON.parse(String(posted[0]!.init.body))).toMatchObject({confirm:"START_OBSERVE_2100",preset:"brief"});
    expect(screen.getByText(/supervised chain \(confirmed\)/)).toBeInTheDocument();
  });
});

describe("System launch uncertainty (HTTP 202)",()=>{
  const stoppedBody=()=>({state:"STOPPED",running:false,pid:null,launcher:null,mode:"observe",supervisor:{state:"SUPERVISOR_UNKNOWN"},sentinel:{state:"SENTINEL_UNKNOWN"}});
  const setup=(startReply:{ok:boolean;status:number;body:unknown},statusAfter:()=>unknown)=>{
    vi.useFakeTimers();vi.setSystemTime(new Date("2026-10-14T11:00:00Z"));
    let statusBody:unknown=stoppedBody();
    const posted:{url:string,init:RequestInit}[]=[];
    vi.stubGlobal("fetch",vi.fn().mockImplementation(async(url:string,init?:RequestInit)=>{
      if(String(url).endsWith("/runtime/readiness"))return {ok:true,json:async()=>({ready:true,reason:"SUPERVISED_CHAIN_VERIFIED",checks:[]})};
      if(String(url).endsWith("/runtime/start")){posted.push({url:String(url),init:init!});statusBody=statusAfter();return startReply.ok?{ok:true,status:startReply.status,json:async()=>startReply.body}:{ok:false,status:startReply.status,json:async()=>startReply.body}};
      return {ok:true,json:async()=>statusBody};
    }));
    return {posted,getStatus:()=>statusBody};
  };
  const openConfirm=async()=>{
    render(<BotControl/>);
    await act(async()=>{await vi.advanceTimersByTimeAsync(1);});
    await act(async()=>{screen.getByRole("button",{name:/Start monitor/}).click();});
    await act(async()=>{screen.getByRole("button",{name:"Confirm start"}).click();await vi.advanceTimersByTimeAsync(10);});
  };
  it("never presents 202 uncertain as success and blocks relaunch while uncertain",async()=>{
    setup({ok:true,status:202,body:{error:"START_TIMEOUT_UNCERTAIN",retry:"reconcile-before-retry",status:{state:"UNKNOWN"}}},()=>stoppedBody());
    await openConfirm();
    expect(screen.queryByText(/started via supervised chain/)).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/uncertain/i);
    expect(screen.getByRole("button",{name:/Start monitor/})).toBeDisabled();
  });
  it("announces success only on later explicit dashboard-owned confirmation",async()=>{
    vi.useFakeTimers();vi.setSystemTime(new Date("2026-10-14T11:00:00Z"));
    const t0=new Date("2026-10-14T11:00:00Z").getTime();
    const running=()=>({state:"RUNNING",running:true,pid:777,launcher:"dashboard",mode:"observe",started_at:new Date(t0+5000).toISOString(),supervisor:{state:"SUPERVISOR_UNKNOWN"},sentinel:{state:"SENTINEL_UNKNOWN"}});
    let late=false;
    vi.stubGlobal("fetch",vi.fn().mockImplementation(async(url:string)=>{
      if(String(url).endsWith("/runtime/readiness"))return {ok:true,json:async()=>({ready:true,reason:"SUPERVISED_CHAIN_VERIFIED",checks:[]})};
      if(String(url).endsWith("/runtime/start"))return {ok:true,status:202,json:async()=>({error:"START_TIMEOUT_UNCERTAIN",retry:"reconcile-before-retry"})};
      return {ok:true,json:async()=>late?running():stoppedBody()};
    }));
    render(<BotControl/>);
    await act(async()=>{await vi.advanceTimersByTimeAsync(1);});
    await act(async()=>{screen.getByRole("button",{name:/Start monitor/}).click();});
    await act(async()=>{screen.getByRole("button",{name:"Confirm start"}).click();await vi.advanceTimersByTimeAsync(10);});
    expect(screen.getByRole("status")).toHaveTextContent(/uncertain/i);
    expect(screen.getByRole("button",{name:/Start monitor/})).toBeDisabled();
    late=true;
    await act(async()=>{await vi.advanceTimersByTimeAsync(10_000);});
    expect(screen.getByRole("status")).toHaveTextContent(/confirmed.*777|777.*confirmed/i);
    expect(screen.queryByText(/uncertain/i)).not.toBeInTheDocument();
  });
  it("keeps uncertainty across failed refreshes and reconciles an inactive run without claiming success",async()=>{
    setup({ok:true,status:202,body:{error:"START_TIMEOUT_UNCERTAIN",retry:"reconcile-before-retry",status:{state:"UNKNOWN"}}},()=>stoppedBody());
    await openConfirm();
    expect(screen.getByRole("button",{name:/Start monitor/})).toBeDisabled();
    // Failed refresh: uncertainty persists, start stays blocked.
    vi.stubGlobal("fetch",vi.fn().mockRejectedValue(new Error("offline")));
    await act(async()=>{await vi.advanceTimersByTimeAsync(10_000);});
    expect(screen.getByRole("status")).toHaveTextContent(/uncertain/i);
    expect(screen.getByRole("button",{name:/Start monitor/})).toBeDisabled();
    // Reconciled inactive run: a new start is allowed, but the old
    // uncertain outcome is never rewritten as success.
    vi.stubGlobal("fetch",vi.fn().mockImplementation(async(url:string)=>{
      if(String(url).endsWith("/runtime/readiness"))return {ok:true,json:async()=>({ready:true,reason:"SUPERVISED_CHAIN_VERIFIED",checks:[]})};
      return {ok:true,json:async()=>stoppedBody()};
    }));
    await act(async()=>{await vi.advanceTimersByTimeAsync(10_000);});
    expect(screen.queryByText(/started via supervised chain/)).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/reconciled/i);
    expect(screen.getByRole("button",{name:/Start monitor/})).toBeEnabled();
  });
});

describe("System watcher observation",()=>{
  it("shows both watchers separately and retains raw evidence when the display expires",async()=>{
    vi.useFakeTimers();vi.setSystemTime(new Date("2026-10-11T04:00:00Z"));
    const stamp=new Date().toISOString();
    const evidence={lease_state:"ACTIVE",lease_last_check_at:stamp,last_check_at:stamp,
      watcher_pid:7,watcher_create_time:"2026-10-11T03:00:00Z",watched_pid:123,
      abort_triggered:false,abort_observed:0,abort_threshold:0};
    const fetcher=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({
      state:"RUNNING",running:true,pid:123,launcher:"agent",mode:"observe",
      observed_at:stamp,supervisor:{...evidence,state:"SUPERVISOR_ACTIVE"},
      sentinel:{...evidence,state:"SENTINEL_ACTIVE",watcher_pid:8},
    })}).mockImplementation(()=>new Promise(()=>{}));
    vi.stubGlobal("fetch",fetcher);render(<BotControl/>);
    await act(async()=>{await vi.advanceTimersByTimeAsync(1)});
    expect(screen.getByText("Supervisor").parentElement?.querySelector("strong")).toHaveTextContent("ACTIVE");
    expect(screen.getByText("Sentinel").parentElement?.querySelector("strong")).toHaveTextContent("ACTIVE");
    expect(screen.getByLabelText("sentinel evidence")).toHaveTextContent("Watcher PID8");
    await act(async()=>{await vi.advanceTimersByTimeAsync(91_000)});
    expect(screen.getByText("Supervisor").parentElement?.querySelector("strong")).toHaveTextContent("STALE");
    expect(screen.getByText("Sentinel").parentElement?.querySelector("strong")).toHaveTextContent("STALE");
    expect(screen.getByLabelText("sentinel evidence")).toHaveTextContent("SENTINEL_ACTIVE");
    expect(screen.getByRole("button",{name:/Start monitor/})).toBeDisabled();
  });
  it("clears earlier ACTIVE observations when the next status fetch fails",async()=>{
    vi.useFakeTimers();vi.setSystemTime(new Date("2026-10-11T04:00:00Z"));
    const stamp=new Date().toISOString();
    vi.stubGlobal("fetch",vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({
      state:"RUNNING",running:true,pid:123,launcher:"agent",mode:"observe",observed_at:stamp,
      supervisor:{state:"SUPERVISOR_ACTIVE",lease_state:"ACTIVE",lease_last_check_at:stamp,
        watcher_pid:7,watcher_create_time:"2026-10-11T03:00:00Z",watched_pid:123},
    })}).mockRejectedValue(new Error("offline")));
    render(<BotControl/>);
    await act(async()=>{await vi.advanceTimersByTimeAsync(1)});
    await act(async()=>{await vi.advanceTimersByTimeAsync(10_000)});
    expect(screen.getByText("Supervisor").parentElement?.querySelector("strong")).toHaveTextContent("UNKNOWN");
    expect(screen.getByText("Sentinel").parentElement?.querySelector("strong")).toHaveTextContent("UNKNOWN");
    expect(screen.getByRole("alert")).toHaveTextContent("STATUS_UNAVAILABLE");
  });
});