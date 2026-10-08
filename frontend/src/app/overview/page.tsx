import { SectionHeader } from "@/components/shell/SectionHeader";
import { EngineChip, FeedChip, ResearchChip } from "@/components/status/badges";
import { MetricCard } from "@/components/cards/metrics";
import { ResearchOnlyNotice } from "@/components/notices/states";
import { DEMO_ENGINE } from "@/lib/fixtures";
import { DemoDataBanner } from "@/components/shell/AppShell";

export default function OverviewPage() {
  return (
    <div>
      <SectionHeader
        title="Overview"
        aside={
          <>
            <EngineChip state={DEMO_ENGINE.state} />{" "}
            <FeedChip state={DEMO_ENGINE.feed} />{" "}
            <ResearchChip state={DEMO_ENGINE.research} />
          </>
        }
      />
      <DemoDataBanner />
      <div className="v2-grid">
        <MetricCard label="Engine" value={DEMO_ENGINE.state} />
        <MetricCard label="Feed" value={DEMO_ENGINE.feed} />
        <MetricCard label="Research capture" value={DEMO_ENGINE.research} />
      </div>
      <ResearchOnlyNotice>
        Market pulse and external context arrive with the versioned overview
        contract in DASH-V2-01.
      </ResearchOnlyNotice>
    </div>
  );
}
