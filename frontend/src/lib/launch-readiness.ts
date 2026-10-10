import {runtimeStatus} from "@/lib/runtime-control";
import {historicalRead} from "@/lib/historical-db";
export type LaunchReadiness={ready:false;reason:string;checks:{name:string;status:"PASS"|"BLOCKED"|"UNKNOWN";detail:string}[]};
export function launchReadiness():LaunchReadiness{
 const s=runtimeStatus();
 let dbOk=false;try{dbOk=historicalRead(db=>(db.prepare("PRAGMA quick_check").get() as {quick_check:string}|undefined)?.quick_check==="ok")}catch{}
 return {ready:false,reason:"ATOMIC_SUPERVISED_LAUNCH_UNAVAILABLE",checks:[
  {name:"Canonical controller",status:s.error?"UNKNOWN":"PASS",detail:s.error??"Canonical status() is accessible"},
  {name:"No concurrent active run",status:s.running||["STARTING","STOPPING"].includes(s.state)?"BLOCKED":s.error||!['STOPPED','COMPLETED','FAILED'].includes(s.state)?"UNKNOWN":"PASS",detail:"Current state: "+s.state},
  {name:"Operational database",status:dbOk?"PASS":"UNKNOWN",detail:dbOk?"SQLite quick_check passed (read-only)":"Read-only integrity check unavailable"},
  {name:"Observe-only mode",status:s.error||s.mode==="UNKNOWN"?"UNKNOWN":s.mode==="observe"?"PASS":"BLOCKED",detail:s.error?"Controller mode unavailable":"Controller reports "+s.mode},
  {name:"Atomic launch with persistent supervisor and sentinel",status:"BLOCKED",detail:"No verified canonical transactional launch API. Start remains disabled; never leave an unsupervised run."}
 ]};
}

