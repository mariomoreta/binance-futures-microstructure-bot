import type {ProspectiveOutcome} from "./prospective-api";
export type QualityFlag="COMPLETE_BUT_UNAUDITED"|"NON_COMPLETE"|"INVALID_TIMESTAMP"|"INVALID_PRICE"|"MISSING_RETURN";
export function qualityOf(x:ProspectiveOutcome):QualityFlag{
 if(x.observed_at_ms!==null&&(!Number.isSafeInteger(x.observed_at_ms)||x.observed_at_ms<1_500_000_000_000||x.observed_at_ms>4_102_444_800_000))return "INVALID_TIMESTAMP";
 if(x.outcome_state!=="COMPLETE")return "NON_COMPLETE";
 if(x.detected_price===null||x.current_price===null||x.detected_price<=0||x.current_price<=0)return "INVALID_PRICE";
 if(x.mark_return_pct===null)return "MISSING_RETURN";
 return "COMPLETE_BUT_UNAUDITED";
}
export function exportOutcomeCsv(rows:readonly ProspectiveOutcome[]):string{
 const cell=(x:unknown)=>{let v=String(x??"");if(/^[=+@\-\t\r]/.test(v))v="'"+v;return '"'+v.replace(/"/g,'""')+'"'};
 const header=["symbol","horizon","outcome_state","quality","detected_price","observed_price","mark_return_pct","observed_at_utc","candidate_key"];
 return [header.map(cell).join(","),...rows.map(x=>[x.symbol,x.horizon,x.outcome_state,qualityOf(x),x.detected_price,x.current_price,x.mark_return_pct,x.observed_at_ms===null?"":new Date(x.observed_at_ms).toISOString(),x.candidate_key].map(cell).join(","))].join("\r\n");
}
