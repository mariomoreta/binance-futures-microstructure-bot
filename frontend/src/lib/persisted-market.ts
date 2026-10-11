import type {ProfessionalMover} from "./movers-domain";
import type {TokenDetail,MarketState,Direction} from "./token-detail";
export const PERSISTED_SOURCE="PERSISTED_SQLITE_READONLY" as const;
type Obj=Record<string,unknown>;
export const object=(x:unknown):Obj=>x&&typeof x==="object"&&!Array.isArray(x)?x as Obj:{};
export const finite=(x:unknown):number|null=>typeof x==="number"&&Number.isFinite(x)?x:null;
export const timestamp=(x:unknown,now:number):number|null=>{const n=finite(x);return n!==null&&n>0&&n<8640000000000000&&n<=now?n:null};
export const iso=(x:number|null)=>x===null?null:new Date(x).toISOString();
export const age=(x:number|null,now:number)=>x===null?null:now-x;
export const freshness=(x:number|null,now:number):"STALE"|"UNKNOWN"=>x!==null&&now-x>300000?"STALE":"UNKNOWN";
const strings=(x:unknown):string[]=>Array.isArray(x)?x.filter((v):v is string=>typeof v==="string").slice(0,40).map(v=>v.slice(0,500)):[];
export type StoredFeature={symbol:string;updated_ms:number;feature_json:string};
export type MarketInput={discovery:{updated_ms:number;payload_json:string}|null;features:Record<string,StoredFeature[]>;counts:{setups:number;outcomes:number;samples:number};latestSampleMs:number|null};
export function parseStored(x:string):Obj{try{return object(JSON.parse(x))}catch{return {}}}
export function persistedMarket(input:MarketInput,now:number){
 const d=parseStored(input.discovery?.payload_json??""),dt=timestamp(d.generated_at_ms,now),tops=object(d.tops);
 const discovery=new Map<string,Obj>();
 for(const group of ["gainers","losers","most_active"]){const list=tops[group];if(!Array.isArray(list))continue;for(const raw of list.slice(0,50)){const x=object(raw);if(typeof x.symbol==="string"&&/^[A-Z0-9]{2,32}$/.test(x.symbol))discovery.set(x.symbol,x)}}
 const maps:Record<string,Map<string,Obj>>={};
 for(const [table,rows] of Object.entries(input.features)){maps[table]=new Map();for(const row of rows.slice(0,500)){const x=parseStored(row.feature_json);if(/^[A-Z0-9]{2,32}$/.test(row.symbol)&&x.symbol===row.symbol&&timestamp(row.updated_ms,now)!==null)maps[table].set(row.symbol,x)}}
 const returns=maps.return_features??new Map<string,Obj>(),core=new Set(dt===null?[]:strings(d.core));
 const symbols=new Set([...discovery.keys(),...Object.values(maps).flatMap(m=>[...m.keys()])]);
 const rows:ProfessionalMover[]=[...symbols].sort().slice(0,500).map(symbol=>{
  const scan=discovery.get(symbol)??{},r=returns.get(symbol)??{},momentum=object(r.momentum);
  const rt=timestamp(r.source_timestamp_ms,now),deepTime=timestamp(momentum.as_of_ms,now);
  const hasScan=dt!==null&&discovery.has(symbol),hasDeep=rt!==null;
  const scanPrice=hasScan?finite(scan.price):null,deepPrice=hasDeep?finite(r.current_price):null;
  const takeDeep=deepPrice!==null&&deepPrice>0&&(scanPrice===null||dt===null||rt!>=dt);
  const price=takeDeep?deepPrice:scanPrice!==null&&scanPrice>0?scanPrice:null;
  const pt=price===null?null:takeDeep?rt:dt,observed=pt??deepTime??(hasScan?dt:null);
  return {symbol,tier:core.has(symbol)?"CORE":r.tier==="HOT"?"HOT":"DISCOVERY",capability:freshness(observed,now),
   subscribed:hasDeep,price,change24hPct:hasScan?finite(scan.change_24h_pct):null,quoteVolume24h:hasScan?finite(scan.quote_volume_24h):null,
   velocity1m:deepTime===null?null:finite(object(momentum.velocity)["1m"]),accel1m:deepTime===null?null:finite(object(momentum.acceleration)["1m"]),
   sampleAgeMs:age(pt,now),observedAt:iso(pt),source:PERSISTED_SOURCE,
   discoveryAsOf:hasScan?iso(dt):null,featureAsOf:iso(deepTime),priceSource:takeDeep?typeof r.source==="string"?r.source:"return_features":"discovery_snapshots"};
 });
 return {schema_version:1 as const,source:PERSISTED_SOURCE,readAt:new Date(now).toISOString(),available:true,discoveryAsOf:iso(dt),
  eligibleCount:dt===null?null:finite(d.eligible_count),rows,counts:input.counts,latestSampleAsOf:iso(timestamp(input.latestSampleMs,now)),features:maps};
}
export type PersistedMarket=ReturnType<typeof persistedMarket>;
export function recordedToken(m:PersistedMarket,symbol:string,now:number):TokenDetail{
 const row=m.rows.find(r=>r.symbol===symbol),feature=(table:string)=>m.features[table]?.get(symbol)??{};
 const r=feature("return_features"),f=feature("flow_features"),b=feature("book_features"),oi=feature("oi_features"),structure=feature("structure_features"),state=feature("state_features");
 const st=timestamp(state.observed_at_ms,now),metric=(label:string,value:number|null,unit:string,table:string,x:Obj)=>{const t=timestamp(x.as_of_ms,now)??timestamp(object(x.momentum).as_of_ms,now);return {label,value:t===null||value===null?null:(value!==0&&Math.abs(value)<0.0001?value.toExponential(3):value.toLocaleString("en-US",{maximumFractionDigits:6}))+unit,context:table+" · "+(iso(t)??"UNKNOWN")+" · "+freshness(t,now)}};
 const states:MarketState[]=["NORMAL","IGNITION","EXPANSION","EXHAUSTION","REVERSAL"],dirs:Direction[]=["UP","DOWN","NONE"];
 return {symbol,market:"Binance USD-M Futures",featureSections:featureSections(m,symbol,now),source:PERSISTED_SOURCE,priceSource:row?.priceSource??"UNKNOWN",discoveryAsOf:row?.discoveryAsOf??null,evaluationAsOf:iso(st),
  tier:row?.tier??"DISCOVERY",capability:row?.capability??"UNKNOWN",price:row?.price??null,change24h:row?.change24hPct??null,asOf:row?.observedAt??null,
  state:st!==null&&states.includes(state.state as MarketState)?state.state as MarketState:"UNKNOWN",direction:st!==null&&dirs.includes(state.direction as Direction)?state.direction as Direction:"UNKNOWN",
  ruleVersion:st!==null&&typeof state.rules_version==="string"?state.rules_version:null,previousState:st!==null&&states.includes(object(state.transition).previous_state as MarketState)?object(state.transition).previous_state as MarketState:null,
  evidence:st===null?[]:strings(state.evidence_for),counterevidence:st===null?[]:strings(state.evidence_against),
  missing:[...strings(state.missing_features),...(!row?["No canonical observations for this symbol"]:[]),"Current feed liveness is not established by stored records"],
  metrics:[
   metric("1m Return",finite(object(r.returns)["1m"])===null?null:finite(object(r.returns)["1m"])!*100,"%", "return_features",r),
   metric("Velocity 1m",row?.velocity1m??null," /s","return_features",r),
   metric("Aggressive flow",finite(object(object(f.horizons)["1m"]).signed_delta)," USDT","flow_features",f),
   metric("Order book spread",finite(object(b.book).spread_bps)," bps","book_features",b),
   metric("Open interest change 1m",finite(object(object(oi.horizons)["1m"]).delta_pct)===null?null:finite(object(object(oi.horizons)["1m"]).delta_pct)!*100,"%","oi_features",oi),
   metric("Volatility 1m",finite(object(object(structure.volatility)["1m"]).realized_vol)===null?null:finite(object(object(structure.volatility)["1m"]).realized_vol)!*100,"%","structure_features",structure)
  ]};
}

