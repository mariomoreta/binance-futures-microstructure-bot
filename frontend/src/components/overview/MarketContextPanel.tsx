import { MetricPrice } from "@/components/cards/metrics";
import type { MarketContextFacts } from "@/lib/types";

export function MarketContextPanel({ context }: { context: MarketContextFacts }) {
  return (
    <section className="v2-section" aria-label="Market context">
      <h2>Market Context</h2>
      <div className="v2-card" data-testid="context-panel">
        <table className="v2-table">
          <tbody>
            <tr>
              <th scope="row">BTC reference</th>
              <td>
                <MetricPrice value={context.btcRef} />
              </td>
            </tr>
            <tr>
              <th scope="row">ETH reference</th>
              <td>
                <MetricPrice value={context.ethRef} />
              </td>
            </tr>
          </tbody>
        </table>
        <p className="v2-muted">{context.categoriesNote}</p>
        <p className="v2-muted">{context.aggregateNote}</p>
        <p className="v2-muted">{context.providerNote}</p>
      </div>
    </section>
  );
}
