import {offlineEval, evalUtc, evalMoney, OFFLINE_EVAL_SCALES} from "@/lib/offline-eval";
const td = {padding: "9px 8px", borderBottom: "1px solid #213649", textAlign: "left" as const, fontSize: 12};
const th = {...td, color: "#8ea4b5", fontWeight: 700};
const GROUPS: Array<{id: string; note: string}> = [
  {id: "continuation", note: "H1"},
  {id: "correction-exhaustion", note: "H2 leg"},
  {id: "correction-reversal", note: "H2 leg"},
  {id: "bearish-continuation", note: "H3"},
];
export function OfflineEvalSection() {
  let v: ReturnType<typeof offlineEval> | null = null;
  try { v = offlineEval(); } catch { v = null; }
  if (!v) return <section role="region" aria-label="Offline entry exit evaluation"><p role="alert" style={{padding: 16, border: "1px solid #795a32", marginTop: 18}}>Offline evaluation artifact unavailable. No replacement data.</p></section>;
  const data = v;
  return <section role="region" aria-label="Offline entry exit evaluation" style={{background: "#102233", borderRadius: 9, padding: 18, marginTop: 18}}>
    <h2 style={{fontSize: 16, fontWeight: 700}}>Offline entry/exit evaluation (read-only)</h2>
    <p style={{fontSize: 12, color: "#8ea4b5"}}>{data.label}. {data.semantics}</p>
    <p style={{fontSize: 12, color: "#8ea4b5"}}>Scope: each cell replays under its own single position (max_concurrent=1 within symbol+group+segment only); the pooled reference is arithmetic aggregation, not a portfolio. Per-trade causality (formation/available/entry), funding coverage, and units are audited in docs/evidence/OFFLINE_EVAL_AUDIT_V1.json; eval is time-held-out (non-pristine).</p>
    <div style={{display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 10, marginTop: 12, fontSize: 12}}>
      {[["Engine", data.engine_version], ["Formation", data.formation_method], ["Map candidate", data.map_candidate],
        ["Cutoff UTC", evalUtc(data.cutoff_ms)], ["Costs", `${data.cost_id ?? "UNKNOWN"} fee ${data.fee_bps ?? "UNKNOWN"}bps / spread ${data.spread_bps ?? "UNKNOWN"}bps / slip ${data.slippage_bps ?? "UNKNOWN"}bps (assumed)`],
        ["Eval segment", "time-held-out (non-pristine), never clean OOS"]].map(([k, val]) =>
        <div key={k} style={{background: "#0c1c2b", borderRadius: 7, padding: 10}}><small style={{color: "#8ea4b5"}}>{k}</small><p style={{marginTop: 4}}>{val}</p></div>)}
    </div>
    <h3 style={{fontSize: 14, fontWeight: 700, marginTop: 16}}>Dataset &amp; flow (events → admissible → discarded → trades)</h3>
    <div style={{overflowX: "auto"}}><table style={{width: "100%", borderCollapse: "collapse"}}>
      <thead><tr>{["Symbol", "Candles 15m", "Window UTC", "Chain violations", "Events", "Dev / OOS / purged", "Input hash", "Funding settlements"].map(x => <th style={th} key={x}>{x}</th>)}</tr></thead>
      <tbody>{Object.entries(data.symbols).map(([sym, s]) =>
        <tr key={sym}><td style={td}>{sym}</td><td style={td}>{s.n_candles ?? "UNKNOWN"}</td>
          <td style={td}>{evalUtc(s.window_open_ms)} → {evalUtc(s.window_close_ms)}</td>
          <td style={td}>{s.close_chain_violations ?? "UNKNOWN"}</td><td style={td}>{s.n_events ?? "UNKNOWN"}</td>
          <td style={td}>{s.n_dev ?? "?"} / {s.n_oos ?? "?"} / {s.n_purged ?? "?"}</td>
          <td style={td}>{s.input_hash ?? "UNKNOWN"}</td><td style={td}>{s.funding_n ?? "UNKNOWN"}</td></tr>)}</tbody>
    </table></div>
    <h3 style={{fontSize: 14, fontWeight: 700, marginTop: 16}}>Cells @1x with 2x/3x sensitivity (realized-only; open marks excluded)</h3>
    <div style={{overflowX: "auto"}}><table style={{width: "100%", borderCollapse: "collapse"}}>
      <thead><tr>{["Symbol", "Group", "Seg", "Events", "Traded", "Overlap skips", "Stops", "E[net] realized @1x", "Total realized @1x", "E[net] @2x", "E[net] @3x", "Fees @1x", "Funding @1x", "DD realized @1x", "Open", "MFE/MAE"].map(x => <th style={th} key={x}>{x}</th>)}</tr></thead>
      <tbody>{Object.keys(data.symbols).flatMap(sym => GROUPS.flatMap(g => (["dev", "oos"] as const).map(seg => {
        const c1 = data!.cells[sym]?.[g.id]?.[seg]?.["1.0"];
        if (!c1) return null;
        const thin = (c1.n_events ?? 99) < 30;
        return <tr key={`${sym}-${g.id}-${seg}`}>
          <td style={td}>{sym}</td><td style={td}>{g.id} ({g.note}){thin ? " — INSUFFICIENT sample, no reading" : ""}</td>
          <td style={td}>{seg}</td><td style={td}>{c1.n_events ?? "?"}</td><td style={td}>{c1.n_trades ?? "?"}</td>
          <td style={td}>{c1.skipped_overlap ?? "?"}</td><td style={td}>{c1.exit_reasons.stop ?? "?"}</td>
          <td style={td}>{evalMoney(c1.expectancy_net)}</td><td style={td}>{evalMoney(c1.total_net_realized)}</td>
          <td style={td}>{evalMoney(data!.cells[sym]?.[g.id]?.[seg]?.["2.0"]?.expectancy_net ?? null)}</td>
          <td style={td}>{evalMoney(data!.cells[sym]?.[g.id]?.[seg]?.["3.0"]?.expectancy_net ?? null)}</td>
          <td style={td}>{evalMoney(c1.total_fees)}</td><td style={td}>{evalMoney(c1.total_funding)}</td>
          <td style={td}>{evalMoney(c1.max_drawdown_realized)}</td><td style={td}>{c1.n_open ?? "?"}</td>
          <td style={td}>{c1.mfe_mean?.toFixed(3) ?? "?"} / {c1.mae_mean?.toFixed(3) ?? "?"}</td></tr>;
      })))}
      </tbody>
    </table></div>
    <h3 style={{fontSize: 14, fontWeight: 700, marginTop: 16}}>Pooled reference (arithmetic sum over directional groups — not a strategy)</h3>
    <div style={{overflowX: "auto"}}><table style={{width: "100%", borderCollapse: "collapse"}}>
      <thead><tr>{["Segment", ...OFFLINE_EVAL_SCALES.map(s => `E[net] realized @${s}x`), "Trades", "Realized", "Open", "Fees @1x", "Funding @1x"].map(x => <th style={th} key={x}>{x}</th>)}</tr></thead>
      <tbody>{Object.entries(data.pooled).map(([seg, sc]) =>
        <tr key={seg}><td style={td}>{seg}</td>
          {OFFLINE_EVAL_SCALES.map(s => <td style={td} key={s}>{evalMoney((sc as Record<string, {expectancy_net_realized: number | null}>)[s]?.expectancy_net_realized ?? null)}</td>)}
          <td style={td}>{(sc as Record<string, {n_trades: number | null}>)["1.0"]?.n_trades ?? "?"}</td>
          <td style={td}>{(sc as Record<string, {n_realized: number | null}>)["1.0"]?.n_realized ?? "?"}</td>
          <td style={td}>{(sc as Record<string, {n_open: number | null}>)["1.0"]?.n_open ?? "?"}</td>
          <td style={td}>{evalMoney((sc as Record<string, {total_fees: number | null}>)["1.0"]?.total_fees ?? null)}</td>
          <td style={td}>{evalMoney((sc as Record<string, {total_funding: number | null}>)["1.0"]?.total_funding ?? null)}</td></tr>)}</tbody>
    </table></div>
    <h3 style={{fontSize: 14, fontWeight: 700, marginTop: 16}}>Reproducibility (isolated package)</h3>
    <p style={{fontSize: 12, color: "#8ea4b5"}}>Artifact sha256 c051e888…287b3a (pinned). Per-symbol input hashes above re-verified by full replay from the canonical DB (byte-identical rebuild, 1412 trades, inputs identical). Bulky candles/events live outside Git; manifest with full SHA256, versions, units, coverage, gaps, provenance and commands: docs/evidence/OFFLINE_EVAL_PACKAGE_V1.md. Reproduce via scripts/reproduce_offline_eval.py. External reproduction without the DB/package stays PENDING (clean checkouts verify artifact/aggregation/UI only — aggregation determinism is not replay from raw data).</p>
    <h3 style={{fontSize: 14, fontWeight: 700, marginTop: 16}}>Causality by family (mechanics vs signal)</h3>
    <div style={{overflowX: "auto"}}><table style={{width: "100%", borderCollapse: "collapse"}}>
      <thead><tr>{["Family", "Formation", "Selection", "Live availability", "Reading"].map(x => <th style={th} key={x}>{x}</th>)}</tr></thead>
      <tbody>{[
        ["H1 bullish continuation (LONG)", "prefix-causal, strict-posterior invariant", "retrospective pilot subset", "UNKNOWN", "retrospective — not a signal"],
        ["H3 bearish continuation (SHORT)", "prefix-causal, strict-posterior invariant", "retrospective pilot subset", "UNKNOWN", "retrospective — not a signal"],
        ["H2 exhaustion / reversal legs", "prefix-causal mechanics", "retrospective + n≤14 INSUFFICIENT + non-fade convention", "UNKNOWN", "fenced, no reading"],
        ["H2 rebound variant", "no source definition", "0 events, excluded", "UNKNOWN", "UNKNOWN (untestable)"],
      ].map(([f, a, b, c, d]) => <tr key={f as string}><td style={td}>{f}</td><td style={td}>{a}</td><td style={td}>{b}</td><td style={td}>{c}</td><td style={td}>{d}</td></tr>)}
      </tbody>
    </table></div>
    <p style={{fontSize: 12, color: "#8ea4b5"}}>Per-trade entry ≥ available_at holds 1412/1412 (mechanical causality, not tradability). Full matrix: docs/OFFLINE_EVAL_CAUSAL_AUDIT_V2.md. No retrospective result is shown as an operable signal.</p>
    <h3 style={{fontSize: 14, fontWeight: 700, marginTop: 16}}>Breakeven (assumed costs; spread/slippage UNKNOWN)</h3>
    <p style={{fontSize: 12, color: "#8ea4b5"}}>Costs are COST-ASSUME-v1 (fee 5bps + spread 1bps + slippage 2bps, ~1.60 USDT/op on $1000 notional) — assumed, never measured; fee tier unknown; no historical spread/depth. Breakeven scale s* = E[gross]/1.60; max round-trip friction = E[gross]×10 bps. All 12 directional cells turn negative at 2x (fragile, no demonstrated edge). Detail: docs/OFFLINE_EVAL_COST_BREAKEVEN_V1.md.</p>
    <div style={{overflowX: "auto"}}><table style={{width: "100%", borderCollapse: "collapse"}}>
      <thead><tr>{["Symbol", "Group", "Seg", "E[gross]/op", "s* (breakeven scale)", "max round-trip", "@2x verdict"].map(x => <th style={th} key={x}>{x}</th>)}</tr></thead>
      <tbody>{Object.keys(data.symbols).flatMap(sym => ["continuation", "bearish-continuation"].flatMap(g => (["dev", "oos"] as const).map(seg => {
        const c1 = data!.cells[sym]?.[g]?.[seg]?.["1.0"];
        const c2 = data!.cells[sym]?.[g]?.[seg]?.["2.0"];
        if (!c1 || c1.expectancy_gross === null || c1.expectancy_net === null) return null;
        const f1 = (c1.expectancy_gross as number) - (c1.expectancy_net as number);
        const sstar = f1 > 0 ? (c1.expectancy_gross as number) / f1 : null;
        return <tr key={`${sym}-${g}-${seg}-be`}>
          <td style={td}>{sym}</td><td style={td}>{g}</td><td style={td}>{seg}</td>
          <td style={td}>{evalMoney(c1.expectancy_gross)}</td>
          <td style={td}>{sstar === null ? "UNKNOWN" : sstar.toFixed(2) + "x"}</td>
          <td style={td}>{((c1.expectancy_gross as number) * 10).toFixed(1) + " bps"}</td>
          <td style={td}>{(c2?.expectancy_net ?? 0) < 0 ? "negative (fragile)" : "UNKNOWN"}</td></tr>;
      })))}
      </tbody>
    </table></div>
    <h3 style={{fontSize: 14, fontWeight: 700, marginTop: 16}}>Limits (binding)</h3>
    <ul style={{fontSize: 12, color: "#9cabbc"}}>{data.limits.map((l, i) => <li key={i}>{l}</li>)}</ul>
  </section>;
}
