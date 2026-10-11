"use client";
import {usePollingJson} from "@/lib/use-polling-json";
import {pricePath} from "@/lib/price-series";
import type {PriceSeries} from "@/lib/price-series";
export function VerifiedSparkline({symbol}:{symbol:string}){
 const {data:series,error}=usePollingJson<PriceSeries>("/api/v1/price-series/"+encodeURIComponent(symbol));
 const state=error?"UNAVAILABLE":series?.status==="AVAILABLE"?"READY":series?"UNAVAILABLE":"LOADING";
 const points=series?.points??[];
 if(state!=="READY"||points.length<3)return <span title={state==="LOADING"?"Checking persisted observations":"No verified 1h price history"} style={{fontSize:9,color:"var(--text-3)",border:"1px dashed var(--border)",borderRadius:3,padding:"5px 7px",display:"inline-block",minWidth:80,textAlign:"center"}}>{state==="LOADING"?"CHECKING":"NO SERIES"}</span>;
 const path=pricePath(points,90,30);
 return <svg role="img" aria-label={`Verified historical markPrice 1h for ${symbol}, ${points.length} observations`} viewBox="0 0 90 30" width="90" height="30"><path d={path} stroke="#36c6ef" strokeWidth="1.8" fill="none" strokeLinejoin="round"/></svg>;
}
