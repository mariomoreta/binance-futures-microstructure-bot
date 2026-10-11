import {NextRequest,NextResponse} from "next/server";
import {historicalRead} from "@/lib/historical-db";
import {normalizePersistedSeries} from "@/lib/price-series";
export const dynamic="force-dynamic";export const runtime="nodejs";
export async function GET(_req:NextRequest,{params}:{params:Promise<{symbol:string}>}){
 const {symbol:raw}=await params;const symbol=raw.toUpperCase();if(!/^[A-Z0-9]{2,32}$/.test(symbol))return NextResponse.json({error:"INVALID_SYMBOL"},{status:400});
 try{const now=Date.now();const rows=historicalRead(db=>db.prepare("SELECT bucket_ms timestamp,price FROM price_samples WHERE symbol=? AND bucket_ms<=? ORDER BY bucket_ms DESC LIMIT 600").all(symbol,now));
  return NextResponse.json(normalizePersistedSeries(rows,symbol,now),{headers:{"Cache-Control":"no-store"}});
 }catch{return NextResponse.json({error:"CANONICAL_PRICE_SERIES_UNAVAILABLE"},{status:503,headers:{"Cache-Control":"no-store"}})}
}
