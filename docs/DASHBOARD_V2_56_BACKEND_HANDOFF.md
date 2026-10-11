# Backend agent prompt - supervised transactional launch preparation

Workspace: C:\proyectos\binance-futures-microstructure-bot
Branch: phase1/market-intelligence-dashboard
Expected base: e3175692f44e8d717f023c5693fcef56b5b83e18
Frontend review: 7b2b5e75cf69263cbcdd1bf2e78bd01848ec63c4,
docs/DASHBOARD_V2_55_CORRECTIONS_ACCEPTANCE.md (read through Git; leave V2 untouched).

Task: document the canonical supervised transactional launch contract and implement
the minimum backend preparation with deterministic tests. Operational access stays
disabled. Do not reopen accepted R1/R2 without new evidence.

Preflight branch/SHA/dirty files and preserve unrelated work. Read current docs,
canonical start/supervisor/sentinel/lease/identity/rollback paths and reuse them.
Never create a second lifecycle controller or registry.

Before implementation record:
- prerequisites and required capabilities;
- transaction/run/process identities and ownership;
- launch sequence, confirmation criteria for both supervisor and sentinel;
- finite verification budget;
- partial failure/cancellation/rollback behavior;
- confirmed/rejected/uncertain outcomes and evidence;
- backend/BFF responsibilities and public compatibility.

A spawn, stored ACTIVE or fresh heartbeat alone is not a confirmed supervised
launch. Verify watcher identity, run association, valid time and all contract
conditions. Confirmation is point-in-time, not permanent protection.

Rollback may act only on verified processes owned by this transaction. Preserve
foreign runs, replacements and terminal/enforcement records. If cleanup cannot
be established, return uncertain with evidence; never report completed rollback.
Keep canonical status_readonly in all GET projections.

Use simulated processes/temp registries, including:
complete success; spawn/registration failures per component; absent/stale/future/
malformed/wrong-run leases; dead/reused watchers; timeout; interleaved takeover/
STOPPING/terminal; write failures; rollback refusal/incompleteness; concurrent/
repeated requests; pure GET no mutations. Failing-first where applicable.

Do not expose a new enabled HTTP operation or change a public contract without
documented and tested boundaries. Any needed new interface is delivered as
disabled preparation pending frontend review. V2 Start remains disabled.

No actual probes, market traffic, backfills, P1-14C, long runs, paper, orders,
Start activation or gate advancement. Preserve V2/main/SUCCESS_GATES, canonical
SQLite/logs/evidence and unrelated files. This task does not authorize strategy
implementation or actual supervised-run validation.

Run python run_tests.py; update ARCHITECTURE/CURRENT_STATE/TASK_QUEUE, append-only
decisions and backlog. Selective owned-file commit/push only.
Deliver initial/final/remote SHAs, contract/document location, available versus
disabled implementation, failure/rollback matrix, tests/exit codes, compatibility
changes, residuals and seven required closeout fields. Verdict DONE bounded,
never general PASS, demonstrated longevity or operational authorization.
