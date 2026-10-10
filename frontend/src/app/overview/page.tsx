import s from "./Overview.module.css";
export const dynamic="force-dynamic";
import {RuntimeDiagnostics} from "@/components/system/RuntimeDiagnostics";
import { TopBar } from "@/components/overview/TopBar";
import { OverviewMetricGrid } from "@/components/overview/OverviewMetricGrid";
import { MarketPulsePanel } from "@/components/overview/MarketPulsePanel";
import { MoversSnapshot } from "@/components/overview/MoversSnapshot";
import { ExtremeMoveWatch } from "@/components/overview/ExtremeMoveWatch";
import { ResearchHealthPanel } from "@/components/overview/ResearchHealthPanel";
import { MarketContextPanel } from "@/components/overview/MarketContextPanel";
import { ResearchOnlyNotice } from "@/components/notices/states";
import {
  DEMO_CONTEXT,
  DEMO_ENGINE,
  DEMO_EXTREMES,
  DEMO_HEALTH,
  DEMO_METRICS,
  DEMO_MOVERS,
  DEMO_PULSE,
} from "@/lib/fixtures";

export default function OverviewPage() {
  return (
    <div className={s.root}>
      <TopBar
        engine={DEMO_ENGINE.state}
        feed={DEMO_ENGINE.feed}
        research={DEMO_ENGINE.research}
        lastData="last data: — (demo)"
      />
      <ResearchOnlyNotice>
        Demo composition. Every panel below renders labeled fixtures until
        the versioned overview contract lands in a later slice.
      </ResearchOnlyNotice>
      <OverviewMetricGrid metrics={DEMO_METRICS} />
      <div className={s.context}><MarketPulsePanel pulse={DEMO_PULSE} /><MarketContextPanel context={DEMO_CONTEXT} /></div>
      <MoversSnapshot rows={DEMO_MOVERS} />
      <div className={s.research}><ExtremeMoveWatch rows={DEMO_EXTREMES} /><ResearchHealthPanel health={DEMO_HEALTH} /><RuntimeDiagnostics compact /></div>
    </div>
  );
}
