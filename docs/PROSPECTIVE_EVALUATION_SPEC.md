# P1-14A Prospective Setup Evaluation — Specification

**Status:** IMPLEMENTED · VERIFIED (tests + 554/554 suite) · 2026-10-08
**Module:** `src/microstructure_probe/prospective.py`
**Schema:** Persistence v9 (`prospective_setups`, `prospective_outcomes`)
**Dashboard:** `/api/prospective` (read-only, RESEARCH ONLY banner)

---

## Purpose

Register P1-13A opportunity setups at first **DETECTED** occurrence and observe **forward mark-price outcomes** at versioned horizons. Research-only; no executable P&L, no lookahead, no fabricated probabilities.

---

## Horizons (ms)

| Horizon | ms        |
|---------|-----------|
| 1m      | 60,000    |
| 5m      | 300,000   |
| 15m     | 900,000   |
| 1h      | 3,600,000 |
| 4h      | 14,400,000 |

Order of maturity evaluation: `1m → 5m → 15m → 1h → 4h`.

---

## Registration (idempotent)

- **Trigger:** Candidate lifecycle == `DETECTED` and `evals_in_lifecycle <= 1`.
- **Key:** `candidate_key` (symbol + family + timestamp; same episode → same key).
- **Duplicate handling:** Returns `False`, no new registration.
- **Persisted fields:**
  - `candidate_key`, `symbol`, `setup_family`, `direction`, `market_state`
  - `rules_version`, `capability_tier`, `detected_at_ms`, `detected_mark_price`
  - `score`, `lifecycle`, `evidence_for`, `evidence_against`, `missing_features`, `data_freshness`

---

## Observation (no lookahead)

- Called once per summary cycle with **current** `as_of_ms` and **current** `mark_price`.
- For each registered setup of the observed symbol:
  - For each horizon in order:
    - If `now_ms < detected_at_ms + horizon_ms` → skip (not matured).
    - If `(candidate_key, horizon)` already in `_seen_outcomes` → skip (dedup).
    - Compute outcome using **only** the mark price at observation time.
- Never uses price data at or before detection time for outcome computation.

---

## Outcome States

| State                     | Meaning                                                             |
|---------------------------|---------------------------------------------------------------------|
| `COMPLETE`                | Horizon matured with valid reference price; return computed.        |
| `PENDING`                 | Horizon matured but no mark price available at maturity.            |
| `INSUFFICIENT_HISTORY`    | Setup lacked `detected_mark_price` (no reference).                  |
| `INVALID_GAP`             | (Reserved) Gap in data exceeds tolerance.                           |
| `PARTIAL`                 | (Reserved) Some but not all required data present.                  |

**Missing ≠ zero.** Incomplete outcomes stay `PENDING` / `INVALID_GAP` / `INSUFFICIENT_HISTORY` — **never forced to `COMPLETE`**.

---

## Outcome Payload (COMPLETE)

```json
{
  "candidate_key": "REV_BTCUSDT_1717000000000",
  "horizon": "1m",
  "observed_at_ms": 1717000060000,
  "outcome_state": "COMPLETE",
  "mark_return_pct": 1.0,
  "detected_price": 100000.0,
  "current_price": 101000.0,
  "reason": "horizon matured with valid reference"
}
```

Formula: `mark_return_pct = (current - detected) / detected * 100`.

---

## Idempotency & Restart Safety

- In-memory `_registered` rehydrated from DB on `ProspectiveRecorder` construction (`_load_from_db`).
- `_seen_outcomes` set prevents duplicate outcome emission across restarts.
- Persistence uses `INSERT OR REPLACE` with unique constraint `(candidate_key, horizon, observed_at_ms)`.

---

## Bounded Storage

- **In-memory queue:** `max_queue` (default 1000). Drops counted in telemetry.
- **Persisted outcomes per setup:** max 500 (oldest purged on insert).
- **Retention cleanup:** `research_retention_cleanup(retention_days)` — deletes rows older than configured days (default 90). Runs at most hourly.

---

## Telemetry (status())

```json
{
  "enabled": true,
  "state": "RUNNING",
  "registered_setups": 42,
  "writes": 128,
  "drops": 0,
  "errors": 0,
  "inflight": 3,
  "high_water": 17
}
```

State machine: `DISABLED → READY → RUNNING → DEGRADED (on DB error) → STOPPED`.

---

## Dashboard Integration

- **Endpoint:** `GET /api/prospective`
- **Response:**
  ```json
  {
    "generated_at": "2026-10-08T12:00:00Z",
    "note": "RESEARCH ONLY — NOT A TRADE SIGNAL. Forward outcome observation for P1-13A setups. Horizons: 1m/5m/15m/1h/4h.",
    "schema_version": 9,
    "prospective": { /* status() + setup_count + outcome_count + latest_outcomes[:10] */ }
  }
  ```

---

## Limitations (Statistical)

- **No probability estimation:** Returns are observed, not predicted.
- **No MFE/MAE:** Only directional mark-price return at exact horizon.
- **No slippage/execution model:** Mark price ≠ fill price.
- **Survivorship:** Only setups that reach `DETECTED` are registered.
- **Clock dependency:** Uses probe's wall clock (`_wall_clock_ms()`). Skew tolerated by 60s freshness gate upstream.
- **Sample size:** Early horizons (1m) mature quickly; 4h needs genuinely later data.

---

## Tests

`tests/test_prospective.py` — 35 deterministic tests covering:
- Unit helpers (`_fnum`, `_normalize_candidate_key`)
- Registration (idempotent, duplicate, disabled, invalid key, persist, restart)
- Observation (pre-maturity, at maturity, no-lookahead, dedup, symbol isolation)
- Missing mark price, missing detection price
- Queue backpressure / drops
- Status shape (enabled/disabled)
- Schema v9 (tables, indexes, version)
- Persistence round-trip (setup + outcome, idempotent, bounded 500)
- Outcome determinism (LONG positive, SHORT negative, no fabrication)
- Multiple horizons mature
- Dashboard integration (`prospective_status` shape + empty)
- Retention cleanup

Full suite: **554/554 tests pass**.