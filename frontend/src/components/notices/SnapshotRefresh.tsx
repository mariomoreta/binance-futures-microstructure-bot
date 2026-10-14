"use client";
import {useEffect,useState} from "react";
import {useRouter} from "next/navigation";
import {usePollingJson} from "@/lib/use-polling-json";
export function SnapshotRefresh({readAt,available,pollUrl="/api/v1/market-snapshot",sourceLabel="Canonical SQLite"}:{readAt:string;available:boolean;pollUrl?:string;sourceLabel?:string}){
 const router=useRouter(),[paused,setPaused]=useState(false);
 const {data,error}=usePollingJson<unknown>(pollUrl);
 useEffect(()=>{if(data)router.refresh()},[data,router]);
 useEffect(()=>{const changed=()=>setPaused(document.visibilityState==="hidden");changed();document.addEventListener("visibilitychange",changed);return()=>document.removeEventListener("visibilitychange",changed)},[]);
 return <p role="status" className="v2-muted" style={{fontSize:12}}>{sourceLabel} · read only · {available&&!error?"read "+readAt:"SOURCE UNAVAILABLE — no substitute data"} · {paused?"refresh paused while hidden":"refresh every 15 s; bounded retry on failure"} · Read time is not observation time.</p>;
}
