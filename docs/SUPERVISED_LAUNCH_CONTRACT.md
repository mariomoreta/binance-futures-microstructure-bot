# Supervised transactional launch — contract (preparation, DISABLED)

Status: PREPARATION ONLY. Operational access is disabled
(`control.SUPERVISED_LAUNCH_ENABLED = False`); the public entry point
refuses without spawning anything. No HTTP route, CLI subcommand, Start
enablement, probe launch, gate advancement or trading follows from this
document. Enabling requires explicit authorization plus a code change, and
a V2 review of the exact enabled SHA.

Reused mechanisms (no parallel controller): `start_probe` (spawn + locked
STARTING commit + same-child adoption + log handoff), probe
self-registration (`try_register`), registry leases (`claim_supervision` /
`claim_sentinel`), PID+image+ctime identity (`is_canonical_pid`,
`pid_is_ours`, `own_creation_time`), handle-bound verified termination
(`_terminate_verified_pid`), the sidecar registry lock (`update_registry`),
and pure observation (`read_registry` / `status_readonly`).

## 1. Preconditions and required capacity

- P1: no live canonical run holds the registry (an active record whose PID
  is alive, python-image and ctime-matched). A live foreign run rejects the
  transaction before any spawn.
- P2: the registry lock is acquirable (a no-write locked probe that raises
  `OSError` rejects the transaction as `registry-unavailable`).
- P3: capacity bound -- at most one active run per registry and at most
  three processes per transaction (probe + supervisor + sentinel). The
  launcher identity string is required (no anonymous launches).
- P4: an evidence directory is creatable/writable for the controlled log
  (owned by `start_probe`; failures surface, never silent).

## 2. Identity and association of each process with the run

- Probe: PID + creation-time captured at spawn; the run record must show
  the same PID+ctime (`_commit_start` adoption or STARTING commit).
- Supervisor: lease must be ACTIVE, `pid` == spawned supervisor PID,
  `watched_pid` == run PID, `create_time` == spawn-captured supervisor
  ctime, and the watcher must be alive with matching ctime.
- Sentinel: same rule on the `sentinel` lease with the spawned sentinel
  PID/ctime.
- Association is always lease→run (`watched_pid` == run PID); a lease
  owned by the right PID but bound to another run is wrong-run and never
  confirms. Timestamps must parse and be strictly non-future and
  fresh (within `SUPERVISOR_LEASE_FRESH_S`).

## 3. Launch sequence

1. Preflight: validate finite budget/cadence and launcher, then P1-P4.
   No process or registry-record write; sidecar lock and an owned temporary
   evidence write-test are permitted filesystem preparation effects.
2. Probe step: `start_probe` (spawn, same-child adoption, log handoff).
   Refusal stops the transaction with nothing else launched.
3. Spawn supervisor, then sentinel (injectable spawners; production
   spawners Popen the canonical `control supervise` / `control sentinel`
   entry points with merged UTF-8 logs). Any spawn failure rolls back.
4. Verification loop (§5) over pure registry reads until confirmation,
   terminal/takeover evidence, or budget exhaustion.
5. Rollback (§6) on every non-confirmed outcome that launched anything.

## 4. Supervisor and sentinel confirmation criteria

Each watcher confirms only when, on one fresh read: its lease exists and
is ACTIVE; `lease.pid` == spawned watcher PID; `lease.create_time` ==
spawn-captured ctime; `lease.watched_pid` == run PID; the watcher is
alive with matching ctime (injected identity check; production
`pid_is_ours`); `last_check_at` parses and its age is within
[0s, `SUPERVISOR_LEASE_FRESH_S`]. The run record on the same read must
be STARTING/RUNNING with the transaction PID+ctime and canonical
liveness. Popen success, an ACTIVE lease alone, or a recent heartbeat
alone NEVER confirms.

## 5. Finite verification budget

`verify_budget_s` total with `poll_interval_s` cadence (defaults 60s / 2s;
tests use milliseconds). The loop exits on: full confirmation, terminal
or takeover evidence (early reject), or budget exhaustion (timeout
reject). Poll reads are pure; the verification phase performs zero
registry writes.

## 6. Partial failure, cancellation and rollback

