import {NextResponse} from "next/server";
import {normalizeProspective} from "@/lib/prospective-api";
import {historicalSnapshot} from "@/lib/historical-db";
export const dynamic="force-dynamic";export const runtime="nodejs";
const headers={"Cache-Control":"no-store"};
export async function GET(){
 try{
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),1800);
  try{
   const response=await fetch("http://127.0.0.1:8091/api/prospective",{cache:"no-store",signal:controller.signal,headers:{accept:"application/json"}});
   if(response.ok){const length=response.headers.get("content-length");if(length&&Number(length)>2_000_000)throw Error("Oversize");const body=await response.text();if(body.length>2_000_000)throw Error("Oversize");const raw=JSON.parse(body) as {schema_version?:unknown};if(raw.schema_version!==9)throw Error("Schema mismatch");return NextResponse.json(normalizeProspective(raw),{headers});}
  }finally{clearTimeout(timer)}
 }catch{}
 try{
  const h=historicalSnapshot();
  return NextResponse.json({schema_version:9,source:"persisted-sqlite-readonly",generated_at:h.latest_outcome_ms?new Date(h.latest_outcome_ms).toISOString():null,status:"HISTORICAL_ONLY",setup_count:h.counts.setups,outcome_count:h.counts.outcomes,drops:null,errors:null,completed:null,pending:null,insufficient:null,in_grace:null,latest_outcomes:h.latest_outcomes,note:"Read-only persisted data fallback. Not live, not freshly verified, no lifetime emission counters."},{headers});
 }catch{return NextResponse.json({error:"UPSTREAM_AND_HISTORY_UNAVAILABLE"},{status:503,headers})}
}
