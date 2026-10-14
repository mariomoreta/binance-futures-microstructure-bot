import type {ProfessionalMover} from "@/lib/movers-domain";
import s from "./MoversMarketPulse.module.css";
export function MoversMarketPulse({rows}:{rows:readonly ProfessionalMover[]}){
 const valid=rows.filter(r=>r.change24hPct!==null);
 const gain=valid.filter(r=>(r.change24hPct as number)>0).length;
 const loss=valid.filter(r=>(r.change24hPct as number)<0).length;
 const neutral=valid.length-gain-loss;
 const unknown=rows.length-valid.length;
 const total=Math.max(rows.length,1);
 const deep=rows.filter(r=>r.subscribed&&r.tier!=="DISCOVERY").length;
 return <section className={s.pulse} aria-label="Retained subset direction">
 <div className={s.header}><div><strong>Retained subset <span>· HISTORICAL</span></strong><p>24h direction across {valid.length} measured retained contracts; {unknown} unavailable</p></div><div className={s.legend}><span className={s.pos}>▲ {gain} gainers</span><span className={s.neg}>▼ {loss} losers</span><span>{neutral} flat</span><span>{unknown} unknown</span></div></div>
 <div className={s.track} role="img" aria-label={`Retained subset direction: ${gain} rising, ${loss} falling, ${neutral} unchanged, ${unknown} unknown`}><span className={s.green} style={{width:`${gain/total*100}%`}}/><span className={s.red} style={{width:`${loss/total*100}%`}}/><span className={s.flat} style={{width:`${neutral/total*100}%`}}/><span className={s.missing} style={{width:`${unknown/total*100}%`}}/></div>
 <div className={s.footer}><span>RETAINED DEEP EVIDENCE {deep} / {rows.length}</span><span>DISCOVERY IS NOT DEEP LIVE</span><span>SELECTED TOPS ONLY · NOT MARKET-WIDE BREADTH</span></div></section>;
}
