import {NextResponse} from "next/server";
import {historicalCoverage,historyFilter} from "@/lib/historical-coverage";
export const runtime="nodejs";export const dynamic="force-dynamic";
const headers={"Cache-Control":"no-store"};
export async function GET(req:Request){
 const q=new URL(req.url).searchParams;
 if(q.getAll("symbol").length>1||q.getAll("definition").length>1)return NextResponse.json({error:"INVALID_HISTORY_FILTER"},{status:400,headers});
 let filter;try{filter=historyFilter(q.get("symbol")??"",q.get("definition")??"")}catch{return NextResponse.json({error:"INVALID_HISTORY_FILTER"},{status:400,headers})}
 try{return NextResponse.json(historicalCoverage(filter),{headers})}catch{return NextResponse.json({error:"HISTORICAL_COVERAGE_UNAVAILABLE",source:"HISTORICAL_SQLITE_READONLY",available:false},{status:503,headers})}
}
