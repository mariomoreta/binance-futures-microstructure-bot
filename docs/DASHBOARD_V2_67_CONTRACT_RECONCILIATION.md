# DASH-V2-67 — Backend contract reconciliation and historical source audit

2026-10-11. DONE bounded; no general PASS, cutover or operational authorization.

## Exact checkpoints and independent evidence
Backend local and origin/phase1/market-intelligence-dashboard both: `5dedacb19152e6f1bab0d475d15f477bb22ddad1`.
Frontend implementation base: `6e1a70c00492bfc73e16d04226b2a2ec4a3ac1f9` (V2-66).
Diff c635938..5dedacb: six files, documentation plus tests/test_dashboard_get_purity.py; no source change. Unrelated untracked files preserved in both worktrees.
Three focused GET purity tests independently pass. Full backend canonical suite: 905/905, exit 0 (see design/qa/v2-67/backend-tests.log and review-evidence.json). No frontend implementation changes or fresh visual acceptance in this checkpoint; previous V2-66 checks remain historical evidence.
Five deployed V2 GETs checked: runtime, readiness, BTC 24h price-series, retained-symbol search, historical-research. See evidence for actual response status. A separate runtime GET preserved canonical registry bytes SHA256 45c6a39ec91f55db708e1b9011f86bc55248b4485e582c015ea4442cc7cab5da. Recorded COMPLETED does not certify PID liveness; feed UNKNOWN and stale watcher observations remain separate.

## Acceptance and corrections to report interpretation
Accept the reconciliation, source inventory and additive GET regressions within their bounded scope. Preserve earlier c635938 disabled-launch acceptance; no reopening of closed fixes.
The backend inventory read V2-64 (8780da2), not V2-65/66. Its V2 schema-2/600-bucket description is historical, not current production.
The bridge runtime-control.ts uses fixed canonical cwd/PYTHONPATH and status_readonly, failing closed when absent. It DOES NOT inspect Git SHA on every consumption. Identity was manually verified on this checkpoint; the inventory phrase 'V2 re-verifies SHA before consuming' must not be read as an implemented automatic runtime guard. No automatic pinned-version protection is claimed.
Pure GET regression scope is probe_status; it does not certify every legacy GET's non-mutating storage behavior. HistoryStore read helpers call _ensure(), which can initialize/migrate through writable connections. V2 must avoid those methods for read-only presentation and use an explicit read-only database adapter without creating absent DBs.

## Current contract reconciliation
| Area | Legacy | Current V2 | Remaining boundary |
|---|---|---|---|
| Search | retained universe, max25, broader symbol parser | retained records, max50, ASCII query validation | Unicode symbols and differing source unions are not full parity |
| Prices | five ranges anchored to REQUEST time, max1000 display | response schema3, five ranges anchored to LAST_RETAINED_SAMPLE, max10000 raw/1200 display | REQUEST-time mode remains absent; historical range is explicitly labeled |
| Exports | same sampled old-series points | fresh independent read of selected historical range, CSV/JSON metadata and gaps | not frozen earlier chart snapshot or exhaustive raw export |
| Historical-research route | separate HistoryStore coverage/events | existing V2 route reads prospective archive in microprobe.db | name alone does not establish bar/study parity |
| Runtime | pure stored process and separate feed projection | canonical pure controller, feed UNKNOWN on runtime bridge | no current process identity or live feed certification |

## Next frontend slice: V2-68 historical coverage/studies
Source audited read-only: canonical data/historical/historical.db, history_meta schema2, 14 coverage rows, 17270 contract klines, 2157 mark klines, 2831 event instances and 16986 outcomes across six stored definitions. Counts are observation-time snapshots, not fresh acquisition or strategy validation.
One stored BTC 1h klines coverage row has zero bars and null span/ratio. Preserve it; never upgrade it from neighboring datasets. Stored coverage ratio 1.0 is the recorded interval result, not current completeness for all requested history.
Implement a separate allowlisted readonly adapter and explicitly named coverage/study endpoints. Keep historical provenance separate from the prospective archive and mark-price samples. Render per-source dates, requested/actual bounds, expected/actual counts and gaps; absent database -> unavailable without creating it. Preserve raw event-summary semantics: legacy AVG(forward_return) includes all non-null outcome rows, while n_usable is a separate count. Do not silently change the statistical population; any methodology change is a separate research task.
Acceptance: real and absent/temp DB tests, null/zero/time-unit handling, provenance and bounded response checks; existing frontend checks and canonical V2 suite; fresh desktop/mobile reference review before visual completion. Diagnostic parity follows; Unicode/current-window variants remain tracked migration residuals.

## Backend-owned follow-up
Extract shared repo_root/process_info/pid_is_ours/no_window_flags into a non-HTTP module, preserving exact behavior and old public helper compatibility. Audit imports and patch-target compatibility before implementation. Do not remove/gate old HTML, enable Start, or launch operational runs. See DASHBOARD_V2_67_BACKEND_HANDOFF.md.
Dependency blocks removing/gating dashboard.py; merely stopping its HTTP listener is a different reversible operation. No listener or file retirement performed here.

## Seven closeout fields
- DECISIONS_REVIEWED: V2-63 through V2-66, migration plan, canonical read inventory, pure-status boundary.
- NEW_DECISIONS_RECORDED: manual SHA verification clarified; separate read-only historical adapter required; no silent window or statistical-population substitution.
- FEATURES_IMPLEMENTED: reconciliation documentation, historical source audit, evidence and bounded backend handoff only.
- FEATURES_VERIFIED: exact local/remote backend SHA, source-free diff, focused 3 tests, canonical 905 tests, deployed GET checks and unchanged registry bytes.
- DEFERRED_FEATURES: coverage/study UI implementation, Unicode/REQUEST-window parity, diagnostics completeness, helper extraction, cutover, Start and operational longevity.
- BACKLOG_UPDATED: F-V2-BFF-01 and F-V2-DATA-MIG-01 remain PARTIAL for complete migration; next V2-68 acceptance defined.
- DOCUMENTATION_CONFLICTS: schema2/600 description superseded by schema3; automatic SHA verification claim unsupported; prospective archive vs separate historical research distinguished.
