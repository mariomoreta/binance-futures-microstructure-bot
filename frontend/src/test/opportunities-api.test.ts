import {describe,it,expect} from "vitest";import {normalizeOpportunities} from "@/lib/opportunities-api";
describe("read-only opportunity adapter",()=>{const now=1800000000000;const row={candidate_key:"a",symbol:"BTCUSDT",setup_family:"REVERSAL_WATCH",observed_at_ms:now-600000,lifecycle:"DETECTED",direction:"UP",market_state:"REVERSAL",capability_tier:"CORE",rule_version:"v0.1.0",evidence_for:["sample"],evidence_against:[],missing_features:["flow"],ranking:{score:5,interpretation:"research only"},historical_reference:{status:"INSUFFICIENT_HISTORICAL_EVIDENCE"}};
it("marks persisted aged observations stale",()=>{const x=normalizeOpportunities({candidates:[row]},now);expect(x.freshness).toBe("STALE");expect(x.items[0]?.ranking?.score).toBe(5);});
it("does not convert missing metrics to zero",()=>{const x=normalizeOpportunities({candidates:[{...row,ranking:{score:null}}]},now);expect(x.items[0]?.ranking?.score).toBeNull();});
it("ignores invalid identities and future timestamps",()=>{const x=normalizeOpportunities({candidates:[{...row,symbol:"../file"},{...row,observed_at_ms:now+100000}]},now);expect(x.items).toHaveLength(0);expect(x.freshness).toBe("UNKNOWN");});
it("handles empty and malformed input",()=>{expect(normalizeOpportunities({},now).items).toEqual([]);expect(normalizeOpportunities(null,now).freshness).toBe("UNKNOWN");});
});