- Any component spawn/registration failure, any failed confirmation
  condition, timeout, takeover/STOPPING/terminal interleave, or write
  failure triggers rollback of everything this transaction launched.
- Rollback acts ONLY on transaction PIDs with spawn-captured identity,
  in reverse order (sentinel, supervisor, probe), via verified
  termination. Already-dead processes count as cleaned (`already-gone`).
- Foreign runs and terminal records are never written, marked, or killed
  by rollback. Registry reconciliation stays with `status()`.
- Cancellation is cooperative: there is no remote abort of an in-flight
  launch; a caller stops polling and the budget expiry drives the same
  reject+rollback path.
- If any launched process cannot be verified dead (kill refused, still
  alive on recheck, or identity lost to PID reuse) or the registry cannot
  be read to assess the final state, the outcome is UNCERTAIN with pending
  evidence per process -- never declared completed.

## 7. Confirmed, rejected or uncertain outcomes

- `confirmed`: every §4 condition held simultaneously on one fresh read
  inside the budget. Point-in-time only: it certifies the transaction
  started supervised, NOT future protection, liveness, or health.
- `rejected`: preconditions failed (nothing launched) or verification
  failed/timed out with rollback fully verified (every transaction
  process confirmed dead and no owned live run remains).
- `uncertain`: rollback incomplete or unverifiable. Carries `pending`
  evidence (`role`, `pid`, reason) and the last observed record state.
  Requires operator follow-up; never reinterpret as completed.
- Response envelope (stable keys for BFF review): `outcome`, `reason`,
  `run: {pid, create_time}`, `watchers: {supervisor: {pid, create_time,
  confirmed}, sentinel: {...}}`, `verification: {polls, ages, budget_s}`,
  `rollback: {cleaned, pending}`, `evidence: {log}`, `scope`
  (`"point-in-time confirmation, not future protection"`).

## 8. Backend / BFF responsibilities and field compatibility

- Backend owns: preconditions, spawn, verification, rollback, and the
  outcome envelope above. It exposes NO enabled HTTP/CLI launch operation
  in this preparation (`SUPERVISED_LAUNCH_ENABLED = False`; the entry
  point returns `rejected/supervised-launch-disabled` without side
  effects).
- BFF owns: Start remaining disabled, preflight unwillingness display,
  and -- once a future review enables -- rendering `outcome/reason`,
  per-watcher confirmation, `pending` evidence, and the point-in-time
  scope disclaimer. No new wire contract is introduced here: the envelope
  reuses existing registry field names (`state`, `pid`, `create_time`,
  `watched_pid`, `last_check_at`, `lease_state`) plus the additive result
  keys above, all nullable-safe. `status_readonly()` stays the GET path;
  launch polling must use pure reads.


## V2-62 correction design (recorded before implementation, 2026-10-11)

The public operation remains disabled. A private optional spawn callback on start_probe passes the actual Popen child and captured ctime directly to the transaction before registration/handoff. Existing callers/results retain their semantics. Registry reads validate association only; they never establish transaction ownership. Missing captured ctime cannot confirm or authorize PID-only rollback; it remains UNCERTAIN unless process absence is independently proved.

Verification uses one lease evaluation per watcher retaining its age, strict non-future freshness, finite positive budget and finite nonnegative cadence validated before effects. The verification budget starts after spawns and is checked before polling and after read/identity callbacks; sleeps clamp to remaining budget. This is a bounded verification loop, not a hard wall-clock bound on blocking Popen, identity, lock, IO or termination calls. Default supervisor command maps role supervisor to CLI supervise.

Rollback distinguishes owned, gone, replaced and unknown process identities. Only owned identities may be terminated; only independently proved gone identities count as cleaned. Replaced/unknown remain pending. Verification/rollback never write registry records. A final pure registry read is required to assess cleanup; unreadable/malformed final observation yields UNCERTAIN with registry assessment pending, even after successful simulated process cleanup. No completed-cleanup declaration from missing evidence. Rollback is run once per failure path.

P2 is an actual no-write sidecar lock acquisition before any spawn. P4 checks evidence directory using an exclusively created temporary file that is closed and removed. This may create directories and sidecar files; it is not a claim of filesystem-pure preflight. No unapproved runtime operation follows.
