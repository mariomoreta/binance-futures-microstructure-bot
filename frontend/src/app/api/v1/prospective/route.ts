import {NextResponse} from "next/server";
import {normalizeProspective} from "@/lib/prospective-api";
export const dynamic="force-dynamic";
export const runtime="nodejs";
export async function GET(){
 try{
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),2500);
  let upstream:Response;
  try{upstream=await fetch("http://127.0.0.1:8091/api/prospective",{cache:"no-store",signal:controller.signal,headers:{accept:"application/json"}})}finally{clearTimeout(timer)}
  if(!upstream.ok)return NextResponse.json({error:"UPSTREAM_UNAVAILABLE"},{status:503,headers:{"Cache-Control":"no-store"}});
  const length=upstream.headers.get("content-length");
  if(length&&Number(length)>2_000_000)throw new Error("Oversize");
  const content=await upstream.text();if(content.length>2_000_000)throw new Error("Oversize");
  const parsed=JSON.parse(content) as unknown;
  if((parsed as {schema_version?:unknown})?.schema_version!==9)throw new Error("Unexpected schema");
  return NextResponse.json(normalizeProspective(parsed),{headers:{"Cache-Control":"no-store"}});
 }catch{return NextResponse.json({error:"UPSTREAM_UNAVAILABLE"},{status:503,headers:{"Cache-Control":"no-store"}})}
}
