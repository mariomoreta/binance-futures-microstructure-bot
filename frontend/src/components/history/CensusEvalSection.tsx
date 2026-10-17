import {censusEval, censusMoney, CENSUS_EVAL_GROUPS} from "@/lib/census-eval";
const td = {padding: "9px 8px", borderBottom: "1px solid #213649", textAlign: "left" as const, fontSize: 12};
const th = {...td, color: "#8ea4b5", fontWeight: 700};
const GROUP_NOTE: Record<string, string> = {
  "continuation": "H1", "bearish-continuation": "H3",
  "correction-exhaustion": "H2 fade SHORT (NEW-HYPOTHESIS)",
  "correction-reversal": "H2 fade LONG (NEW-HYPOTHESIS)",
  "baseline": "TIME-PLACEBO-v1",
};
export function CensusEvalSection() {
  let v: ReturnType<typeof censusEval> | null = null;
  try { v = censusEval(); } catch { v = null; }
  if (!v) return <section role="region" aria-label="Causal census evaluation"><p role="alert" style={{padding: 16, border: "1px solid #795a32", marginTop: 18}}>Census evaluation summary unavailable. No replacement data.</p></section>;
  const data = v;
  const c = data.census;
  return <section role="region" aria-label="Causal census evaluation" style={{background: "#102233", borderRadius: 9, padding: 18, marginTop: 18}}>
    <h2 style={{fontSize: 16, fontWeight: 700}}>Causal census + same-grid evaluation (read-only)</h2>
    <p style={{fontSize: 12, color: "#8ea4b5"}}>{data.label} Research display only, no operable signals.</p>
    <div style={{display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 10, marginTop: 12, fontSize: 12}}>
      {[["Census", `${String(c.detections ?? "?")} detections → ${String(c.admitted ?? "?")} admitted, ${String(c.discarded ?? "?")} discarded`],
        ["Originals reproduced", String(c.originals_matched ?? "?")],
        ["Census-only (never in pilot subset)", String(c.census_only ?? "?")],
        ["Duplicates (correlated, counted)", `${String((c as Record<string, unknown>).duplicate_groups ?? "?")} groups`],
        ["Prefix + invariance", String(c.prefix_cells_ok ?? "?")],
        ["Entry ≥ available_at", String(c.entry_ge_available ?? "?")],
        ["Mapping", data.mapping ?? "UNKNOWN"], ["Horizon rule", data.horizon_rule ?? "UNKNOWN"],
        ["Costs", data.cost_id ?? "UNKNOWN"]].map(([k, val]) =>
        <div key={k} style={{background: "#0c1c2b", borderRadius: 7, padding: 10}}><small style={{color: "#8ea4b5"}}>{k}</small><p style={{marginTop: 4}}>{val}</p></div>)}
    </div>
    <h3 style={{fontSize: 14, fontWeight: 700, marginTop: 16}}>Selection, discards and coverage</h3>
    <p style={{fontSize: 12, color: "#8ea4b5"}}>Excluded with motive (counted, never fabricated): formation-gap rows, tail-edge rows without same-grid entry, H2 unconfirmed/reclaimed. Stored 15m trio was EXTENDED-only (2.3% of the exhaustive 15m census); V1 replayed 1h-formed events on 15m candles without an explicit rule — this census never replays across resolutions (ENTRY-SAME-GRID-v1).</p>
    <div style={{overflowX: "auto"}}><table style={{width: "100%", borderCollapse: "collapse"}}>
      <thead><tr>{["Input", "Availability"].map(x => <th style={th} key={x}>{x}</th>)}</tr></thead>
      <tbody>{Object.entries(data.coverage).map(([k, val]) => <tr key={k}><td style={td}>{k}</td><td style={td}>{val}</td></tr>)}</tbody>
    </table></div>
    <h3 style={{fontSize: 14, fontWeight: 700, marginTop: 16}}>Eligible / fenced / excluded families</h3>
    <div style={{overflowX: "auto"}}><table style={{width: "100%", borderCollapse: "collapse"}}>
      <thead><tr>{["Scenario", "Sources", "Status"].map(x => <th style={th} key={x}>{x}</th>)}</tr></thead>
      <tbody>{data.families.map((f, i) => <tr key={i}><td style={td}>{f.scenario ?? "?"}</td><td style={td}>{f.sources ?? "?"}</td><td style={td}>{f.status ?? "?"}</td></tr>)}</tbody>
    </table></div>
    <h3 style={{fontSize: 14, fontWeight: 700, marginTop: 16}}>Cells @1x vs placebo (fenced where n&lt;30; no picking)</h3>
    <div style={{overflowX: "auto"}}><table style={{width: "100%", borderCollapse: "collapse"}}>
      <thead><tr>{["Symbol", "Resolution", "Group", "Seg", "Events", "Traded", "Open", "E[net] @1x", "E[gross]", "s*", "Placebo E[net] @1x", "E[net] @2x", "Verdict"].map(x => <th style={th} key={x}>{x}</th>)}</tr></thead>
      <tbody>{Object.keys(data.cells).flatMap(sym => Object.keys(data.cells[sym] ?? {}).flatMap(res => CENSUS_EVAL_GROUPS.flatMap(g => (["dev", "oos"] as const).map(seg => {
        const c1 = data!.cells[sym]?.[res]?.[g]?.[seg]?.["1.0"];
        const c2 = data!.cells[sym]?.[res]?.[g]?.[seg]?.["2.0"];
        if (!c1) return null;
        return <tr key={`${sym}-${res}-${g}-${seg}`}>
          <td style={td}>{sym}</td><td style={td}>{res}</td><td style={td}>{g} ({GROUP_NOTE[g] ?? ""})</td>
          <td style={td}>{seg}</td><td style={td}>{c1.n_events ?? "?"}</td><td style={td}>{c1.n_trades ?? "?"}</td>
          <td style={td}>{c1.n_open ?? "?"}</td><td style={td}>{censusMoney(c1.E_net)}</td>
          <td style={td}>{censusMoney(c1.E_gross)}</td><td style={td}>{c1.s_star === null || c1.s_star === undefined ? "UNKNOWN" : c1.s_star.toFixed(2) + "x"}</td>
          <td style={td}>{censusMoney(c1.placebo_E_net)}</td><td style={td}>{censusMoney(c2?.E_net ?? null)}</td>
          <td style={td}>{c1.verdict ?? "?"}</td></tr>;
      }))))}
      </tbody>
    </table></div>
    <h3 style={{fontSize: 14, fontWeight: 700, marginTop: 16}}>BTC context (when present)</h3>
    <p style={{fontSize: 12, color: "#8ea4b5"}}>{data.btc_context ?? "UNKNOWN"}</p>
    <h3 style={{fontSize: 14, fontWeight: 700, marginTop: 16}}>Limits (binding)</h3>
    <ul style={{fontSize: 12, color: "#9cabbc"}}>{data.limits.map((l, i) => <li key={i}>{l}</li>)}</ul>
  </section>;
}
