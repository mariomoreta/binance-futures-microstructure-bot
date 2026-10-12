import {LaunchReadiness} from "@/components/system/LaunchReadiness";
import {RuntimeDiagnostics} from "@/components/system/RuntimeDiagnostics";
import {SystemEvidence} from "@/components/system/SystemEvidence";
import {BotControl} from "@/components/system/BotControl";
import {PersistencePanel,ResearchPanel,UniversePanel,ClassifierPanel,ResourcePanel} from "@/components/system/RecordedSystemPanels";
import {SnapshotRefresh} from "@/components/notices/SnapshotRefresh";
import {canonicalSystemEvidence} from "@/lib/system-evidence";
import styles from "./System.module.css";
export const dynamic = "force-dynamic";
export default function SystemPage() {
 const data=canonicalSystemEvidence();
 return <div className={styles.root} data-testid="system-v2">
  <header className={styles.header}><div><h1>System</h1><p>Infrastructure, transport, persistence and research pipeline</p></div><span className={styles.tag}>RESEARCH WORKSPACE</span></header>
  <BotControl/>
  <SnapshotRefresh readAt={data.read_at} available={data.available} pollUrl="/api/v1/system-evidence" sourceLabel="Recorded system SQLite"/>
  <div className={styles.grid}><RuntimeDiagnostics/><PersistencePanel data={data}/><ResearchPanel data={data}/></div>
  <div className={styles.grid}><UniversePanel data={data}/><ClassifierPanel data={data}/><ResourcePanel/></div>
  <details className={styles.panel}><summary>Launch preflight · Start remains disabled</summary><LaunchReadiness/></details>
  <SystemEvidence/>
  <section className={styles.panel} aria-label="System events and audit log">
   <div className={styles.auditHeading}><div><small>OPERATIONAL HISTORY</small><h2>System events and audit log</h2></div><span className={styles.unknown}>NO OPERATIONAL EVENT FEED</span></div>
   <p className={styles.note}>No real operational events loaded. Saved universe, classification and opportunity transitions are research records; aggregate counters are not an operational audit log.</p>
  </section>
 </div>;
}
