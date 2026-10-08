import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MetricDelta } from "@/components/cards/metrics";
import {
  DataTable,
  FilterTabs,
  type Column,
} from "@/components/tables/table";
import { DEMO_MOVERS } from "@/lib/fixtures";
import type { MoverRow } from "@/lib/types";

const SYMBOL_COLS: Column<MoverRow>[] = [
  { key: "symbol", header: "Symbol", render: (r) => r.symbol },
];

describe("tables", () => {
  it("renders rows without inventing values", () => {
    render(
      <DataTable columns={SYMBOL_COLS} rows={DEMO_MOVERS} caption="demo" />,
    );
    expect(screen.getByTestId("data-table")).toBeInTheDocument();
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
  });

  it("filter tabs report selection to the caller", () => {
    const onChange = vi.fn();
    render(
      <FilterTabs tabs={["All", "CORE"]} active="All" onChange={onChange} />,
    );
    fireEvent.click(screen.getByRole("tab", { name: "CORE" }));
    expect(onChange).toHaveBeenCalledWith("CORE");
  });

  it("delta keeps null distinct from zero", () => {
    const { rerender } = render(<MetricDelta pct={null} />);
    expect(screen.getByTestId("metric-delta")).toHaveTextContent("—");
    rerender(<MetricDelta pct={0} />);
    expect(screen.getByTestId("metric-delta")).toHaveTextContent("0.00%");
  });
});
