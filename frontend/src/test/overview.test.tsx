import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DataFreshnessIndicator } from "@/components/overview/TopBar";
import { ExtremeMoveWatch } from "@/components/overview/ExtremeMoveWatch";
import { MarketPulsePanel } from "@/components/overview/MarketPulsePanel";
import { MoversSnapshot } from "@/components/overview/MoversSnapshot";
import {
  DEMO_EXTREMES,
  DEMO_METRICS,
  DEMO_MOVERS,
  DEMO_PULSE,
} from "@/lib/fixtures";

describe("overview freshness", () => {
  it("distinguishes FRESH, STALE, and UNKNOWN textually", () => {
    const { rerender } = render(
      <DataFreshnessIndicator freshness="FRESH" age="4s" />,
    );
    expect(screen.getByTestId("freshness")).toHaveTextContent("FRESH");
    rerender(<DataFreshnessIndicator freshness="STALE" age="12m" />);
    expect(screen.getByTestId("freshness")).toHaveTextContent("STALE");
    rerender(<DataFreshnessIndicator freshness="UNKNOWN" />);
    expect(screen.getByTestId("freshness")).toHaveTextContent("UNKNOWN");
  });

  it("stale research capture stays missing, never zero", () => {
    expect(DEMO_METRICS["researchCapture"]?.value).toBeNull();
    expect(
      DEMO_METRICS["researchCapture"]?.unavailable,
    ).toMatch(/unknown/i);
  });
});

describe("overview honesty", () => {
  it("extreme watch contains no prediction or trade language", () => {
    render(<ExtremeMoveWatch rows={DEMO_EXTREMES} />);
    const text =
      screen.getByTestId("extreme-watch").textContent ?? "";
    for (const word of [
      "will rise",
      "will fall",
      "target price",
      "stop-loss",
      "take-profit",
      "buy now",
      "sell now",
      "entry zone",
    ]) {
      expect(text.toLowerCase()).not.toContain(word.toLowerCase());
    }
  });

  it("pulse disclaims signal interpretation", () => {
    render(<MarketPulsePanel pulse={DEMO_PULSE} />);
    expect(screen.getByTestId("pulse-panel").textContent).toMatch(
      /never rendered as rally probability/i,
    );
  });

  it("movers snapshot links to the full screen and symbol routes", () => {
    render(<MoversSnapshot rows={DEMO_MOVERS} />);
    const links = screen
      .getByTestId("movers-snapshot")
      .querySelectorAll("a[href]");
    const hrefs = Array.from(links).map((a) =>
      a.getAttribute("href"),
    );
    expect(hrefs).toContain("/movers");
    expect(hrefs).toContain("/symbol/BTCUSDT");
  });
});
