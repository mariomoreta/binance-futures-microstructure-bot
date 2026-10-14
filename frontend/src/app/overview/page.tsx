import s from "./Overview.module.css";
import {RuntimeDiagnostics} from "@/components/system/RuntimeDiagnostics";
import {TopBar} from "@/components/overview/TopBar";
import {OverviewMetricGrid} from "@/components/overview/OverviewMetricGrid";
import {MarketPulsePanel} from "@/components/overview/MarketPulsePanel";
import {MoversSnapshot} from "@/components/overview/MoversSnapshot";
import {ExtremeMoveWatch} from "@/components/overview/ExtremeMoveWatch";
import {ResearchHealthPanel} from "@/components/overview/ResearchHealthPanel";
import {MarketContextPanel} from "@/components/overview/MarketContextPanel";
import {ResearchOnlyNotice} from "@/components/notices/states";
import {SnapshotRefresh} from "@/components/notices/SnapshotRefresh";
import {canonicalMarket} from "@/lib/canonical-market";
import {overviewModel} from "@/lib/overview-model";
export const dynamic="force-dynamic";export const runtime="nodejs";
export default function OverviewPage(){
 const m=canonicalMarket(),v=overviewModel(m);
 return <div className={s.root}>
 <TopBar engine="UNKNOWN" feed="UNKNOWN" research="UNKNOWN" lastData={"Discovery: "+(m.discoveryAsOf??"UNKNOWN")} demo={false}/>
 <SnapshotRefresh readAt={m.readAt} available={m.available}/>
 <ResearchOnlyNotice>Saved Python observations · historical, not current quotes. Runtime and feed health are evaluated separately below.</ResearchOnlyNotice>
 <OverviewMetricGrid metrics={v.metrics}/>
 <div className={s.context}><MarketPulsePanel pulse={v.pulse}/><MarketContextPanel context={v.context}/></div>
 <MoversSnapshot rows={v.movers}/>
 <div className={s.research}><ExtremeMoveWatch rows={v.extremes}/><ResearchHealthPanel health={v.health}/><RuntimeDiagnostics compact/></div>
 </div>;
}
