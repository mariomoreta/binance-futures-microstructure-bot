import {NextResponse} from "next/server";
import {normalizeOpportunities} from "@/lib/opportunities-api";
export const dynamic="force-dynamic";
export const runtime="nodejs";
const ORIGIN="http://127.0.0.1:8091";
export async function GET(){
 try{
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),2500);
  let response:Response;
  try{response=await fetch(ORIGIN+"/api/opportunities",{cache:"no-store",signal:controller.signal,headers:{accept:"application/json"}})}finally{clearTimeout(timeout)}
  if(!response.ok)return NextResponse.json({schema_version:"1",error:{code:"UPSTREAM_UNAVAILABLE",message:"Python opportunity data unavailable"}},{status:503,headers:{"Cache-Control":"no-store"}});
  const length=response.headers.get("content-length");if(length&&Number(length)>2_000_000)throw new Error("upstream too large");
  const body=await response.text();if(body.length>2_000_000)throw new Error("upstream too large");
  const parsed=normalizeOpportunities(JSON.parse(body),Date.now());
  return NextResponse.json(parsed,{headers:{"Cache-Control":"no-store"}});
 }catch{return NextResponse.json({schema_version:"1",error:{code:"UPSTREAM_UNAVAILABLE",message:"Python opportunity data unavailable"}},{status:503,headers:{"Cache-Control":"no-store"}})}
}
