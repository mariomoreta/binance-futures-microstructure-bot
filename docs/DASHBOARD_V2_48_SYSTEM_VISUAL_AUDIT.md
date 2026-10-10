# DASH-V2-48 — System terminal composition

Date: 2026-10-10. Starting remote SHA: d4df766 (DASH-V2-47).
Frontend worktree: C:/proyectos/binance-futures-dashboard-v2-worktree.

## Audit and bounded plan

Inspected the real system.png approved reference on the operator's device and
captured the running pre-change System screen at 1672x941. The reference uses
compact state cards and dense panel rows; the existing screen's first viewport
was almost entirely process controls, followed by duplicated UNKNOWN tiles.

Plan: compact runtime state strip, native disclosure for control/supervisor
details, three-column transport/readiness/integration layout, separate archived
evidence. Remove obsolete duplicated health tiles and unsupported connected
badge. Preserve all real values, UNKNOWN, polling and foreign-process protection.
No backend edits or engine start/stop. Rollback: revert this frontend slice.

Acceptance: desktop/mobile captures compared to reference; native disclosure
and refresh checked; layout overflow checked; type/lint/tests/build; Windows
Python regression check. No illustrative sparklines or healthy statuses.

## Verified result

- Windows frontend: 86/86 Vitest tests (24 files), TypeScript, ESLint and
  production Next build PASS.
- Reproduced original System test timeout (85/86): real controller/SQLite
  dependencies in a presentation unit test. Isolated its sources; full rerun PASS.
- V2 worktree Python snapshot: 496/496 PASS (80.140s). This resolves the Linux
  limitation from V2-47; it does not verify the other agent's newer backend suite.
- Chrome 1672x941 / 390x941: no page overflow (scrollWidth 1657 / 375);
  disclosure and Refresh PASS, browser exception/errors 0. Overview captured.
- Overview narrow diagnostics had pre-existing four-column squeezed values;
  corrected the compact shared panel to two columns at mobile widths.
- Reference comparison PARTIAL: compact cards, dark terminal surfaces and dense
  panels improved. Shared top navigation retained instead of reference sidebar;
  four actual runtime states replace five illustrative performance cards.
  No synthetic sparklines, uptime/availability figures or event rows.
- Captures show agent-owned runtime and supervisor independently of feed health;
  fresh persisted samples are labeled separately. No probe start/stop invoked.
- Canonical V2 port 3020 restarted only after verifying managed PID, command and
  creation time. V1 and the other agent's engine/worktree were not modified.

## Integration handoff

Await the owning backend's finished report and committed contracts for live
universe, recorder lifecycle, classifier/opportunity counters, host resources
and timestamped operational events. Each requires provenance, as-of, freshness,
nullability and state semantics. NOT CONNECTED describes this screen only.
An observed active supervisor does not prove V2 start atomically registers both
supervisor and sentinel. Start stays disabled.

## Closeout

- DECISIONS_REVIEWED: V2 decisions/design/architecture, reference README and
  actual system.png, repository dashboard-v2 skill.
- NEW_DECISIONS_RECORDED: bounded System composition and reference departures
  in DASHBOARD_V2_DECISIONS.md; no backend/methodology decision.
- FEATURES_IMPLEMENTED: F-V2-SYSTEM-01 System presentation PARTIAL;
  F-V2-BFF-01 existing runtime presentation still PARTIAL.
- FEATURES_VERIFIED: layout, client fallback, foreign ownership, desktop/mobile
  rendering and controls inspection; no complete integration/parity claim.
- DEFERRED_FEATURES: five data integrations, atomic start and full reference parity.
- BACKLOG_UPDATED: scoped System evidence and pending contracts.
- DOCUMENTATION_CONFLICTS: old static-only System claims superseded by this
  update; historical backend records do not establish current runtime state.

Evidence: design/qa/v2-48/ and scripts/qa-dashboard-system.mjs.
