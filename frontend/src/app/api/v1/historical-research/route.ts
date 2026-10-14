import {NextResponse} from "next/server";
import {historicalSnapshot} from "@/lib/historical-db";
export const runtime="nodejs";export const dynamic="force-dynamic";
export async function GET(){try{return NextResponse.json(historicalSnapshot(),{headers:{"Cache-Control":"no-store"}})}catch{return NextResponse.json({error:"HISTORICAL_DB_UNAVAILABLE"},{status:503,headers:{"Cache-Control":"no-store"}})}}
