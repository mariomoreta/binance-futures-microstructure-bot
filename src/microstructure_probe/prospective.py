"""P1-14A prospective setup evaluation foundation (research only).

Registers P1-13A opportunity setups at detection and observes forward
outcomes at versioned horizons. Never computes executable P&L, never
looks ahead, never fabricates probabilities.

Horizons (proposed, finalize only when enough genuinely later data
exists): 1m / 5m / 15m / 1h / 4h.

Outcome metrics (directional mark-price return, MFE/MAE, time to
extrema, completeness). Missing != zero. Incomplete outcomes stay
PENDING/INVALID — never forced to COMPLETE.
"""

from __future__ import annotations

import math
import logging
import queue
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LOGGER = logging.getLogger(__name__)

PROSPECTIVE_SCHEMA_VERSION = 9

HORIZONS_MS: Dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
}
HORIZON_ORDER = ("1m", "5m", "15m", "1h", "4h")

OUTCOME_COMPLETE = "COMPLETE"
OUTCOME_PARTIAL = "PARTIAL"
OUTCOME_INVALID_GAP = "INVALID_GAP"
OUTCOME_INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
OUTCOME_PENDING = "PENDING"

SETUP_REGISTRATION_REASON = "first qualifying detection"
SETUP_DUPLICATE_REASON = "duplicate evaluation — same episode"

# Outcome Contract version (P1-14B.4): v1.1 adds freshness verdicts, strict
# unknown-age handling, and grace-deferred terminal PENDING. Schema stays v9.
PROSPECTIVE_CONTRACT_VERSION = "1.1"

# LOCAL_POLICY (P1-14B.3): a mark quote older than this at observation time
# is too stale to complete a horizon. Such horizons record PENDING with an
# explicit reason instead of a stale-price COMPLETE.
STALE_MARK_AGE_MS = 120_000

# LOCAL_POLICY (P1-14B.4): magnitude of negative age tolerated as
# snapshot/observe clock skew. Beyond this the quote is ahead of the
# observation clock (clock pathology), never silently clamped to fresh.
_FUTURE_AGE_TOLERANCE_MS = 1_000


def _fnum(value: Any) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _normalize_candidate_key(key: Any) -> Optional[str]:
    if not isinstance(key, str) or not key:
        return None
    return key


def _classify_mark_age(mark_age_ms: Any) -> Tuple[str, Optional[float]]:
    """Classify an observation-time quote age (pure, testable).

    Returns (verdict, value) with verdict in:
      ok        -- finite age >= -tolerance (tiny negatives clamped to 0.0)
      unknown   -- None / malformed (UNKNOWN is never FRESH)
      nonfinite -- inf / nan (would otherwise slip comparisons silently)
      future    -- quote ahead of the observation clock beyond tolerance
    """
    if mark_age_ms is None:
        return ("unknown", None)
    try:
        age = float(mark_age_ms)
    except (TypeError, ValueError):
        return ("unknown", None)
    if not math.isfinite(age):
        return ("nonfinite", None)
    if age < -_FUTURE_AGE_TOLERANCE_MS:
        return ("future", None)
    if age < 0:
        return ("ok", 0.0)
    return ("ok", age)


