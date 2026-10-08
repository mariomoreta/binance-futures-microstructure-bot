import type { PulseData } from "@/lib/types";
import { DataFreshnessIndicator } from "./TopBar";

export function MarketPulsePanel({ pulse }: { pulse: PulseData }) {
  const total = pulse.breadthTotal ?? 0;
  const up = pulse.breadthUp ?? 0;
  const down = pulse.breadthDown ?? 0;
  const upPct = total > 0 ? (up / total) * 100 : 0;
  const downPct = total > 0 ? (down / total) * 100 : 0;
  const row = (label: string, value: string) => (
    <tr>
      <th scope="row">{label}</th>
      <td className="v2-mono">{value}</td>
    </tr>
  );
  return (
    <section className="v2-section" aria-label="Market pulse">
      <h2>Market Pulse</h2>
      <div className="v2-card" data-testid="pulse-panel">
        <div className="v2-muted" style={{ marginBottom: 8 }}>
          Breadth {up}/{down} of {total} ·{" "}
          <DataFreshnessIndicator freshness={pulse.freshness} />
        </div>
        <div
          className="v2-pulse-bar"
          role="img"
          aria-label={`${up} advancing, ${down} declining of ${total}`}
          data-testid="breadth-bar"
        >
          <span className="v2-pulse-pos" style={{ width: `${upPct}%` }} />
          <span className="v2-pulse-neg" style={{ width: `${downPct}%` }} />
        </div>
        <table className="v2-table" style={{ marginTop: 12 }}>
          <tbody>
            {row("Acceleration share", pulse.accelShare !== null ? `${(pulse.accelShare * 100).toFixed(1)}%` : "—")}
            {row("Observed volatility", pulse.observedVol !== null ? pulse.observedVol.toFixed(4) : "—")}
            {row("Relative activity", pulse.relativeActivity !== null ? `${pulse.relativeActivity.toFixed(1)}×` : "—")}
            {row("Top-mover concentration", pulse.concentrationTop !== null ? `${(pulse.concentrationTop * 100).toFixed(0)}%` : "—")}
          </tbody>
        </table>
        <p className="v2-muted">{pulse.coverageNote}</p>
        <p className="v2-muted">
          Descriptive distribution only. Buyer aggression is never rendered as
          rally probability; no LONG/SHORT signal exists on this screen.
        </p>
      </div>
    </section>
  );
}
