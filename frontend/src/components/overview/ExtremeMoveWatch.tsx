import { SymbolLink } from "@/components/cards/SymbolLink";
import { DataStateBadge } from "@/components/status/badges";
import { formatCompact, formatSignedPct } from "@/lib/format";
import type { ExtremeMoveRow } from "@/lib/types";

export function ExtremeMoveWatch({ rows }: { rows: ExtremeMoveRow[] }) {
  return (
    <section className="v2-section" aria-label="Extreme move watch">
      <h2>Extreme Move Watch</h2>
      <div className="v2-card" data-testid="extreme-watch">
        <p className="v2-muted">
          Descriptive research monitor for extension, exhaustion, continuation
          and reversal studies. No predictions, probabilities, entries, exits,
          targets, or stop levels.
        </p>
        <table className="v2-table">
          <thead>
            <tr>
              <th scope="col">Symbol</th>
              <th scope="col">Observed change</th>
              <th scope="col">Period</th>
              <th scope="col">Volume</th>
              <th scope="col">Coverage</th>
              <th scope="col">Data</th>
              <th scope="col">Research</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.symbol}>
                <td>
                  <SymbolLink symbol={row.symbol} />
                </td>
                <td className="v2-mono">
                  {formatSignedPct(row.observedChangePct)}
                </td>
                <td className="v2-muted">{row.period}</td>
                <td className="v2-mono">
                  {formatCompact(row.quoteVolume)}
                </td>
                <td>
                  <DataStateBadge capability={row.coverage} />
                </td>
                <td className="v2-muted">{row.dataAvailable}</td>
                <td>
                  <SymbolLink symbol={row.symbol} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
