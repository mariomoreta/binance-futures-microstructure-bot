import {describe,expect,it} from "vitest";
import {isTerminalRunState,normalizeWatcher,processDisplay,processDisplayFresh,watcherDisplayState,utcTimestamp} from "@/lib/supervision";
const now=Date.parse("2026-10-11T04:00:00Z");
const observed="2026-10-11T04:00:00Z";
const valid={
  state:"SUPERVISOR_ACTIVE",lease_state:"ACTIVE",lease_last_check_at:observed,
  last_check_at:observed,watcher_pid:7,watcher_create_time:"2026-10-11T03:00:00+00:00",
  watched_pid:123,abort_triggered:false,abort_threshold:0,abort_observed:0,
};
describe("Watcher contract and observation freshness",()=>{
  it("preserves explicit false, numeric zero and textual sentinel thresholds",()=>{
    const e=normalizeWatcher({...valid,abort_threshold:"<=120s",action_taken:"none"},"supervisor");
    expect(e.abort_triggered).toBe(false);expect(e.abort_observed).toBe(0);
    expect(e.abort_threshold).toBe("<=120s");expect(e.action_taken).toBe("none");
  });
  it.each([null,[],true,"ACTIVE"])("rejects non-object evidence %s",value=>{
    expect(normalizeWatcher(value,"sentinel").state).toBe("SENTINEL_UNKNOWN");
  });
  it("keeps malformed raw evidence inspectable but never ACTIVE",()=>{
    const e=normalizeWatcher({...valid,lease_last_check_at:"bad"},"supervisor");
    expect(e.lease_last_check_at).toBe("bad");
    expect(watcherDisplayState("supervisor",e,123,observed,now)).toBe("SUPERVISOR_STALE");
  });
  it("accepts only complete canonical ACTIVE evidence for this run",()=>{
    expect(watcherDisplayState("supervisor",normalizeWatcher(valid,"supervisor"),123,observed,now)).toBe("SUPERVISOR_ACTIVE");
    const e=normalizeWatcher({...valid,state:"SENTINEL_ACTIVE"},"sentinel");
    expect(watcherDisplayState("sentinel",e,123,observed,now)).toBe("SENTINEL_ACTIVE");
  });
  it.each([
    {state:"SUPERVISOR_STALE"},
    {lease_state:"STOPPED"},
    {watched_pid:999},
    {watcher_pid:0},
    {watcher_create_time:null},
    {lease_last_check_at:"2026-10-11T04:00:01Z"},
    {lease_last_check_at:"2026-10-11T03:58:29Z"},
    {lease_last_check_at:"2026-10-11T04:00:00"},
  ])("rejects contradictory ACTIVE evidence %j",patch=>{
    expect(watcherDisplayState("supervisor",normalizeWatcher({...valid,...patch},"supervisor"),123,observed,now)).toBe("SUPERVISOR_STALE");
  });
  it("ages a cached ACTIVE observation without receiving another response",()=>{
    const e=normalizeWatcher(valid,"supervisor");
    expect(watcherDisplayState("supervisor",e,123,observed,now+90_000)).toBe("SUPERVISOR_ACTIVE");
    expect(watcherDisplayState("supervisor",e,123,observed,now+90_001)).toBe("SUPERVISOR_STALE");
  });
  it.each([undefined,"bad","2026-10-11T04:00:01Z","2026-10-11T03:58:29Z"])("rejects unavailable/future/expired observation %s",stamp=>{
    expect(watcherDisplayState("supervisor",normalizeWatcher(valid,"supervisor"),123,stamp,now)).toBe("SUPERVISOR_STALE");
  });
  it("does not fabricate an established lease from missing evidence",()=>{
    expect(watcherDisplayState("sentinel",undefined,123,observed,now)).toBe("SENTINEL_UNKNOWN");
    expect(normalizeWatcher({watcher_pid:Infinity,abort_observed:NaN},"sentinel").abort_observed).toBeNull();
  });
  it("distinguishes owned, gone, replaced and unknown identities",()=>{
    expect(processDisplay("owned",true)).toBe("OWNED-LIVE");
    expect(processDisplay("gone",false)).toBe("NOT-LIVE (gone)");
    expect(processDisplay("replaced",false)).toBe("REPLACED (run replaced)");
    expect(processDisplay("unknown",false)).toBe("UNVERIFIED (unknown)");
    // Unknown is never NOT-LIVE, and owned without verification never claims live.
    expect(processDisplay("unknown",false)).not.toContain("NOT-LIVE");
    expect(processDisplay("owned",false)).not.toBe("OWNED-LIVE");
    expect(processDisplay(null,false)).toBe("UNVERIFIED (unknown)");
  });
  it("treats only explicit terminal states as closed; UNKNOWN never confirms a close",()=>{
    for(const s of ["STOPPED","COMPLETED","FAILED","ABORTED"])expect(isTerminalRunState(s)).toBe(true);
    for(const s of ["RUNNING","STARTING","STOPPING","UNKNOWN","LOADING","",null,undefined])expect(isTerminalRunState(s)).toBe(false);
  });
  it("expires verification when the observation is stale, pending or failed",()=>{
    const stamp="2026-10-11T04:00:00Z";
    expect(processDisplayFresh("owned",true,stamp,now)).toBe("OWNED-LIVE");
    expect(processDisplayFresh("owned",true,stamp,now+30_000)).toBe("OWNED-LIVE");
    expect(processDisplayFresh("owned",true,stamp,now+30_001)).toBe("UNVERIFIED (expired)");
    expect(processDisplayFresh("gone",false,stamp,now+31_000)).toBe("UNVERIFIED (expired)");
    expect(processDisplayFresh("owned",true,undefined,now)).toBe("UNVERIFIED (expired)");
    expect(processDisplayFresh("owned",true,"bad",now)).toBe("UNVERIFIED (expired)");
  });
  it("requires a valid UTC calendar timestamp",()=>{
    expect(utcTimestamp("2026-02-30T04:00:00Z")).toBeNull();
    expect(utcTimestamp("2026-10-11T04:00:00+01:00")).toBeNull();
    expect(utcTimestamp("2026-10-11T04:00:00.123456+00:00")).toBe(now+123);
  });
});
