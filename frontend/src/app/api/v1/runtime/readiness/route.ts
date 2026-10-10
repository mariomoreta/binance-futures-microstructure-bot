import {NextResponse} from "next/server";
import {launchReadiness} from "@/lib/launch-readiness";
export const runtime="nodejs";export const dynamic="force-dynamic";
export function GET(){return NextResponse.json(launchReadiness(),{headers:{"Cache-Control":"no-store"}})}
