import {controllerHasLaunch, runtimeStatus} from "@/lib/runtime-control";
import {historicalRead} from "@/lib/historical-db";
export type LaunchReadiness={ready:boolean;reason:string;checks:{name:string;status:"PASS"|"BLOCKED"|"UNKNOWN";detail:string}[]};
export function launchReadiness():LaunchReadiness{
 const s=runtimeStatus();
 let dbOk=false;try{dbOk=historicalRead(db=>(db.prepare("PRAGMA quick_check").get() as {quick_check:string}|undefined)?.quick_check==="ok")}catch{}
 const atomic=controllerHasLaunch();
 const checks=[
  {name:"Canonical controller",status:s.error?"UNKNOWN":"PASS",detail:s.error??"Canonical read-only status is accessible"},
  {name:"Registry reports no active run",status:s.running||["STARTING","STOPPING"].includes(s.state)?"BLOCKED":s.error||!['STOPPED','COMPLETED','FAILED'].includes(s.state)?"UNKNOWN":"PASS",detail:"Recorded state: "+s.state},
  {name:"Operational database",status:dbOk?"PASS":"UNKNOWN",detail:dbOk?"SQLite quick_check passed (read-only)":"Read-only integrity check unavailable"},
  {name:"Observe-only mode",status:s.error||s.mode==="UNKNOWN"?"UNKNOWN":s.mode==="observe"?"PASS":"BLOCKED",detail:s.error?"Controller mode unavailable":"Controller reports "+s.mode},
  {name:"Atomic launch with persistent supervisor and sentinel",status:atomic?"PASS":"BLOCKED",detail:atomic?"Canonical transactional launch verified present; Start requires readiness-green plus confirmation plus preset":"No verified canonical transactional launch API. Start remains disabled; never leave an unsupervised run."}
 ] as LaunchReadiness["checks"];
 const ready=checks.every(c=>c.status==="PASS");
 return {ready,reason:ready?"SUPERVISED_CHAIN_VERIFIED":atomic?"READINESS_BLOCKED":"ATOMIC_SUPERVISED_LAUNCH_UNAVAILABLE",checks};
}
