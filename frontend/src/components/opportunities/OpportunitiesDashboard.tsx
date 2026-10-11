"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  DEFAULT_FILTERS, FAMILIES, filterOpportunities,
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
      <td><span className={s.chip} data-lifecycle={item.lifecycle}>{fmt(item.lifecycle)}</span></td>
      <td>{item.marketState} · <span className={s.direction} data-direction={item.direction}>{item.direction}</span></td>
      <td>{item.priority === null ? "—" : item.priority.toFixed(1)}<div className={s.sub}>research priority</div></td>
      <td><span className={s.stale}>{item.freshness}</span></td>
    </tr>
  );
}

function EvidenceList({ items, empty }: { items: string[]; empty: string }) {
  return items.length ? <ul>{items.map(item => <li key={item}>{item}</li>)}</ul> : <p className={s.meta}>{empty}</p>;
}

export function OpportunitiesDashboard({items,demo=false,available=true}:{items:Opportunity[];demo?:boolean;available?:boolean}) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [selected, setSelected] = useState("a");
  const [page,setPage]=useState(0);
  const pageSize=12;
  const rows = useMemo(() => sortOpportunities(filterOpportunities(items, filters)), [items,filters]);
  const pages=Math.max(1,Math.ceil(rows.length/pageSize)),safePage=Math.min(page,pages-1),shown=rows.slice(safePage*pageSize,(safePage+1)*pageSize);
  const active = shown.find(item => item.id === selected) ?? shown[0];
  const set = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    {setPage(0);setFilters(previous => ({ ...previous, [key]: value }));}
  const count = (lifecycle: string) => items.filter(item => item.lifecycle === lifecycle).length;
  const staleCount = items.filter(item => item.freshness === "STALE").length;
  const reset = () => { setPage(0);setFilters(DEFAULT_FILTERS); setSelected("a"); };

  return (
    <div className={s.root} data-testid="opportunities-v2">
      <header className={s.header}>
        <div>
          <h1>Research Opportunities</h1>
          <p>Binance USD-M Futures · explainable setup monitor</p>
        </div>
      </header>

      {!available?<p role="alert">Canonical source unavailable. Counts and candidates are not verified; no substitute rows.</p>:null}
      <section className={s.summary} aria-label="Research summary">
        <div><small>{demo?"Demo candidates":"Stored candidates"}</small><strong>{available?items.length:"UNKNOWN"}</strong><span>{demo?"STATIC EXAMPLES":"PERSISTED · NOT LIVE"}</span></div>
        <div><small>Saved active</small><strong>{available?count("ACTIVE_RESEARCH"):"UNKNOWN"}</strong><span>NOT EXECUTABLE</span></div>
        <div><small>Watching</small><strong>{available?count("WATCHING"):"UNKNOWN"}</strong><span>RESEARCH ONLY</span></div>
        <div><small>Edge validation</small><strong>UNKNOWN</strong><span>INSUFFICIENT EVIDENCE</span></div>
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
          {["ALL", "CORE", "HOT", "UNKNOWN"].map(value => <option key={value}>{value}</option>)}
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
              <tbody>{shown.map(item => <DataRow key={item.id} item={item}
                selected={active?.id === item.id} onPick={() => setSelected(item.id)} />)}</tbody>
            </table>
            {!rows.length && <div className={s.empty}>No setups match these filters. <button type="button" onClick={reset}>Clear filters</button></div>}
          </div>
          <div style={{display:"flex",justifyContent:"space-between",gap:12,flexWrap:"wrap",padding:"12px 0"}}><span className={s.meta} role="status">Page {safePage+1}/{pages} · {rows.length} matching saved candidates · 12 rows per page</span><div><button type="button" disabled={safePage===0} onClick={()=>setPage(safePage-1)}>Previous candidates</button> <button type="button" disabled={safePage+1>=pages} onClick={()=>setPage(safePage+1)}>Next candidates</button></div></div>
          <div className={s.provenance} aria-label="Dataset provenance">
            <h3>Dataset provenance</h3>
            <div className={s.provenanceBadges}>
              <span>{demo?"DEMO FIXTURE":"CANONICAL SQLITE"}</span><span>{staleCount}/{items.length} STALE</span>
              <span>OUTCOME LINKAGE NOT VERIFIED</span><span>{demo?"API NOT CONNECTED":"READ ONLY"}</span>
            </div>
            <p>{demo?"These examples demonstrate research workflow only. Neither their lifecycle labels nor their priority rankings are current market observations.":"Saved lifecycle and ranking describe the recorded evaluation. They are not current setups, validated predictive edges or executable signals."}</p>
          </div>
        </section>

        <section className={s.panel} id="candidate-evidence" aria-label="Candidate evidence">
          <div className={s.panelTitle}>
            <h2>Evidence inspector</h2><span>{active ? demo?"DEMO FIXTURE":"PERSISTED RECORD" : "NO CANDIDATE"}</span>
          </div>
          {active ? <>
            <div className={s.detailHead}>
              <h3 aria-live="polite">{active.symbol}</h3>
              <span className={s.chip}>{fmt(active.family)}</span>
            </div>
            <div className={s.inspectorGrid} role="region" aria-label="Selected candidate summary">
              <div><small>Lifecycle</small><strong data-lifecycle={active.lifecycle}>{fmt(active.lifecycle)}</strong></div>
              <div><small>Observed state</small><strong>{active.marketState} · <span className={s.direction} data-direction={active.direction}>{active.direction}</span></strong></div>
              <div><small>Priority score</small><strong>{active.priority === null ? "—" : active.priority.toFixed(1)}</strong></div>
              <div><small>Freshness</small><strong data-freshness={active.freshness}>{active.freshness}</strong></div>
            </div>
            <p className={s.meta}>Rules {active.ruleVersion} · Priority is research ranking, not probability or expected profit.</p>
            <h4>Supporting evidence</h4><EvidenceList items={active.support} empty="No verified supporting evidence" />
            <h4>Counterevidence</h4><EvidenceList items={active.against} empty="Not evaluated" />
            <h4>Missing inputs</h4><EvidenceList items={active.missing} empty={demo?"None reported in fixture":"No missing inputs reported at saved evaluation"} />
            <div className={s.historical}>
              Historical evidence: {fmt(active.historical)}
              <div>Timestamp: {active.asOf} · Source: {demo?"DEMO FIXTURE":"opportunity_candidates"}</div>
            </div>
            <Link href={`/symbol/${active.symbol}`}>Open token detail →</Link>
          </> : <p className={s.meta}>No candidate matches the current filters. Adjust filters to inspect evidence.</p>}
        </section>
      </div>
      <p className={s.disclaimer}>RESEARCH ONLY · {demo?"DEMO DATA":"PERSISTED RECORDS"} — NOT LIVE · No entries, exits, positions, projected returns, probability or P&amp;L.</p>
    </div>
  );
}
