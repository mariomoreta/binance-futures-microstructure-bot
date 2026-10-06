# WORKFLOW

For every engineering task:

```text
AUDIT → IMPLEMENT (minimal) → targeted tests → static/type checks
  → safe live verification (when applicable)
  → update CURRENT_STATE → update DECISIONS (if methodology changed)
  → update TASK_QUEUE → selective Git commit
  → evaluate phase gate → choose next authorized task
```

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

## Autonomous loop

`LOOP PHASE <n>` repeats the above across tasks already authorized in phase n.
It MUST STOP when: human authorization is required; live/account mutation
would be needed; methodology or strategy change is required; evidence
contradicts the plan; tests fail unresolved; external dependency blocks;
destructive migration required; secrets needed; or the phase gate is reached.
Never "keep coding until something looks profitable."
