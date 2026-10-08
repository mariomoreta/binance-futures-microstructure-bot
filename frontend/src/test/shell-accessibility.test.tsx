import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { AppShell } from "@/components/shell/AppShell";
import { OpportunitiesDashboard } from "@/components/opportunities/OpportunitiesDashboard";
import { TokenDetail } from "@/components/token/TokenDetail";
import { getDemoTokenDetail } from "@/lib/token-detail";

vi.mock("next/navigation", () => ({ usePathname: () => "/opportunities" }));

describe("DASH-V2-05 accessible research views", () => {
  it("offers skip navigation and one main landmark", () => {
    render(<AppShell><OpportunitiesDashboard /></AppShell>);
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute("href", "#main-content");
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("link", { name: /Opportunities/i })).toHaveAttribute("aria-current", "page");
  });

  it("keeps token detail within one main landmark", () => {
    render(<AppShell><TokenDetail data={getDemoTokenDetail("BTCUSDT")} /></AppShell>);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByText("Observed state")).toBeInTheDocument();
  });
});

describe("Opportunities keyboard inspection", () => {
  it("marks selected candidate and exposes a focusable table", () => {
    render(<OpportunitiesDashboard />);
    const region = screen.getByRole("region", { name: "Opportunity candidates table" });
    expect(region).toHaveAttribute("tabindex", "0");
    const btc = within(region).getByRole("button", { name: /Inspect BTCUSDT/ });
    const ogn = within(region).getByRole("button", { name: /Inspect OGNUSDT/ });
    expect(btc).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(ogn);
    expect(ogn).toHaveAttribute("aria-pressed", "true");
    expect(btc).toHaveAttribute("aria-pressed", "false");
    expect(ogn).toHaveAttribute("aria-controls", "candidate-evidence");
    expect(screen.getByRole("region", { name: "Candidate evidence" })).toHaveAttribute("id", "candidate-evidence");
  });
});
