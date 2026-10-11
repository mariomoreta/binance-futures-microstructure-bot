# Backend agent task - V2 deployment and read-only diagnostic audit

Work only on phase1/market-intelligence-dashboard in the Binance project. Frontend/V2 and main are preserved. Read DASHBOARD_V2_64_CUTOVER_AUDIT.md from the frontend branch; V2-63 now reads persisted canonical data directly. Do not create a second collector, copy/migrate production SQLite, or repeat completed corrections.

Preflight: record branch/local/remote SHA, dirty paths, existing processes and canonical data location without modifying them. The accepted remote checkpoint is c635938fc5542be992e06838a8727652225e1657; the original checkout observed by V2 was da231b911e9b1a0cfe86b3aaa3325e5b71928687. Reconcile normally by fast-forward only when no conflicting tracked work or active Python process makes that unsafe; otherwise report the concrete blocker and preserve work. Verify exact deployed imports afterward. Do not reset/clean or stop processes to force reconciliation.

Audit deliverables:
1. Inventory old Python dashboard GET data routes and exact fields, units, nullable values, timestamps, query bounds and sources. Distinguish persisted evidence from process/transport/feed health. Identify data V2 can already render from stored JSON, so frontend can migrate it without new calculations.
2. Confirm status_readonly remains pure and additive diagnostic projection can expose independently verifiable run/process/supervisor/sentinel/feed facts without reconciliations or registry writes. Fresh timestamp alone never proves alive/bound protection. Explicit UNKNOWN for unverified identity/liveness. Specify whether evidence requires a future authorized observation run.
3. Specify read-only contracts for symbol universe/search, saved historical coverage and event-study detail, plus price ranges 5m/15m/1h/4h/24h and CSV/JSON metadata. Existing functions first; no duplicate formulas, no current-window/historical-anchor silent substitution, bounded queries/truncation.
4. List dependencies of old HTML server vs canonical data/control modules. Provide a reversible old-UI retirement plan that preserves the collector, SQLite, registry and controller. Do not execute retirement.

Implement only genuinely missing additive read-only contract/helpers needed for this audit, with failing-first regressions if code changes. Do not enable launch_supervised_transaction, HTTP/CLI Start, probes, market requests, backfills, P1-14C, long runs, paper or orders; no SUCCESS_GATES advancement. No live runtime experiment is authorized by this task. Frontend will review exact SHA/contract before consuming changes.

Closeout: starting/ending/local/remote SHA; deployed-source identity; evidence per finding and command exits; before/after canonical tests if code changed; docs/current-state/queue/backlog reconciliation and seven closeout fields. Verdict DONE bounded / pending where appropriate, never general PASS or longevity proof. Preserve SQLite/logs/untracked evidence and others' work.
