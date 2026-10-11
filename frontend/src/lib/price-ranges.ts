import type {PricePoint,PriceSeries} from "./price-series";
export const PRICE_RANGES={"5m":300000,"15m":900000,"1h":3600000,"4h":14400000,"24h":86400000} as const;
export type PriceRange=keyof typeof PRICE_RANGES;
export const RAW_PRICE_LIMIT=10000,DISPLAY_PRICE_LIMIT=1200;
export const isPriceRange=(x:string):x is PriceRange=>Object.hasOwn(PRICE_RANGES,x);
export type RangePriceSeries=PriceSeries&{schema_version:3;range:PriceRange;read_at:string;window_anchor:"LAST_RETAINED_SAMPLE";requested_start:string|null;observed_start:string|null;observed_end:string|null;raw_count:number;display_count:number;read_limit:number;display_limit:number;truncated:boolean;downsampled:boolean;gap_count:number;coverage:"PARTIAL_OR_UNVERIFIED"};
export function normalizeRangeSeries(raw:unknown,symbol:string,range:PriceRange,now:number,overflow=false):RangePriceSeries{
 const rows=Array.isArray(raw)?raw.slice(0,RAW_PRICE_LIMIT):[],map=new Map<number,number>();
 for(const row of rows){if(!row||typeof row!=="object")continue;const p=row as Record<string,unknown>;if(typeof p.timestamp==="number"&&Number.isSafeInteger(p.timestamp)&&p.timestamp>0&&p.timestamp<=now&&typeof p.price==="number"&&Number.isFinite(p.price)&&p.price>0)map.set(p.timestamp,p.price)}
 const all=[...map].sort((a,b)=>a[0]-b[0]),end=all.at(-1)?.[0]??null,start=end===null?null:end-PRICE_RANGES[range];
 const kept=all.filter(([t])=>start!==null&&t>=start).map(([timestamp,price])=>({timestamp,price}));
 const gaps=[0];for(let i=1;i<kept.length;i++)gaps[i]=gaps[i-1]!+Number(kept[i]!.timestamp-kept[i-1]!.timestamp>60000);
 const size=Math.min(DISPLAY_PRICE_LIMIT,kept.length),indices=Array.from({length:size},(_,i)=>size<=1?0:Math.round(i*(kept.length-1)/(size-1)));
 const points:PricePoint[]=indices.map((index,i)=>({...kept[index]!,gapBefore:i===0?false:gaps[index]!>gaps[indices[i-1]!]!}));
 const truncated=overflow||(Array.isArray(raw)&&raw.length>RAW_PRICE_LIMIT),downsampled=points.length<kept.length;
 return {schema_version:3,symbol,range,source:"markPrice",window_anchor:"LAST_RETAINED_SAMPLE",read_at:new Date(now).toISOString(),generated_at:end===null?null:new Date(end).toISOString(),requested_start:start===null?null:new Date(start).toISOString(),observed_start:kept.length?new Date(kept[0]!.timestamp).toISOString():null,observed_end:end===null?null:new Date(end).toISOString(),points,status:points.length>=3?"AVAILABLE":"INSUFFICIENT_HISTORY",raw_count:kept.length,display_count:points.length,read_limit:RAW_PRICE_LIMIT,display_limit:DISPLAY_PRICE_LIMIT,truncated,downsampled,gap_count:gaps.at(-1)??0,coverage:"PARTIAL_OR_UNVERIFIED",note:"Saved historical samples anchored to last retained valid mark-price observation, not the current window. Coverage is partial or unverified; no interpolation. Export contains the same bounded sampled series as the chart."};
}
export function priceCsv(data:RangePriceSeries){
 const header=["schema_version","symbol","source","range","window_anchor","read_at","requested_start","observed_start","observed_end","coverage","raw_count","display_count","truncated","downsampled","gap_count","timestamp_ms","timestamp_utc","mark_price_usdt","gap_before"];
 const meta=[3,data.symbol,data.source,data.range,data.window_anchor,data.read_at,data.requested_start,data.observed_start,data.observed_end,data.coverage,data.raw_count,data.display_count,data.truncated,data.downsampled,data.gap_count];
 const quote=(x:unknown)=>'"'+String(x??"").replaceAll('"','""')+'"';
 const rows=data.points.length?data.points.map(p=>[...meta,p.timestamp,new Date(p.timestamp).toISOString(),p.price,p.gapBefore??false]):[[...meta,null,null,null,null]];
 return [header.map(quote).join(","),...rows.map(row=>row.map(quote).join(","))].join("\r\n")+"\r\n";
}
