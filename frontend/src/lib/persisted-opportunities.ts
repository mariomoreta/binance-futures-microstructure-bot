import type {OpportunityReadModel} from "./opportunities-api";
import {FAMILIES,type Opportunity,type Lifecycle,type Direction} from "./opportunities-domain";
export function recordedOpportunities(m:OpportunityReadModel,now:number):Opportunity[]{
 return m.items.map(x=>({id:x.candidate_key,symbol:x.symbol,family:FAMILIES.includes(x.setup_family as Opportunity["family"])?x.setup_family as Opportunity["family"]:"EXTREME_MOVE_RESEARCH",
  lifecycle:(["DETECTED","WATCHING","ACTIVE_RESEARCH","INVALIDATED","EXPIRED"] as string[]).includes(x.lifecycle)?x.lifecycle as Lifecycle:"UNKNOWN",
  direction:(["UP","DOWN","NONE"] as string[]).includes(x.direction)?x.direction as Direction:"UNKNOWN",
  marketState:x.market_state,tier:x.capability_tier==="CORE"?"CORE":x.capability_tier==="HOT"?"HOT":"UNKNOWN",
  priority:x.ranking?.score??null,asOf:new Date(x.observed_at_ms).toISOString(),freshness:now-x.observed_at_ms>300000?"STALE":"UNKNOWN",
  support:x.evidence_for,against:x.evidence_against,missing:x.missing_features,historical:x.historical_reference?.status??"UNKNOWN",ruleVersion:x.rule_version}));
}
