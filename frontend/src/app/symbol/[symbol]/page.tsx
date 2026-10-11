import Link from "next/link";
import {notFound} from "next/navigation";
import {TokenDetail} from "@/components/token/TokenDetail";
import {SnapshotRefresh} from "@/components/notices/SnapshotRefresh";
import {canonicalMarket} from "@/lib/canonical-market";
import {recordedToken} from "@/lib/persisted-market";
export const dynamic="force-dynamic";export const runtime="nodejs";
export default async function SymbolPage({params}:{params:Promise<{symbol:string}>}){const {symbol:raw}=await params;const symbol=raw.toUpperCase();if(!/^[A-Z0-9]{2,32}$/.test(symbol))notFound();const m=canonicalMarket(),now=Date.parse(m.readAt);return <><SnapshotRefresh readAt={m.readAt} available={m.available}/><TokenDetail data={recordedToken(m,symbol,now)}/><p className="v2-muted" style={{fontSize:12,marginTop:18}}><Link href={"/historical-research/coverage?symbol="+encodeURIComponent(symbol)}>Historical coverage and recorded events for {symbol} →</Link> · Separate historical research source; availability is not current feed health.</p></>}
