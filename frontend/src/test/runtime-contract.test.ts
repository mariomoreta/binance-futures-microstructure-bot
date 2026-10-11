import {afterEach,describe,expect,it,vi} from "vitest";
const run=vi.hoisted(()=>vi.fn());
vi.mock("node:child_process",()=>({spawnSync:run,default:{spawnSync:run}}));
import {runtimeStatus} from "@/lib/runtime-control";
afterEach(()=>vi.resetAllMocks());
describe("Runtime BFF additive watcher contract",()=>{
  it("preserves both raw watcher blocks and adds its own observation time",()=>{
    const stamp="2026-10-11T04:00:00+00:00";
    run.mockReturnValue({status:0,stdout:JSON.stringify({state:"RUNNING",running:true,pid:123,mode:"observe",
      supervisor:{state:"SUPERVISOR_STALE",lease_state:"STOPPED",watcher_pid:7,watched_pid:123,
        watcher_create_time:stamp,lease_last_check_at:stamp,abort_triggered:true,abort_threshold:0,abort_observed:0},
      sentinel:{state:"SENTINEL_STALE",lease_state:"ACTIVE",watcher_pid:8,watched_pid:123,
        watcher_create_time:stamp,lease_last_check_at:stamp,action_taken:"none",action_reason:"stale-supervision"}})});
    const x=runtimeStatus();
    expect(x.supervisor?.abort_threshold).toBe(0);expect(x.supervisor?.abort_triggered).toBe(true);
    expect(x.sentinel?.watcher_pid).toBe(8);expect(x.sentinel?.lease_state).toBe("ACTIVE");
    expect(x.sentinel?.action_reason).toBe("stale-supervision");
    expect(Number.isFinite(Date.parse(x.observed_at!))).toBe(true);
    expect(run.mock.calls[0]?.[1]?.[1]).toContain("control.status()");
  });
  it("keeps both watchers UNKNOWN when controller unavailable or blocks malformed",()=>{
    run.mockReturnValue({status:1,stdout:""});
    expect(runtimeStatus().sentinel?.state).toBe("SENTINEL_UNKNOWN");
    run.mockReturnValue({status:0,stdout:JSON.stringify({state:"COMPLETED",running:false,supervisor:[],sentinel:"ACTIVE"})});
    const x=runtimeStatus();expect(x.supervisor?.state).toBe("SUPERVISOR_UNKNOWN");
    expect(x.sentinel?.state).toBe("SENTINEL_UNKNOWN");expect(x.state).toBe("COMPLETED");
  });
});
