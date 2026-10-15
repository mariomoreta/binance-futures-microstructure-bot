import {afterEach,describe,expect,it,vi} from "vitest";
const run=vi.hoisted(()=>vi.fn());
vi.mock("node:child_process",()=>({spawnSync:run,default:{spawnSync:run}}));
import {parseLaunchPreset,runtimeStatus,runtimeAction} from "@/lib/runtime-control";
afterEach(()=>vi.resetAllMocks());
describe("Runtime BFF additive watcher contract",()=>{
  it("preserves both raw watcher blocks and adds its own observation time",()=>{
    const stamp="2026-10-11T04:00:00+00:00";
    run.mockReturnValue({status:0,stdout:JSON.stringify({state:"RUNNING",running:true,pid:123,mode:"observe",
      run_id:"probe-x",expected_end_at:"2026-10-11T04:02:00+00:00",elapsed_seconds:10,remaining_seconds:110,
      last_exit_code:null,last_exit_reason:null,last_exit_at:null,process_state:"owned",process_verified:true,preset:"brief",
      feed_health:"HEALTHY",latest_snapshot_age:5,
      supervisor:{state:"SUPERVISOR_STALE",lease_state:"STOPPED",watcher_pid:7,watched_pid:123,
        watcher_create_time:stamp,lease_last_check_at:stamp,abort_triggered:true,abort_threshold:0,abort_observed:0},
      sentinel:{state:"SENTINEL_STALE",lease_state:"ACTIVE",watcher_pid:8,watched_pid:123,
        watcher_create_time:stamp,lease_last_check_at:stamp,action_taken:"none",action_reason:"stale-supervision"}})});
    const x=runtimeStatus();
    expect(x.supervisor?.abort_threshold).toBe(0);expect(x.supervisor?.abort_triggered).toBe(true);
    expect(x.sentinel?.watcher_pid).toBe(8);expect(x.sentinel?.lease_state).toBe("ACTIVE");
    expect(x.sentinel?.action_reason).toBe("stale-supervision");
    expect(Number.isFinite(Date.parse(x.observed_at!))).toBe(true);
    expect(run.mock.calls[0]?.[1]?.[1]).toContain("status_readonly");
    expect(x.run_id).toBe("probe-x");expect(x.process_state).toBe("owned");expect(x.process_verified).toBe(true);
    expect(x.remaining_seconds).toBe(110);expect(x.feed_health).toBe("HEALTHY");expect(x.latest_snapshot_age).toBe(5);
  });
  it("keeps both watchers UNKNOWN when controller unavailable or blocks malformed",()=>{
    run.mockReturnValue({status:1,stdout:""});
    expect(runtimeStatus().sentinel?.state).toBe("SENTINEL_UNKNOWN");
    run.mockReturnValue({status:0,stdout:JSON.stringify({state:"COMPLETED",running:false,supervisor:[],sentinel:"ACTIVE"})});
    const x=runtimeStatus();expect(x.supervisor?.state).toBe("SUPERVISOR_UNKNOWN");
    expect(x.sentinel?.state).toBe("SENTINEL_UNKNOWN");expect(x.state).toBe("COMPLETED");
  });
});

