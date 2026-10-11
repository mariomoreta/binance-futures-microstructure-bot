export type PricePoint={timestamp:number;price:number};
export type PriceSeries={schema_version:1|2;window_anchor?:"LAST_RETAINED_SAMPLE";read_at?:string;symbol:string;range:"1h";source:"markPrice";generated_at:string|null;points:PricePoint[];status:"AVAILABLE"|"INSUFFICIENT_HISTORY";note:string};
export function normalizePriceSeries(raw:unknown,symbol:string,now:number):PriceSeries{
 const x=raw&&typeof raw==="object"&&!Array.isArray(raw)?raw as Record<string,unknown>:{};
 const rows=Array.isArray(x.points)?x.points.slice(0,1000):[];
 const pointMap=new Map<number,number>();
 for(const row of rows){if(!row||typeof row!=="object")continue;const p=row as Record<string,unknown>;if(typeof p.timestamp!=="number"||!Number.isSafeInteger(p.timestamp)||p.timestamp>now||p.timestamp<now-3600000||typeof p.price!=="number"||!Number.isFinite(p.price)||p.price<=0)continue;pointMap.set(p.timestamp,p.price)}
 const points=[...pointMap].sort((a,b)=>a[0]-b[0]).slice(-600).map(([timestamp,price])=>({timestamp,price}));
 return {schema_version:1,symbol,range:"1h",source:"markPrice",generated_at:typeof x.generated_at==="string"?x.generated_at:null,points,status:points.length>=3?"AVAILABLE":"INSUFFICIENT_HISTORY",note:"Persisted markPrice observations, not executable fills, not necessarily current. Time-window and source-gated."};
}

export function normalizePersistedSeries(raw:unknown,symbol:string,now:number):PriceSeries{
 const rows=Array.isArray(raw)?raw:[],valid=rows.filter(x=>x&&typeof x==="object").map(x=>x as Record<string,unknown>).filter(x=>typeof x.timestamp==="number"&&Number.isSafeInteger(x.timestamp)&&x.timestamp>0&&x.timestamp<=now&&typeof x.price==="number"&&Number.isFinite(x.price)&&x.price>0);
 const end=valid.length?Math.max(...valid.map(x=>x.timestamp as number)):now;
 const model=normalizePriceSeries({points:valid,generated_at:valid.length?new Date(end).toISOString():null},symbol,end);
 return {...model,schema_version:2,window_anchor:"LAST_RETAINED_SAMPLE",read_at:new Date(now).toISOString(),note:"Canonical SQLite price_samples: historical 1h anchored to last retained valid sample, not the current hour. Gaps over 60s are not connected."};
}
export function pricePath(points:PricePoint[],width:number,height:number):string{
 if(points.length<3)return "";
 const lo=Math.min(...points.map(p=>p.price)),hi=Math.max(...points.map(p=>p.price)),span=hi-lo||Math.max(hi*.0001,1e-10),start=points[0]!.timestamp,duration=Math.max(1,points[points.length-1]!.timestamp-start);
 return points.map((p,i)=>(i&&p.timestamp-points[i-1]!.timestamp<=60000?"L":"M")+(2+(p.timestamp-start)/duration*(width-4)).toFixed(2)+","+(height-2-(p.price-lo)/span*(height-4)).toFixed(2)).join(" ");
}
