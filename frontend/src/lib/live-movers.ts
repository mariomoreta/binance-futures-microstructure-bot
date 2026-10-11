export type LiveMover={symbol:string;tier:string;price:number|null;change24hPct:number|null;quoteVolume24h:number|null;velocity1m:number|null;sampleAgeMs:number|null;deepEvidence:boolean;priceSource:"discovery"|"momentum"|"unknown";discoveryEvidence:boolean};
export type LiveMoversModel={source:"python-persisted"|"persisted-sqlite-readonly";generated_at:string;rows:LiveMover[];sources:{discovery:boolean;momentum:boolean};warnings:string[];alignment:"UNVERIFIED";freshness:"UNVERIFIED";availableFields:{discovery:string[];momentum:string[]}};
const obj=(x:unknown):Record<string,unknown>=>x!==null&&typeof x==="object"&&!Array.isArray(x)?x as Record<string,unknown>:{};
const number=(x:unknown):number|null=>typeof x==="number"&&Number.isFinite(x)?x:null;
const symbol=(x:unknown)=>typeof x==="string"&&/^[A-Z0-9]{2,32}$/.test(x)?x:null;
export function composeLiveMovers(discovery:unknown,momentum:unknown,now:number):LiveMoversModel{
 const d=obj(obj(discovery).discovery),m=obj(momentum);const rows=new Map<string,LiveMover>();
 const add=(s:string)=>{if(!rows.has(s))rows.set(s,{symbol:s,tier:"DISCOVERY",price:null,change24hPct:null,quoteVolume24h:null,velocity1m:null,sampleAgeMs:null,deepEvidence:false,priceSource:"unknown",discoveryEvidence:false});return rows.get(s)!};
 const tops=obj(d.tops);
 for(const category of ["gainers","losers","most_active"]){const items=tops[category];if(!Array.isArray(items))continue;for(const entry of items.slice(0,50)){const v=obj(entry),s=symbol(v.symbol);if(!s)continue;const r=add(s);r.discoveryEvidence=true;r.change24hPct=number(v.change_24h_pct);r.quoteVolume24h=number(v.quote_volume_24h);const dp=number(v.price);if(dp!==null&&dp>0){r.price=dp;r.priceSource="discovery";}}}
 const core=new Set(Array.isArray(d.core)?d.core.filter((v):v is string=>typeof v==="string"):[]);
 const hot=new Set(Array.isArray(d.hot_dynamic)?d.hot_dynamic.filter((v):v is string=>typeof v==="string"):[]);
 for(const s of core){const k=symbol(s);if(k)add(k).tier="CORE";}
 for(const s of hot){const k=symbol(s);if(k&&!core.has(k))add(k).tier="HOT PROPOSED";}
 const features=Array.isArray(m.features)?m.features:[];
 for(const entry of features.slice(0,100)){const v=obj(entry),s=symbol(v.symbol);if(!s)continue;const r=add(s);r.deepEvidence=true;r.tier=core.has(s)?"CORE":hot.has(s)?"HOT":"SUBSCRIBED";const mp=number(v.current_price);if(mp!==null&&mp>0){r.price=mp;r.priceSource="momentum"}r.sampleAgeMs=number(v.sample_age_ms);const vels=obj(obj(v.momentum).velocity);r.velocity1m=number(vels["1m"]);}
 return {source:"python-persisted",generated_at:new Date(now).toISOString(),rows:[...rows.values()].sort((a,b)=>a.symbol.localeCompare(b.symbol)).slice(0,200),sources:{discovery:Object.keys(d).length>0,momentum:features.length>0},alignment:"UNVERIFIED",freshness:"UNVERIFIED",availableFields:{discovery:["change24hPct","quoteVolume24h","discoveryPrice"],momentum:["momentumPrice","velocity1m","sampleAgeMs"]},warnings:["Read time is not observation time: generated_at records adapter response creation only.","Discovery and momentum snapshots do not provide a verified common as-of time.","Per-symbol price provenance is explicit; historical quote returns must not be attributed to momentum observations.","Deep coverage cannot be inferred from discovery-only records.","Observational research only: no executable trading outcomes."]};
}
