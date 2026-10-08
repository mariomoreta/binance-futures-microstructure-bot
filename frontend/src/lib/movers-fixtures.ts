import type { ProfessionalMover } from "./movers-domain";
const T="2026-10-07T12:00:00Z",S="demo-fixture / centralized-fixture/movers-v2";
const r=(symbol:string,tier:ProfessionalMover["tier"],capability:ProfessionalMover["capability"],subscribed:boolean,price:number|null,change24hPct:number|null,quoteVolume24h:number|null,velocity1m:number|null,accel1m:number|null,sampleAgeMs:number|null):ProfessionalMover=>({symbol,tier,capability,subscribed,price,change24hPct,quoteVolume24h,velocity1m,accel1m,sampleAgeMs,observedAt:sampleAgeMs===null?null:T,source:S});
export const MOVERS_AS_OF=T;
export const DEMO_PROFESSIONAL_MOVERS:ProfessionalMover[]=[
 r("BTCUSDT","CORE","WARMING",true,97500,2.4,1_900_000_000,1.1e-6,null,12000),r("ETHUSDT","CORE","UNKNOWN",true,null,null,null,null,null,null),
 r("SOLUSDT","CORE","LIVE",true,162.41,8.6,820_000_000,2.8e-6,4.2e-8,4000),r("WIFUSDT","HOT","LIVE",true,3.18,41.2,356_000_000,5.4e-6,7.8e-8,6000),
 r("1000PEPEUSDT","HOT","WARMING",true,.0124,21.7,188_000_000,1.6e-6,2.1e-8,29000),r("DOGEUSDT","DISCOVERY","DISCOVERY ONLY",false,.173,6.1,470_000_000,null,null,78000),
 r("NMRUSDT","HOT","DEGRADED",true,18.7,-18.3,42_000_000,-3.2e-6,-5.1e-8,205000),r("ORCAUSDT","DISCOVERY","DISCOVERY ONLY",false,2.31,-25.1,14_200_000,null,null,91000),
 r("MINAUSDT","DISCOVERY","STALE",false,.48,-7.4,9_800_000,-1.1e-6,-1.4e-8,920000),r("ARBUSDT","DISCOVERY","DISCOVERY ONLY",false,.63,0,112_000_000,null,null,62000),
 r("SEIUSDT","HOT","LIVE",true,.42,-4.8,104_000_000,1.2e-6,-2.5e-8,8000),r("SUIUSDT","HOT","LIVE",true,2.04,13.9,590_000_000,3.1e-6,1.2e-8,5000),
 r("TIAUSDT","DISCOVERY","STALE",false,4.72,-16.4,84_000_000,-1.8e-6,-2.2e-8,1_280_000),r("新币USDT","DISCOVERY","UNKNOWN",false,null,null,null,null,null,null),
 r("XRPUSDT","CORE","DEGRADED",true,.58,3.2,720_000_000,null,null,410000),r("AVAXUSDT","HOT","LIVE",true,31.8,-2.1,132_000_000,-.5e-6,.8e-8,9000),
];