export function featureSections(m:PersistedMarket,symbol:string,now:number){
 const f=(table:string)=>m.features[table]?.get(symbol)??{};
 const n=(value:unknown,unit="",scale=1)=>{const x=finite(value);return x===null?null:(x!==0&&Math.abs(x*scale)<0.0001?(x*scale).toExponential(3):(x*scale).toLocaleString("en-US",{maximumFractionDigits:8}))+unit};
 const windows=["1m","3m","5m","15m","1h"],r=f("return_features"),flow=f("flow_features"),book=f("book_features"),oi=f("oi_features"),structure=f("structure_features");
 const section=(title:string,table:string,x:Obj,rows:{label:string;value:string|null}[])=>{
  const t=timestamp(x.as_of_ms,now)??timestamp(object(x.momentum).as_of_ms,now);return {title,source:table,asOf:iso(t),freshness:freshness(t,now),rows:rows.map(row=>({...row,value:t===null?null:row.value}))};
 };
 return [
 section("Returns and momentum","return_features",r,windows.flatMap(h=>[{label:h+" return",value:n(object(r.returns)[h],"%",100)},{label:h+" velocity",value:n(object(object(r.momentum).velocity)[h]," /s")},{label:h+" acceleration",value:n(object(object(r.momentum).acceleration)[h]," /s²")}])),
 section("Aggressive flow and activity","flow_features",flow,windows.flatMap(h=>{const x=object(object(flow.horizons)[h]),baseline=object(object(flow.baselines)[h]);return [{label:h+" signed delta",value:n(x.signed_delta," USDT")},{label:h+" buy share",value:n(x.buy_pct,"%")},{label:h+" sell share",value:n(x.sell_pct,"%")},{label:h+" volume z-score",value:n(baseline.z_score)}]})),
 section("Book and depth","book_features",book,[{label:"Best bid",value:n(object(book.book).best_bid," USDT")},{label:"Best ask",value:n(object(book.book).best_ask," USDT")},{label:"Spread",value:n(object(book.book).spread_bps," bps")},{label:"Notional imbalance",value:n(object(book.book).imbalance_notional,"% of signed balance",100)}]),
 section("Open interest","oi_features",oi,[{label:"Recorded OI",value:n(oi.current_oi," base units")},...windows.map(h=>({label:h+" OI change",value:n(object(object(oi.horizons)[h]).delta_pct,"%",100)}))]),
 section("VWAP and volatility","structure_features",structure,windows.flatMap(h=>[{label:h+" VWAP displacement",value:n(object(object(structure.vwap)[h]).displacement_pct,"%")},{label:h+" realized volatility",value:n(object(object(structure.volatility)[h]).realized_vol,"%",100)}])),
 ];
}
