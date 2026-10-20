# Dashboard V2 Design Specification

**Purpose:** preserve the approved financial-terminal direction as reusable
tokens, components and truthful capability rules.  
**Status:** DESIGN FOUNDATION APPROVED; VISUAL IMPLEMENTATION NOT STARTED.  
**Date:** 2026-10-07.

The four prior reference mockups were not present in this repository or the
supplied attachment. This specification preserves the supplied direction and
the verified prior-audit findings, but a future visual PASS still requires the
actual reference images and screenshot comparison.

## Principles

- Dark navy/charcoal surfaces; restrained blue/cyan accents; green/red only
  for signed movement; amber for warming/warnings.
- Dense but legible analytical hierarchy, minimal glow and no decorative
  metrics.
- Every value has provenance, timestamp/freshness and honest availability.
- `LIVE`, `WARMING`, `DISCOVERY ONLY`, `STALE`, `DEGRADED`, `UNKNOWN` are
  data capabilities. `CORE`, `HOT`, `DISCOVERY` are neutral universe tiers.
- Contextual CMC/CoinGecko values visibly name their provider and never appear
  as Binance perpetual prices or liquidity.

## Proposed tokens

```css
:root {
  --bg-0: #071019; --bg-1: #0b1621; --surface-1: #101e2b;
  --surface-2: #152635; --border: #24394a;
  --text-1: #edf5fb; --text-2: #a8bac8; --text-3: #718796;
  --accent: #38bdf8; --accent-muted: #164e63;
  --positive: #34d399; --negative: #fb7185; --warning: #fbbf24;
  --danger: #f43f5e; --unknown: #78909c;
  --radius-sm: 4px; --radius-md: 8px; --radius-lg: 12px;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
  --font-ui: Inter, system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;
}
```

Values are initial contracts, not pixel-perfect approval. Final colors and
spacing must be measured against the available reference mockups and pass
contrast checks.

## Reusable components

- `AppShell`, `PrimaryNav`, `SymbolSearch`, `PageHeader`.
- `CapabilityBadge`, `TierBadge`, `FreshnessIndicator`, `SourceLabel`,
  `QualityFlags`, `EmptyState`, `UnavailableState`.
- `MetricCard`, `MetricPair`, `DeltaValue`, `CompactSparkline` (real data
  only), `DataTable`, `ChartPanel`, `EvidenceList`.
- `MarketEngineControl` for observe-only process control; engine/feed/research
  states are separate.
- `ProviderAttribution` for CMC/CoinGecko/TradingView obligations.

Status components always include text/icon semantics and machine-readable
labels; color alone is insufficient.

## Information architecture and capability matrix

| Screen | Available now | Needs API/view model | Future/blocked |
|---|---|---|---|
| Overview | health, snapshot, discovery, live raw features | one aggregated pulse contract; external context | classified regimes until P1-12 |
| Movers | current composed rows/categories | stable paginated/filterable contract, server timestamps | 500-symbol full-depth live claims |
| Symbol Detail | live feature panels, price history, history coverage/events | one normalized detail contract; identity/profile | setup recommendation/probability |
| Opportunities | explanatory empty shell only | lifecycle/evidence/counterevidence contract | candidates until P1-12/P1-13A |
| Backtest | nav/blocked explanation | run definitions/results | engine until P1-14 |
| Paper Lab | nav/blocked explanation | portfolio/orders/fills/risk contracts | engine until P1-15/16 |
| System | health, control, research, APIs | consolidated diagnostics contract | none beyond engine phases |

Symbol Detail is selection/search driven, not a permanent primary nav item.

## Screen contracts

### Overview

Market pulse, feed/engine/research health, live-universe summary, notable
venue movers and broad context. Never show fake account equity, win rate,
positions or generated “AI signals.”

### Movers

Sortable/filterable raw numeric table with separate venue discovery and live
feature columns. Preserve the P1-11A rule: every category binds its own source
field, unit and formatter. Positive/negative velocity tables are sign-filtered;
zero/non-finite/unknown belongs in neither.

### Symbol Detail

Binance contract identity, mark-price chart, returns/momentum, flow, book, OI,
VWAP/vol/structure, historical coverage and research events. Historical-only
symbols must route and render available history even without current discovery
or live features; the current `ORCAUSDT` route gap is explicitly a V2 API issue.

### Opportunities (future)

Each candidate must explain symbol, selection reason, live capability,
market-state evidence, flow/book/OI/VWAP/structure, BTC context, historical
analogs, completeness, counterevidence, risks and lifecycle. Direction, entry
zone, invalidation, targets, expected horizon, costs, sizing and paper results
are nullable research fields that require their owning engines and independent
validation. No fabricated confidence or recommendation.

### Dynamic universe (future)

Render `DISCOVERY -> WATCH -> HOT -> LIVE TRACKED` as an evidence/timestamped
lifecycle. Broad REST discovery and the much smaller subscribed universe stay
visually distinct. P1-12B is not implemented and no “500 live depth streams”
claim is allowed.

## Responsive behavior

Current scope override (user decision 2026-10-20): DESKTOP WEB ONLY.
See `docs/DESKTOP_FIRST_SCOPE_20261020.md`. Keep the desktop 12-column grid,
utility/nav region and dense tables readable at desktop browser widths.
Existing responsive behavior may remain, but phone/tablet layouts, 360/390 px
QA/captures, Flutter and mobile acceptance are DEFERRED until the desktop
functional scope is complete and explicitly accepted by the user.
Historical mobile evidence is preserved; mobile is not a current work item.

## Visual acceptance

For every slice: render fixed real/fixture-backed states at approved viewport;
capture screenshots; compare with references for layout, hierarchy, spacing,
typography and state honesty; repair; then record exact evidence in
`DASHBOARD_V2_PROGRESS.md`. A test pass without screenshot comparison is not a
visual PASS.

## Dependencies and next action

Depends on the architecture and API contract documents. `DASH-V2-00` may
implement tokens/components only after explicit authorization and after the
four reference mockups are accessible to the implementing agent.

## Traceability

Design agreements on this page are indexed in `docs/FEATURE_BACKLOG.md`
(F-STATE-V2-OV-01, F-STATE-V2-MV-01, F-STATE-V2-TK-01, F-OPP-UI-01,
F-V2-BFF-01, F-CMC-01). That file tracks approval vs implementation status;
this spec remains the design authority.
