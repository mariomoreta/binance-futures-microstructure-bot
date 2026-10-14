import {DatabaseSync} from "node:sqlite";
const DB="C:/proyectos/binance-futures-microstructure-bot/data/microprobe.db";
export function withReadonlyDatabase<T>(path:string,fn:(db:DatabaseSync)=>T):T{
 const db=new DatabaseSync(path,{readOnly:true,timeout:1000});
 try{return fn(db)}finally{db.close()}
}
export const historicalRead=<T>(fn:(db:DatabaseSync)=>T):T=>withReadonlyDatabase(DB,fn);
export function historicalSnapshot(){
 return historicalRead(db=>{
  // Report the ACTUAL operational schema (9|10), never a hardcoded
  // label: readers admit both (system-evidence gate), and the live DB
  // is v10. Any other value fails closed (route maps to 503).
  const schemaValue=(db.prepare("SELECT value FROM persistence_meta WHERE key='schema_version'").get() as {value:unknown}|undefined)?.value;
  if(schemaValue!=="9"&&schemaValue!=="10")throw Error("UNSUPPORTED_SYSTEM_SCHEMA");
  const counts={symbols:Number((db.prepare("SELECT COUNT(DISTINCT symbol) n FROM prospective_outcomes").get() as {n:number}).n),setups:Number((db.prepare("SELECT COUNT(*) n FROM prospective_setups").get() as {n:number}).n),outcomes:Number((db.prepare("SELECT COUNT(*) n FROM prospective_outcomes").get() as {n:number}).n),samples:Number((db.prepare("SELECT COUNT(*) n FROM price_samples").get() as {n:number}).n)};
  const latest=db.prepare("SELECT candidate_key,symbol,horizon,observed_at_ms,mark_return_pct,detected_price,current_price,outcome_state,reason FROM prospective_outcomes ORDER BY observed_at_ms DESC LIMIT 50").all();
  const states=db.prepare("SELECT outcome_state state, COUNT(*) count FROM prospective_outcomes GROUP BY outcome_state ORDER BY outcome_state").all();
  const symbols=db.prepare("SELECT symbol,COUNT(*) count FROM prospective_outcomes GROUP BY symbol ORDER BY count DESC,symbol ASC LIMIT 20").all();
  const samples=db.prepare("SELECT symbol,COUNT(*) count,MAX(bucket_ms) latest_ms FROM price_samples GROUP BY symbol ORDER BY count DESC LIMIT 30").all();
  const setups=db.prepare("SELECT symbol,family,direction,market_state,detected_at_ms FROM prospective_setups ORDER BY detected_at_ms DESC LIMIT 15").all();
  const latestMs=Number((db.prepare("SELECT MAX(observed_at_ms) n FROM prospective_outcomes").get() as {n:number|null}).n??0);
  return {source:"PERSISTED_SQLITE_READONLY" as const,schema_version:(schemaValue==="10"?10:9) as 9|10,counts,latest_outcome_ms:latestMs,states,symbols,samples,setups,latest_outcomes:latest};
 });
}

export const canonicalReadTime=()=>new Date().toISOString();
