import {SnapshotRefresh} from "@/components/notices/SnapshotRefresh";
import {canonicalReadTime} from "@/lib/historical-db";
import {historicalRead} from "@/lib/historical-db";
import {MarketLabView} from "@/components/market-lab/MarketLabView";
import {ContractExplorer} from "@/components/market-lab/ContractExplorer";
export const dynamic="force-dynamic";
type P={symbol:string;bucket_ms:number;price:number};
export default function MarketLab(){
 let rows:P[]=[];let error=false;
 try{rows=historicalRead(db=>db.prepare("SELECT symbol,bucket_ms,price FROM price_samples WHERE bucket_ms > 0 AND price > 0 ORDER BY symbol,bucket_ms LIMIT 5000").all().map((x)=>{const p=x as P;return {symbol:String(p.symbol),bucket_ms:Number(p.bucket_ms),price:Number(p.price)}}))}catch{error=true}
 return <><SnapshotRefresh readAt={canonicalReadTime()} available={!error}/><ContractExplorer/><MarketLabView rows={rows} error={error}/></>;
}
