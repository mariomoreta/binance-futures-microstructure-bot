import {normalizeOpportunities} from "./opportunities-api";
import {recordedOpportunities} from "./persisted-opportunities";
import {historicalRead} from "./historical-db";
import {persistedMarket,recordedToken,type MarketInput,type StoredFeature} from "./persisted-market";
export function canonicalMarket(now=Date.now()){
 try{return historicalRead(db=>{
  db.exec("BEGIN");try{
   const discovery=db.prepare("SELECT updated_ms,payload_json FROM discovery_snapshots WHERE id=0").get() as MarketInput["discovery"]|undefined;
   const features:MarketInput["features"]={};
   for(const table of ["return_features","flow_features","book_features","oi_features","structure_features","state_features"])features[table]=db.prepare("SELECT symbol,updated_ms,feature_json FROM "+table+" ORDER BY symbol LIMIT 500").all() as unknown as StoredFeature[];
   const count=(table:string)=>Number((db.prepare("SELECT COUNT(*) n FROM "+table).get() as {n:number}).n);
   const latestSampleMs=(db.prepare("SELECT MAX(bucket_ms) n FROM price_samples").get() as {n:number|null}).n;
   const data=persistedMarket({discovery:discovery??null,features,counts:{setups:count("prospective_setups"),outcomes:count("prospective_outcomes"),samples:count("price_samples")},latestSampleMs},now);
   db.exec("COMMIT");return data;
  }catch(e){db.exec("ROLLBACK");throw e}
 })}catch{return {...persistedMarket({discovery:null,features:{},counts:{setups:0,outcomes:0,samples:0},latestSampleMs:null},now),available:false}}
}
export const canonicalToken=(symbol:string)=>{const now=Date.now();return recordedToken(canonicalMarket(now),symbol,now)};
export function canonicalOpportunities(){return historicalRead(db=>db.prepare("SELECT candidate_json FROM opportunity_candidates ORDER BY updated_ms DESC LIMIT 200").all().map(r=>{try{return JSON.parse(String(r.candidate_json)) as unknown}catch{return null}}))}

export function canonicalOpportunityView(){const now=Date.now();try{return {available:true,readAt:new Date(now).toISOString(),items:recordedOpportunities(normalizeOpportunities({candidates:canonicalOpportunities()},now),now)}}catch{return {available:false,readAt:new Date(now).toISOString(),items:[]}}}
