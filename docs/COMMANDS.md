# COMMANDS

Semantic commands for assisted/autonomous work. All operate within the current
phase's authorization unless stated.

| Command | Meaning |
|---|---|
| `STATUS` | Report phase, objective, active/next tasks, gates, safety, git + test state. No code changes. |
| `CONTINUE` | Execute exactly the next authorized task from `TASK_QUEUE.md` (full workflow). |
| `NEXT` | Report the next task + reasoning. Do NOT implement. |
| `AUDIT <target>` | Inspect target (file/dir/system), report facts + unknowns. No changes. |
| `IMPLEMENT <target>` | Minimal implementation of an authorized target. Includes tests + docs + checkpoint. |
| `VERIFY <target>` | Re-run evidence for target (tests, `--show-streams`, bounded live probe). Report pass/fail. |
| `TEST` | Run the canonical `python run_tests.py` from repo root. Report result. |
| `CHECKPOINT` | Selective commit of completed coherent work with evidence message. |
| `WORK PHASE <n>` | One meaningful verified unit of work in phase n (audit→commit). Stop at boundary. |
| `LOOP PHASE <n>` | Multiple verified units until gate/blocker/authorization boundary. Stop rules in `docs/WORKFLOW.md`. |
| `DASHBOARD STATUS` | `python -m microstructure_probe.dashboard status` — PID-alive + health-endpoint check + route spot-check. Binance dashboard only. No changes. |
| `DASHBOARD START` | `python -m microstructure_probe.dashboard start [--port N] [--db PATH]` — first-free-port startup on 127.0.0.1, PID file, health verify, report URL block. Binance dashboard only. |
| `DASHBOARD STOP` | `python -m microstructure_probe.dashboard stop` — terminate only the tracked Binance-dashboard PID, remove PID file. Never touch unrelated processes. |
| `DASHBOARD RESTART` | `python -m microstructure_probe.dashboard restart` — STOP + START. Must never start trading or need private credentials. |
| `HISTORY STATUS` | `python -m microstructure_probe.history status [--db PATH]` — historical research coverage summary (series, bars, ratios). Read-only. |
| `HISTORY FETCH` | `python -m microstructure_probe.history fetch --symbol X [--interval 1h] [--source klines\|mark_klines\|oi_hist] [--days 7] [--max-requests 25] [--dry-run]` — bounded, resumable, listing-aware fetch. Explicit symbols only; no all-symbols mode exists. Public REST only. |
| `HISTORY VERIFY` | `python -m microstructure_probe.history verify --symbol X ...` — re-validate stored series (gaps, malformed, duplicates, partials). |
| `PROBE STATUS` | `python -m microstructure_probe.control status` — canonical probe state (read-only; JSON with process + feed separation). |
| `PROBE START` | `python -m microstructure_probe.control start [--duration N] [--preset standard\|validation-6h]` — one observe-only probe; refuses when one runs; merged UTF-8 log per run. Public data only. |
| `PROBE STOP` | `python -m microstructure_probe.control stop` — terminate ONLY the verified canonical probe PID (bounded wait); stale records recovered, never unrelated processes. |

## Canonical test command (binding for autonomous loops)

```text
python run_tests.py
```

Run from the repository root. Exit 0 = green, non-zero = fail. `python
run_tests.py -q` for quiet mode. No `PYTHONPATH`, no install step, no venv
assumptions. Every loop iteration and every `TEST`/`VERIFY` uses this command.

## LOOP PHASE rules (binding)

Each iteration: read AGENTS + docs → inspect repo state → select
highest-priority authorized task → audit → implement minimally → verify
(canonical test command) → document evidence → checkpoint selectively →
evaluate gate → continue only if safe and still within the approved phase.

STOP on: authorization needed, account/trade mutation, methodology change,
contradictory evidence, unresolved test failure, blocked dependency,
destructive migration, secrets needed, gate reached.

## P1-11C event-study CLI

- python -m microstructure_probe.events definitions � list the 6 versioned research families (read-only).
- python -m microstructure_probe.events run --definition EXTENDED_GAINER --symbol MINAUSDT --interval 1h [--mark] [--start MS] [--end MS] � bounded deterministic study (writes research tables only; never trades).
- python -m microstructure_probe.events summary --definition EXTENDED_GAINER � per-horizon N/usable/mean (machine-readable).
