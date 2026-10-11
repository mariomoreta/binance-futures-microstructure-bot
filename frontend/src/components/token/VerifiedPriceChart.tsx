"use client";
import {usePollingJson} from "@/lib/use-polling-json";
import {pricePath} from "@/lib/price-series";
import type {PriceSeries} from "@/lib/price-series";
export function VerifiedPriceChart({symbol}:{symbol:string}){const {data,error}=usePollingJson<PriceSeries>("/api/v1/price-series/"+encodeURIComponent(symbol)),failure=error!==null;
 const pts=data?.points??[];const usable=pts.length>=3&&data?.status==="AVAILABLE";
 const path=usable?pricePath(pts,580,142):"";
 return <div style={{display:"grid",gap:12,minHeight:190,marginTop:12}} aria-label="Verified mark-price 1h chart">
 <div style={{display:"flex",justifyContent:"space-between",gap:10,alignItems:"center",fontSize:11,color:"var(--text-3)"}}><span>MARK PRICE / HISTORICAL 1H / SQLITE</span><span>{usable?pts.length+" observed points":"NO VERIFIED SERIES"}</span></div>
 {usable?<><svg viewBox="0 0 580 142" width="100%" role="img" aria-label={`Persisted mark-price series for ${symbol}, ${pts.length} observations`} style={{background:"var(--bg-1)",border:"1px solid var(--border)",borderRadius:7}}><path d="M12 17H568M12 71H568M12 125H568" fill="none" stroke="#24394a" strokeDasharray="3 5"/><path d={path} fill="none" stroke="#31bff9" strokeWidth="2" strokeLinejoin="round" vectorEffect="non-scaling-stroke"/></svg><span style={{fontSize:11,color:"var(--text-3)"}}>First: {new Date(pts[0]!.timestamp).toISOString()} · Last: {new Date(pts[pts.length-1]!.timestamp).toISOString()} · Stored historical samples, not a live quote / gaps over 60s are not connected</span></>:<div role="status" style={{display:"grid",placeItems:"center",background:"var(--bg-1)",border:"1px dashed var(--border)",borderRadius:7,padding:24,textAlign:"center",fontSize:12,color:"var(--text-3)"}}>{failure?"Canonical price-series source unavailable. No chart fabricated.":data?"INSUFFICIENT HISTORY — at least three valid samples required.":"Checking verified price samples…"}</div>}
 </div>}
