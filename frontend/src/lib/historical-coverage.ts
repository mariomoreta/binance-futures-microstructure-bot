import type {DatabaseSync} from "node:sqlite";
import {withReadonlyDatabase} from "./historical-db";
export const HISTORICAL_DB="C:/proyectos/binance-futures-microstructure-bot/data/historical/historical.db";
export const EVENT_FAMILIES=["EXTENDED_GAINER","EXTENDED_LOSER","MOMENTUM_ACCELERATION_UP","MOMENTUM_ACCELERATION_DOWN","FAILED_HIGH_CANDIDATE","FAILED_LOW_CANDIDATE"] as const;
export const COVERAGE_LIMIT=500,GAP_LIMIT=100,EVENT_LIMIT=50,STUDY_LIMIT=100;
export type HistoryFilter={symbol:string;definition:string};
export function historyFilter(symbol:unknown="",definition:unknown=""):HistoryFilter{
 if(typeof symbol!=="string"||typeof definition!=="string")throw Error("INVALID_HISTORY_FILTER");
 const s=symbol.trim().toUpperCase(),d=definition.trim().toUpperCase();
 if((s&&!/^[A-Z0-9]{2,32}$/.test(s))||(d&&!EVENT_FAMILIES.includes(d as typeof EVENT_FAMILIES[number])))throw Error("INVALID_HISTORY_FILTER");
 return {symbol:s,definition:d};
}
type Row=Record<string,unknown>;
const num=(v:unknown)=>typeof v==="number"&&Number.isFinite(v)?v:null;
const str=(v:unknown)=>typeof v==="string"?v:null;
export type CoverageRow={symbol:string;interval:string;source:string;requested_start:number|null;actual_start:number|null;first_open:number|null;last_open:number|null;expected_bars:number|null;actual_bars:number|null;coverage_ratio:number|null;updated_at:number|null;gap_records:number|null};
export type GapRow={symbol:string;interval:string;source:string;missing_from:number|null;missing_to:number|null;expected_count:number|null};
export type StudyRow={definition:string;version:number|null;horizon:string;n_total:number|null;n_usable:number|null;n_with_return:number|null;mean_forward_return:number|null;first_event_ms:number|null;last_event_ms:number|null};
export type EventRow={event_id:string;symbol:string;definition:string;version:number|null;event_time:number|null;direction:string|null;context:string|null;reference_price:number|null;reference_source:string|null;data_quality:string|null};
export type HistoryCoverage={schema_version:1;historical_schema_version:2|3;available:true;source:"HISTORICAL_SQLITE_READONLY";read_at:string;filter:HistoryFilter;coverage:CoverageRow[];gaps:GapRow[];studies:StudyRow[];events:EventRow[];counts:{contract_bars:number|null;mark_bars:number|null;events:number|null;outcomes:number|null};limits:{coverage:number;gaps:number;studies:number;events:number};truncated:{coverage:boolean;gaps:boolean;studies:boolean;events:boolean};semantics:string};
export function readHistoricalCoverage(db:DatabaseSync,filter:HistoryFilter,readAt=new Date().toISOString()):HistoryCoverage{
 filter=historyFilter(filter.symbol,filter.definition);
 db.exec("BEGIN");
 try{
  const meta=db.prepare("SELECT value FROM history_meta WHERE key='schema_version'").get();
  if(meta?.value!=="2"&&meta?.value!=="3")throw Error("UNSUPPORTED_HISTORICAL_SCHEMA");
  const schema:2|3=meta?.value==="3"?3:2;
  const have=new Set((db.prepare("SELECT name FROM sqlite_master WHERE type='table'").all() as Row[]).map(r=>String(r.name)));
  const required=["historical_coverage","historical_gaps","event_outcomes","event_instances","historical_klines","historical_mark_klines"];
  const missing=required.filter(t=>!have.has(t));
  if(missing.length)throw Error("UNSUPPORTED_HISTORICAL_SCHEMA: absent tables "+missing.join(","));
  const coverageRows=db.prepare(`SELECT c.symbol,c.interval,c.source,c.requested_start,c.actual_start,c.first_open,c.last_open,c.expected_bars,c.actual_bars,c.coverage_ratio,c.updated_at,(SELECT COUNT(*) FROM historical_gaps g WHERE g.symbol=c.symbol AND g.interval=c.interval AND g.source=c.source) gap_records FROM historical_coverage c WHERE (?='' OR c.symbol=?) ORDER BY c.symbol,c.interval,c.source LIMIT ?`).all(filter.symbol,filter.symbol,COVERAGE_LIMIT+1) as Row[];
  const gapRows=db.prepare("SELECT symbol,interval,source,missing_from,missing_to,expected_count FROM historical_gaps WHERE (?='' OR symbol=?) ORDER BY symbol,interval,source,missing_from LIMIT ?").all(filter.symbol,filter.symbol,GAP_LIMIT+1) as Row[];
  const predicate="e.definition_version=1 AND e.definition_name IN ('EXTENDED_GAINER','EXTENDED_LOSER','MOMENTUM_ACCELERATION_UP','MOMENTUM_ACCELERATION_DOWN','FAILED_HIGH_CANDIDATE','FAILED_LOW_CANDIDATE') AND (?='' OR e.symbol=?) AND (?='' OR e.definition_name=?)";
  const params=[filter.symbol,filter.symbol,filter.definition,filter.definition];
  const studyRows=db.prepare(`SELECT e.definition_name,e.definition_version,o.horizon,COUNT(*) n_total,SUM(o.usable_for_statistics) n_usable,COUNT(o.forward_return) n_with_return,AVG(o.forward_return) mean_forward_return,MIN(e.event_time) first_event_ms,MAX(e.event_time) last_event_ms FROM event_outcomes o JOIN event_instances e ON o.event_id=e.event_id WHERE ${predicate} GROUP BY e.definition_name,e.definition_version,o.horizon ORDER BY e.definition_name,CASE o.horizon WHEN '1m' THEN 1 WHEN '3m' THEN 2 WHEN '5m' THEN 3 WHEN '15m' THEN 4 WHEN '30m' THEN 5 WHEN '1h' THEN 6 ELSE 7 END,o.horizon LIMIT ?`).all(...params,STUDY_LIMIT+1) as Row[];
  const eventRows=db.prepare(`SELECT e.event_id,e.symbol,e.definition_name,e.definition_version,e.event_time,e.direction,e.context,e.reference_price,e.reference_source,e.data_quality FROM event_instances e WHERE ${predicate} ORDER BY e.event_time DESC,e.event_id LIMIT ?`).all(...params,EVENT_LIMIT+1) as Row[];
  const count=(sql:string,args:(string|number)[])=>num(db.prepare(sql).get(...args)?.n);
  const counts={contract_bars:count("SELECT COUNT(*) n FROM historical_klines WHERE (?='' OR symbol=?)",[filter.symbol,filter.symbol]),mark_bars:count("SELECT COUNT(*) n FROM historical_mark_klines WHERE (?='' OR symbol=?)",[filter.symbol,filter.symbol]),events:count(`SELECT COUNT(*) n FROM event_instances e WHERE ${predicate}`,params),outcomes:count(`SELECT COUNT(*) n FROM event_outcomes o JOIN event_instances e ON o.event_id=e.event_id WHERE ${predicate}`,params)};
  const result:HistoryCoverage={schema_version:1,historical_schema_version:schema,available:true,source:"HISTORICAL_SQLITE_READONLY",read_at:readAt,filter,
   coverage:coverageRows.slice(0,COVERAGE_LIMIT).map(r=>({symbol:String(r.symbol),interval:String(r.interval),source:String(r.source),requested_start:num(r.requested_start),actual_start:num(r.actual_start),first_open:num(r.first_open),last_open:num(r.last_open),expected_bars:num(r.expected_bars),actual_bars:num(r.actual_bars),coverage_ratio:num(r.coverage_ratio),updated_at:num(r.updated_at),gap_records:num(r.gap_records)})),
   gaps:gapRows.slice(0,GAP_LIMIT).map(r=>({symbol:String(r.symbol),interval:String(r.interval),source:String(r.source),missing_from:num(r.missing_from),missing_to:num(r.missing_to),expected_count:num(r.expected_count)})),
   studies:studyRows.slice(0,STUDY_LIMIT).map(r=>({definition:String(r.definition_name),version:num(r.definition_version),horizon:String(r.horizon),n_total:num(r.n_total),n_usable:num(r.n_usable),n_with_return:num(r.n_with_return),mean_forward_return:num(r.mean_forward_return),first_event_ms:num(r.first_event_ms),last_event_ms:num(r.last_event_ms)})),
   events:eventRows.slice(0,EVENT_LIMIT).map(r=>({event_id:String(r.event_id),symbol:String(r.symbol),definition:String(r.definition_name),version:num(r.definition_version),event_time:num(r.event_time),direction:str(r.direction),context:str(r.context),reference_price:num(r.reference_price),reference_source:str(r.reference_source),data_quality:str(r.data_quality)})),
   counts,limits:{coverage:COVERAGE_LIMIT,gaps:GAP_LIMIT,studies:STUDY_LIMIT,events:EVENT_LIMIT},
   truncated:{coverage:coverageRows.length>COVERAGE_LIMIT,gaps:gapRows.length>GAP_LIMIT,studies:studyRows.length>STUDY_LIMIT,events:eventRows.length>EVENT_LIMIT},
   semantics:"Stored historical research only. Mean forward return is AVG over all non-null stored returns, without filtering usable_for_statistics, matching the legacy backend. Usable counts are separate. Returns are simple price fractions, not fees-adjusted trading P&L. Coverage is the stored interval result, not current feed health. All timestamps are epoch milliseconds; read_at is response time."};
  db.exec("COMMIT");return result;
 }catch(error){db.exec("ROLLBACK");throw error}
}
export const historicalCoverage=(filter:HistoryFilter)=>withReadonlyDatabase(HISTORICAL_DB,db=>readHistoricalCoverage(db,filter));
export function historyUtc(v:number|null){return v!==null&&Number.isSafeInteger(v)&&v>0&&v<=8640000000000000?new Date(v).toISOString():"UNKNOWN"}
export function historyPercent(v:number|null){return v===null||!Number.isFinite(v)||!Number.isFinite(v*100)?"UNKNOWN":(v*100).toFixed(4)+"%"}
