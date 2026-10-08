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
    <div>
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
      <MarketPulsePanel pulse={DEMO_PULSE} />
      <MoversSnapshot rows={DEMO_MOVERS} />
      <ExtremeMoveWatch rows={DEMO_EXTREMES} />
      <ResearchHealthPanel health={DEMO_HEALTH} />
      <MarketContextPanel context={DEMO_CONTEXT} />
    </div>
  );
}
