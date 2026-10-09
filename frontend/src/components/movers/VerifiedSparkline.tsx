"use client";
import {useEffect,useState} from "react";
import type {PriceSeries} from "@/lib/price-series";
export function VerifiedSparkline({symbol}:{symbol:string}){
 const [state,setState]=useState<"LOADING"|"UNAVAILABLE"|"READY">("LOADING");
 const [series,setSeries]=useState<PriceSeries|null>(null);
 useEffect(()=>{const controller=new AbortController();
 fetch("/api/v1/price-series/"+encodeURIComponent(symbol),{cache:"no-store",signal:controller.signal})
 .then(async r=>{if(!r.ok)throw Error("Unavailable");return r.json() as Promise<PriceSeries>})
 .then(data=>{if(controller.signal.aborted)return;setSeries(data);setState(data.status==="AVAILABLE"&&data.points.length>=3?"READY":"UNAVAILABLE")})
 .catch(()=>{if(!controller.signal.aborted)setState("UNAVAILABLE")});
 return()=>controller.abort();
 },[symbol]);
 const points=series?.points??[];
 if(state!=="READY"||points.length<3)return <span title={state==="LOADING"?"Checking persisted observations":"No verified 1h price history"} style={{fontSize:9,color:"var(--text-3)",border:"1px dashed var(--border)",borderRadius:3,padding:"5px 7px",display:"inline-block",minWidth:80,textAlign:"center"}}>{state==="LOADING"?"CHECKING":"NO SERIES"}</span>;
 const prices=points.map(p=>p.price),lo=Math.min(...prices),hi=Math.max(...prices),spread=hi-lo||Math.max(hi*.0001,1e-9);
 const path=points.map((p,i)=>(i?"L":"M")+(2+i/(points.length-1)*86).toFixed(1)+","+(27-(p.price-lo)/spread*23).toFixed(1)).join(" ");
 return <svg role="img" aria-label={`Verified historical markPrice 1h for ${symbol}, ${points.length} observations`} viewBox="0 0 90 30" width="90" height="30"><path d={path} stroke="#36c6ef" strokeWidth="1.8" fill="none" strokeLinejoin="round"/></svg>;
}
