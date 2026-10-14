// @vitest-environment node
import {it,expect} from "vitest";
import {DatabaseSync} from "node:sqlite";
import {mkdtempSync,readFileSync,rmSync,existsSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {readSystemEvidence,systemUtc} from "@/lib/system-evidence";
import {withReadonlyDatabase} from "@/lib/historical-db";
function fixture(path=":memory:"){
 const db=new DatabaseSync(path);
 db.exec(`CREATE TABLE persistence_meta(key TEXT,value TEXT);INSERT INTO persistence_meta VALUES('schema_version','9');
 CREATE TABLE discovery_snapshots(id INTEGER,updated_ms INTEGER,payload_json TEXT);
 CREATE TABLE telemetry_snapshots(timestamp REAL);INSERT INTO telemetry_snapshots VALUES(1234);
 CREATE TABLE price_samples(bucket_ms INTEGER);INSERT INTO price_samples VALUES(4567890);
 CREATE TABLE prospective_setups(detected_at_ms INTEGER);INSERT INTO prospective_setups VALUES(5000);
 CREATE TABLE prospective_outcomes(observed_at_ms INTEGER,outcome_state TEXT);INSERT INTO prospective_outcomes VALUES(6000,'COMPLETE'),(7000,'PENDING');
 CREATE TABLE state_features(updated_ms INTEGER,feature_json TEXT);
 CREATE TABLE opportunity_candidates(updated_ms INTEGER,candidate_json TEXT);
 CREATE TABLE opportunity_events(id INTEGER);CREATE TABLE state_transitions(id INTEGER);CREATE TABLE universe_events(id INTEGER,detail TEXT);
 INSERT INTO state_features VALUES(1000,'{"state":"NORMAL","rules_version":"v0.1"}'),(9000,'{"state":"REVERSAL","rules_version":"v0.2"}');
 INSERT INTO opportunity_candidates VALUES(2000,'{"lifecycle":"WATCHING","rule_version":"v0.1"}'),(8000,'{"lifecycle":"ACTIVE_RESEARCH","rule_version":"v0.1"}');`);
 return db;
}
function run(fn:(db:DatabaseSync)=>void){const db=fixture();try{fn(db)}finally{db.close()}}
it("reads exact independent populations and units",()=>run(db=>{
 const s=readSystemEvidence(db,"2026-01-01T00:00:00Z");
 expect(s.research).toMatchObject({setups:1,outcomes:2,complete_outcomes:1,latest_setup_ms:5000,latest_outcome_ms:7000});
 expect(s.persistence).toMatchObject({telemetry_rows:1,price_rows:1,last_telemetry_ms:1234000,last_price_ms:4567890});
 expect(s.classifier.span).toEqual({first_ms:1000,last_ms:9000});expect(s.opportunities.span).toEqual({first_ms:2000,last_ms:8000});
 expect(s.read_at).toBe("2026-01-01T00:00:00Z");expect(s.classifier.states).toContainEqual({label:"NORMAL",count:1});
}));
it("preserves zero HOT lists and deduplicates genuine symbol lists",()=>run(db=>{
 db.prepare("INSERT INTO discovery_snapshots VALUES(0,123,?)").run(JSON.stringify({core:["BTCUSDT","BTCUSDT"],hot_dynamic:[],hot_subscribed:[],eligible_count:0}));
 expect(readSystemEvidence(db).universe).toEqual({updated_ms:123,core:1,hot_dynamic:0,hot_subscribed:0,eligible:0,unverified_test_detail_rows:0});
}));
it("missing discovery does not manufacture empty allocations",()=>run(db=>{
 expect(readSystemEvidence(db).universe).toEqual({updated_ms:null,core:null,hot_dynamic:null,hot_subscribed:null,eligible:null,unverified_test_detail_rows:0});
}));
it("invalid payload and malformed lists preserve unknown",()=>run(db=>{
 db.prepare("INSERT INTO discovery_snapshots VALUES(0,123,?)").run(JSON.stringify({core:["BTCUSDT",null],hot_dynamic:false,eligible_count:-1}));
 expect(readSystemEvidence(db).universe).toMatchObject({core:null,hot_dynamic:null,eligible:null,unverified_test_detail_rows:0});
 db.exec("UPDATE discovery_snapshots SET payload_json='['");
 expect(readSystemEvidence(db).universe.core).toBeNull();
}));
it("aggregates all retained lifecycles including malformed candidates without inventing live activity",()=>run(db=>{
 db.prepare("INSERT INTO opportunity_candidates VALUES(3000,?)").run("[");
 const s=readSystemEvidence(db);
 expect(s.opportunities.records).toBe(3);expect(s.opportunities.lifecycles).toContainEqual({label:"UNKNOWN",count:1});
 expect(s.opportunities.lifecycles).toContainEqual({label:"ACTIVE_RESEARCH",count:1});
}));
it("bounds distinct version output and flags overflow",()=>run(db=>{
 const add=db.prepare("INSERT INTO state_features VALUES(1000,?)");
 for(let i=0;i<25;i++)add.run(JSON.stringify({state:"IGNITION",rules_version:"v"+i}));
 const s=readSystemEvidence(db);expect(s.classifier.versions).toHaveLength(20);expect(s.classifier.versions_truncated).toBe(true);
 expect(s.classifier.states.reduce((sum,x)=>sum+x.count,0)).toBe(27);
}));
it("empty retained tables are real zero with unknown dates",()=>run(db=>{
 db.exec("DELETE FROM prospective_setups;DELETE FROM prospective_outcomes;DELETE FROM state_features");
 const s=readSystemEvidence(db);expect(s.research.setups).toBe(0);expect(s.research.latest_setup_ms).toBeNull();expect(s.classifier.states).toEqual([]);
}));
it("rejects unsupported schemas and rolls back cleanly",()=>run(db=>{
 db.exec("UPDATE persistence_meta SET value='99'");expect(()=>readSystemEvidence(db)).toThrow("UNSUPPORTED_SYSTEM_SCHEMA");
 db.exec("UPDATE persistence_meta SET value='9'");expect(readSystemEvidence(db).available).toBe(true);
}));
it("accepts schema 10 with the actual version recorded",()=>run(db=>{
 db.exec("UPDATE persistence_meta SET value='10'");
 const s=readSystemEvidence(db);expect(s.available).toBe(true);expect(s.persistence.schema).toBe(10);
}));
it("rejects absent tables without substituting values",()=>run(db=>{
 db.exec("DROP TABLE price_samples");
 expect(()=>readSystemEvidence(db)).toThrow(/absent tables price_samples/);
}));
it("readonly access preserves file bytes and does not create missing storage",()=>{
 const dir=mkdtempSync(join(tmpdir(),"v2-system-")),path=join(dir,"store.db"),missing=join(dir,"absent.db");
 try{fixture(path).close();const before=readFileSync(path);
 expect(withReadonlyDatabase(path,db=>readSystemEvidence(db)).research.outcomes).toBe(2);
 expect(readFileSync(path)).toEqual(before);expect(()=>withReadonlyDatabase(missing,db=>readSystemEvidence(db))).toThrow();expect(existsSync(missing)).toBe(false);
 }finally{rmSync(dir,{recursive:true,force:true})}
});
it("UTC formatting preserves absence",()=>{expect(systemUtc(null)).toBe("UNKNOWN");expect(systemUtc(0)).toBe("1970-01-01T00:00:00.000Z")});

it("marks test-tagged universe rows without deleting or silently excluding them",()=>run(db=>{
 db.exec("INSERT INTO universe_events VALUES(1,'test'),(2,'ordinary'),(3,'test')");
 const s=readSystemEvidence(db);expect(s.research.universe_events).toBe(3);expect(s.universe.unverified_test_detail_rows).toBe(2);
 expect(db.prepare("SELECT COUNT(*) n FROM universe_events").get()!.n).toBe(3);
}));
