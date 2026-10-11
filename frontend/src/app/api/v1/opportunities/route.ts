import {NextResponse} from "next/server";
import {normalizeOpportunities} from "@/lib/opportunities-api";
import {canonicalOpportunities} from "@/lib/canonical-market";
export const dynamic="force-dynamic";export const runtime="nodejs";
export function GET(){try{const model=normalizeOpportunities({candidates:canonicalOpportunities()},Date.now());return NextResponse.json({...model,source:"persisted-sqlite-readonly"},{headers:{"Cache-Control":"no-store"}})}catch{return NextResponse.json({error:"CANONICAL_SOURCE_UNAVAILABLE"},{status:503,headers:{"Cache-Control":"no-store"}})}}
