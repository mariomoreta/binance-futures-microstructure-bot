// @vitest-environment node
import {it,expect} from "vitest";
import {DatabaseSync} from "node:sqlite";
import {readPriceRange} from "@/lib/price-range-db";
const now=1791720000000,end=now-86400000;
function withDb(fn:(db:DatabaseSync)=>void){const db=new DatabaseSync(":memory:");db.exec("CREATE TABLE price_samples(symbol TEXT,bucket_ms INTEGER,price REAL); CREATE INDEX price_symbol_time ON price_samples(symbol,bucket_ms)");try{fn(db)}finally{db.close()}}
it("native SQLite gates anchor, symbol and selected window in one read transaction",()=>withDb(db=>{const stmt=db.prepare("INSERT INTO price_samples VALUES(?,?,?)");for(const [symbol,t,price] of [["BTCUSDT",end-300001,1],["BTCUSDT",end-300000,2],["BTCUSDT",end,3],["BTCUSDT",end+1,-1],["BTCUSDT",now+1,5],["ETHUSDT",end+1000,6]])stmt.run(symbol as string,t as number,price as number);const s=readPriceRange(db,"BTCUSDT","5m",now);expect(s.points.map(p=>p.price)).toEqual([2,3]);expect(s.observed_end).toBe(new Date(end).toISOString());expect(db.prepare("SELECT COUNT(*) n FROM price_samples").get()!.n).toBe(6)}));
it("native reader reports overflow and bounds a large retained window",()=>withDb(db=>{const stmt=db.prepare("INSERT INTO price_samples VALUES(?,?,?)");db.exec("BEGIN");for(let i=0;i<10005;i++)stmt.run("BTCUSDT",end-10005000+i*1000,10);db.exec("COMMIT");const s=readPriceRange(db,"BTCUSDT","24h",now);expect(s.truncated).toBe(true);expect(s.raw_count).toBe(10000);expect(s.points).toHaveLength(1200);expect(s.gap_count).toBe(0)}));
it("unknown symbols remain empty",()=>withDb(db=>{expect(readPriceRange(db,"ZZZNODATAUSDT","4h",now).points).toEqual([])}));
