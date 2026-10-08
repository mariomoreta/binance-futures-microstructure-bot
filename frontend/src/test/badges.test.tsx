import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  DataStateBadge,
  EngineChip,
  FeedChip,
  ResearchChip,
  TierBadge,
} from "@/components/status/badges";

describe("state badges", () => {
  it("keeps engine, feed, and research states distinct", () => {
    render(
      <>
        <EngineChip state="RUNNING" />
        <FeedChip state="HEALTHY" />
        <ResearchChip state="UNKNOWN" />
      </>,
    );
    expect(screen.getByTestId("engine-chip")).toHaveTextContent(
      "ENGINE RUNNING",
    );
    expect(screen.getByTestId("feed-chip")).toHaveTextContent("FEED HEALTHY");
    expect(screen.getByTestId("research-chip")).toHaveTextContent(
      "RESEARCH UNKNOWN",
    );
  });

  it("renders tier and capability as neutral text plus tone", () => {
    render(
      <>
        <TierBadge tier="DISCOVERY" />
        <DataStateBadge capability="DISCOVERY ONLY" />
      </>,
    );
    expect(screen.getByTestId("tier-badge")).toHaveTextContent("DISCOVERY");
    expect(screen.getByTestId("capability-badge")).toHaveTextContent(
      "DISCOVERY ONLY",
    );
  });

  it("uses text, not color alone", () => {
    render(<FeedChip state="DEGRADED" />);
    expect(screen.getByTestId("feed-chip")).toHaveTextContent("DEGRADED");
  });
});
