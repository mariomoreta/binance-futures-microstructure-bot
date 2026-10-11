# Dashboard V2 Frontend Architecture


## Current implementation — DASH-V2-63 (2026-10-11)
The scaffold/folder descriptions below are the approved historical plan, not current unimplemented status.
Implemented data path: Python acquisition/features/research -> canonical SQLite -> read-only Next.js server projection -> browser views / same-origin BFF. Runtime/control retains the existing pure Python control adapter; Start disabled. Browser SQLite and frontend trading decisions remain prohibited.
Direct SQLite projection reuses the historical-reader boundary rather than duplicating an engine or relying on old HTML/8091. Sources/contracts and remaining parity: DASHBOARD_V2_63_DATA_CONTRACT.md.


**Purpose:** define a parallel professional frontend without rewriting the
Python market/research backend.  
**Status at 2026-10-07:** ARCHITECTURE APPROVED; NEXT.JS SCAFFOLD NOT IMPLEMENTED (historical; current checkpoint above).
**Date:** 2026-10-07.

## Decision

Use **React + Next.js App Router + TypeScript strict mode** for Dashboard V2,
in a separate future `frontend/` directory. Preserve the existing Python SSR
dashboard at `127.0.0.1:8091` throughout migration.

The recommendation is based on the future terminal's multiple routes,
interactive chart/table workbenches, shared layouts, typed server boundary,
and a same-origin Backend-for-Frontend (BFF). It is not permission to scaffold
or install packages in this documentation task.

## Alternatives evaluated

| Criterion | Modernize Python SSR | React + Vite SPA | React + Next.js App Router |
|---|---|---|---|
| Interactivity | increasingly custom JS | excellent | excellent |
| Complexity now | lowest | low | medium |
| Charts/tables | possible, manual integration | strong ecosystem | strong ecosystem |
| Refresh/cache | custom polling | client cache | server BFF + client cache |
| Operational processes | one Python process | Python + static/dev server | Python + Node server |
| Windows local deployment | simplest | simplest React option | acceptable; document two-process start |
| Security/API boundary | current controls already safe | cross-origin/CORS pressure | same-origin BFF avoids browser-to-Python CORS |
| Testing | current Python suite | Vitest/RTL/E2E | Vitest/RTL + route/BFF + E2E |
| Bundle/runtime | smallest | leanest React | larger runtime and server overhead |
| Opportunities/Paper Lab evolution | presentation friction grows | capable | best structured multi-route/server-boundary fit |

Vite is the rational simpler choice for a permanently localhost-only,
client-only terminal. Next.js wins here only because the BFF can centralize
schema validation, source/freshness normalization and control-token handling,
while App Router gives durable route/layout boundaries for future labs. If
the BFF requirement is later removed and deployment must be static-only,
reopen the Vite decision rather than carrying unnecessary server overhead.

Official framework references: [Next.js App Router](https://nextjs.org/docs/app)
and [Vite guide](https://vite.dev/guide/).

## Hard separation

```text
Binance/public providers
  -> Python acquisition/features/research/control/SQLite
  -> versioned Python HTTP API on loopback
  -> Next.js server-side BFF route handlers
  -> React client components
```

- TypeScript never reimplements MarketProbe, feature formulas, discovery,
  history/event methods, recorder, registry or control manager.
- Browser components never open SQLite and never receive provider/API keys.
- The engine never reads React/DOM/state.
- There is one Python process manager: the existing `control.py` registry.
- External provider adapters, if approved, remain Python backend services and
  never enter the WebSocket critical path.

## Same-origin BFF and control security

Recommended public browser origin: the Next.js origin only. Browser requests
go to `/api/v1/*` on Next.js; server route handlers proxy an allowlisted set
to Python loopback. Read-only routes may be cached according to contract.

Control mutations require additional rules:

1. BFF server reads the Python control nonce server-side; it is never embedded
   in HTML, JavaScript, local storage or a client response.
2. Browser sends a BFF-issued same-origin CSRF token/session proof. The BFF
   checks `Origin`, `Host`, method and content type, then adds the Python nonce.
3. BFF forwards only fixed start/stop operations and validated allowlisted
   fields. No arbitrary URL, module, argument, path or shell string.
4. Python retains its existing localhost Host/Origin/nonce validation and
   fixed argv. Integration must adapt trusted-origin configuration narrowly;
   it must not disable checks or add wildcard CORS.
5. Both services bind `127.0.0.1`. Proxy targets are constant server config;
   reject redirects and SSRF-shaped inputs. Add body limits, timeouts and
   audit logs. Never expose the Python port to LAN.

Because the current Python check only accepts local origins, the detailed
implementation must prove whether a server-to-server request with an approved
local Origin is accepted or whether Python needs a narrow, tested additional
trusted origin. That is a future implementation decision; no safeguard is
weakened here.

## Future folder plan

```text
frontend/
  package.json
  next.config.ts
  tsconfig.json
  src/
    app/
      layout.tsx
      page.tsx                  # redirect/overview
      overview/page.tsx
      movers/page.tsx
      symbols/[symbol]/page.tsx
      opportunities/page.tsx
      backtest/page.tsx
      paper-lab/page.tsx
      system/page.tsx
      api/v1/[...path]/route.ts # explicit dispatcher, not open proxy
    components/
      shell/
      status/
      cards/
      tables/
      charts/
      controls/
    features/
      overview/
      movers/
      symbol/
      opportunities/
      system/
    lib/
      api/
        contracts.ts
        client.ts
        errors.ts
        provenance.ts
      format/
      freshness/
      security/
    styles/
      tokens.css
      globals.css
    test/
  public/
  e2e/
```

Routes for Opportunities, Backtest and Paper Lab may initially render honest
blocked/availability explanations. They must not fabricate rankings, setups,
positions or account values.

## State, charts and tables

- Prefer server components for shell/static initial reads; client components
  for polling, filters, tables and charts.
- Use a small fetch layer with runtime schema validation and explicit
  `unknown/null/stale` states. Evaluate TanStack Query only where shared
  polling/cache invalidation justifies it; do not add global state by default.
- Recommend TanStack Table for Movers because sorting/filtering/column state
  is complex and headless accessibility can be controlled.
- Recommend TradingView Lightweight Charts for time series after a prototype
  verifies accessibility/fallback tables. It is Apache-2.0, but the official
  project requires the NOTICE attribution and a TradingView link on a public
  user-visible page. See [license guidance](https://tradingview.github.io/lightweight-charts/docs).
- Numeric formatting is centralized. Preserve raw numeric values for sorting;
  render locale-aware compact values, explicit units, signed percentages and
  `—` only for absent values. Never convert absent to zero.

## Accessibility and performance

Keyboard-reachable navigation/filters/control confirmation; visible focus;
semantic tables; text plus color for status; WCAG AA contrast; reduced-motion
support; chart text/table summary; no flashing/pulse without reduced-motion
fallback. Poll only visible/current data, pause in background, batch requests,
and update chart points incrementally rather than replacing the full series.

## Testing contract

TypeScript strict + lint; unit tests for formatting/freshness/contracts;
component tests for all capability states; BFF security tests for Host/Origin/
CSRF/nonce non-disclosure/allowlists; Playwright smoke for routes and control
confirmation; screenshot comparisons against approved references at fixed
desktop widths. Python canonical suite remains mandatory.

## Dependencies and next action

Depends on `DASHBOARD_V2_API_CONTRACTS.md` and a versioned Python facade.
Next implementation slice is `DASH-V2-00` only after explicit authorization.
Port 3000 is a proposed default and must be checked, never assumed free.
