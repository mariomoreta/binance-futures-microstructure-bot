import {describe,it,expect} from "vitest";
import {searchQuery,searchSymbols} from "@/lib/symbol-search";
describe("retained symbol search",()=>{
 it("normalizes case and rejects query injection/wildcards/unsupported identities",()=>{expect(searchQuery(" btc ").query).toBe("BTC");for(const q of ["%","BTC';DROP","币USDT","a".repeat(33)])expect(searchQuery(q).valid).toBe(false)});
 it("finds fragments, removes duplicates and favors exact/prefix matches",()=>{expect(searchSymbols(["XBTCUSDT","BTCUSDT","BTC","BTCUSDT","BAD/USDT"],"BTC").symbols).toEqual(["BTC","BTCUSDT","XBTCUSDT"])});
 it("bounds large result sets and reports truncation",()=>{const r=searchSymbols(Array.from({length:100},(_,i)=>"TOK"+i+"USDT"),"");expect(r.symbols).toHaveLength(50);expect(r.truncated).toBe(true)});
 it("does not supply fixture rows for no matches",()=>expect(searchSymbols(["BTCUSDT"],"ZZZ").symbols).toEqual([]));
});
