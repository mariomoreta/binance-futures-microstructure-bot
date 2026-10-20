# WORKFLOW

## Active scope override (2026-10-20)

`docs/DESKTOP_FIRST_SCOPE_20261020.md` governs current delivery: desktop web
only. Visual verification remains required for desktop changes. Mobile
layouts, 360/390 px QA/captures and Flutter are deferred and must not block
acceptance or create tasks. Preserve historical mobile evidence.


For every engineering task:

```text
AUDIT → IMPLEMENT (minimal) → targeted tests → static/type checks
  → safe live verification (when applicable)
  → update CURRENT_STATE → update DECISIONS (if methodology changed)
  → update TASK_QUEUE → selective Git commit
  → evaluate phase gate → choose next authorized task
```

For every Dashboard V2 slice, the binding expansion is:

```text
AUDIT → PLAN → IMPLEMENT → TEST → VISUAL VERIFY
  → DOCUMENT → CHECKPOINT → NEXT
```

`VISUAL VERIFY` means a fresh render/capture compared with the approved
reference at the required viewport(s). It is mandatory for visual changes and
may be marked `NOT APPLICABLE` only for documentation-only or nonvisual work.
Tests do not substitute for visual evidence. See
`docs/DASHBOARD_V2_MIGRATION_PLAN.md` and
`.agents/skills/dashboard-v2/SKILL.md`.

## Step details

1. **AUDIT** — read the actual files/config/tests involved. State what exists
   before touching it. No assumptions from filenames.
2. **IMPLEMENT** — smallest change that completes the task. Extend the
   baseline; don't restructure speculatively. Thresholds go in config, not code.
3. **Tests** — add/extend targeted unit tests (known-value style). Full suite
   must pass via the canonical command from the repo root:
   `python run_tests.py` (see `docs/COMMANDS.md`).
4. **Static/type checks** — available tooling as configured; keep imports and
   public behavior clean.
5. **Safe live verification** — public streams only, bounded `--duration`,
   logs via external capture. The probe itself stays stateless; durable
   storage goes through the P1-02 persistence foundation, never ad-hoc files.
6. **Document** — `CURRENT_STATE` reflects reality; `DECISIONS` gets
   methodology changes; `TASK_QUEUE` advances. Never describe intent as done.
7. **Checkpoint** — selective `git add` of the coherent unit; evidence-backed
   message. Never blind bulk staging when unrelated work exists.
8. **Gate** — check `docs/SUCCESS_GATES.md`: did this move a gate? Say which,
   with evidence link.
9. **Next** — pick the next authorized task in the current phase only.

For Dashboard V2, `PLAN` records the bounded slice, contracts, acceptance
criteria, and rollback boundary before implementation. `TEST` includes
contract and regression checks. `VISUAL VERIFY` follows those checks and
precedes factual documentation.

## Autonomous loop

`LOOP PHASE <n>` repeats the above across tasks already authorized in phase n.
It MUST STOP when: human authorization is required; live/account mutation
would be needed; methodology or strategy change is required; evidence
contradicts the plan; tests fail unresolved; external dependency blocks;
destructive migration required; secrets needed; or the phase gate is reached.
Never "keep coding until something looks profitable."
