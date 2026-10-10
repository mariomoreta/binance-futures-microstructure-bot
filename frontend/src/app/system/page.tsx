import {LaunchReadiness} from "@/components/system/LaunchReadiness";
import {RuntimeDiagnostics} from "@/components/system/RuntimeDiagnostics";
import {SystemEvidence} from "@/components/system/SystemEvidence";
import {BotControl} from "@/components/system/BotControl";
import styles from "./System.module.css";

export const dynamic = "force-dynamic";
const pending = [
  ["Live universe", "CORE / HOT allocation and subscription budgets"],
  ["Research recorder", "Current queue, writes, drops and recorder lifecycle"],
  ["Classifier & opportunities", "Latest evaluations and rule versions"],
  ["Host resources", "CPU, memory and network samples with capture time"],
  ["Operational events", "Timestamped events with component and severity"],
];

export default function SystemPage() {
  return <div className={styles.root} data-testid="system-v2">
    <header className={styles.header}>
      <div><h1>System</h1><p>Infrastructure, transport, persistence and research pipeline</p></div>
      <span className={styles.tag}>RESEARCH WORKSPACE</span>
    </header>
    <BotControl />
    <div className={styles.grid}>
      <RuntimeDiagnostics />
      <LaunchReadiness />
      <section className={styles.panel} aria-label="Integration coverage">
        <div className={styles.heading}><small>SCREEN COVERAGE</small><h2>Research pipeline</h2><p>Backend capabilities awaiting integration in this screen.</p></div>
        <div className={styles.rows}>{pending.map(([name, detail]) =>
          <div className={styles.row} key={name}><div><strong>{name}</strong><small>{detail}</small></div><span className={styles.unknown}>NOT CONNECTED</span></div>
        )}</div>
        <p className={styles.note}>Unavailable in V2 does not mean absent from the Python engine. Recorded evidence below is separate from current runtime health.</p>
      </section>
    </div>
    <SystemEvidence />
    <section className={styles.panel} aria-label="System events and audit log">
      <div className={styles.auditHeading}><div><small>OPERATIONAL HISTORY</small><h2>System events and audit log</h2></div><span className={styles.unknown}>NO EVENT FEED</span></div>
      <p className={styles.note}>No real events loaded. A timestamped event contract is required; aggregate counters in archived evidence are not an event log.</p>
    </section>
  </div>;
}
