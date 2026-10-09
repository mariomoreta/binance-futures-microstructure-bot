export type PricePoint={timestamp:number;price:number};
export type PriceSeries={schema_version:1;symbol:string;range:"1h";source:"markPrice";generated_at:string|null;points:PricePoint[];status:"AVAILABLE"|"INSUFFICIENT_HISTORY";note:string};
export function normalizePriceSeries(raw:unknown,symbol:string,now:number):PriceSeries{
 const x=raw&&typeof raw==="object"&&!Array.isArray(raw)?raw as Record<string,unknown>:{};
 const rows=Array.isArray(x.points)?x.points.slice(0,1000):[];
 const pointMap=new Map<number,number>();
 for(const row of rows){if(!row||typeof row!=="object")continue;const p=row as Record<string,unknown>;if(typeof p.timestamp!=="number"||!Number.isSafeInteger(p.timestamp)||p.timestamp>now||p.timestamp<now-3600000||typeof p.price!=="number"||!Number.isFinite(p.price)||p.price<=0)continue;pointMap.set(p.timestamp,p.price)}
 const points=[...pointMap].sort((a,b)=>a[0]-b[0]).slice(-600).map(([timestamp,price])=>({timestamp,price}));
 return {schema_version:1,symbol,range:"1h",source:"markPrice",generated_at:typeof x.generated_at==="string"?x.generated_at:null,points,status:points.length>=3?"AVAILABLE":"INSUFFICIENT_HISTORY",note:"Persisted markPrice observations, not executable fills, not necessarily current. Time-window and source-gated."};
}
