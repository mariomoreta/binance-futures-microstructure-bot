import Link from "next/link";
import {canonicalSearch} from "@/lib/canonical-search";
export const dynamic="force-dynamic";export const runtime="nodejs";
export default async function SearchPage({searchParams}:{searchParams:Promise<{q?:string|string[]}>}){
 const {q}=await searchParams;const data=canonicalSearch(typeof q==="string"?q:"");
 return <section className="v2-records"><h1>Symbol search</h1><p className="v2-muted">Retained Python / SQLite records and saved discovery tops. This archive is not the current Binance contract universe.</p>
 <form action="/search" className="v2-search-form"><label htmlFor="symbol-query">Symbol or fragment</label><input id="symbol-query" name="q" defaultValue={data.query} maxLength={32} placeholder="BTC, LUMIA..." autoComplete="off"/><button type="submit">Search records</button></form>
 <p className="v2-muted">Read: {data.readAt} / read only / ASCII identity support</p>
 {!data.valid?<p role="alert">Use up to 32 letters A-Z or digits. Other contract identities are not supported by this version.</p>:!data.available?<p role="alert">Canonical source unavailable. No demo results substituted.</p>:<>
 <p>{data.symbols.length} displayed{data.truncated?" / capped at 50; narrow your query":""}. A retained record does not establish current subscription, live health or token identity.</p>
 <div className="v2-table-wrapper"><table className="v2-table v2-search-table"><caption>Matching retained symbols</caption><thead><tr><th>Symbol</th><th>Evidence scope</th><th>Inspect</th></tr></thead><tbody>{data.symbols.map(symbol=><tr key={symbol}><th scope="row">{symbol}</th><td>Saved records / current coverage unverified</td><td><Link href={"/symbol/"+symbol}>Open {symbol}</Link></td></tr>)}{data.symbols.length===0?<tr><td colSpan={3}>No matching retained records.</td></tr>:null}</tbody></table></div></>}
 </section>;
}