describe("Pure runtime observation capability",()=>{
 it("returns UNKNOWN/error when pure capability is absent and never selects legacy status",()=>{
  run.mockReturnValue({status:0,stdout:JSON.stringify({error:"READ_ONLY_STATUS_REQUIRED"})});
  const x=runtimeStatus();expect(x.state).toBe("UNKNOWN");
  expect(x.error).toBe("READ_ONLY_STATUS_REQUIRED");
  expect(x.sentinel?.state).toBe("SENTINEL_UNKNOWN");
  const script=run.mock.calls[0]?.[1]?.[1];
  expect(script).toContain("status_readonly");expect(script).not.toContain("control.status()");
 });
  it("requires the same pure capability for stop preflight",()=>{
   run.mockReturnValue({status:0,stdout:JSON.stringify({error:"READ_ONLY_STATUS_REQUIRED"})});
   expect(runtimeAction("stop").data.error).toBe("READ_ONLY_STATUS_REQUIRED");
   expect(run.mock.calls[0]?.[1]?.[1]).not.toContain("control.status()");
  });
  it("rejects unknown presets without spawning anything",()=>{
   expect(parseLaunchPreset("nope")).toBeNull();
   expect(parseLaunchPreset("brief")).toBe("brief");
   expect(runtimeAction("start","nope").data.error).toBe("INVALID_PRESET");
   expect(run).not.toHaveBeenCalled();
  });
  it.each(["toString","constructor","__proto__","hasOwnProperty","valueOf","BRIEF","Brief",""])("rejects prototype-chain and off-list preset %j without spawning",preset=>{
   expect(parseLaunchPreset(preset)).toBeNull();
   expect(runtimeAction("start",preset).data.error).toBe("INVALID_PRESET");
  });
  it("rejects non-string presets without spawning",()=>{
   for(const v of [null,undefined,0,120,{},[],true])expect(parseLaunchPreset(v)).toBeNull();
   expect(run).not.toHaveBeenCalled();
  });
  it("validates the observation-10m preset and propagates its 600s duration",()=>{
    expect(parseLaunchPreset("observation-10m")).toBe("observation-10m");
    expect(parseLaunchPreset("brief")).toBe("brief");
    run.mockImplementation((...a:unknown[])=>{
      if(String((a[1] as string[])[1]).includes("launch_supervised_transaction"))
        return {status:0,stdout:JSON.stringify({outcome:"confirmed",reason:"verified",run_id:"r1"})};
      return {status:0,stdout:JSON.stringify({state:"STOPPED",running:false,pid:null,launcher:null,mode:"observe",supervisor:null,sentinel:null})};
    });
    const r=runtimeAction("start","observation-10m");
    expect(r.ok).toBe(true);
    const launch=run.mock.calls.filter(c=>String((c[1] as string[])[1]).includes("launch_supervised_transaction"));
    expect(launch).toHaveLength(1);
    const script=String(launch[0]?.[1]?.[1]);
    expect(script).toContain("duration_seconds=600");
    expect(script).toContain("preset='observation-10m'");
    expect(script).toContain("launcher='dashboard'");
  });
  it("launches only fixed allowlisted code on the green path",()=>{
   run.mockImplementation((...a:unknown[])=>{
    if(String((a[1] as string[])[1]).includes("launch_supervised_transaction"))
     return {status:0,stdout:JSON.stringify({outcome:"confirmed",reason:"verified",run_id:"r1"})};
    return {status:0,stdout:JSON.stringify({state:"STOPPED",running:false,pid:null,launcher:null,mode:"observe",supervisor:null,sentinel:null})};
   });
   const r=runtimeAction("start","standard");
   expect(r.ok).toBe(true);
   const launch=run.mock.calls.filter(c=>String((c[1] as string[])[1]).includes("launch_supervised_transaction"));
   expect(launch).toHaveLength(1);
   const script=String(launch[0]?.[1]?.[1]);
   expect(script).toContain("launch_supervised_transaction");
   expect(script).toContain("duration_seconds=3600");
   expect(script).toContain("preset='standard'");
   expect(script).toContain("launcher='dashboard'");
   expect(script).not.toContain("nope");
  });
  it("uses separate spawn budgets: fast status, bounded stop, 60s-covering start",()=>{
   run.mockImplementation((...a:unknown[])=>{
    const code=String((a[1] as string[])[1]);
    if(code.includes("launch_supervised_transaction"))
     return {status:0,stdout:JSON.stringify({outcome:"confirmed",run_id:"r1"})};
    return {status:0,stdout:JSON.stringify({state:"STOPPED",running:false,pid:null,launcher:null,mode:"observe",supervisor:null,sentinel:null})};
   });
   runtimeStatus();
   const statusTimeout=(run.mock.calls[0]?.[2] as {timeout:number}).timeout;
   expect(statusTimeout).toBe(4200);
   runtimeAction("start","brief");
   const launchTimeouts=run.mock.calls.filter(c=>String((c[1] as string[])[1]).includes("launch_supervised_transaction")).map(c=>(c[2] as {timeout:number}).timeout);
   expect(launchTimeouts).toEqual([65000]);
  });
});
