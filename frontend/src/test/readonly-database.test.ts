// @vitest-environment node
import {describe,it,expect} from "vitest";
import {DatabaseSync} from "node:sqlite";
import {mkdtempSync,rmSync,existsSync,readFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {withReadonlyDatabase} from "@/lib/historical-db";
describe("canonical SQLite read-only boundary",()=>{
 it("reads a temporary fixture but denies writes and preserves bytes",()=>{
  const dir=mkdtempSync(join(tmpdir(),"v2-readonly-")),path=join(dir,"fixture.db");
  try{const seed=new DatabaseSync(path);seed.exec("CREATE TABLE facts(n INTEGER); INSERT INTO facts VALUES(7)");seed.close();const before=readFileSync(path);
   expect(withReadonlyDatabase(path,db=>db.prepare("SELECT n FROM facts").get()?.n)).toBe(7);
   expect(()=>withReadonlyDatabase(path,db=>db.exec("UPDATE facts SET n=99"))).toThrow();
   expect(readFileSync(path)).toEqual(before);
  }finally{rmSync(dir,{recursive:true,force:true})}
 });
 it("a missing source is not silently created",()=>{const dir=mkdtempSync(join(tmpdir(),"v2-missing-")),path=join(dir,"absent.db");try{expect(()=>withReadonlyDatabase(path,()=>null)).toThrow();expect(existsSync(path)).toBe(false)}finally{rmSync(dir,{recursive:true,force:true})}});
});
