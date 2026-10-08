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
