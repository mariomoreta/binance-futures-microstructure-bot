"use client";
import {useEffect,useState} from "react";
export function usePollingJson<T>(url:string,retryKey=0){
 const [state,setState]=useState<{url:string;data:T|null;error:string|null;loading:boolean}>({url,data:null,error:null,loading:true});
 useEffect(()=>{let disposed=false,busy=false,failures=0;let timer:ReturnType<typeof setTimeout>|undefined,controller:AbortController|undefined;
  const schedule=()=>{clearTimeout(timer);if(!disposed&&document.visibilityState!=="hidden")timer=setTimeout(run,Math.min(60000,15000*2**failures))};
  const run=async()=>{if(disposed||busy||document.visibilityState==="hidden")return;busy=true;controller=new AbortController();const timeout=setTimeout(()=>controller?.abort(),5000);
   try{const res=await fetch(url,{cache:"no-store",signal:controller.signal});if(!res.ok)throw Error("unavailable");const value=await res.json() as T;if(controller.signal.aborted)throw Error("timeout");if(!disposed){setState({url,data:value,error:null,loading:false});failures=0}}
   catch{if(!disposed){setState({url,data:null,error:"Canonical source unavailable — no substitute data",loading:false});failures=Math.min(2,failures+1)}}
   finally{clearTimeout(timeout);busy=false;schedule()}};
  const visibility=()=>{clearTimeout(timer);if(document.visibilityState!=="hidden")void run()};
  void run();document.addEventListener("visibilitychange",visibility);
  return()=>{disposed=true;clearTimeout(timer);controller?.abort();document.removeEventListener("visibilitychange",visibility)};
 },[url,retryKey]);
 return state.url===url?state:{data:null,error:null,loading:true};
}
