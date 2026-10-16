import {NextResponse} from "next/server";
import {offlineEval} from "@/lib/offline-eval";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store"};
export async function GET() {
  try {
    return NextResponse.json(offlineEval(), {headers});
  } catch {
    return NextResponse.json({error: "OFFLINE_EVAL_UNAVAILABLE", available: false}, {status: 503, headers});
  }
}
