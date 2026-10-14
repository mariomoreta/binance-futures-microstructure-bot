import type {
  Capability,
  EngineState,
  FeedState,
  ResearchState,
  Tier,
} from "@/lib/types";

type Tone = "pos" | "neg" | "warn" | "info" | "muted";

export function StatusChip({
  label,
  tone = "muted",
  testId,
}: {
  label: string;
  tone?: Tone;
  testId?: string;
}) {
  return (
    <span className="v2-chip" data-tone={tone} data-testid={testId ?? "chip"}>
      {label}
    </span>
  );
}

const ENGINE_TONE: Record<EngineState, Tone> = {
  UNKNOWN: "muted",
  RUNNING: "pos",
  COMPLETED: "info",
  STARTING: "warn",
  STOPPING: "warn",
  STOPPED: "muted",
  FAILED: "neg",
};

const FEED_TONE: Record<FeedState, Tone> = {
  HEALTHY: "pos",
  DEGRADED: "warn",
  STALE: "warn",
  UNKNOWN: "muted",
};

const RESEARCH_TONE: Record<ResearchState, Tone> = {
  RUNNING: "pos",
  DEGRADED: "warn",
  STOPPED: "muted",
  UNKNOWN: "muted",
};

const CAPABILITY_TONE: Record<Capability, Tone> = {
  LIVE: "pos",
  WARMING: "warn",
  "DISCOVERY ONLY": "info",
  STALE: "warn",
  DEGRADED: "warn",
  UNKNOWN: "muted",
};

export function EngineChip({ state }: { state: EngineState }) {
  return (
    <StatusChip label={`ENGINE ${state}`} tone={ENGINE_TONE[state]} testId="engine-chip" />
  );
}

export function FeedChip({ state }: { state: FeedState }) {
  return (
    <StatusChip label={`FEED ${state}`} tone={FEED_TONE[state]} testId="feed-chip" />
  );
}

export function ResearchChip({ state }: { state: ResearchState }) {
  return (
    <StatusChip
      label={`RESEARCH ${state}`}
      tone={RESEARCH_TONE[state]}
      testId="research-chip"
    />
  );
}

export function TierBadge({ tier }: { tier: Tier }) {
  return <StatusChip label={tier} tone="muted" testId="tier-badge" />;
}

export function DataStateBadge({
  capability,
}: {
  capability: Capability;
}) {
  return (
    <StatusChip
      label={capability}
      tone={CAPABILITY_TONE[capability]}
      testId="capability-badge"
    />
  );
}
