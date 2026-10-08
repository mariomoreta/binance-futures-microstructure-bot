"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  DEFAULT_FILTERS, DEMO_OPPORTUNITIES, FAMILIES, filterOpportunities,
  sortOpportunities, type Filters, type Opportunity
} from "@/lib/opportunities-domain";
import s from "./OpportunitiesDashboard.module.css";

const fmt = (value: string) => value.replaceAll("_", " ");

function DataRow({ item, selected, onPick }: { item: Opportunity; selected: boolean; onPick: () => void }) {
  return (
    <tr className={selected ? s.selected : ""}>
      <td>
        <button className={s.rowPick} onClick={onPick} aria-pressed={selected}
          aria-controls="candidate-evidence" aria-label={`Inspect ${item.symbol} ${item.family}`}>
          {item.symbol}
        </button>
        <div className={s.sub}>{item.tier}</div>
      </td>
      <td>{fmt(item.family)}</td>
      <td><span className={s.chip}>{fmt(item.lifecycle)}</span></td>
      <td>{item.marketState} · {item.direction}</td>
      <td>{item.priority === null ? "—" : item.priority.toFixed(1)}<div className={s.sub}>research priority</div></td>
      <td><span className={s.stale}>{item.freshness}</span></td>
    </tr>
  );
}

function EvidenceList({ items, empty }: { items: string[]; empty: string }) {
  return items.length ? <ul>{items.map(item => <li key={item}>{item}</li>)}</ul> : <p className={s.meta}>{empty}</p>;
}

export function OpportunitiesDashboard() {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [selected, setSelected] = useState("a");
  const rows = useMemo(() => sortOpportunities(filterOpportunities(DEMO_OPPORTUNITIES, filters)), [filters]);
  const active = rows.find(item => item.id === selected) ?? rows[0];
  const set = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    setFilters(previous => ({ ...previous, [key]: value }));
  const count = (lifecycle: string) => DEMO_OPPORTUNITIES.filter(item => item.lifecycle === lifecycle).length;
  const reset = () => { setFilters(DEFAULT_FILTERS); setSelected("a"); };

  return (
    <div className={s.root} data-testid="opportunities-v2">
      <header className={s.header}>
        <div>
          <h1>Research Opportunities</h1>
          <p>Binance USD-M Futures · explainable setup monitor</p>
        </div>
      </header>

      <section className={s.summary} aria-label="Research summary">
        <div><small>Demo candidates</small><strong>{DEMO_OPPORTUNITIES.length}</strong><span>STATIC EXAMPLES</span></div>
        <div><small>Active research</small><strong>{count("ACTIVE_RESEARCH")}</strong><span>NOT EXECUTABLE</span></div>
        <div><small>Watching</small><strong>{count("WATCHING")}</strong><span>RESEARCH ONLY</span></div>
        <div><small>Historical validation</small><strong>NONE</strong><span>INSUFFICIENT EVIDENCE</span></div>
      </section>

      <section className={s.controls} aria-label="Opportunity filters">
        <label>Symbol<input aria-label="Search symbol" value={filters.query}
          onChange={event => set("query", event.target.value)} placeholder="Search BTC, SOL…" /></label>
        <label>Setup family<select aria-label="Setup family" value={filters.family}
          onChange={event => set("family", event.target.value as Filters["family"])}>
          <option value="ALL">All families</option>
          {FAMILIES.map(family => <option key={family} value={family}>{fmt(family)}</option>)}
        </select></label>
        <label>Lifecycle<select aria-label="Lifecycle" value={filters.lifecycle}
          onChange={event => set("lifecycle", event.target.value as Filters["lifecycle"])}>
          {["ALL", "DETECTED", "WATCHING", "ACTIVE_RESEARCH", "INVALIDATED", "EXPIRED", "UNKNOWN"].map(value =>
            <option key={value} value={value}>{fmt(value)}</option>)}
        </select></label>
        <label>Direction<select aria-label="Direction" value={filters.direction}
          onChange={event => set("direction", event.target.value as Filters["direction"])}>
          {["ALL", "UP", "DOWN", "NONE", "UNKNOWN"].map(value => <option key={value}>{value}</option>)}
        </select></label>
        <label>Coverage<select aria-label="Coverage" value={filters.coverage}
          onChange={event => set("coverage", event.target.value as Filters["coverage"])}>
          {["ALL", "CORE", "HOT"].map(value => <option key={value}>{value}</option>)}
        </select></label>
        <button type="button" onClick={reset}>Reset</button>
      </section>

      <div className={s.columns}>
        <section className={s.panel} aria-label="Setup candidates">
          <div className={s.panelTitle}>
            <h2>Setup candidates</h2>
            <span role="status" aria-live="polite">{rows.length} matching · priority score is NOT probability</span>
          </div>
          <div className={s.tableWrap} role="region" aria-label="Opportunity candidates table" tabIndex={0}>
            <table>
              <thead><tr>
                <th scope="col">Symbol</th><th scope="col">Research family</th>
                <th scope="col">Lifecycle</th><th scope="col">Observed state</th>
                <th scope="col">Priority</th><th scope="col">Freshness</th>
              </tr></thead>
              <tbody>{rows.map(item => <DataRow key={item.id} item={item}
                selected={active?.id === item.id} onPick={() => setSelected(item.id)} />)}</tbody>
            </table>
            {!rows.length && <div className={s.empty}>No setups match these filters. <button type="button" onClick={reset}>Clear filters</button></div>}
          </div>
        </section>

        <section className={s.panel} id="candidate-evidence" aria-label="Candidate evidence">
          <div className={s.panelTitle}>
            <h2>Evidence inspector</h2><span>{active ? "DEMO FIXTURE" : "NO CANDIDATE"}</span>
          </div>
          {active ? <>
            <div className={s.detailHead}>
              <h3 aria-live="polite">{active.symbol}</h3>
              <span className={s.chip}>{fmt(active.family)}</span>
            </div>
            <div className={s.inspectorGrid} role="region" aria-label="Selected candidate summary">
              <div><small>Lifecycle</small><strong>{fmt(active.lifecycle)}</strong></div>
              <div><small>Observed state</small><strong>{active.marketState} · {active.direction}</strong></div>
              <div><small>Priority score</small><strong>{active.priority === null ? "—" : active.priority.toFixed(1)}</strong></div>
              <div><small>Freshness</small><strong data-freshness={active.freshness}>{active.freshness}</strong></div>
            </div>
            <p className={s.meta}>Rules {active.ruleVersion} · Priority is research ranking, not probability or expected profit.</p>
            <h4>Supporting evidence</h4><EvidenceList items={active.support} empty="No verified supporting evidence" />
            <h4>Counterevidence</h4><EvidenceList items={active.against} empty="Not evaluated" />
            <h4>Missing inputs</h4><EvidenceList items={active.missing} empty="None reported in fixture" />
            <div className={s.historical}>
              Historical evidence: {fmt(active.historical)}
              <div>Timestamp: {active.asOf} · Source: DEMO FIXTURE</div>
            </div>
            <Link href={`/symbol/${active.symbol}`}>Open token detail →</Link>
          </> : <p className={s.meta}>No candidate matches the current filters. Adjust filters to inspect evidence.</p>}
        </section>
      </div>
      <p className={s.disclaimer}>RESEARCH ONLY · DEMO DATA — NOT LIVE · No entries, exits, positions, projected returns, probability or P&amp;L. Backend integration pending verified contract.</p>
    </div>
  );
}
