import type {PersistedMarket} from "./persisted-market";
import {freshness} from "./persisted-market";
import type {MetricPoint,MoverRow,PulseData,HealthFacts,MarketContextFacts} from "./types";
export function overviewModel(m:PersistedMarket){
 const now=Date.parse(m.readAt),rows=m.rows;
 const point=(value:number|null,unit:string,period:string,asOf:string|null):MetricPoint=>({value,unit,period,asOf,freshness:freshness(asOf===null?null:Date.parse(asOf),now),source:m.source});
 const changes=rows.filter(r=>r.change24hPct!==null),up=changes.filter(r=>r.change24hPct!>0),down=changes.filter(r=>r.change24hPct!<0);
 const metrics={discovered:point(m.eligibleCount,"contracts","last saved scan",m.discoveryAsOf),deepTracked:point(m.available?rows.filter(r=>r.subscribed).length:null,"symbols","retained feature evidence, not live coverage",null),
  topGainer:point(up.length?Math.max(...up.map(r=>r.change24hPct!)):null,"% 24h","retained discovery tops",m.discoveryAsOf),
  topLoser:point(down.length?Math.min(...down.map(r=>r.change24hPct!)):null,"% 24h","retained discovery tops",m.discoveryAsOf),
  activity:{...point(null,"msg/s","current feed",null),unavailable:"No current feed-rate contract. Persisted snapshots do not certify liveness."},
  researchCapture:point(m.available?m.counts.samples:null,"samples","stored price observations",m.latestSampleAsOf)};
 const pulse:PulseData={breadthUp:changes.length?up.length:null,breadthDown:changes.length?down.length:null,breadthTotal:changes.length||null,accelShare:null,observedVol:null,relativeActivity:null,concentrationTop:null,coverageNote:"Retained discovery tops only; this selected subset is NOT market-wide breadth. Deep features have separate timestamps.",asOf:m.discoveryAsOf,freshness:freshness(m.discoveryAsOf===null?null:Date.parse(m.discoveryAsOf),now),source:m.source};
 const movers:MoverRow[]=rows.map(r=>({...r,ret1m:null,flowDelta:null,volZ1m:null})).sort((a,b)=>(b.change24hPct??-Infinity)-(a.change24hPct??-Infinity));
 const context:MarketContextFacts={btcRef:rows.find(r=>r.symbol==="BTCUSDT")?.price??null,ethRef:rows.find(r=>r.symbol==="ETHUSDT")?.price??null,categoriesNote:"References are stored observations; inspect each token for price source and timestamp.",aggregateNote:"Broad-market aggregates and taxonomy: UNKNOWN. Discovery tops are not a complete market census.",providerNote:"Canonical Python SQLite; no external enrichment requested."};
 const health:HealthFacts={recorder:"UNKNOWN",persistence:m.available?"Canonical SQLite readable · "+m.counts.setups+" setups / "+m.counts.outcomes+" outcomes":"SOURCE UNAVAILABLE",feedFreshness:"Current feed: UNKNOWN",wsHealth:"Current WebSocket health: UNKNOWN",lastUpdate:m.latestSampleAsOf,errorsGaps:"Persisted records do not establish current recorder activity or error counters."};
 return {metrics,pulse,movers,context,health,extremes:movers.filter(r=>r.change24hPct!==null&&Math.abs(r.change24hPct)>=15).slice(0,8).map(r=>({symbol:r.symbol,observedChangePct:r.change24hPct,period:"saved 24h",quoteVolume:r.quoteVolume24h,coverage:r.capability,dataAvailable:"Discovery context; inspect token for dated features"}))};
}
