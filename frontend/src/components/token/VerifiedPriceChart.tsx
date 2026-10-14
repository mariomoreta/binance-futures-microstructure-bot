"use client";
import {useState} from "react";
import {usePollingJson} from "@/lib/use-polling-json";
import {pricePath} from "@/lib/price-series";
import {PRICE_RANGES,type PriceRange,type RangePriceSeries} from "@/lib/price-ranges";
export function VerifiedPriceChart({symbol}:{symbol:string}){
 const [range,setRange]=useState<PriceRange>("1h"),url="/api/v1/price-series/"+encodeURIComponent(symbol)+"?range="+range;
 const {data,error}=usePollingJson<RangePriceSeries>(url),pts=data?.points??[],usable=pts.length>=3&&data?.status==="AVAILABLE";
 return <div className="v2-price-chart" aria-label="Verified historical mark-price chart">
 <div className="v2-price-controls"><label>Historical range <select aria-label="Historical price range" value={range} onChange={e=>setRange(e.target.value as PriceRange)}>{Object.keys(PRICE_RANGES).map(r=><option key={r} value={r}>{r}</option>)}</select></label><span>MARK PRICE / SQLITE / NOT LIVE</span>
 <a href={url+"&format=json"} download>JSON</a><a href={url+"&format=csv"} download>CSV</a></div>
 {data?<p className="v2-muted" data-testid="price-coverage">Requested: {range} / {data.raw_count} valid samples / {data.display_count} displayed / Partial or unverified coverage{data.downsampled?" / DOWNSAMPLED":""}{data.truncated?" / READ LIMIT REACHED":""} / {data.gap_count} recorded gaps</p>:null}
 {usable?<svg viewBox="0 0 580 142" width="100%" role="img" aria-label={`Persisted mark-price ${range} for ${symbol}, ${pts.length} observations`}><path d="M12 17H568M12 71H568M12 125H568" fill="none" stroke="#24394a" strokeDasharray="3 5"/><path d={pricePath(pts,580,142)} fill="none" stroke="#31bff9" strokeWidth="2" strokeLinejoin="round" vectorEffect="non-scaling-stroke"/></svg>:<div role="status" className="v2-price-empty">{error?"Canonical price-series source unavailable. No chart fabricated.":data?"INSUFFICIENT HISTORY / at least three valid samples required.":"Checking saved price samples..."}</div>}
 {data?<div className="v2-price-meta"><span>Observed: {data.observed_start??"UNKNOWN"} / {data.observed_end??"UNKNOWN"}</span><span>Requested start: {data.requested_start??"UNKNOWN"} / anchor: last retained valid sample</span><span>Read: {data.read_at} / read time is not observation time</span><span>Partial/unverified coverage; saved mark-price samples, not fills. Gaps remain disconnected. Downloads contain this same bounded sampled series.</span></div>:null}
 </div>;
}
