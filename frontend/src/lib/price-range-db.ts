import type {DatabaseSync} from "node:sqlite";
import {normalizeRangeSeries,PRICE_RANGES,RAW_PRICE_LIMIT,type PriceRange} from "./price-ranges";
export function readPriceRange(db:DatabaseSync,symbol:string,range:PriceRange,now:number){
 db.exec("BEGIN");
 try{
 const anchor=db.prepare("SELECT bucket_ms timestamp FROM price_samples WHERE symbol=? AND typeof(bucket_ms)='integer' AND bucket_ms>0 AND bucket_ms<=? AND typeof(price) IN ('real','integer') AND price>0 AND price<=? ORDER BY bucket_ms DESC LIMIT 1").get(symbol,now,Number.MAX_VALUE);
 const end=typeof anchor?.timestamp==="number"?anchor.timestamp:null;
 const rows=end===null?[]:db.prepare("SELECT bucket_ms timestamp,price FROM price_samples WHERE symbol=? AND bucket_ms>=? AND bucket_ms<=? ORDER BY bucket_ms DESC LIMIT ?").all(symbol,end-PRICE_RANGES[range],end,RAW_PRICE_LIMIT+1);
 const result=normalizeRangeSeries(rows.slice(0,RAW_PRICE_LIMIT),symbol,range,now,rows.length>RAW_PRICE_LIMIT);
 db.exec("COMMIT");return result;
 }catch(e){db.exec("ROLLBACK");throw e}
}