class ProspectiveRecorder:
    """Register opportunity setups and observe forward outcomes.

    Idempotent, restart-safe, bounded. Lives inside the canonical
    probe process — never a second process, never independent launcher.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        max_queue: int = 1000,
        retention_days: Optional[Dict[str, int]] = None,
        enabled: bool = True,
    ) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.max_queue = max(16, int(max_queue))
        self.retention_days = retention_days or {
            "prospective_setups": 90,
            "prospective_outcomes": 90,
        }
        self.enabled = bool(enabled)
        self.state = "DISABLED" if not enabled else "READY"
        self._queue: "queue.Queue[Any]" = queue.Queue(maxsize=self.max_queue)
        self._registered: Dict[str, Dict[str, Any]] = {}
        self._seen_outcomes: set = set()
        # P1-14B.4: grace-deferred PENDING. Maps (candidate_key, horizon) to
        # the first failed-evaluation ms; a horizon records terminal PENDING
        # only after now - first exceeds one horizon-length past maturity
        # (recovery window; obs < det + 2H bound). Memory-only: a restart
        # restarts grace (bounded, documented). Cleared on terminal emission.
        self._pending_since: Dict[Tuple[str, str], int] = {}
        self._writes = 0
        self._drops = 0
        self._errors = 0
        self._completed = 0
        self._pending = 0
        self._insufficient = 0
        self._inflight = 0
        self._high_water = 0
        self._last_cleanup = 0.0
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._load_from_db()

    def _load_from_db(self) -> None:
        """Restart safety: rehydrate in-memory registry from DB.

        Uses the default store when no explicit db_path was given (the
        production configuration: config/probe.json carries no db_path),
        mirroring the worker/read paths. Also rebuilds the seen-outcome
        set from stored outcome rows so already-observed horizons never
        re-emit after a restart (exact cross-restart idempotency).
        """
        if not self.enabled:
            return
        try:
            from .persistence import PersistenceStore
            store = PersistenceStore(db_path=self.db_path) if self.db_path else PersistenceStore()
            store.init_db()
            for setup in store.prospective_setups():
                key = setup.get("candidate_key")
                if key:
                    self._registered[key] = setup.get("setup_json", {})
            for key, horizon in store.prospective_outcome_keys():
                self._seen_outcomes.add((key, horizon))
        except Exception as exc:
            LOGGER.warning("prospective rehydrate failed: %r", exc)

    # -- lifecycle ------------------------------------------------

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self.state = "RUNNING"
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._worker, name="prospective-recorder", daemon=True
        )
        self._thread.start()

    def stop_and_drain(self, timeout: float = 10.0) -> Dict[str, Any]:
        self._stop.set()
        thr = self._thread
        if thr is not None:
            thr.join(timeout=timeout)
        self._thread = None
        if self.enabled:
            self.state = "STOPPED"
        return self.status()

    # -- public API -----------------------------------------------

    def register_setup(
        self, candidate_key: str, setup_record: Dict[str, Any], as_of_ms: int
    ) -> bool:
        """Register a setup at first DETECTED occurrence.

        Returns True when newly registered, False when duplicate
        (same candidate_key already known — same episode, no new
        independent observation) or when disabled.
        """
        if not self.enabled:
            return False
        key = _normalize_candidate_key(candidate_key)
        if key is None:
            return False
        now_ms = int(as_of_ms)
        with self._lock:
            if key in self._registered:
                return False
            self._registered[key] = {
                "candidate_key": key,
                "detected_at_ms": now_ms,
                "detected_mark_price": setup_record.get("detect_price"),
                "setup_family": setup_record.get("setup_family"),
                "direction": setup_record.get("direction"),
                "market_state": setup_record.get("market_state"),
                "rules_version": setup_record.get("rule_version"),
                "capability_tier": setup_record.get("capability_tier"),
                "symbol": setup_record.get("symbol"),
                "score": (setup_record.get("ranking") or {}).get("score"),
                "lifecycle": setup_record.get("lifecycle"),
                "evidence_for": setup_record.get("evidence_for", []),
                "evidence_against": setup_record.get("evidence_against", []),
                "missing_features": setup_record.get("missing_features", []),
                "data_freshness": setup_record.get("data_freshness", {}),
            }
            try:
                self._queue.put_nowait(("register", key, now_ms))
            except queue.Full:
                self._drops += 1
                return False
        return True

    def observe(
        self, symbol: str, as_of_ms: int, mark_price: Optional[float],
        mark_age_ms: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Check matured horizons for registered setups of this symbol.

        Returns newly matured outcomes (empty list when none ready).
        Never accesses data at or before detection time for outcome
        computation — only strictly later observations.
        Contract v1.1: mark_age_ms is classified strictly (UNKNOWN is never
        FRESH). Horizons that mature without a valid sample retry silently
        (absent, no row) while within the recovery window (one
        horizon-length past maturity); only after the window exhausts is
        terminal PENDING recorded. INSUFFICIENT_HISTORY (no reference) stays
        immediate + terminal.
        """
        sym = str(symbol).upper()
        now_ms = int(as_of_ms)
        age_verdict, age_value = _classify_mark_age(mark_age_ms)
        matured: List[Dict[str, Any]] = []
        with self._lock:
            for key, reg in list(self._registered.items()):
                if reg.get("symbol") != sym:
                    continue
                for horizon in HORIZON_ORDER:
                    horizon_ms = HORIZONS_MS[horizon]
                    mature_at = reg["detected_at_ms"] + horizon_ms
                    if now_ms < mature_at:
                        continue
                    outcome_key = (key, horizon)
                    if outcome_key in self._seen_outcomes:
                        continue
                    if reg.get("detected_mark_price") is None:
                        outcome = self._compute_outcome(
                            key, reg, horizon, mature_at, now_ms, mark_price,
                            pending_reason="no detection-time reference price",
                            insufficient=True,
                        )
                        self._emit_locked(key, horizon, now_ms, outcome, outcome_key, matured)
                        continue
                    pending_reason = self._freshness_failure(
                        mark_price, age_verdict, age_value)
                    if pending_reason is None:
                        outcome = self._compute_outcome(
                            key, reg, horizon, mature_at, now_ms, mark_price)
                        self._pending_since.pop(outcome_key, None)
                        self._emit_locked(key, horizon, now_ms, outcome, outcome_key, matured)
                        continue
                    # Failed evaluation: grace-deferred terminal PENDING.
                    first = self._pending_since.setdefault(outcome_key, now_ms)
                    if now_ms - first > horizon_ms:
                        outcome = self._compute_outcome(
                            key, reg, horizon, mature_at, now_ms, mark_price,
                            pending_reason=pending_reason + "; recovery window exhausted",
                        )
                        self._pending_since.pop(outcome_key, None)
                        self._emit_locked(key, horizon, now_ms, outcome, outcome_key, matured)
                    # else: within recovery window — absent, retry next tick.
        return matured

    @staticmethod
    def _freshness_failure(mark_price: Optional[float], age_verdict: str,
                           age_value: Optional[float]) -> Optional[str]:
        """Return a PENDING reason when the sample is unusable, else None."""
        if mark_price is None:
            return "no mark price available at maturity"
        if age_verdict == "unknown":
            return ("unknown mark age; maturity honest, "
                    "quote freshness unverifiable")
        if age_verdict == "nonfinite":
            return ("non-finite mark age; maturity honest, "
                    "quote freshness unverifiable")
        if age_verdict == "future":
            return ("mark quote ahead of observation clock; "
                    "maturity honest, clock pathology")
        if age_value is not None and age_value > STALE_MARK_AGE_MS:
            return ("stale mark price (age %dms exceeds %dms); "
                    "maturity honest, quote too old" % (int(age_value), STALE_MARK_AGE_MS))
        return None

    def _emit_locked(self, key: str, horizon: str, now_ms: int,
                     outcome: Dict[str, Any], outcome_key: Tuple[str, str],
                     matured: List[Dict[str, Any]]) -> None:
        """Record one terminal outcome (seen + counters + queue). Lock held."""
        state = outcome.get("outcome_state")
        if state == OUTCOME_COMPLETE:
            self._completed += 1
        elif state == OUTCOME_PENDING:
            self._pending += 1
        elif state == OUTCOME_INSUFFICIENT_HISTORY:
            self._insufficient += 1
        self._seen_outcomes.add(outcome_key)
        matured.append(outcome)
        try:
            self._queue.put_nowait(("outcome", key, horizon, now_ms, outcome))
        except queue.Full:
            self._drops += 1

    def _worker(self) -> None:
        from .persistence import PersistenceStore
        try:
            db = PersistenceStore(db_path=self.db_path) if self.db_path else PersistenceStore()
            db.init_db()
            while not self._stop.is_set() or not self._queue.empty():
                try:
                    item = self._queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                try:
                    kind = item[0]
                    if kind == "register":
                        _, key, detected_at_ms = item
                        db.store_prospective_setup(key, self._registered[key], detected_at_ms)
                    elif kind == "outcome":
                        _, key, horizon, observed_at_ms, outcome = item
                        sym = self._registered.get(key, {}).get("symbol", "")
                        db.store_prospective_outcome(
                            key, sym, horizon, observed_at_ms, outcome)
                    with self._lock:
                        self._writes += 1
                except Exception:
                    with self._lock:
                        self._errors += 1
                        if self.state == "RUNNING":
                            self.state = "DEGRADED"
                finally:
                    with self._lock:
                        self._inflight = self._queue.qsize()
                        if self._inflight > self._high_water:
                            self._high_water = self._inflight
                    now = time.monotonic()
                    if now - self._last_cleanup > 3600 and self.enabled:
                        self._last_cleanup = now
                        try:
                            db.research_retention_cleanup(self.retention_days)
                        except Exception:
                            self.log_error("retention cleanup failed")
        except Exception as exc:
            import sys
            print(f"WORKER CRASHED: {exc!r}", file=sys.stderr, flush=True)
            raise

    def _compute_outcome(
        self,
        key: str,
        reg: Dict[str, Any],
        horizon: str,
        mature_at: int,
        as_of_ms: int,
        mark_price: float,
        pending_reason: Optional[str] = None,
        insufficient: bool = False,
    ) -> Dict[str, Any]:
        detected_price = reg.get("detected_mark_price")
        if detected_price is None or insufficient:
            return {
                "candidate_key": key,
                "horizon": horizon,
                "observed_at_ms": as_of_ms,
                "outcome_state": OUTCOME_INSUFFICIENT_HISTORY,
                "reason": "no detection-time reference price",
            }
        if pending_reason is not None:
            return {
                "candidate_key": key,
                "horizon": horizon,
                "observed_at_ms": as_of_ms,
                "outcome_state": OUTCOME_PENDING,
                "reason": pending_reason,
            }
        ret = (mark_price - detected_price) / detected_price * 100.0
        return {
            "candidate_key": key,
            "horizon": horizon,
            "observed_at_ms": as_of_ms,
            "outcome_state": OUTCOME_COMPLETE,
            "mark_return_pct": round(ret, 6),
            "detected_price": detected_price,
            "current_price": mark_price,
            "reason": "horizon matured with valid reference",
        }

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "state": self.state,
                "registered_setups": len(self._registered),
                "writes": self._writes,
                "drops": self._drops,
                "errors": self._errors,
                "inflight": self._queue.qsize(),
                "high_water": self._high_water,
                "completed": self._completed,
                "pending": self._pending,
                "insufficient": self._insufficient,
                "in_grace": len(self._pending_since),
            }

    def registered_setups(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._registered.values())

    def outcomes_for(self, candidate_key: str) -> List[Dict[str, Any]]:
        """Outcomes for one candidate (re-read from persistence store)."""
        from .persistence import PersistenceStore
        store = PersistenceStore(db_path=self.db_path) if self.db_path else PersistenceStore()
        return store.prospective_outcomes(candidate_key=candidate_key, limit=50)