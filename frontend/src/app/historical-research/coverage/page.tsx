import {SnapshotRefresh} from "@/components/notices/SnapshotRefresh";
import {historicalCoverage,historyFilter,type HistoryCoverage} from "@/lib/historical-coverage";
import {HistoryNavigation} from "@/components/history/HistoryNavigation";
import {HistoricalCoverageView} from "@/components/history/HistoricalCoverageView";
import styles from "@/components/history/HistoricalCoverage.module.css";
export const dynamic="force-dynamic";export const runtime="nodejs";
export default async function CoveragePage({searchParams}:{searchParams:Promise<{symbol?:string|string[];definition?:string|string[]}>}){
 const q=await searchParams;let filter={symbol:"",definition:""},invalid=false,data:HistoryCoverage|null=null;
 try{filter=historyFilter(q.symbol??"",q.definition??"")}catch{invalid=true}
 if(!invalid)try{data=historicalCoverage(filter)}catch{}
 return <div className={styles.workspace}><header className={styles.heading}><div><small>RESEARCH ARCHIVE / HISTORICAL EVIDENCE</small><h1>Historical coverage &amp; studies</h1><p>Stored bars, coverage boundaries and descriptive event outcomes from the separate Python research database.</p></div><span className={styles.badge}>READ ONLY · HISTORICAL</span></header><HistoryNavigation active="coverage"/>{!invalid&&<SnapshotRefresh readAt={data?.read_at??new Date().toISOString()} available={data!==null} sourceLabel="Historical SQLite" pollUrl={"/api/v1/historical-coverage?"+new URLSearchParams(filter)}/> }<HistoricalCoverageView data={data} filter={filter} invalid={invalid}/></div>
}
