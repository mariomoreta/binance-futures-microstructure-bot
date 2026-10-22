import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import {LiveChart} from "@/components/paper-lab-live/LiveChart";
import type {PaperCandle} from "@/lib/paper-lab-live";

// Vela revelada solo por su open: el backend publica high/low/close/close_time
// como null hasta que su cierre se conoce en T.
const openOnly = {
  open_time_ms: 900000,
  open: 101,
  high: null,
  low: null,
  close: null,
  close_time_ms: null,
} as unknown as PaperCandle;

const closed: PaperCandle = {
  open_time_ms: 0,
  open: 100,
  high: 102,
  low: 99,
  close: 101,
  close_time_ms: 899999,
};

describe("LiveChart con vela abierta (solo open conocido)", () => {
  it("no contamina la escala con null ni dibuja NaN", () => {
    const {container} = render(
      <LiveChart
        candles={[closed, openOnly]}
        contextCandles={[]}
        entryPx={101}
        stopPx={95.95}
        exitPx={null}
        exitShown={false}
        currentTimeMs={900000}
        direction="LONG"
      />,
    );
    expect(container.innerHTML).not.toContain("NaN");
    // La escala usa solo velas cerradas + niveles (95.95..102), no 0.
    expect(screen.queryByText("0.00")).not.toBeInTheDocument();
    expect(screen.getByText("102.00")).toBeInTheDocument();
    expect(screen.getByText("95.95")).toBeInTheDocument();
  });
});
