import {historicalRead,canonicalReadTime} from "./historical-db";
import {parseStored,object} from "./persisted-market";
import {searchQuery,searchSymbols} from "./symbol-search";
export function canonicalSearch(raw:string){
 const {query,valid}=searchQuery(raw),readAt=canonicalReadTime();
 if(!valid)return {query,valid,available:true,readAt,symbols:[] as string[],truncated:false};
 try{return historicalRead(db=>{
  const tables=["return_features","flow_features","book_features","oi_features","structure_features","state_features","price_samples","prospective_setups","prospective_outcomes","opportunity_candidates"];
  const union=tables.map(t=>"SELECT symbol FROM "+t).join(" UNION ");
  const rows=db.prepare("SELECT symbol FROM ("+union+") WHERE symbol LIKE ? ORDER BY (symbol = ?) DESC, (symbol LIKE ?) DESC, symbol LIMIT 51").all("%"+query+"%",query,query+"%");
  const d=db.prepare("SELECT payload_json FROM discovery_snapshots WHERE id=0").get();
  const tops=object(parseStored(String(d?.payload_json??"")).tops),discovery:string[]=[];
  for(const key of ["gainers","losers","most_active"]){const group=tops[key];if(Array.isArray(group))for(const r of group.slice(0,50)){const s=object(r).symbol;if(typeof s==="string")discovery.push(s)}}
  const result=searchSymbols([...rows.map(r=>String(r.symbol)),...discovery],query);
  return {query,valid,available:true,readAt,...result,truncated:result.truncated||rows.length===51};
 })}catch{return {query,valid,available:false,readAt,symbols:[] as string[],truncated:false}}
}
