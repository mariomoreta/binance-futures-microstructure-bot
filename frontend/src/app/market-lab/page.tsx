import {SnapshotRefresh} from "@/components/notices/SnapshotRefresh";
import {canonicalReadTime} from "@/lib/historical-db";
import {historicalRead} from "@/lib/historical-db";
import {MarketLabView} from "@/components/market-lab/MarketLabView";
import {ContractExplorer} from "@/components/market-lab/ContractExplorer";
import {MarketFlowPanel} from "@/components/market-lab/MarketFlowPanel";
import EngineeringSession from "@/components/session-lab/EngineeringSession";
import {PilotMonitor} from "@/components/pilot-monitor/PilotMonitor";
import Link from "next/link";
import styles from "./market-lab.module.css";
export const dynamic="force-dynamic";
type P={symbol:string;bucket_ms:number;price:number};
type S={vista?:string;run?:string};
export default async function MarketLab({searchParams}:{searchParams:Promise<S>}){
  const sp=await searchParams;
  const vista=sp.vista==="piloto"?"piloto":"explorador";
  const run=typeof sp.run==="string"?sp.run.trim():"";
  if(vista==="piloto"){
    // Modo monitor: NO se monta el explorador, el panel de flujo ni la sesion
    // de ingenieria. Abrir o recargar la vista no abre procesos, streams ni
    // descargas ajenas al ledger del piloto.
    return (
      <>
        <nav className={styles.modes} aria-label="Vista del laboratorio de mercado">
          <Link href="/market-lab" className={styles.mode}>Explorador</Link>
          <span className={styles.modeActive} aria-current="page">Monitor del piloto</span>
        </nav>
        <PilotMonitor runId={run}/>
      </>
    );
  }
  let rows:P[]=[];let error=false;
  try{rows=historicalRead(db=>db.prepare("SELECT symbol,bucket_ms,price FROM price_samples WHERE bucket_ms > 0 AND price > 0 ORDER BY symbol,bucket_ms LIMIT 5000").all().map((x)=>{const p=x as P;return {symbol:String(p.symbol),bucket_ms:Number(p.bucket_ms),price:Number(p.price)}}))}catch{error=true}
  return (
    <>
      <nav className={styles.modes} aria-label="Vista del laboratorio de mercado">
        <span className={styles.modeActive} aria-current="page">Explorador</span>
        <Link href="/market-lab?vista=piloto" className={styles.mode}>Monitor del piloto</Link>
      </nav>
      <SnapshotRefresh readAt={canonicalReadTime()} available={!error}/>
      <ContractExplorer/>
      <MarketFlowPanel symbol="BTCUSDT"/>
      <MarketLabView rows={rows} error={error}/>
      <section style={{marginTop:32}}>
        <EngineeringSession symbol="MINAUSDT" interval="1m" bars={90}/>
      </section>
    </>
  );
}
