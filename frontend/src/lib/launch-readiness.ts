import {controllerLaunchCapability, runtimeStatus} from "@/lib/runtime-control";
import {historicalRead} from "@/lib/historical-db";
import {readStorageEvidence} from "@/lib/storage-preflight";
export type LaunchReadiness={ready:boolean;reason:string;checks:{name:string;status:"PASS"|"BLOCKED"|"UNKNOWN";detail:string}[]};
// Storage gate thresholds (documented, 2026-10-14): WARN_FREE_BYTES
// (1_000_000_000, from scripts/storage_preflight.py) is a WARNING floor,
// never a launch block. BLOCK needs the operational DB readable plus a
// hard free-space floor (256MB) or a measurable free value at all:
// below the hard floor (or unmeasurable) a retention-capped run cannot
// be guaranteed. Historical-DB absence degrades research coverage to
// UNKNOWN and stays advisory, never blocking.
export const STORAGE_BLOCK_FLOOR_BYTES=256_000_000;
export const STORAGE_WARN_FLOOR_BYTES=1_000_000_000;
export function launchReadiness():LaunchReadiness{
 const s=runtimeStatus();
 let dbOk=false;try{dbOk=historicalRead(db=>(db.prepare("PRAGMA quick_check").get() as {quick_check:string}|undefined)?.quick_check==="ok")}catch{}
 // NOTE: historicalRead opens data/microprobe.db (operational store);
 // the name is legacy. Historical research lives at
 // data/historical/historical.db (see historical-coverage.ts).
 const cap=controllerLaunchCapability();
 const capabilityOk=cap.present&&cap.enabled&&cap.verify_budget_s!==null&&cap.verify_budget_s>0&&cap.poll_s!==null&&cap.poll_s>=0;
 const capabilityDetail="present="+String(cap.present)+" enabled="+String(cap.enabled)+
  " verify_budget_s="+String(cap.verify_budget_s)+" poll_s="+String(cap.poll_s)+
  (capabilityOk?"; enabled capability with explicit preconditions":"; Start stays disabled until the controller reports enabled with a finite positive budget");
 const ev=(()=>{try{return readStorageEvidence()}catch{return null}})();
 let storageStatus:"PASS"|"BLOCKED"|"UNKNOWN"="UNKNOWN",storageDetail="Storage evidence unavailable";
 if(ev){
  const opBytes=ev.measured.operational_db.bytes,free=ev.measured.disk_free_bytes;
  const histBytes=ev.measured.historical_db.bytes;
  if(opBytes===null) {storageStatus="BLOCKED";storageDetail="Operational DB absent/unreadable: run state UNKNOWN; refusing launch";}
  else if(free===null){storageStatus="BLOCKED";storageDetail="Disk free UNKNOWN (statfs unavailable); refusing launch without a measurable floor";}
  else if(free<STORAGE_BLOCK_FLOOR_BYTES){storageStatus="BLOCKED";storageDetail="Disk free "+free+"B below hard floor "+STORAGE_BLOCK_FLOOR_BYTES+"B; refusing launch";}
  else{
   const warns=ev.alerts.map(a=>a.text).concat(ev.errors);
   const lowWarn=free<STORAGE_WARN_FLOOR_BYTES?["disk free "+free+"B below warning floor "+STORAGE_WARN_FLOOR_BYTES+"B (advisory, non-blocking)"]:[];
   const histWarn=histBytes===null?["historical DB absent/unreadable: research coverage UNKNOWN (advisory, non-blocking)"]:[];
   const notes=lowWarn.concat(histWarn).concat(warns);
   storageStatus="PASS";
   storageDetail="op="+opBytes+"B free="+free+"B"+(notes.length?"; advisory: "+notes.slice(0,4).join(" | "):"; no advisories");
  }
 }
 const checks=[
  {name:"Canonical controller",status:s.error?"UNKNOWN":"PASS",detail:s.error??"Canonical read-only status is accessible"},
  {name:"Registry reports no active run",status:s.running||["STARTING","STOPPING"].includes(s.state)?"BLOCKED":s.error||!['STOPPED','COMPLETED','FAILED','ABORTED'].includes(s.state)?"UNKNOWN":"PASS",detail:"Recorded state: "+s.state+(s.state==="ABORTED"?" (terminal; prior abort preserved in controller evidence)":"")},
  {name:"Operational database",status:dbOk?"PASS":"UNKNOWN",detail:dbOk?"SQLite quick_check passed (read-only)":"Read-only integrity check unavailable"},
  {name:"Observe-only mode",status:s.error||s.mode==="UNKNOWN"?"UNKNOWN":s.mode==="observe"?"PASS":"BLOCKED",detail:s.error?"Controller mode unavailable":"Controller reports "+s.mode},
  {name:"Atomic launch with persistent supervisor and sentinel",status:capabilityOk?"PASS":"BLOCKED",detail:capabilityDetail},
  {name:"Storage preflight",status:storageStatus,detail:storageDetail}
 ] as LaunchReadiness["checks"];
 const ready=checks.every(c=>c.status==="PASS");
 return {ready,reason:ready?"SUPERVISED_CHAIN_VERIFIED":capabilityOk?"READINESS_BLOCKED":"ATOMIC_SUPERVISED_LAUNCH_UNAVAILABLE",checks};
}
