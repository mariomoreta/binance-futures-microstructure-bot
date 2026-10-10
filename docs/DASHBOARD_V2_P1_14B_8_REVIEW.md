# V2 review of P1-14B.8 — integration remains blocked

Date: 2026-10-10. Backend SHA babf3ac583ffeafbb2f1c8cfcc2f0365e31dbd09.
V2 baseline 140377b. Review only; no backend changes or market run launched.

## Verified evidence

GitHub compare confirms one commit from 9150c74, eight files; backend branch
and remote both babf3ac, main d6801a5. No frontend or dashboard.py change in
this commit. Backend working tree has pre-existing untracked files, preserved.

Reran tests/test_sentinel.py on Windows: 15/15 OK, 3.412s, including isolated
registry real-sleeper abort with foreign sleeper preserved. 775/775 full suite
is reported by the owner, not independently rerun in this review.
Read-only SQLite quick_check OK; prospective_setups 66, prospective_outcomes
228. Prior-row byte identity/no-lookahead not independently revalidated here.

Long-run final log: runtimeSeconds 2102.147; 20/20 streams, zero timestamp
rejects/reconnects, missing/stale empty; prospective errors/drops zero,
registered_setups 66, completed 26. Supervisor stdout confirms 70 cycles and
no-active-run. Brief stdout confirms supervisor 14 / sentinel 12 cycles.
Long-run sentinel stdout is empty; report acknowledges its early death.
This supports long-run supervisor continuity and brief three-layer execution,
not uninterrupted three-layer protection throughout 35 minutes.

## Required backend corrections / regression cases

1. HIGH — _supervision_verdict accepts fresh STOPPED as ok-supervised.
   Reproduced by pure function with state STOPPED and current last_check_at.
   ACTIVE with unrelated watched_pid is also accepted; this function does not
   verify supervisor PID/image/create_time or association with this run.
   Require authoritative active, fresh, identity-verified, run-bound supervision.
   Specify handling of stopped/dead/mismatched leases while the run is active.

2. HIGH — malformed established heartbeat returns unsupervised and no abort.
   Reproduced ACTIVE + last_check_at="bad". Missing-before-establishment and
   loss/corruption-after-establishment must be distinct. Define bounded recovery
   and safe-stop policy; future timestamps must not count as fresh (negative
   age currently satisfies age <= stale_after). Add regression tests.

3. HIGH for UI contract — _sentinel_block publishes SENTINEL_ACTIVE for an
   ACTIVE lease timestamped 2020. Pure function reproduced. It also does not
   verify watcher identity. Return UNKNOWN/STALE (document actual contract)
   unless freshness, PID identity and run association are verified.
   Preserve raw lifecycle and last evidence separately. V2 must not turn the
   label into proof of protection.

4. PROBABLE concurrency risk — _write_registry is direct write_text.
   Supervisor and sentinel perform whole-record read/modify/write without
   shared lock or compare-and-swap. Lost updates/truncated reads are possible;
   heartbeat/finalization code also lacks ownership fencing against a replaced
   lease. Require concurrent-writer/takeover tests and owner-guarded writes.
   Atomic rename alone avoids torn files but does not prevent lost updates.
   No concurrent corruption was reproduced in this review.

5. Integration blocker — start_probe contains no supervisor/sentinel launch.
   V2 runtimeAction still invokes start_probe alone; runtimeStatus maps the
   supervisor but drops the new sentinel block. Additive backend fields do not
   imply V2 rendering. Keep start disabled until a canonical transactional
   supervised launch verifies both leases and rolls back partial startup.
   Do not solve this by frontend spawning independent watchers.

## Documentation corrections

Report says 69 summaries + final; parsed log contains 68 kind=summary + one
final_summary. Final duration is 2102.147 vs submitted 2102.5.
Report baseline says pre-run 66/228 while handoff says 57/202: distinguish
35-minute preflight from subsequent brief-run preflight.
Report lists dashboard.py changed, absent from this commit.
Buffered output explains missing diagnostics, not the actual cause of watcher
death; exact killer remains unknown. -u/flush improve observability, not
process lifetime. Qualify global PASS with the long sentinel gap.

## V2 decision and closeout

No gate advancement, 4–6h authorization or new 35-minute run. No UI code change;
visual verification NOT APPLICABLE for this documentation-only review.
Next frontend work: read-only sentinel presentation with honest availability,
plus timestamped recorded host/universe/research fields after stable contracts.
DECISIONS_REVIEWED: V2 runtime mapping, launch-readiness, control and sentinel,
owner report and real logs.
NEW_DECISIONS_RECORDED: no strategy change; integration remains blocked.
FEATURES_IMPLEMENTED: none in this review.
FEATURES_VERIFIED: existing F-V2-BFF-01 remains PARTIAL; sentinel path not mapped.
DEFERRED_FEATURES: supervised V2 start and reliable active sentinel presentation.
BACKLOG_UPDATED: review blockers recorded in V2 documentation.
DOCUMENTATION_CONFLICTS: five evidence/scope discrepancies above.
