import {NextRequest,NextResponse} from "next/server";
import {normalizePriceSeries} from "@/lib/price-series";
export const dynamic="force-dynamic";export const runtime="nodejs";
export async function GET(_req:NextRequest,{params}:{params:Promise<{symbol:string}>}){
 const {symbol:raw}=await params;const symbol=raw.toUpperCase();
 if(!/^[A-Z0-9]{2,32}$/.test(symbol))return NextResponse.json({error:"INVALID_SYMBOL"},{status:400});
 try{const c=new AbortController();const t=setTimeout(()=>c.abort(),2500);let res:Response;try{res=await fetch("http://127.0.0.1:8091/api/symbol/"+symbol+"/price?range=1h",{signal:c.signal,cache:"no-store"})}finally{clearTimeout(t)}
 if(!res.ok)return NextResponse.json({error:"PRICE_SERIES_UNAVAILABLE"},{status:503,headers:{"Cache-Control":"no-store"}});
 const size=res.headers.get("content-length");if(size&&Number(size)>1000000)throw Error("oversize");const text=await res.text();if(text.length>1000000)throw Error("oversize");
 const x=JSON.parse(text);if(x?.symbol!==symbol||x?.source!=="markPrice"||x?.range!=="1h")throw Error("source mismatch");
 return NextResponse.json(normalizePriceSeries(x,symbol,Date.now()),{headers:{"Cache-Control":"no-store"}});
 }catch{return NextResponse.json({error:"PRICE_SERIES_UNAVAILABLE"},{status:503,headers:{"Cache-Control":"no-store"}})}
}
