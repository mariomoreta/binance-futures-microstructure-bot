// @vitest-environment node
import {it,expect} from "vitest";
import {DatabaseSync} from "node:sqlite";
import {mkdtempSync,rmSync,existsSync,readFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {withReadonlyDatabase} from "@/lib/historical-db";
import {readHistoricalCoverage,historyFilter,historyPercent,historyUtc} from "@/lib/historical-coverage";
function fixture(path=":memory:"){
 const db=new DatabaseSync(path);db.exec(`
 CREATE TABLE history_meta(key TEXT,value TEXT);INSERT INTO history_meta VALUES('schema_version','2');
 CREATE TABLE historical_coverage(symbol TEXT,interval TEXT,source TEXT,requested_start INTEGER,actual_start INTEGER,first_open INTEGER,last_open INTEGER,expected_bars INTEGER,actual_bars INTEGER,coverage_ratio REAL,updated_at INTEGER);
 CREATE TABLE historical_gaps(symbol TEXT,interval TEXT,source TEXT,missing_from INTEGER,missing_to INTEGER,expected_count INTEGER);
 CREATE TABLE historical_klines(symbol TEXT);CREATE TABLE historical_mark_klines(symbol TEXT);
 CREATE TABLE event_instances(event_id TEXT,symbol TEXT,definition_name TEXT,definition_version INTEGER,event_time INTEGER,direction TEXT,context TEXT,reference_price REAL,reference_source TEXT,data_quality TEXT);
 CREATE TABLE event_outcomes(event_id TEXT,horizon TEXT,forward_return REAL,usable_for_statistics INTEGER);
 INSERT INTO historical_coverage VALUES('BTCUSDT','1h','klines',1000,500,NULL,NULL,0,0,NULL,2000);
 INSERT INTO historical_coverage VALUES('ETHUSDT','1h','klines',1000,500,1000,2000,2,2,1,2000);
 INSERT INTO historical_gaps VALUES('BTCUSDT','1h','klines',1000,2000,2);
 INSERT INTO historical_klines VALUES('BTCUSDT');INSERT INTO historical_mark_klines VALUES('ETHUSDT');
 INSERT INTO event_instances VALUES('a','BTCUSDT','EXTENDED_GAINER',1,1000,'up','HISTORICAL_MOMENTUM_PROXY',10,'mark_klines',NULL),('b','BTCUSDT','EXTENDED_GAINER',1,2000,'up',NULL,20,'klines','PARTIAL'),('c','ETHUSDT','EXTENDED_GAINER',1,3000,'up',NULL,NULL,NULL,NULL),('v2','BTCUSDT','EXTENDED_GAINER',2,4000,'up',NULL,30,'klines',NULL),('other','BTCUSDT','UNKNOWN_FAMILY',1,5000,NULL,NULL,30,NULL,NULL);
 INSERT INTO event_outcomes VALUES('a','1m',0.1,1),('b','1m',0.3,0),('c','1m',NULL,0),('v2','1m',1,1),('other','1m',1,1);`);
 return db;
}
function run(fn:(db:DatabaseSync)=>void){const db=fixture();try{fn(db)}finally{db.close()}}
it("preserves zero coverage and null span without inferring current completeness",()=>run(db=>{const s=readHistoricalCoverage(db,historyFilter());expect(s.coverage[0]).toMatchObject({actual_bars:0,expected_bars:0,coverage_ratio:null,first_open:null,gap_records:1});expect(s.coverage[1]?.coverage_ratio).toBe(1);expect(s.historical_schema_version).toBe(2);expect(s.counts).toMatchObject({events:3,outcomes:3})}));
it("matches legacy unfiltered mean population while reporting usable/nonnull counts separately",()=>run(db=>{const s=readHistoricalCoverage(db,historyFilter());expect(s.studies).toHaveLength(1);expect(s.studies[0]).toMatchObject({n_total:3,n_usable:1,n_with_return:2,first_event_ms:1000,last_event_ms:3000});expect(s.studies[0]?.mean_forward_return).toBeCloseTo(0.2);expect(s.events.some(x=>x.event_id==="v2"||x.event_id==="other")).toBe(false)}));
it("exact symbol filter applies before all limits and definition only filters research",()=>run(db=>{const s=readHistoricalCoverage(db,historyFilter(" ethusdt ","EXTENDED_GAINER"));expect(s.coverage.map(x=>x.symbol)).toEqual(["ETHUSDT"]);expect(s.gaps).toEqual([]);expect(s.counts).toEqual({contract_bars:0,mark_bars:1,events:1,outcomes:1});expect(s.studies[0]?.mean_forward_return).toBeNull();expect(s.events[0]?.symbol).toBe("ETHUSDT")}));
it("unknown symbols remain empty rather than inheriting another dataset",()=>run(db=>{const s=readHistoricalCoverage(db,historyFilter("ZZZNODATAUSDT"));expect(s.coverage).toEqual([]);expect(s.studies).toEqual([]);expect(s.events).toEqual([]);expect(s.counts.events).toBe(0)}));
it("bounds recent events, coverage and gaps with honest overflow flags",()=>run(db=>{db.exec("BEGIN");const cov=db.prepare("INSERT INTO historical_coverage VALUES(?,'1h','klines',1,1,1,2,1,1,1,2)"),gap=db.prepare("INSERT INTO historical_gaps VALUES('BTCUSDT','1h','klines',?,?,1)"),event=db.prepare("INSERT INTO event_instances VALUES(?,'BTCUSDT','EXTENDED_GAINER',1,?,'up',NULL,1,NULL,NULL)");for(let i=0;i<501;i++)cov.run("Z"+i);for(let i=0;i<101;i++)gap.run(i+1,i+2);for(let i=0;i<60;i++)event.run("z"+i,i+10000);db.exec("COMMIT");const s=readHistoricalCoverage(db,historyFilter());expect(s.coverage).toHaveLength(500);expect(s.gaps).toHaveLength(100);expect(s.events).toHaveLength(50);expect(s.truncated).toMatchObject({coverage:true,gaps:true,events:true});expect(s.events[0]?.event_time).toBe(10059)}));
it("rejects unsafe or unsupported filters and schema before returning a dataset",()=>{expect(()=>historyFilter("BTC'; DROP TABLE")).toThrow();expect(()=>historyFilter("龙虾USDT")).toThrow();expect(()=>historyFilter("BTCUSDT","made_up")).toThrow();expect(()=>historyFilter(["BTCUSDT"])).toThrow();run(db=>{db.exec("UPDATE history_meta SET value='99'");expect(()=>readHistoricalCoverage(db,historyFilter())).toThrow("UNSUPPORTED_HISTORICAL_SCHEMA");expect(db.prepare("SELECT COUNT(*) n FROM historical_coverage").get()!.n).toBe(2)})});
it("accepts schema 3 with the actual version recorded",()=>run(db=>{db.exec("UPDATE history_meta SET value='3'");const s=readHistoricalCoverage(db,historyFilter());expect(s.historical_schema_version).toBe(3);expect(s.coverage).toHaveLength(2)}));
it("rejects absent tables without substituting values",()=>run(db=>{db.exec("DROP TABLE historical_gaps");expect(()=>readHistoricalCoverage(db,historyFilter())).toThrow(/absent tables historical_gaps/)}));
it("readonly historical presentation preserves bytes and never creates absent storage",()=>{const dir=mkdtempSync(join(tmpdir(),"v2-history-")),path=join(dir,"historical.db"),missing=join(dir,"absent.db");try{fixture(path).close();const before=readFileSync(path);const s=withReadonlyDatabase(path,db=>readHistoricalCoverage(db,historyFilter()));expect(s.coverage).toHaveLength(2);expect(readFileSync(path)).toEqual(before);expect(()=>withReadonlyDatabase(path,db=>db.exec("DELETE FROM event_instances"))).toThrow();expect(()=>withReadonlyDatabase(missing,db=>readHistoricalCoverage(db,historyFilter()))).toThrow();expect(existsSync(missing)).toBe(false)}finally{rmSync(dir,{force:true,recursive:true})}});
it("formats raw simple returns as percentages while preserving zero and unknown",()=>{expect(historyPercent(0)).toBe("0.0000%");expect(historyPercent(-0.05)).toBe("-5.0000%");expect(historyPercent(null)).toBe("UNKNOWN");expect(historyPercent(Infinity)).toBe("UNKNOWN");expect(historyUtc(null)).toBe("UNKNOWN");expect(historyUtc(NaN)).toBe("UNKNOWN");expect(historyUtc(1000)).toBe("1970-01-01T00:00:01.000Z")});
