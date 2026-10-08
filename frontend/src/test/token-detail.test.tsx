import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { getDemoTokenDetail } from "@/lib/token-detail";
import { TokenDetail } from "@/components/token/TokenDetail";

describe("DASH-V2-03 token detail", () => {
  it("never claims authoritative live state from a demo price", () => {
    const data = getDemoTokenDetail("btcusdt");
    expect(data.state).toBe("UNKNOWN");
    render(<TokenDetail data={data} />);
    expect(screen.getByText("Market State Intelligence")).toBeInTheDocument();
    expect(screen.getByText(/No authoritative live classifier response/)).toBeInTheDocument();
    expect(screen.getAllByText(/DEMO/).length).toBeGreaterThan(0);
  });
  it("unknown symbols do not inherit BTC metrics", () => {
    const data = getDemoTokenDetail("ORCAUSDT");
    expect(data.price).toBeNull();
    expect(data.capability).toBe("UNKNOWN");
    expect(data.metrics.every(m => m.value === null)).toBe(true);
  });
});


describe("DASH-V2-08 token detail provenance", () => {
  it("shows fixture as-of and API disconnection without implying a live observation", () => {
    render(<TokenDetail data={getDemoTokenDetail("BTCUSDT")} />);
    const provenance = screen.getByLabelText("Token dataset provenance");
    expect(provenance).toHaveTextContent("STATIC DEMO FIXTURE");
    expect(provenance).toHaveTextContent("Oct 7, 2026");
    expect(provenance).toHaveTextContent("NOT LIVE");
    expect(provenance).toHaveTextContent("Classifier API: NOT CONNECTED");
    expect(screen.getByText(/illustrative rules label v0.1.0/)).toBeInTheDocument();
  });
  it("does not invent a timestamp or price for an unknown symbol", () => {
    render(<TokenDetail data={getDemoTokenDetail("ORCAUSDT")} />);
    const provenance = screen.getByLabelText("Token dataset provenance");
    expect(provenance).toHaveTextContent("NO SYMBOL FIXTURE");
    expect(provenance).toHaveTextContent("No symbol-specific observation or timestamp available");
    expect(provenance).not.toHaveTextContent("Oct 7, 2026");
    expect(screen.getByText(/Classifier not connected/)).toBeInTheDocument();
  });
});
