export type MoversTier = "CORE" | "HOT" | "DISCOVERY";
export type MoversCapability = "LIVE" | "WARMING" | "STALE" | "DEGRADED" | "UNKNOWN" | "DISCOVERY ONLY";
export type Direction = "ALL" | "GAINERS" | "LOSERS";
export type Interest = "ALL" | "EXTREME_GAINERS" | "EXTREME_LOSERS" | "ACCELERATING_UP" | "ACCELERATING_DOWN" | "HIGH_VOLUME";
export type SortKey = "symbol" | "change24hPct" | "quoteVolume24h" | "velocity1m" | "accel1m" | "sampleAgeMs";
export interface ProfessionalMover { symbol:string; tier:MoversTier; capability:MoversCapability; subscribed:boolean; price:number|null; change24hPct:number|null; quoteVolume24h:number|null; velocity1m:number|null; accel1m:number|null; sampleAgeMs:number|null; observedAt:string|null; source:string; }
export interface MoversFiltersState { query:string; direction:Direction; coverage:"ALL"|MoversTier; state:"ALL"|MoversCapability; interest:Interest; }
export const DEFAULT_FILTERS: MoversFiltersState = { query:"", direction:"ALL", coverage:"ALL", state:"ALL", interest:"ALL" };
export const DEMO_CRITERIA = {
  EXTREME_GAINERS:"24h change exists and is at least +20%", EXTREME_LOSERS:"24h change exists and is at most -15%",
  ACCELERATING_UP:"velocity and acceleration exist; both are positive", ACCELERATING_DOWN:"velocity and acceleration exist; both are negative",
  HIGH_VOLUME:"24h quote volume exists and is at least 100M USDT",
} as const;
export const normalizeSearch=(q:string)=>q.trim().toUpperCase();
const interestMatch=(r:ProfessionalMover,i:Interest)=> i==="ALL" ||
  (i==="EXTREME_GAINERS"&&r.change24hPct!==null&&r.change24hPct>=20) || (i==="EXTREME_LOSERS"&&r.change24hPct!==null&&r.change24hPct<=-15) ||
  (i==="ACCELERATING_UP"&&r.velocity1m!==null&&r.accel1m!==null&&r.velocity1m>0&&r.accel1m>0) ||
  (i==="ACCELERATING_DOWN"&&r.velocity1m!==null&&r.accel1m!==null&&r.velocity1m<0&&r.accel1m<0) ||
  (i==="HIGH_VOLUME"&&r.quoteVolume24h!==null&&r.quoteVolume24h>=100_000_000);
export function filterMovers(rows:readonly ProfessionalMover[],f:MoversFiltersState){const q=normalizeSearch(f.query);return rows.filter(r=>(!q||r.symbol.toUpperCase().includes(q))&&(f.direction==="ALL"||(f.direction==="GAINERS"?r.change24hPct!==null&&r.change24hPct>0:r.change24hPct!==null&&r.change24hPct<0))&&(f.coverage==="ALL"||r.tier===f.coverage)&&(f.state==="ALL"||r.capability===f.state)&&interestMatch(r,f.interest));}
export function sortMovers(rows:readonly ProfessionalMover[],key:SortKey,dir:"asc"|"desc"){return rows.map((r,i)=>({r,i})).sort((a,b)=>{const av=a.r[key],bv=b.r[key],am=av===null||(typeof av==="number"&&!Number.isFinite(av)),bm=bv===null||(typeof bv==="number"&&!Number.isFinite(bv));if(am!==bm)return am?1:-1;if(am&&bm)return a.i-b.i;const c=typeof av==="string"&&typeof bv==="string"?av.localeCompare(bv):Number(av)-Number(bv);return c===0?a.i-b.i:dir==="asc"?c:-c;}).map(x=>x.r);}
export function summarize(rows:readonly ProfessionalMover[]){const v=rows.filter(r=>r.change24hPct!==null),p=v.filter(r=>(r.change24hPct as number)>0),n=v.filter(r=>(r.change24hPct as number)<0);return{total:rows.length,deep:rows.filter(r=>r.subscribed).length,positive:p.length,negative:n.length,high:p.length?Math.max(...p.map(r=>r.change24hPct as number)):null,low:n.length?Math.min(...n.map(r=>r.change24hPct as number)):null};}
