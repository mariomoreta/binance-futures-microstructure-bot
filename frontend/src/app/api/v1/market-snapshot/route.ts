import {NextResponse} from "next/server";
import {canonicalMarket} from "@/lib/canonical-market";
export const dynamic="force-dynamic";export const runtime="nodejs";
export function GET(){const {features,...data}=canonicalMarket();void features;return NextResponse.json(data,{status:data.available?200:503,headers:{"Cache-Control":"no-store"}})}
