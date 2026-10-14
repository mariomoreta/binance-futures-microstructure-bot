import {describe,expect,it,vi} from "vitest";
vi.mock("@/lib/runtime-control",()=>({runtimeStatus:()=>({state:"RUNNING"})}));
vi.mock("@/lib/historical-db",()=>({historicalRead:()=>{throw Error("unavailable")}}));
import {projectRecordedTelemetry,diagnostics} from "@/lib/runtime-diagnostics";
const now=1800000000000;
const row=(quality:unknown={},clock:unknown={})=>({
 timestamp:now/1000,runtime_seconds:0,
 data_quality_json:JSON.stringify(quality),clock_sync_json:JSON.stringify(clock),
});
describe("Recorded diagnostic evidence",()=>{
 it("recent timestamp never proves a run association",()=>{
  expect(projectRecordedTelemetry(row(),now)?.provenance).toBe("RECENT_RECORDED_SAMPLE");
 });
 it("future timestamps stay future and do not clamp age",()=>{
  const r=projectRecordedTelemetry({...row(),timestamp:(now+10000)/1000},now);
  expect(r?.provenance).toBe("FUTURE_RECORDED_SAMPLE");expect(r?.ageSeconds).toBe(-10);
 });
 it("labels samples older than 90 seconds historical",()=>{
  expect(projectRecordedTelemetry({...row(),timestamp:(now-90001)/1000},now)?.provenance).toBe("HISTORICAL_ONLY");
 });
 it("keeps observed zero and negative clock offsets",()=>{
  const r=projectRecordedTelemetry(row({activeStreams:0,missingStreams:[],timestampRejected:0},{clockOffsetMs:-2.5}),now);
  expect(r?.active).toBe(0);expect(r?.missing).toBe(0);expect(r?.rejected).toBe(0);expect(r?.clockOffsetMs).toBe(-2.5);
 });
 it("preserves absent counters as unknown",()=>{
  const r=projectRecordedTelemetry(row(),now);
  expect(r?.missing).toBeNull();expect(r?.rejected).toBeNull();expect(r?.clockOffsetMs).toBeNull();
 });
 it("rejects arrays and partially malformed counter totals",()=>{
  expect(projectRecordedTelemetry(row({timestampRejected:[1,2]}),now)?.rejected).toBeNull();
  expect(projectRecordedTelemetry(row({reconnections:{a:2,b:null}}),now)?.reconnects).toBeNull();
 });
 it("sums complete finite counter maps",()=>{
  expect(projectRecordedTelemetry(row({reconnections:{market:2,public:3}}),now)?.reconnects).toBe(5);
 });
 it("rejects invalid dates and malformed metric objects",()=>{
  expect(projectRecordedTelemetry({...row(),timestamp:NaN},now)).toBeNull();
  expect(projectRecordedTelemetry({...row(),data_quality_json:"["},now)?.active).toBeNull();
  expect(projectRecordedTelemetry(row([]),now)?.active).toBeNull();
 });
 it("unavailable database preserves registry state without invented telemetry",()=>{
  expect(diagnostics()).toEqual({process:{state:"RUNNING"},snapshot:null});
 });
});
