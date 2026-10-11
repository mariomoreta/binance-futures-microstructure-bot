# Backend handoff — DASH-V2-67 helper extraction

Work only in C:\proyectos\binance-futures-microstructure-bot on phase1/market-intelligence-dashboard. Expected base 5dedacb19152e6f1bab0d475d15f477bb22ddad1; inspect actual local/origin SHA and worktree before any change. Preserve untracked evidence. Read current frontend DASHBOARD_V2_67_CONTRACT_RECONCILIATION.md from Git without changing V2 checkout.

Objective: remove control.py's dependency on the HTTP dashboard module by extracting shared repo_root, process_info, pid_is_ours and no_window_flags into an appropriate non-HTTP utility module. Audit all callers/import cycles and unittest patch targets first. Keep exact identity checks, ctypes ABI, return values, platform behavior, locking, stop/launch semantics and original dashboard helper compatibility. Add meaningful import-boundary and compatibility regressions; avoid a second implementation of identity logic.

Update DASHBOARD_V1_READ_CONTRACTS.md: automatic V2 Git-SHA verification is not implemented (verification is manual); latest production response schema is3, five historical ranges, 10000 raw/1200 display and separate exports. Preserve explicit REQUEST vs LAST_RETAINED_SAMPLE difference, ASCII/Unicode boundary and separate historical DB. Explain that probe-status purity tests do not certify every HistoryStore GET: _ensure can initialize storage. Do not change statistical formulas or expand scope to a new data collector.

Run failing-first focused regressions where applicable and python run_tests.py. Verify old imports remain compatible and control's shared utilities no longer require the HTTP module; report exact limits. Commit/push only coherent source/tests/docs. Deliver initial/final/local/remote SHA, tests, exact files, residuals and seven closeout fields. DONE bounded, never general PASS.

No probes, backfill, market traffic, P1-14C, long runs, paper, orders, Start enablement, main merge, SUCCESS_GATES change, DB/registry/log mutation or old-server/file retirement. Source extraction is preparation, not permission to disable the old dashboard. Do not reopen accepted c635938 launch corrections.
