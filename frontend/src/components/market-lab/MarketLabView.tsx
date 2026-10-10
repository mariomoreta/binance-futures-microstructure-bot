"use client";
import {useMemo,useState} from "react";
import Link from "next/link";
import s from "./MarketLabView.module.css";
type P={symbol:string;bucket_ms:number;price:number};
const ranges=[["All saved",Infinity],["1 hour",3600000],["6 hours",21600000],["24 hours",86400000]] as const;
function svgPath(points:P[],min:number,max:number){const span=max-min||1;const first=points[0]?.bucket_ms??0;const last=points.at(-1)?.bucket_ms??first+1;return points.map((p,i)=>`${i===0||p.bucket_ms-points[i-1]!.bucket_ms>120000?"M":"L"} ${25+((p.bucket_ms-first)/(last-first||1))*850} ${210-((p.price-min)/span)*180}`).join(" ")}
export function MarketLabView({rows,error}:{rows:P[];error:boolean}){
 const symbols=useMemo(()=>[...new Set(rows.map(r=>r.symbol))], [rows]);
 const [symbol,setSymbol]=useState("BTCUSDT"),[range,setRange]=useState("All saved"),[compare,setCompare]=useState("ETHUSDT");
 const selected=symbols.includes(symbol)?symbol:symbols[0]??"";
 const latest=rows.reduce((m,r)=>Math.max(m,r.bucket_ms),0);
 const windowMs=ranges.find(r=>r[0]===range)?.[1]??Infinity;
 const cutoff=Number.isFinite(windowMs)?latest-windowMs:-Infinity;
 const current=rows.filter(r=>r.symbol===selected&&r.bucket_ms>=cutoff);
 const other=rows.filter(r=>r.symbol===compare&&r.bucket_ms>=cutoff);
 const min=current.length?Math.min(...current.map(p=>p.price)):0,max=current.length?Math.max(...current.map(p=>p.price)):0;
 const change=current.length>1?(current.at(-1)!.price/current[0]!.price-1)*100:null;
 const comparison=other.length>1?(other.at(-1)!.price/other[0]!.price-1)*100:null;
 const stamp=(x:number)=>new Date(x).toISOString().replace("T"," ").slice(0,19)+" UTC";
 return <main className={s.root}><header className={s.header}><div><small>MARKET INTELLIGENCE / SQLITE RESEARCH</small><h1>Historical Market Lab</h1><p>Stored mark-price observations. Session gaps are not filled. Comparisons are descriptive, not investment signals.</p></div><Link href="/market-archive">Market Archive →</Link></header>
 {error?<p role="alert">Historical database unavailable. No substitute data displayed.</p>:<>
 <div className={s.notice}>PERSISTED SQLITE · NOT LIVE · Latest stored sample: {latest?stamp(latest):"UNKNOWN"} · Displayed time windows are measured from the last saved sample, not the current clock.</div>
 <div className={s.toolbar}><label>Symbol<select aria-label="Select symbol" value={selected} onChange={e=>setSymbol(e.target.value)}>{symbols.map(x=><option key={x}>{x}</option>)}</select></label><label>Historical window<select aria-label="Historical time window" value={range} onChange={e=>setRange(e.target.value)}>{ranges.map(([x])=><option key={x}>{x}</option>)}</select></label><label>Compare symbol<select aria-label="Compare symbol" value={compare} onChange={e=>setCompare(e.target.value)}>{symbols.map(x=><option key={x}>{x}</option>)}</select></label></div>
 <div className={s.metrics}>{[["Saved points",String(current.length)],["Last saved mark",current.length?String(current.at(-1)?.price):"UNKNOWN"],["Observed change",change===null?"UNKNOWN":change.toFixed(3)+"%"],["Compared symbol change",comparison===null?"UNKNOWN":comparison.toFixed(3)+"%"]].map(([k,v])=><section key={k}><small>{k}</small><strong>{v}</strong></section>)}</div>
 <section className={s.panel}><h2>{selected} — persisted price sequence</h2>{current.length<2?<p>Insufficient stored observations in the selected window. No chart or interpolation.</p>:<><svg role="img" aria-label={selected+" historical mark price chart"} viewBox="0 0 900 235" preserveAspectRatio="none"><path d={svgPath(current,min,max)} fill="none" stroke="#62c6f3" strokeWidth="2.5" vectorEffect="non-scaling-stroke"/><line x1="25" x2="875" y1="210" y2="210" stroke="#45627b" strokeWidth="1"/></svg><div className={s.axis}><span>{stamp(current[0]!.bucket_ms)}</span><span>Range: {min.toPrecision(7)} — {max.toPrecision(7)}</span><span>{stamp(current.at(-1)!.bucket_ms)}</span></div></>}</section>
 <section className={s.panel}><h2>Symbol comparison · observed change within stored window</h2><div className={s.compare}>{[selected,compare].map((name,i)=>{const val=i===0?change:comparison;const n=i===0?current.length:other.length;return <div key={i}><b>{name}</b><strong>{val===null?"UNKNOWN":val.toFixed(3)+"%"}</strong><small>{n} saved samples</small></div>})}</div><p>These returns are mark-price comparisons over the available points only. Missing periods and sampling differences prevent like-for-like performance conclusions.</p></section>
 <section className={s.panel}><h2>Coverage and freshness diagnostics</h2><table><thead><tr><th>Symbol</th><th>Stored samples</th><th>First UTC</th><th>Last UTC</th><th>Gap vs newest saved sample</th></tr></thead><tbody>{symbols.map(sym=>{const x=rows.filter(r=>r.symbol===sym);const most=x.at(-1)?.bucket_ms??0;const age=most?Math.max(0,latest-most):null;return <tr key={sym}><td>{sym}</td><td>{x.length}</td><td>{stamp(x[0]!.bucket_ms)}</td><td>{stamp(most)}</td><td>{age===null?"UNKNOWN":(age/3600000).toFixed(1)+"h (snapshot gap)"}</td></tr>})}</tbody></table></section>
 </>}</main>
}
