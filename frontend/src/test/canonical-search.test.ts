// @vitest-environment node
import {it,expect,vi} from "vitest";
vi.mock("@/lib/historical-db",async()=>{
 const {DatabaseSync}=await import("node:sqlite");
 return {canonicalReadTime:()=>"2026-10-11T00:00:00Z",historicalRead:(fn:(db:InstanceType<typeof DatabaseSync>)=>unknown)=>{
 const db=new DatabaseSync(":memory:");
 try{for(const t of ["return_features","flow_features","book_features","oi_features","structure_features","state_features","price_samples","prospective_setups","prospective_outcomes","opportunity_candidates"])db.exec("CREATE TABLE "+t+" (symbol TEXT)");
 db.exec("CREATE TABLE discovery_snapshots(id INTEGER,payload_json TEXT)");
 for(let i=0;i<100;i++)db.prepare("INSERT INTO price_samples VALUES (?)").run("TOK"+i+"USDT");
 db.prepare("INSERT INTO discovery_snapshots VALUES (0,?)").run(JSON.stringify({tops:{gainers:[{symbol:"DISCOVERYUSDT"}]}}));return fn(db);
 }finally{db.close()}
 }};
});
import {canonicalSearch} from "@/lib/canonical-search";
it("queries matching retained history before the output cap",()=>{expect(canonicalSearch("TOK99").symbols).toEqual(["TOK99USDT"]);const d=canonicalSearch("");expect(d.symbols).toHaveLength(50);expect(d.truncated).toBe(true)});
it("merges discovery-only identities without claiming live coverage",()=>{expect(canonicalSearch("DISCOVERY").symbols).toEqual(["DISCOVERYUSDT"]);expect(canonicalSearch("MISSING").symbols).toEqual([])});
it("rejects SQL/wildcard input before scanning the source",()=>{expect(canonicalSearch("%").valid).toBe(false);expect(canonicalSearch("' OR 1=1").symbols).toEqual([])});
