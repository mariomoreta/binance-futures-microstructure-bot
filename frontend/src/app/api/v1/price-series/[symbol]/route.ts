import {NextRequest,NextResponse} from "next/server";
import {historicalRead} from "@/lib/historical-db";
import {readPriceRange} from "@/lib/price-range-db";
import {isPriceRange,priceCsv} from "@/lib/price-ranges";
export const dynamic="force-dynamic";export const runtime="nodejs";
export async function GET(req:NextRequest,{params}:{params:Promise<{symbol:string}>}){
 const {symbol:raw}=await params,symbol=raw.toUpperCase(),range=req.nextUrl.searchParams.get("range")??"1h",format=req.nextUrl.searchParams.get("format");
 const headers={"Cache-Control":"no-store"};
 if(!/^[A-Z0-9]{2,32}$/.test(symbol))return NextResponse.json({error:"INVALID_SYMBOL"},{status:400,headers});
 if(!isPriceRange(range))return NextResponse.json({error:"INVALID_RANGE"},{status:400,headers});
 if(format!==null&&format!=="json"&&format!=="csv")return NextResponse.json({error:"INVALID_FORMAT"},{status:400,headers});
 try{const now=Date.now(),series=historicalRead(db=>readPriceRange(db,symbol,range,now));
  if(format==="csv")return new NextResponse(priceCsv(series),{headers:{...headers,"Content-Type":"text/csv; charset=utf-8","Content-Disposition":'attachment; filename="'+symbol+"-"+range+'-historical.csv"',"X-Content-Type-Options":"nosniff"}});
  return NextResponse.json(series,{headers:format==="json"?{...headers,"Content-Disposition":'attachment; filename="'+symbol+"-"+range+'-historical.json"'}:headers});
 }catch{return NextResponse.json({error:"CANONICAL_PRICE_SERIES_UNAVAILABLE"},{status:503,headers})}
}
