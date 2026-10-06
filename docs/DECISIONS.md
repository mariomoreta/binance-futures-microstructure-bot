# DECISIONS

Append-only. Newest at the bottom. Never rewrite past entries; supersede with
a new dated entry.

## 2026-09-01 — Observe-only probe baseline (v0.1.0)

Public WS only (`bookTicker`, `depth20@100ms`, `aggTrade`, markPrice/funding,
forceOrder), `BOT_MODE=observe` enforced, thresholds in `config/probe.json`.
12.1s connectivity evidence; 0 threshold crossings — not calibration.

## 2026-09-01 — Phase 1B latency/clock correction (v0.2.0)

Single global clamped lag retired as gate metric (kept labeled `legacy`).
Per-stream/symbol raw/corrected E- and T-lags, monotonic processing split,
5-sample midpoint clock sync, near-miss/warm-up telemetry, cadence-only
staleness (event-driven silence ≠ stale). Rationale: the old metric mixed
semantics and hid the responsible stream.

## 2026-10-06 — PROJECT_BRAIN infrastructure created

Created `AGENTS.md` + 20 docs under `docs/` defining product goal, strategy
hypotheses (A momentum / B exhaustion, both unproven), feature model, market
states, dashboard spec, event labeling, paper/position/risk rules, gates,
roadmap, workflow, commands, and task queue. No engine/safety code changed;
`docs/PHASE_1_REPORT.md` preserved. Baseline: 28/28 tests green
(`PYTHONPATH=src`), commit `157e85e`, clean tree. Current phase set to
PHASE 1 — MARKET INTELLIGENCE + DASHBOARD.

## 2026-10-06 — Phase 1 execution order refined (P1-00…P1-14)

Binding dependency: RAW MARKET DATA → RAW FEATURES → PERSISTENCE →
DASHBOARD VISIBILITY → LIVE FEATURE VALIDATION → STATE CLASSIFIER.
No prolonged blind observation before the dashboard exists (minimal dashboard
at P1-03: `/overview`, `/system`); no classifier before raw-feature dashboard
validation (classifier P1-12 BLOCKED until P1-11 passes). This supersedes the
earlier "soak first" sketch.

## 2026-10-06 — Persistence foundation moved into Phase 1 (P1-02)

The "Phase 1 persists nothing" rule is superseded: a local observe-only
persistence foundation (raw market data/features → dashboard) is now an
explicit Phase 1 task. Rationale: the dashboard must become useful
progressively; it cannot visualize what is never stored. Still forbidden in
Phase 1: trading data, keys, private APIs, paper/live trading. Full event
snapshots + forward outcomes remain Phase 2 (`docs/EVENT_LABELING.md`).

## 2026-10-06 — Canonical test command (P1-00)

`python run_tests.py` from repo root (new root runner, prepends `src/` to
`sys.path`; exit 0/1). Retires the `PYTHONPATH=src` workaround. 28/28 green,
no application behavior changed. Dashboard port policy set: ordered candidates
from 8091, first-free at startup, bind 127.0.0.1, health endpoint, PID file;
8091/8092/8093/18091/18765 probed FREE.
