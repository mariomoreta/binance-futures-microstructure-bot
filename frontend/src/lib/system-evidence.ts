import type {DatabaseSync} from "node:sqlite";
import {historicalRead} from "./historical-db";
type Span={first_ms:number|null;last_ms:number|null};
type Bucket={label:string;count:number};
export type SystemEvidenceData={
 schema_version:1;source:"CANONICAL_SQLITE_READONLY";available:true;read_at:string;
 persistence:{schema:9|10;allocated_bytes:number|null;telemetry_rows:number;price_rows:number;last_telemetry_ms:number|null;last_price_ms:number|null};
 universe:{updated_ms:number|null;core:number|null;hot_dynamic:number|null;hot_subscribed:number|null;eligible:number|null;unverified_test_detail_rows:number};
 research:{setups:number;outcomes:number;complete_outcomes:number;latest_setup_ms:number|null;latest_outcome_ms:number|null;opportunity_events:number;state_transitions:number;universe_events:number};
 classifier:{records:number;span:Span;states:Bucket[];versions:string[];versions_truncated:boolean};
 opportunities:{records:number;span:Span;lifecycles:Bucket[];versions:string[];versions_truncated:boolean};
};
export type SystemEvidenceResult=SystemEvidenceData|{schema_version:1;source:"CANONICAL_SQLITE_READONLY";available:false;read_at:string;error:"SYSTEM_EVIDENCE_UNAVAILABLE"};
const n=(x:unknown)=>typeof x==="number"&&Number.isFinite(x)?x:null;
const timestamp=(x:unknown)=>{const value=n(x);return value!==null&&Number.isFinite(new Date(value).getTime())?value:null};
const natural=(x:unknown)=>{const value=n(x);return value!==null&&Number.isInteger(value)&&value>=0?value:null};
function object(x:unknown):Record<string,unknown>{
 try {const v:unknown=JSON.parse(String(x));return v&&typeof v==="object"&&!Array.isArray(v)?v as Record<string,unknown>:{}}catch{return {}}
}
const symbols=(x:unknown)=>Array.isArray(x)&&x.every(s=>typeof s==="string"&&s.length>0)?new Set(x).size:null;
export function systemUtc(x:number|null){return x===null?"UNKNOWN":new Date(x).toISOString()}
export function readSystemEvidence(db:DatabaseSync,readAt=new Date().toISOString()):SystemEvidenceData{
 db.exec("BEGIN");
 try{
  const schemaValue=db.prepare("SELECT value FROM persistence_meta WHERE key='schema_version'").get()?.value;
  if(schemaValue!=="9"&&schemaValue!=="10")throw Error("UNSUPPORTED_SYSTEM_SCHEMA");
  const schema:9|10=schemaValue==="10"?10:9;
  const have=new Set((db.prepare("SELECT name FROM sqlite_master WHERE type='table'").all() as {name:unknown}[]).map(r=>String(r.name)));
  const required=["telemetry_snapshots","price_samples","discovery_snapshots","universe_events","prospective_setups","prospective_outcomes","opportunity_events","state_transitions","state_features","opportunity_candidates"];
  const missing=required.filter(t=>!have.has(t));
  if(missing.length)throw Error("UNSUPPORTED_SYSTEM_SCHEMA: absent tables "+missing.join(","));
  const count=(table:string)=>Number(db.prepare("SELECT COUNT(*) n FROM "+table).get()!.n);
  const max=(table:string,column:string,scale=1)=>{const value=n(db.prepare("SELECT MAX("+column+") n FROM "+table).get()?.n);return timestamp(value===null?null:value*scale)};
  const span=(table:string):Span=>{const r=db.prepare("SELECT MIN(updated_ms) first_ms,MAX(updated_ms) last_ms FROM "+table).get()!;return {first_ms:timestamp(r.first_ms),last_ms:timestamp(r.last_ms)}};
  const groups=(table:string,column:string,key:string,allowed:string[]):Bucket[]=>{
   const values=allowed.map(x=>"'"+x+"'").join(",");
   const field="json_extract("+column+", '$."+key+"')";
   const label="CASE WHEN json_valid("+column+") THEN CASE WHEN "+field+" IN ("+values+") THEN "+field+" ELSE 'UNKNOWN' END ELSE 'UNKNOWN' END";
   return db.prepare("SELECT "+label+" label,COUNT(*) n FROM "+table+" GROUP BY label ORDER BY n DESC,label").all().map(r=>({label:String(r.label),count:Number(r.n)}));
  };
  const versions=(table:string,column:string,key:string)=>{
   const field="json_extract("+column+", '$."+key+"')";
   const rows=db.prepare("SELECT DISTINCT CASE WHEN json_valid("+column+") THEN CASE WHEN json_type("+column+", '$."+key+"')='text' AND length("+field+") BETWEEN 1 AND 64 THEN "+field+" ELSE 'UNKNOWN' END ELSE 'UNKNOWN' END v FROM "+table+" ORDER BY v LIMIT 21").all();
   return {versions:rows.slice(0,20).map(r=>String(r.v)),versions_truncated:rows.length>20};
  };
  const discovery=db.prepare("SELECT updated_ms,CASE WHEN length(payload_json)<=1048576 THEN payload_json END payload_json FROM discovery_snapshots WHERE id=0").get();
  const d=object(discovery?.payload_json);
  const pageSize=n(db.prepare("PRAGMA page_size").get()?.page_size),pages=n(db.prepare("PRAGMA page_count").get()?.page_count);
  const result:SystemEvidenceData={schema_version:1,source:"CANONICAL_SQLITE_READONLY",available:true,read_at:readAt,
   persistence:{schema,allocated_bytes:pageSize===null||pages===null?null:pageSize*pages,telemetry_rows:count("telemetry_snapshots"),price_rows:count("price_samples"),last_telemetry_ms:max("telemetry_snapshots","timestamp",1000),last_price_ms:max("price_samples","bucket_ms")},
   universe:{updated_ms:timestamp(discovery?.updated_ms),core:symbols(d.core),hot_dynamic:symbols(d.hot_dynamic),hot_subscribed:symbols(d.hot_subscribed),eligible:natural(d.eligible_count),unverified_test_detail_rows:Number(db.prepare("SELECT COUNT(*) n FROM universe_events WHERE detail='test'").get()!.n)},
   research:{setups:count("prospective_setups"),outcomes:count("prospective_outcomes"),complete_outcomes:Number(db.prepare("SELECT COUNT(*) n FROM prospective_outcomes WHERE outcome_state='COMPLETE'").get()!.n),latest_setup_ms:max("prospective_setups","detected_at_ms"),latest_outcome_ms:max("prospective_outcomes","observed_at_ms"),opportunity_events:count("opportunity_events"),state_transitions:count("state_transitions"),universe_events:count("universe_events")},
   classifier:{records:count("state_features"),span:span("state_features"),states:groups("state_features","feature_json","state",["UNKNOWN","NORMAL","IGNITION","EXPANSION","EXHAUSTION","REVERSAL"]),...versions("state_features","feature_json","rules_version")},
   opportunities:{records:count("opportunity_candidates"),span:span("opportunity_candidates"),lifecycles:groups("opportunity_candidates","candidate_json","lifecycle",["UNKNOWN","DETECTED","WATCHING","ACTIVE_RESEARCH","INVALIDATED","EXPIRED"]),...versions("opportunity_candidates","candidate_json","rule_version")}
  };
  db.exec("COMMIT");return result;
 }catch(e){db.exec("ROLLBACK");throw e}
}
export function canonicalSystemEvidence():SystemEvidenceResult{
 const read_at=new Date().toISOString();
 try{return historicalRead(db=>readSystemEvidence(db,read_at))}
 catch{return {schema_version:1,source:"CANONICAL_SQLITE_READONLY",available:false,read_at,error:"SYSTEM_EVIDENCE_UNAVAILABLE"}}
}
