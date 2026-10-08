export type ProspectiveOutcome={candidate_key:string;symbol:string;horizon:string;outcome_state:string;observed_at_ms:number|null;mark_return_pct:number|null;detected_price:number|null;current_price:number|null;reason:string};
export type ProspectiveModel={schema_version:9;source:"python-marketprobe";generated_at:string|null;status:string;setup_count:number|null;outcome_count:number|null;drops:number|null;errors:number|null;latest_outcomes:ProspectiveOutcome[];note:string};
const obj=(x:unknown):Record<string,unknown>=>x&&typeof x==="object"&&!Array.isArray(x)?x as Record<string,unknown>:{};
const str=(x:unknown):string=>typeof x==="string"?x.slice(0,500):"UNKNOWN";
const num=(x:unknown):number|null=>typeof x==="number"&&Number.isFinite(x)?x:null;
export function normalizeProspective(raw:unknown):ProspectiveModel{
 const root=obj(raw),p=obj(root.prospective);
 const rawRows=Array.isArray(p.latest_outcomes)?p.latest_outcomes.slice(0,50):[];
 const latest_outcomes=rawRows.map(x=>{const r=obj(x);return {candidate_key:str(r.candidate_key),symbol:str(r.symbol),horizon:str(r.horizon),outcome_state:str(r.outcome_state),observed_at_ms:num(r.observed_at_ms),mark_return_pct:num(r.mark_return_pct),detected_price:num(r.detected_price),current_price:num(r.current_price),reason:str(r.reason)}});
 return {schema_version:9,source:"python-marketprobe",generated_at:typeof root.generated_at==="string"?root.generated_at:null,status:str(p.state),setup_count:num(p.setup_count),outcome_count:num(p.outcome_count),drops:num(p.drops),errors:num(p.errors),latest_outcomes,note:"Prospective mark-price research only, not executable P&L or predictive validation."};
}
