import {describe,it,expect} from "vitest";
import {exportOutcomeCsv,qualityOf} from "@/lib/prospective-quality";
import type {ProspectiveOutcome} from "@/lib/prospective-api";
const base:ProspectiveOutcome={candidate_key:"case-1",symbol:"BTCUSDT",horizon:"1m",outcome_state:"COMPLETE",observed_at_ms:1791500000000,mark_return_pct:0.3,detected_price:100,current_price:100.3,reason:"research"};
describe("prospective evidence integrity",()=>{
 it("never equates complete with verified freshness",()=>expect(qualityOf(base)).toBe("COMPLETE_BUT_UNAUDITED"));
 it("marks missing prices or returns",()=>{expect(qualityOf({...base,current_price:null})).toBe("INVALID_PRICE");expect(qualityOf({...base,mark_return_pct:null})).toBe("MISSING_RETURN")});
 it("rejects implausible timestamps and never labels pending complete",()=>{expect(qualityOf({...base,observed_at_ms:42})).toBe("INVALID_TIMESTAMP");expect(qualityOf({...base,outcome_state:"PENDING"})).toBe("NON_COMPLETE")});
 it("CSV escapes spreadsheet-formula input and only includes supplied filtered rows",()=>{const csv=exportOutcomeCsv([{...base,symbol:"=IMPORT",candidate_key:"-danger"}]);expect(csv).toContain("'=IMPORT");expect(csv).toContain("'-danger");expect(csv.split("\r\n")).toHaveLength(2)});
});