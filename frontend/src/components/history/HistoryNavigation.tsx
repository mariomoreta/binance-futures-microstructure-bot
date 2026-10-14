import Link from "next/link";
import styles from "./HistoricalCoverage.module.css";
export function HistoryNavigation({active}:{active:"archive"|"coverage"}){
 return <nav aria-label="Historical evidence views" className={styles.nav}>
 <Link href="/historical-research" aria-current={active==="archive"?"page":undefined}><strong>Prospective archive</strong><small>Saved setups and observed outcomes</small></Link>
 <Link href="/historical-research/coverage" aria-current={active==="coverage"?"page":undefined}><strong>Coverage & event studies</strong><small>Historical bars and descriptive research</small></Link>
 </nav>
}
