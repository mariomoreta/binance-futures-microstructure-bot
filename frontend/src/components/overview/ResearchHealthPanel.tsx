import { ResearchChip } from "@/components/status/badges";
import type { HealthFacts } from "@/lib/types";
import { DataFreshnessIndicator } from "./TopBar";

export function ResearchHealthPanel({ health }: { health: HealthFacts }) {
  return (
    <section className="v2-section" aria-label="Research and system health">
      <h2>Research &amp; System Health</h2>
      <div className="v2-card" data-testid="health-panel">
        <p>
          <ResearchChip state={health.recorder} />{" "}
          <span className="v2-muted">
            Recorder state is independent of engine and feed state.
          </span>
        </p>
        <table className="v2-table">
          <tbody>
            <tr>
              <th scope="row">Persistence</th>
              <td className="v2-muted">{health.persistence}</td>
            </tr>
            <tr>
              <th scope="row">Feed freshness</th>
              <td className="v2-muted">{health.feedFreshness}</td>
            </tr>
            <tr>
              <th scope="row">WebSocket health</th>
              <td className="v2-muted">{health.wsHealth}</td>
            </tr>
            <tr>
              <th scope="row">Last update</th>
              <td className="v2-mono">{health.lastUpdate ?? "—"}</td>
            </tr>
            <tr>
              <th scope="row">Errors / gaps</th>
              <td className="v2-muted">{health.errorsGaps}</td>
            </tr>
          </tbody>
        </table>
        <p>
          <DataFreshnessIndicator freshness="UNKNOWN" />{" "}
          <span className="v2-muted">
            Example values — operational health is never asserted from
            fixtures.
          </span>
        </p>
      </div>
    </section>
  );
}
