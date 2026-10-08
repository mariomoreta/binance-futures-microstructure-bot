"use client";
import Link from "next/link";
import {formatCompact,formatSignedPct} from "@/lib/format";
import type {ProfessionalMover,MoversFiltersState} from "@/lib/movers-domain";
import s from "./MoversLeaderboards.module.css";
type Metric="change24hPct"|"quoteVolume24h"|"velocity1m"|"accel1m";
type Board={title:string;caption:string;metric:Metric;dir:"asc"|"desc";unit:string;scope:"discovery"|"deep";interest?:MoversFiltersState["interest"]};
const boards:Board[]=[
{title:"Top Gainers 24h",caption:"Discovery · REST 24h",metric:"change24hPct",dir:"desc",unit:"pct",scope:"discovery",interest:"EXTREME_GAINERS"},
{title:"Top Losers 24h",caption:"Discovery · REST 24h",metric:"change24hPct",dir:"asc",unit:"pct",scope:"discovery",interest:"EXTREME_LOSERS"},
{title:"Highest 24h Activity",caption:"Discovery · quote notional",metric:"quoteVolume24h",dir:"desc",unit:"volume",scope:"discovery",interest:"HIGH_VOLUME"},
{title:"Fastest Positive Velocity",caption:"Deep coverage only",metric:"velocity1m",dir:"desc",unit:"velocity",scope:"deep"},
{title:"Fastest Negative Velocity",caption:"Deep coverage only",metric:"velocity1m",dir:"asc",unit:"velocity",scope:"deep"},
{title:"Acceleration Leaders",caption:"Deep coverage only",metric:"accel1m",dir:"desc",unit:"acceleration",scope:"deep",interest:"ACCELERATING_UP"},
{title:"Deceleration Leaders",caption:"Deep coverage only",metric:"accel1m",dir:"asc",unit:"acceleration",scope:"deep",interest:"ACCELERATING_DOWN"},
{title:"Deep Data Coverage",caption:"Subscribed contracts · velocity",metric:"velocity1m",dir:"desc",unit:"velocity",scope:"deep"},
];
export function rankBoard(rows:readonly ProfessionalMover[],board:Board){
 return rows.filter(x=>board.scope==="discovery"||(x.subscribed&&x.tier!=="DISCOVERY")).filter(x=>typeof x[board.metric]==="number"&&Number.isFinite(x[board.metric])).sort((a,b)=>{const av=a[board.metric] as number,bv=b[board.metric] as number;return (board.dir==="asc"?av-bv:bv-av)||a.symbol.localeCompare(b.symbol)}).slice(0,5);
}
export function MoversLeaderboards({rows,onSelect}:{rows:readonly ProfessionalMover[];onSelect:(interest:MoversFiltersState["interest"])=>void}){
 return <section className={s.section} aria-label="Market research leaderboards"><div className={s.heading}><h2>Market activity &amp; momentum</h2><p>Rankings computed only from available DEMO fields · no invented history or sparklines</p></div><div className={s.grid}>{boards.map(board=>{const leaders=rankBoard(rows,board);return <article className={s.board} key={board.title}><header><h3>{board.title}</h3><small>{board.caption}</small></header>{leaders.length?<ol>{leaders.map((row,i)=>{const v=row[board.metric] as number;return <li key={row.symbol}><span className={s.rank}>{i+1}</span><Link href={`/symbol/${row.symbol}`}>{row.symbol}</Link><strong data-sign={v>0?"positive":v<0?"negative":"zero"}>{board.unit==="pct"?formatSignedPct(v):board.unit==="volume"?formatCompact(v):v.toExponential(2)+(board.unit==="acceleration"?"/s²":"/s")}</strong></li>})}</ol>:<p className={s.empty}>INSUFFICIENT DATA — no comparable observations</p>}{board.interest?<button type="button" className={s.action} onClick={()=>onSelect(board.interest!)}>Filter corresponding research interest →</button>:<span className={s.footer}>No signal or outcome implied</span>}</article>})}</div></section>
}
