"""Persistence foundation for Phase 1 market intelligence dashboard.

Provides local SQLite persistence for:
- Telemetry snapshots (feeding P1-03 dashboard)
- Raw market observations (preserved for P1-04+ features)
- Rejection telemetry (skew-invalid messages counted but not valid inputs)

Designed to be:
- Local only (project-local data/ directory, git-ignited)
- Observe-only (no trading/order paths)
- Non-blocking (async DB writes via asyncio.to_thread)
- Bounded growth (retention policies)
- Extensible schema (JSON columns for future features)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from . import models

LOGGER = logging.getLogger("microstructure_probe.persistence")

# Dedicated single-thread writer for telemetry snapshots. Rationale (found
# during P1-03 live verification): observation writes share the default
# executor; under message floods their per-insert retention DELETEs saturate
# all default workers and snapshot tasks starve behind thousands of queued
# observation writes â€” the dashboard feed would stay empty forever during
# live runs. Snapshots are rare (every ~30s) and must never wait behind
# bulk observation traffic.
_SNAPSHOT_EXECUTOR: Optional[ThreadPoolExecutor] = None
_SNAPSHOT_EXECUTOR_LOCK = threading.Lock()


def _snapshot_executor() -> ThreadPoolExecutor:
    global _SNAPSHOT_EXECUTOR
    if _SNAPSHOT_EXECUTOR is None:
        with _SNAPSHOT_EXECUTOR_LOCK:
            if _SNAPSHOT_EXECUTOR is None:
                _SNAPSHOT_EXECUTOR = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="snapshot-writer")
    return _SNAPSHOT_EXECUTOR


def _safe_json(value: Any) -> str:
    """Serialize to JSON, falling back to a degraded record (never raises)."""
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        try:
            return json.dumps({"unserializable": str(value)})
        except (TypeError, ValueError):
            return "{}"


# Default observation sampling intervals (P1-04): persist at most one
# observation per kind/symbol per interval. markPrice arrays and forceOrder
# are ungated (already ~1/s and rare respectively).
DEFAULT_SAMPLE_INTERVAL_MS: Dict[str, int] = {
    "bookTicker": 1000,
    "aggTrade": 1000,
    "depth": 1000,
}


def _log_write_error(task: "asyncio.Task[None]") -> None:
    """Done-callback so fire-and-forget persistence failures are never silent."""
    if not task.cancelled():
        exc = task.exception()
        if exc is not None:
            LOGGER.warning(json.dumps({"kind": "persistence_error", "error": str(exc)}))


class PersistenceStore:
    """Manages SQLite persistence for market intelligence data.
    
    Thread-safe for concurrent access (SQLite handles this via file locking).
    Designed for observe-only, local persistence feeding the dashboard.
    """
    
    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        """Initialize persistence store.
        
        Args:
            db_path: Path to SQLite database file. Defaults to data/microprobe.db
                    in project root. Directory is created if needed.
        """
        if db_path is None:
            # Default to data/ directory (already git-ignored via .gitignore)
            db_path = Path(__file__).resolve().parent.parent.parent / "data" / "microprobe.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connection will be established on first use
        self._connection: Optional[sqlite3.Connection] = None
        self._initialized = False
        # Serializes DB access across the event-loop thread and writer threads
        self._lock = threading.Lock()

        # Retention policy: keep most recent N snapshots/observations
        self.max_snapshots = 1000  # telemetry snapshots
        self.max_observations = 10000  # market observations
        self.max_rejections = 1000  # rejection telemetry records
        self.max_price_samples_per_symbol = 9200  # ~25.5h of 10s buckets

        # Observation sampling gate (P1-04 backpressure remedy): minimum
        # event-time gap between two persisted observations of the same
        # (stream kind, symbol). First sighting always accepted. Empty dict
        # disables the gate (used by unit tests needing full fidelity).
        self.sample_interval_ms: Dict[str, int] = dict(DEFAULT_SAMPLE_INTERVAL_MS)
        self._sample_last_ms: Dict[str, int] = {}
        self._sample_accepted: Dict[str, int] = {}
        self._sample_dropped: Dict[str, int] = {}

        # In-flight fire-and-forget write tracking (queue high-water mark).
        self._inflight = 0
        self._inflight_high_water = 0

    def configure_sampling(self, overrides: Dict[str, int]) -> None:
        """Merge operator sampling overrides over the code defaults.

        A value <= 0 disables the gate for that stream kind.
        """
        for kind, interval in overrides.items():
            if interval is not None and int(interval) <= 0:
                self.sample_interval_ms.pop(str(kind), None)
            elif interval is not None:
                self.sample_interval_ms[str(kind)] = int(interval)

    @staticmethod
    def _sample_kind(stream_type: str) -> Optional[str]:
        """Bucket a full stream name to its sampling kind, if gated."""
        name = stream_type.lower()
        if "bookticker" in name:
            return "bookTicker"
        if "depth" in name:
            return "depth"
        if "aggtrade" in name:
            return "aggTrade"
        return None  # markPrice arrays, forceOrder, unknown: always persist

    def _sample_accept(self, stream_type: str, symbol: str,
                       event_time_ms: Optional[int]) -> bool:
        """Decide + record whether an observation write goes through."""
        kind = self._sample_kind(stream_type)
        if kind is None:
            return True
        interval = self.sample_interval_ms.get(kind)
        if interval is None or interval <= 0:
            return True
        now_ms = event_time_ms if event_time_ms is not None else int(time.time() * 1000)
        key = f"{kind}|{symbol.upper()}"
        last = self._sample_last_ms.get(key)
        if last is None or now_ms - last >= interval:
            self._sample_last_ms[key] = now_ms
            self._sample_accepted[kind] = self._sample_accepted.get(kind, 0) + 1
            return True
        self._sample_dropped[kind] = self._sample_dropped.get(kind, 0) + 1
        return False

    def sample_stats(self) -> Dict[str, Any]:
        """Accepted/dropped counts per stream kind (reported, never hidden)."""
        with self._lock:
            return {
                "accepted": dict(self._sample_accepted),
                "dropped": dict(self._sample_dropped),
                "gate_ms": dict(self.sample_interval_ms),
                "inflight": self._inflight,
                "inflight_high_water": self._inflight_high_water,
            }

    def _track_schedule(self) -> None:
        with self._lock:
            self._inflight += 1
            if self._inflight > self._inflight_high_water:
                self._inflight_high_water = self._inflight

    def _track_done(self) -> None:
        with self._lock:
            self._inflight = max(0, self._inflight - 1)
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create SQLite connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,  # Allow multi-thread access
                timeout=30.0
            )
            self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection
    
    @contextmanager
    def _get_cursor(self):
        """Context manager for database cursor with automatic commit/rollback.

        The lock serializes access across the event-loop thread and
        asyncio.to_thread writer threads sharing one connection.
        """
        conn = self._get_connection()
        with self._lock:
            cursor = conn.cursor()
            try:
                yield cursor
                conn.commit()
            except Exception as exc:
                conn.rollback()
                raise
            finally:
                cursor.close()
    
    def init_db(self) -> None:
        """Initialize database schema if not already done.
        
        Creates tables and initializes schema version.
        Idempotent - safe to call multiple times.
        """
        if self._initialized:
            return
            
        with self._get_cursor() as cursor:
            # Schema version tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS persistence_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            
            # Check current schema version
            cursor.execute(
                "SELECT value FROM persistence_meta WHERE key = 'schema_version'"
            )
            row = cursor.fetchone()
            current_version = int(row[0]) if row else 0
            
            if current_version >= 10:
                self._initialized = True
                return

            if current_version == 9:
                # Migrate v9 -> v10: add run_id linkage columns (P3).
                # Pre-existing rows keep run_id NULL (= UNKNOWN provenance,
                # never backfilled).
                self._ensure_run_id_columns(cursor)
                cursor.execute(
                    "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES (?, ?)",
                    ("schema_version", "10")
                )
                self._initialized = True
                return

            if current_version == 8:
                # Migrate v8 -> v9: add prospective setup tables.
                self._create_schema_v9(cursor)
                cursor.execute(
                    "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES (?, ?)",
                    ("schema_version", "9")
                )
                self._initialized = True
                return

            if current_version == 7:
                # Migrate v7 -> v9: keep existing rows, add P1-13A + P1-14A tables.
                self._create_schema_v8(cursor)
                self._create_schema_v9(cursor)
                cursor.execute(
                    "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES (?, ?)",
                    ("schema_version", "9")
                )
                self._initialized = True
                return

            if current_version == 6:
                # Migrate v6 -> v9: keep existing rows, add P1-12A + P1-13A + P1-14A tables.
                self._create_schema_v7(cursor)
                self._create_schema_v8(cursor)
                self._create_schema_v9(cursor)
                cursor.execute(
                    "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES (?, ?)",
                    ("schema_version", "9")
                )
                self._initialized = True
                return
                self._initialized = True
                return

            if current_version == 5:
                # Migrate v5 -> v9: keep existing rows, add P1-08 + P1-12A + P1-13A + P1-14A tables.
                self._create_schema_v6(cursor)
                self._create_schema_v7(cursor)
                self._create_schema_v8(cursor)
                self._create_schema_v9(cursor)
                cursor.execute(
                    "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES (?, ?)",
                    ("schema_version", "9")
                )
                self._initialized = True
                return

            if current_version == 4:
                # Migrate v4 -> v9: keep existing rows, add P1-07 + P1-08 + P1-12A + P1-13A + P1-14A tables.
                self._create_schema_v5(cursor)
                self._create_schema_v6(cursor)
                self._create_schema_v7(cursor)
                self._create_schema_v8(cursor)
                self._create_schema_v9(cursor)
                cursor.execute(
                    "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES (?, ?)",
                    ("schema_version", "9")
                )
                self._initialized = True
                return

            if current_version == 3:
                # Migrate v3 -> v9: keep existing rows, add P1-06..P1-08 + P1-12A + P1-13A + P1-14A tables.
                self._create_schema_v4(cursor)
                self._create_schema_v5(cursor)
                self._create_schema_v6(cursor)
                self._create_schema_v7(cursor)
                self._create_schema_v8(cursor)
                self._create_schema_v9(cursor)
                cursor.execute(
                    "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES (?, ?)",
                    ("schema_version", "9")
                )
                self._initialized = True
                return

            if current_version == 2:
                # Migrate v2 -> v9: keep existing rows, add P1-05..P1-08 + P1-12A + P1-13A + P1-14A tables.
                self._create_schema_v3(cursor)
                self._create_schema_v4(cursor)
                self._create_schema_v5(cursor)
                self._create_schema_v6(cursor)
                self._create_schema_v7(cursor)
                self._create_schema_v8(cursor)
                self._create_schema_v9(cursor)
                cursor.execute(
                    "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES (?, ?)",
                    ("schema_version", "9")
                )
                self._initialized = True
                return

            if current_version == 1:
                # Migrate v1 -> v9: keep existing rows, add P1-04..P1-08 + P1-12A + P1-13A + P1-14A tables.
                self._ensure_snapshot_columns(cursor)
                self._create_schema_v2(cursor)
                self._create_schema_v3(cursor)
                self._create_schema_v4(cursor)
                self._create_schema_v5(cursor)
                self._create_schema_v6(cursor)
                self._create_schema_v7(cursor)
                self._create_schema_v8(cursor)
                self._create_schema_v9(cursor)
                cursor.execute(
                    "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES (?, ?)",
                    ("schema_version", "9")
                )
                self._initialized = True
                return
                self._initialized = True
                return

            # Create tables for schema v1
            self._create_schema_v1(cursor)
            # Create tables for schema v2
            self._create_schema_v2(cursor)
            # Create tables for schema v3
            self._create_schema_v3(cursor)
            # Create tables for schema v4
            self._create_schema_v4(cursor)
            # Create tables for schema v5
            self._create_schema_v5(cursor)
            # Create tables for schema v6
            self._create_schema_v6(cursor)
            # Create tables for schema v7
            self._create_schema_v7(cursor)
             # Create tables for schema v8
            self._create_schema_v8(cursor)
            # Create tables for schema v9
            self._create_schema_v9(cursor)
            # v10 run linkage on fresh databases (same call, no second init).
            self._ensure_run_id_columns(cursor)

            # Set schema version
            cursor.execute(
                "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES (?, ?)",
                ("schema_version", "10")
            )

            self._initialized = True
    
    @staticmethod
    def _ensure_run_id_columns(cursor: sqlite3.Cursor) -> None:
        """P3 run linkage: nullable run_id on execution-linked tables.

        Idempotent (PRAGMA-checked, same idiom as _ensure_snapshot_columns).
        Existing rows keep NULL = UNKNOWN provenance; no backfill exists
        anywhere by design (see docs/RUN_LINKAGE_P3.md).
        """
        for table in ("universe_events", "prospective_setups",
                      "prospective_outcomes", "telemetry_snapshots"):
            cursor.execute("PRAGMA table_info(%s)" % table)
            existing = {row[1] for row in cursor.fetchall()}
            if "run_id" not in existing:
                cursor.execute(
                    "ALTER TABLE %s ADD COLUMN run_id TEXT" % table)
    
    @staticmethod
    def _ensure_snapshot_columns(cursor: sqlite3.Cursor) -> None:
        """Add columns introduced after schema v1 to pre-existing databases."""
        cursor.execute("PRAGMA table_info(telemetry_snapshots)")
        existing = {row[1] for row in cursor.fetchall()}
        if "spread_bps_json" not in existing:
            cursor.execute("ALTER TABLE telemetry_snapshots ADD COLUMN spread_bps_json TEXT")

    def _create_schema_v2(self, cursor: sqlite3.Cursor) -> None:
        """P1-04 feature tables: sampled price buckets + latest return features."""

        # Sampled 10s event-time price buckets (restart continuity for the
        # return engine, P1-05 velocity input). One row per symbol/bucket;
        # INSERT OR REPLACE makes rewrites idempotent. Bounded by timestamp
        # retention (~25.5h covers the 24h horizon + tolerance).
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_samples (
                symbol TEXT NOT NULL,
                bucket_ms INTEGER NOT NULL,
                price REAL NOT NULL,
                PRIMARY KEY (symbol, bucket_ms)
            )
        """)

        # Latest return feature record per symbol (dashboard reads). One row
        # per symbol, replaced on every feature persist — inherently bounded.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS return_features (
                symbol TEXT PRIMARY KEY,
                updated_ms INTEGER NOT NULL,
                feature_json TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_samples_symbol_ts
            ON price_samples(symbol, bucket_ms DESC)
        """)

    def _create_schema_v3(self, cursor: sqlite3.Cursor) -> None:
        """P1-05 discovery/ranking tables: compact snapshot + event log + ranks.

        Full discovery REST responses are NEVER stored: only the compact
        selection snapshot (counts + HOT set + top lists). Promotion/demotion
        history is an append-only bounded log. Rank vectors are REPLACE-per-
        metric rows (a handful of rows, inherently bounded).
        """
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS discovery_snapshots (
                id INTEGER PRIMARY KEY CHECK (id = 0),
                updated_ms INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS universe_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                kind TEXT NOT NULL,
                symbol TEXT NOT NULL,
                detail TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rank_snapshots (
                metric TEXT PRIMARY KEY,
                updated_ms INTEGER NOT NULL,
                ranks_json TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_universe_events_ts
            ON universe_events(timestamp DESC)
        """)

    def _create_schema_v4(self, cursor: sqlite3.Cursor) -> None:
        """P1-06 flow tables: latest compact flow features + bucket history.

        The engine computes flow from EVERY valid aggTrade in memory; only
        compact aggregates land here. ``flow_features`` is one REPLACE row
        per symbol (dashboard/API feed). ``flow_buckets`` keeps completed
        volume/flow buckets per (symbol, size) for baseline restart
        continuity — INSERT OR REPLACE per primary key makes rewrites
        idempotent, so restarts can never double-count. Retention keeps the
        last 600 buckets per (symbol, size) — bounded by construction.
        """
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS flow_features (
                symbol TEXT PRIMARY KEY,
                updated_ms INTEGER NOT NULL,
                feature_json TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS flow_buckets (
                symbol TEXT NOT NULL,
                size_s INTEGER NOT NULL,
                bucket_ms INTEGER NOT NULL,
                notional REAL NOT NULL,
                base_qty REAL NOT NULL,
                buy_notional REAL NOT NULL,
                sell_notional REAL NOT NULL,
                trades INTEGER NOT NULL,
                PRIMARY KEY (symbol, size_s, bucket_ms)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_flow_buckets_symbol_size_ts
            ON flow_buckets(symbol, size_s, bucket_ms DESC)
        """)

    def _create_schema_v5(self, cursor: sqlite3.Cursor) -> None:
        """P1-07 book + OI tables: latest compact features + OI history.

        ``book_features`` is one REPLACE row per symbol (latest snapshot
        only — the book restarts empty by design and must NOT be restored
        as live without fresh depth data). ``oi_samples`` keeps timestamped
        poll samples per symbol (bounded: last 2000 per symbol) so OI
        deltas survive restarts while timestamps stay valid.
        ``oi_features`` is one REPLACE row per symbol (dashboard/API feed).
        """
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS book_features (
                symbol TEXT PRIMARY KEY,
                updated_ms INTEGER NOT NULL,
                feature_json TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS oi_samples (
                symbol TEXT NOT NULL,
                fetch_ms INTEGER NOT NULL,
                exchange_time_ms INTEGER,
                oi REAL NOT NULL,
                PRIMARY KEY (symbol, fetch_ms)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS oi_features (
                symbol TEXT PRIMARY KEY,
                updated_ms INTEGER NOT NULL,
                feature_json TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_oi_samples_symbol_ts
            ON oi_samples(symbol, fetch_ms DESC)
        """)

    def _create_schema_v6(self, cursor: sqlite3.Cursor) -> None:
        """P1-08 structure table: latest compact VWAP/vol/range record.

        ``structure_features`` is one REPLACE row per symbol (dashboard/API
        feed). Inputs are recomputed each summary from peer-engine state
        (flow aggregates + persisted 10s buckets), so no raw history is
        stored here and restart continuity is inherited, never fabricated.
        """
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS structure_features (
                symbol TEXT PRIMARY KEY,
                updated_ms INTEGER NOT NULL,
                feature_json TEXT NOT NULL
            )
        """)

    def _create_schema_v7(self, cursor: sqlite3.Cursor) -> None:
        """P1-12A state tables: latest classifier output + transition log.

        ``state_features`` is one REPLACE row per symbol (dashboard/API
        feed — observed states with evidence, never signals). Restarts
        recompute from fresh features; memory (dwell/confirmation) restarts
        cold by design and says so in transition reasons.
        ``state_transitions`` is an append-only bounded log (500 rows) of
        actual state changes for audit.
        """
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS state_features (
                symbol TEXT PRIMARY KEY,
                updated_ms INTEGER NOT NULL,
                feature_json TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS state_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                symbol TEXT NOT NULL,
                from_state TEXT,
                to_state TEXT NOT NULL,
                from_direction TEXT,
                to_direction TEXT NOT NULL,
                reason TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_state_transitions_symbol_ts
            ON state_transitions(symbol, timestamp DESC)
        """)

    def _create_schema_v8(self, cursor: sqlite3.Cursor) -> None:
        """P1-13A opportunity tables: latest setup candidates + event log.

        ``opportunity_candidates`` is one REPLACE row per candidate_key
        (research setups with evidence — never orders, entries, or
        positions). Restarts re-evaluate from fresh features; lifecycle
        memory restarts cold by design.
        ``opportunity_events`` is an append-only bounded log (500 rows) of
        lifecycle transitions for audit.
        """
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS opportunity_candidates (
                candidate_key TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                updated_ms INTEGER NOT NULL,
                candidate_json TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS opportunity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                candidate_key TEXT NOT NULL,
                symbol TEXT NOT NULL,
                family TEXT NOT NULL,
                transition TEXT NOT NULL,
                reason TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_opportunity_events_symbol_ts
            ON opportunity_events(symbol, timestamp DESC)
        """)

    def _create_schema_v9(self, cursor: sqlite3.Cursor) -> None:
        """P1-14A prospective setup evaluation tables.

        ``prospective_setups`` stores registered opportunity setups
        at first DETECTED (one REPLACE row per candidate_key).
        ``prospective_outcomes`` is an append-only bounded log (500
        rows per setup) of forward outcome observations at versioned
        horizons (1m/5m/15m/1h/4h).
        """
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prospective_setups (
                candidate_key TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                family TEXT,
                direction TEXT,
                market_state TEXT,
                rules_version TEXT,
                capability_tier TEXT,
                detected_at_ms INTEGER NOT NULL,
                score REAL,
                setup_json TEXT NOT NULL,
                lifecycle TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prospective_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_key TEXT NOT NULL,
                symbol TEXT NOT NULL,
                horizon TEXT NOT NULL,
                observed_at_ms INTEGER NOT NULL,
                mark_return_pct REAL,
                detected_price REAL,
                current_price REAL,
                outcome_state TEXT NOT NULL,
                reason TEXT,
                UNIQUE(candidate_key, horizon, observed_at_ms)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pros_outcomes_key_horizon
            ON prospective_outcomes(candidate_key, horizon, observed_at_ms DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pros_outcomes_symbol_horizon
            ON prospective_outcomes(symbol, horizon, observed_at_ms DESC)
        """)

    def _create_schema_v1(self, cursor: sqlite3.Cursor) -> None:
        """Create initial database schema."""
        
        # Telemetry snapshots (for P1-03 dashboard)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,  -- Unix timestamp (seconds)
                runtime_seconds REAL NOT NULL,
                bot_mode TEXT NOT NULL,
                api_keys_used INTEGER NOT NULL,
                real_orders_sent INTEGER NOT NULL,
                real_capital_at_risk REAL NOT NULL,
                max_drawdown_kill_switch_active INTEGER NOT NULL,
                authenticated_clients_present INTEGER NOT NULL,
                order_execution_path_present INTEGER NOT NULL,
                
                -- Clock sync data (JSON)
                clock_sync_json TEXT,
                
                -- Latency distributions (JSON)
                latency_json TEXT,
                legacy_global_clamped_lag_ms REAL,
                
                -- Processing distributions (JSON)
                processing_json TEXT,
                
                -- Detectors telemetry (JSON)
                detectors_json TEXT,
                
                -- Data quality (JSON)
                data_quality_json TEXT,
                
                -- Events by type (JSON)
                events_by_type_json TEXT,
                
                -- Spread in basis points (JSON)
                spread_bps_json TEXT,

                -- Book imbalance (JSON)
                book_imbalance_json TEXT
            )
        """)
        
        # Market observations (raw/normalized for P1-04+ features)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,  -- Unix timestamp (seconds)
                symbol TEXT NOT NULL,
                stream_type TEXT NOT NULL,  -- bookTicker, depth, aggTrade, etc.
                
                -- Raw payload (JSON)
                payload_json TEXT NOT NULL,
                
                -- Normalized/parsed data (JSON)
                normalized_json TEXT,
                
                -- Event time (E) if available
                event_time_ms INTEGER,
                
                -- Transaction time (T) if available
                transaction_time_ms INTEGER,
                
                -- Whether this observation was valid (not skew-rejected)
                is_valid INTEGER NOT NULL DEFAULT 1
            )
        """)
        
        # Rejection telemetry (skew-invalid messages counted but NOT valid inputs)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rejected_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,  -- Unix timestamp (seconds)
                symbol TEXT NOT NULL,
                stream_type TEXT NOT NULL,
                
                -- Reason for rejection
                rejection_reason TEXT NOT NULL,  -- e.g., "timestamp_skew", "parse_error"
                
                -- Raw payload that was rejected (JSON)
                payload_json TEXT NOT NULL,
                
                -- Event time if available in payload
                event_time_ms INTEGER,
                
                -- Transaction time if available in payload
                transaction_time_ms INTEGER
            )
        """)
        
        # Indexes for query performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_telemetry_snapshots_ts 
            ON telemetry_snapshots(timestamp DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_observations_symbol_ts 
            ON market_observations(symbol, timestamp DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_observations_stream_ts 
            ON market_observations(stream_type, timestamp DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_observations_valid 
            ON market_observations(is_valid)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rejected_reason 
            ON rejected_observations(rejection_reason)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rejected_symbol_ts 
            ON rejected_observations(symbol, timestamp DESC)
        """)
        
        # Indexes for cleanup/retention policies
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_telemetry_snapshots_old 
            ON telemetry_snapshots(timestamp)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_observations_old 
            ON market_observations(timestamp)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rejected_observations_old 
            ON rejected_observations(timestamp)
        """)
    
    def close(self) -> None:
        """Close database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
    
    def _done_callback(self, task: "asyncio.Task[None]") -> None:
        """Task done-callback: close in-flight tracking, then log failures."""
        self._track_done()
        _log_write_error(task)

    def _run_sync_fallback(self, coro) -> None:
        """Execute a write coroutine with no running loop (sync contexts)."""
        self._track_schedule()
        try:
            asyncio.run(coro)
        finally:
            self._track_done()

    def store_telemetry_snapshot(self, summary_dict: Dict[str, Any]) -> None:
        """Store a telemetry snapshot from probe.build_summary().

        Fire-and-forget: schedules the blocking SQLite write on a worker
        thread so the websocket event loop is never blocked. Failures are
        logged via the task done-callback, never raised into the probe.
        """
        try:
            loop = asyncio.get_running_loop()
            self._track_schedule()
            task = loop.create_task(self._store_telemetry_snapshot_async(summary_dict))
            task.add_done_callback(self._done_callback)
        except RuntimeError:
            # No event loop running (e.g., sync tests); execute synchronously
            self._run_sync_fallback(self._store_telemetry_snapshot_async(summary_dict))

    async def _store_telemetry_snapshot_async(self, summary_dict: Dict[str, Any]) -> None:
        """Async wrapper: snapshot insert on the DEDICATED writer, never
        queued behind bulk observation traffic (see module docstring)."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            _snapshot_executor(), self._insert_telemetry_snapshot, summary_dict)

    def _insert_telemetry_snapshot(self, summary_dict: Dict[str, Any]) -> None:
        """Synchronous SQLite insert (runs on a worker thread or test thread)."""
        # Ensure DB is initialized
        if not self._initialized:
            self.init_db()

        # The legacy global lag is a distribution snapshot (dict) in real
        # summaries; the REAL column only accepts a scalar, so store a float
        # when one is given and NULL otherwise. The full dict always remains
        # inside latency_json.
        legacy_lag = summary_dict.get("latency", {}).get("legacyGlobalClampedLagMs")
        legacy_value = float(legacy_lag) if isinstance(legacy_lag, (int, float)) else None
        
        with self._get_cursor() as cursor:
            # Extract key fields for efficient querying
            timestamp = time.time()
            runtime_seconds = summary_dict.get("runtimeSeconds", 0.0)
            safety = summary_dict.get("safety", {})
            clock = summary_dict.get("clock", {})
            latency = summary_dict.get("latency", {})
            processing = summary_dict.get("processing", {})
            detectors = summary_dict.get("detectors", {})
            data_quality = summary_dict.get("dataQuality", {})
            events_by_type = summary_dict.get("eventsByType", {})
            spread_bps = summary_dict.get("spreadBps", {})
            book_imbalance = summary_dict.get("bookImbalance", {})
            
            cursor.execute("""
                INSERT INTO telemetry_snapshots (
                    timestamp, runtime_seconds, bot_mode, api_keys_used,
                    real_orders_sent, real_capital_at_risk,
                    max_drawdown_kill_switch_active, authenticated_clients_present,
                    order_execution_path_present,
                    clock_sync_json, latency_json, legacy_global_clamped_lag_ms,
                    processing_json, detectors_json, data_quality_json,
                    events_by_type_json, spread_bps_json, book_imbalance_json,
                    run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp,
                runtime_seconds,
                safety.get("BOT_MODE", "unknown"),
                int(safety.get("apiKeysUsed", 0)),
                int(safety.get("realOrdersSent", 0)),
                float(safety.get("realCapitalAtRisk", 0.0)),
                int(safety.get("maxDrawdownKillSwitchActive", False)),
                int(safety.get("authenticatedClientsPresent", False)),
                int(safety.get("orderExecutionPathPresent", False)),
                json.dumps(clock),
                json.dumps(latency),
                legacy_value,
                json.dumps(processing),
                json.dumps(detectors),
                json.dumps(data_quality),
                json.dumps(events_by_type),
                _safe_json(spread_bps),
                _safe_json(book_imbalance),
                summary_dict.get("run_id"),
            ))
            
            # Apply retention policy: keep only most recent N snapshots
            self._apply_retention_policy(cursor, "telemetry_snapshots", self.max_snapshots)
    
    def store_market_observation(
        self,
        symbol: str,
        stream_type: str,
        payload: Dict[str, Any],
        normalized: Optional[Dict[str, Any]] = None,
        event_time_ms: Optional[int] = None,
        transaction_time_ms: Optional[int] = None,
        is_valid: bool = True
    ) -> None:
        """Store a market observation (raw or normalized).
        
        Preserves observations for P1-04+ features like returns, velocity, etc.
        Rejected/skew-invalid observations should use store_rejection_record().
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            stream_type: Stream type (e.g., "bookTicker", "depth", "aggTrade")
            payload: Raw WebSocket payload (will be JSON serialized)
            normalized: Normalized/parsed data (optional)
            event_time_ms: Event time from payload (E field) if available
            transaction_time_ms: Transaction time from payload (T field) if available
            is_valid: Whether this observation passed validation (not skew-rejected)
        """
        # Sampling gate first: high-rate streams persist at most one
        # observation per (kind, symbol) per interval. Dropped writes are
        # counted in sample_stats(), never hidden.
        if not self._sample_accept(stream_type, symbol, event_time_ms):
            return
        try:
            loop = asyncio.get_running_loop()
            self._track_schedule()
            task = loop.create_task(self._store_market_observation_async(
                symbol, stream_type, payload, normalized,
                event_time_ms, transaction_time_ms, is_valid
            ))
            task.add_done_callback(self._done_callback)
        except RuntimeError:
            # No event loop running (e.g., sync tests); execute synchronously
            self._run_sync_fallback(self._store_market_observation_async(
                symbol, stream_type, payload, normalized,
                event_time_ms, transaction_time_ms, is_valid
            ))

    async def _store_market_observation_async(
        self,
        symbol: str,
        stream_type: str,
        payload: Dict[str, Any],
        normalized: Optional[Dict[str, Any]],
        event_time_ms: Optional[int],
        transaction_time_ms: Optional[int],
        is_valid: bool
    ) -> None:
        """Async wrapper: run the blocking SQLite write off the event loop."""
        await asyncio.to_thread(
            self._insert_market_observation,
            symbol, stream_type, payload, normalized,
            event_time_ms, transaction_time_ms, is_valid,
        )

    def _insert_market_observation(
        self,
        symbol: str,
        stream_type: str,
        payload: Dict[str, Any],
        normalized: Optional[Dict[str, Any]],
        event_time_ms: Optional[int],
        transaction_time_ms: Optional[int],
        is_valid: bool
    ) -> None:
        """Synchronous SQLite insert (runs on a worker thread or test thread)."""
        if not self._initialized:
            self.init_db()
        
        timestamp = time.time()
        
        with self._get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO market_observations (
                    timestamp, symbol, stream_type,
                    payload_json, normalized_json,
                    event_time_ms, transaction_time_ms, is_valid
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp,
                symbol,
                stream_type,
                _safe_json(payload),
                _safe_json(normalized) if normalized is not None else None,
                event_time_ms,
                transaction_time_ms,
                int(is_valid)
            ))
            
            # Apply retention policy
            self._apply_retention_policy(cursor, "market_observations", self.max_observations)
    
    def store_rejection_record(
        self,
        symbol: str,
        stream_type: str,
        payload: Dict[str, Any],
        rejection_reason: str,
        event_time_ms: Optional[int] = None,
        transaction_time_ms: Optional[int] = None
    ) -> None:
        """Store a rejected observation (skew-invalid, parse error, etc.).
        
        These are counted as rejection telemetry but NOT treated as valid inputs
        for feature engineering.

        Same fire-and-forget contract as the other store methods: safe to call
        with or without a running event loop.

        Args:
            symbol: Trading symbol
            stream_type: Stream type
            payload: Raw WebSocket payload that was rejected
            rejection_reason: Reason for rejection (e.g., "timestamp_skew")
            event_time_ms: Event time from payload if available
            transaction_time_ms: Transaction time from payload if available
        """
        try:
            loop = asyncio.get_running_loop()
            self._track_schedule()
            task = loop.create_task(self._store_rejection_record_async(
                symbol, stream_type, payload, rejection_reason,
                event_time_ms, transaction_time_ms
            ))
            task.add_done_callback(self._done_callback)
        except RuntimeError:
            # No event loop running (e.g., sync tests); execute synchronously
            self._run_sync_fallback(self._store_rejection_record_async(
                symbol, stream_type, payload, rejection_reason,
                event_time_ms, transaction_time_ms
            ))

    async def _store_rejection_record_async(
        self,
        symbol: str,
        stream_type: str,
        payload: Dict[str, Any],
        rejection_reason: str,
        event_time_ms: Optional[int],
        transaction_time_ms: Optional[int]
    ) -> None:
        """Async wrapper: run the blocking SQLite write off the event loop."""
        await asyncio.to_thread(
            self._insert_rejection_record,
            symbol, stream_type, payload, rejection_reason,
            event_time_ms, transaction_time_ms,
        )

    def _insert_rejection_record(
        self,
        symbol: str,
        stream_type: str,
        payload: Dict[str, Any],
        rejection_reason: str,
        event_time_ms: Optional[int],
        transaction_time_ms: Optional[int]
    ) -> None:
        """Synchronous SQLite insert (runs on a worker thread or test thread)."""
        if not self._initialized:
            self.init_db()
        
        timestamp = time.time()
        
        with self._get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO rejected_observations (
                    timestamp, symbol, stream_type,
                    rejection_reason, payload_json,
                    event_time_ms, transaction_time_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp,
                symbol,
                stream_type,
                rejection_reason,
                _safe_json(payload),
                event_time_ms,
                transaction_time_ms
            ))

            # Apply retention policy (keep fewer rejection records)
            self._apply_retention_policy(cursor, "rejected_observations", self.max_rejections)

    def store_price_samples(self, rows: List[Tuple[str, int, float]]) -> None:
        """Persist sampled (symbol, 10s-bucket, price) rows (restart continuity).

        Idempotent per primary key; keeps the last ~25.5h per symbol so the
        24h return horizon plus tolerance always fits. Synchronous: the probe
        calls this from the summary path, which already runs infrequently.
        """
        if not rows:
            return
        if not self._initialized:
            self.init_db()
        cutoff_ms = int(time.time() * 1000) - (25 * 3600 + 1800) * 1000
        with self._get_cursor() as cursor:
            cursor.executemany(
                "INSERT OR REPLACE INTO price_samples (symbol, bucket_ms, price)"
                " VALUES (?, ?, ?)",
                [(symbol.upper(), int(bucket_ms), float(price))
                 for symbol, bucket_ms, price in rows],
            )
            cursor.execute("DELETE FROM price_samples WHERE bucket_ms < ?",
                           (cutoff_ms,))

    def load_price_samples(self, symbol: Optional[str] = None
                           ) -> List[Tuple[str, int, float]]:
        """Load persisted buckets as (symbol, bucket_ms, price), oldest first."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            if symbol is None:
                cursor.execute(
                    "SELECT symbol, bucket_ms, price FROM price_samples"
                    " ORDER BY symbol, bucket_ms")
            else:
                cursor.execute(
                    "SELECT symbol, bucket_ms, price FROM price_samples"
                    " WHERE symbol = ? ORDER BY bucket_ms",
                    (symbol.upper(),))
            return [(row[0], int(row[1]), float(row[2]))
                    for row in cursor.fetchall()]

    def store_return_features(self, features: List[Dict[str, Any]]) -> None:
        """Replace the latest return feature record per symbol (dashboard feed).

        One row per symbol: inherently bounded, no retention sweep needed.
        Same fire-and-forget contract as the other store methods.
        """
        if not features:
            return
        try:
            loop = asyncio.get_running_loop()
            self._track_schedule()
            task = loop.create_task(
                self._store_return_features_async(features))
            task.add_done_callback(self._done_callback)
        except RuntimeError:
            self._run_sync_fallback(self._store_return_features_async(features))

    async def _store_return_features_async(
            self, features: List[Dict[str, Any]]) -> None:
        """Async wrapper: run the blocking SQLite write off the event loop."""
        await asyncio.to_thread(self._insert_return_features, features)

    def _insert_return_features(self, features: List[Dict[str, Any]]) -> None:
        """Synchronous SQLite upsert (runs on a worker thread or test thread)."""
        if not self._initialized:
            self.init_db()
        now_ms = int(time.time() * 1000)
        with self._get_cursor() as cursor:
            cursor.executemany(
                "INSERT OR REPLACE INTO return_features (symbol, updated_ms, feature_json)"
                " VALUES (?, ?, ?)",
                [(str(f.get("symbol", "UNKNOWN")).upper(), now_ms,
                  _safe_json(f)) for f in features],
            )

    def latest_return_features(self) -> List[Dict[str, Any]]:
        """Latest return feature per symbol, ordered by symbol (dashboard/API)."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT feature_json FROM return_features ORDER BY symbol")
            out = []
            for (blob,) in cursor.fetchall():
                try:
                    parsed = json.loads(blob)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    out.append(parsed)
            return out

    def store_discovery_snapshot(self, payload: Dict[str, Any]) -> None:
        """Replace the singleton compact discovery snapshot (P1-05).

        Only counts + HOT set + top-mover lists are stored — never full
        REST responses. Synchronous; scans run every few minutes.
        """
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO discovery_snapshots (id, updated_ms, payload_json)"
                " VALUES (0, ?, ?)",
                (int(time.time() * 1000), _safe_json(payload)),
            )

    def latest_discovery(self) -> Optional[Dict[str, Any]]:
        """Latest compact discovery snapshot, or None before the first scan."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT payload_json FROM discovery_snapshots WHERE id = 0")
            row = cursor.fetchone()
            if row is None:
                return None
            try:
                parsed = json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                return None
            return parsed if isinstance(parsed, dict) else None

    def log_universe_event(self, kind: str, symbol: str,
                           detail: str = "",
                           run_id: Optional[str] = None) -> None:
        """Append a promotion/demotion/scan event (bounded log, 500 rows)."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "INSERT INTO universe_events (timestamp, kind, symbol, detail,"
                " run_id) VALUES (?, ?, ?, ?, ?)",
                (time.time(), str(kind), str(symbol).upper(),
                 str(detail or ""), run_id),
            )
            self._apply_retention_policy(cursor, "universe_events", 500)

    def universe_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Recent universe events, newest first."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT timestamp, kind, symbol, detail, run_id"
                " FROM universe_events ORDER BY id DESC LIMIT ?",
                (max(int(limit), 1),),
            )
            return [{"timestamp": row[0], "kind": row[1],
                     "symbol": row[2], "detail": row[3] or "",
                     "run_id": row[4]}
                    for row in cursor.fetchall()]

    def store_rank_snapshot(self, metric: str,
                            ranks: Dict[str, Dict[str, Any]]) -> None:
        """Replace the rank vector for one metric (a handful of rows total)."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO rank_snapshots (metric, updated_ms, ranks_json)"
                " VALUES (?, ?, ?)",
                (str(metric), int(time.time() * 1000), _safe_json(ranks)),
            )

    def latest_ranks(self) -> Dict[str, Dict[str, Any]]:
        """Latest rank vector per metric, or {} before the first evaluation."""
        if not self._initialized:
            self.init_db()
        out: Dict[str, Dict[str, Any]] = {}
        with self._get_cursor() as cursor:
            cursor.execute("SELECT metric, ranks_json FROM rank_snapshots")
            for metric, blob in cursor.fetchall():
                try:
                    parsed = json.loads(blob)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    out[str(metric)] = parsed
        return out

    def store_flow_features(self, features: List[Dict[str, Any]]) -> None:
        """Replace the latest flow feature record per symbol (dashboard feed).

        One row per symbol: inherently bounded, no retention sweep needed.
        Synchronous; the probe calls this from the infrequent summary path.
        """
        if not features:
            return
        if not self._initialized:
            self.init_db()
        now_ms = int(time.time() * 1000)
        with self._get_cursor() as cursor:
            cursor.executemany(
                "INSERT OR REPLACE INTO flow_features (symbol, updated_ms, feature_json)"
                " VALUES (?, ?, ?)",
                [(str(f.get("symbol", "UNKNOWN")).upper(), now_ms,
                  _safe_json(f)) for f in features],
            )

    def latest_flow_features(self) -> List[Dict[str, Any]]:
        """Latest flow feature per symbol, ordered by symbol (dashboard/API)."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT feature_json FROM flow_features ORDER BY symbol")
            out = []
            for (blob,) in cursor.fetchall():
                try:
                    parsed = json.loads(blob)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    out.append(parsed)
            return out

    def store_flow_buckets(self, rows: List[Dict[str, Any]]) -> None:
        """Persist completed flow buckets (baseline restart continuity).

        Idempotent per (symbol, size_s, bucket_ms); retention keeps the last
        600 buckets per (symbol, size) so storage stays bounded. Synchronous;
        the probe calls this from the infrequent summary path.
        """
        if not rows:
            return
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.executemany(
                "INSERT OR REPLACE INTO flow_buckets"
                " (symbol, size_s, bucket_ms, notional, base_qty,"
                " buy_notional, sell_notional, trades)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(str(r.get("symbol", "UNKNOWN")).upper(),
                  int(r.get("size_s", 0)), int(r.get("bucket_ms", 0)),
                  float(r.get("notional", 0.0)), float(r.get("base", 0.0)),
                  float(r.get("buy_notional", 0.0)),
                  float(r.get("sell_notional", 0.0)),
                  int(r.get("trades", 0)))
                 for r in rows],
            )
            cursor.execute("""
                DELETE FROM flow_buckets
                WHERE (symbol, size_s, bucket_ms) NOT IN (
                    SELECT symbol, size_s, bucket_ms FROM (
                        SELECT symbol, size_s, bucket_ms,
                               ROW_NUMBER() OVER (
                                   PARTITION BY symbol, size_s
                                   ORDER BY bucket_ms DESC) AS rn
                        FROM flow_buckets
                    ) WHERE rn <= 600
                )
            """)

    def load_flow_buckets(self, symbol: Optional[str] = None,
                          size_s: Optional[int] = None,
                          limit: int = 600) -> List[Dict[str, Any]]:
        """Load persisted completed buckets, oldest first (engine restore)."""
        if not self._initialized:
            self.init_db()
        clauses = []
        params: List[Any] = []
        if symbol is not None:
            clauses.append("symbol = ?")
            params.append(str(symbol).upper())
        if size_s is not None:
            clauses.append("size_s = ?")
            params.append(int(size_s))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT symbol, size_s, bucket_ms, notional, base_qty,"
                " buy_notional, sell_notional, trades FROM flow_buckets"
                f" {where} ORDER BY symbol, size_s, bucket_ms DESC"
                f" LIMIT {max(int(limit), 1)}",
                params)
            rows = [{
                "symbol": row[0], "size_s": int(row[1]),
                "bucket_ms": int(row[2]), "notional": float(row[3]),
                "base": float(row[4]), "buy_notional": float(row[5]),
                "sell_notional": float(row[6]), "trades": int(row[7]),
            } for row in cursor.fetchall()]
            rows.reverse()
        return rows

    def store_book_features(self, features: List[Dict[str, Any]]) -> None:
        """Replace the latest book record per symbol (dashboard feed).

        One row per symbol: inherently bounded. Synchronous; the probe
        calls this from the infrequent summary path. The book is never
        restored as live on restart (see load contract below).
        """
        if not features:
            return
        if not self._initialized:
            self.init_db()
        now_ms = int(time.time() * 1000)
        with self._get_cursor() as cursor:
            cursor.executemany(
                "INSERT OR REPLACE INTO book_features (symbol, updated_ms, feature_json)"
                " VALUES (?, ?, ?)",
                [(str(f.get("symbol", "UNKNOWN")).upper(), now_ms,
                  _safe_json(f)) for f in features],
            )

    def latest_book_features(self) -> List[Dict[str, Any]]:
        """Latest book record per symbol, ordered by symbol (dashboard/API)."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT feature_json FROM book_features ORDER BY symbol")
            out = []
            for (blob,) in cursor.fetchall():
                try:
                    parsed = json.loads(blob)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    out.append(parsed)
            return out

    def store_oi_samples(self, rows: List[Dict[str, Any]]) -> None:
        """Persist timestamped OI poll samples (restart continuity).

        Idempotent per (symbol, fetch_ms); retention keeps the last 2000
        samples per symbol (~33h at 60s cadence — covers all OI horizons).
        Synchronous; the probe calls this from the infrequent summary path.
        """
        if not rows:
            return
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.executemany(
                "INSERT OR REPLACE INTO oi_samples"
                " (symbol, fetch_ms, exchange_time_ms, oi)"
                " VALUES (?, ?, ?, ?)",
                [(str(r.get("symbol", "UNKNOWN")).upper(),
                  int(r.get("fetch_ms", 0)),
                  (int(r["exchange_time_ms"])
                   if r.get("exchange_time_ms") is not None else None),
                  float(r.get("oi", 0.0)))
                 for r in rows],
            )
            cursor.execute("""
                DELETE FROM oi_samples
                WHERE (symbol, fetch_ms) NOT IN (
                    SELECT symbol, fetch_ms FROM (
                        SELECT symbol, fetch_ms,
                               ROW_NUMBER() OVER (
                                   PARTITION BY symbol
                                   ORDER BY fetch_ms DESC) AS rn
                        FROM oi_samples
                    ) WHERE rn <= 2000
                )
            """)

    def load_oi_samples(self, symbol: Optional[str] = None,
                        limit: int = 2000) -> List[Dict[str, Any]]:
        """Load persisted OI samples, oldest first (tracker restore)."""
        if not self._initialized:
            self.init_db()
        params: List[Any] = []
        where = ""
        if symbol is not None:
            where = "WHERE symbol = ?"
            params.append(str(symbol).upper())
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT symbol, fetch_ms, exchange_time_ms, oi FROM oi_samples"
                f" {where} ORDER BY symbol, fetch_ms DESC"
                f" LIMIT {max(int(limit), 1)}",
                params)
            rows = [{
                "symbol": row[0], "fetch_ms": int(row[1]),
                "exchange_time_ms": (int(row[2]) if row[2] is not None
                                     else None),
                "oi": float(row[3]),
            } for row in cursor.fetchall()]
        rows.reverse()
        return rows

    def store_oi_features(self, features: List[Dict[str, Any]]) -> None:
        """Replace the latest OI record per symbol (dashboard feed).

        One row per symbol: inherently bounded. Synchronous; the probe
        calls this from the infrequent summary path.
        """
        if not features:
            return
        if not self._initialized:
            self.init_db()
        now_ms = int(time.time() * 1000)
        with self._get_cursor() as cursor:
            cursor.executemany(
                "INSERT OR REPLACE INTO oi_features (symbol, updated_ms, feature_json)"
                " VALUES (?, ?, ?)",
                [(str(f.get("symbol", "UNKNOWN")).upper(), now_ms,
                  _safe_json(f)) for f in features],
            )

    def latest_oi_features(self) -> List[Dict[str, Any]]:
        """Latest OI record per symbol, ordered by symbol (dashboard/API)."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT feature_json FROM oi_features ORDER BY symbol")
            out = []
            for (blob,) in cursor.fetchall():
                try:
                    parsed = json.loads(blob)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    out.append(parsed)
            return out

    def store_structure_features(self, features: List[Dict[str, Any]]) -> None:
        """Replace the latest structure record per symbol (dashboard feed).

        One row per symbol: inherently bounded. Synchronous; the probe
        calls this from the infrequent summary path.
        """
        if not features:
            return
        if not self._initialized:
            self.init_db()
        now_ms = int(time.time() * 1000)
        with self._get_cursor() as cursor:
            cursor.executemany(
                "INSERT OR REPLACE INTO structure_features (symbol, updated_ms, feature_json)"
                " VALUES (?, ?, ?)",
                [(str(f.get("symbol", "UNKNOWN")).upper(), now_ms,
                  _safe_json(f)) for f in features],
            )

    def latest_structure_features(self) -> List[Dict[str, Any]]:
        """Latest structure record per symbol, ordered by symbol."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT feature_json FROM structure_features ORDER BY symbol")
            out = []
            for (blob,) in cursor.fetchall():
                try:
                    parsed = json.loads(blob)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    out.append(parsed)
            return out

    def store_state_features(self, states: List[Dict[str, Any]]) -> None:
        """Replace the latest classifier record per symbol (dashboard feed).

        One row per symbol: inherently bounded. Synchronous; the probe
        calls this from the infrequent summary path. Records are observed
        states with evidence — never signals, entries, or orders.
        """
        if not states:
            return
        if not self._initialized:
            self.init_db()
        now_ms = int(time.time() * 1000)
        with self._get_cursor() as cursor:
            cursor.executemany(
                "INSERT OR REPLACE INTO state_features (symbol, updated_ms, feature_json)"
                " VALUES (?, ?, ?)",
                [(str(s.get("symbol", "UNKNOWN")).upper(), now_ms,
                  _safe_json(s)) for s in states],
            )

    def latest_state_features(self) -> List[Dict[str, Any]]:
        """Latest classifier record per symbol, ordered by symbol."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT feature_json FROM state_features ORDER BY symbol")
            out = []
            for (blob,) in cursor.fetchall():
                try:
                    parsed = json.loads(blob)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    out.append(parsed)
            return out

    def log_state_transition(self, symbol: str, from_state: Optional[str],
                             to_state: str, from_direction: Optional[str],
                             to_direction: str, reason: str = "") -> None:
        """Append one real state change (bounded log, 500 rows)."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "INSERT INTO state_transitions (timestamp, symbol, from_state,"
                " to_state, from_direction, to_direction, reason)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (time.time(), str(symbol).upper(),
                 str(from_state) if from_state else None, str(to_state),
                 str(from_direction) if from_direction else None,
                 str(to_direction), str(reason or "")),
            )
            self._apply_retention_policy(cursor, "state_transitions", 500)

    def state_transitions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Recent state changes, newest first."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT timestamp, symbol, from_state, to_state,"
                " from_direction, to_direction, reason FROM state_transitions"
                " ORDER BY id DESC LIMIT ?",
                (max(int(limit), 1),),
            )
            return [{"timestamp": row[0], "symbol": row[1],
                     "from_state": row[2], "to_state": row[3],
                     "from_direction": row[4], "to_direction": row[5],
                     "reason": row[6] or ""}
                    for row in cursor.fetchall()]

    def store_opportunity_candidates(
            self, candidates: List[Dict[str, Any]]) -> None:
        """Replace the latest setup-candidate record per candidate_key.

        One row per candidate_key: inherently bounded. Synchronous; the
        probe calls this from the infrequent summary path. Records are
        research setups with evidence — never orders, entries, or
        positions. Candidates without a key (rejections) are never
        stored; the caller persists lifecycle events for those only when
        it needs an audit trail.
        """
        rows = [c for c in (candidates or [])
                if isinstance(c, dict) and c.get("candidate_key")]
        if not rows:
            return
        if not self._initialized:
            self.init_db()
        now_ms = int(time.time() * 1000)
        with self._get_cursor() as cursor:
            cursor.executemany(
                "INSERT OR REPLACE INTO opportunity_candidates (candidate_key,"
                " symbol, updated_ms, candidate_json)"
                " VALUES (?, ?, ?, ?)",
                [(str(c.get("candidate_key")),
                  str(c.get("symbol", "UNKNOWN")).upper(), now_ms,
                  _safe_json(c)) for c in rows],
            )

    def latest_opportunity_candidates(self) -> List[Dict[str, Any]]:
        """Latest setup-candidate record per key, ordered by symbol/family."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT candidate_json FROM opportunity_candidates"
                " ORDER BY symbol, candidate_key")
            out = []
            for (blob,) in cursor.fetchall():
                try:
                    parsed = json.loads(blob)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    out.append(parsed)
            return out

    def log_opportunity_event(self, candidate_key: str, symbol: str,
                              family: str, transition: str,
                              reason: str = "") -> None:
        """Append one candidate lifecycle transition (bounded log, 500)."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "INSERT INTO opportunity_events (timestamp, candidate_key,"
                " symbol, family, transition, reason)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), str(candidate_key), str(symbol).upper(),
                 str(family), str(transition), str(reason or "")),
            )
            self._apply_retention_policy_capped(cursor)

    def _apply_retention_policy_capped(
            self, cursor: sqlite3.Cursor) -> None:
        """Bound the opportunity event log to the newest 500 rows."""
        cursor.execute("""
            DELETE FROM opportunity_events
            WHERE id NOT IN (
                SELECT id FROM opportunity_events
                ORDER BY timestamp DESC
                LIMIT 500
            )
        """)

    def opportunity_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Recent candidate lifecycle transitions, newest first."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT timestamp, candidate_key, symbol, family,"
                " transition, reason FROM opportunity_events"
                " ORDER BY id DESC LIMIT ?",
                (max(int(limit), 1),),
            )
            return [{"timestamp": row[0], "candidate_key": row[1],
                     "symbol": row[2], "family": row[3],
                     "transition": row[4], "reason": row[5] or ""}
                    for row in cursor.fetchall()]

    def _apply_retention_policy(
        self, 
        cursor: sqlite3.Cursor, 
        table_name: str, 
        max_rows: int
    ) -> None:
        """Apply retention policy to keep only most recent N rows.
        
        Args:
            cursor: Database cursor
            table_name: Name of table to apply policy to
            max_rows: Maximum number of rows to keep
        """
        cursor.execute(f"""
            DELETE FROM {table_name}
            WHERE id NOT IN (
                SELECT id FROM {table_name}
                ORDER BY timestamp DESC
                LIMIT ?
            )
        """, (max_rows,))
    
    def latest_telemetry(self) -> Optional[Dict[str, Any]]:
        """Get the most recent telemetry snapshot for dashboard consumption.
        
        Returns:
            Dictionary matching the structure expected by P1-03 dashboard,
            or None if no data available.
        """
        if not self._initialized:
            return None
        
        with self._get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM telemetry_snapshots
                ORDER BY timestamp DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if row is None:
                return None
            
            # Convert row to dictionary
            columns = [description[0] for description in cursor.description]
            result = dict(zip(columns, row))
            
            # Parse JSON fields back to dictionaries
            json_fields = [
                "clock_sync_json", "latency_json", "processing_json",
                "detectors_json", "data_quality_json", "events_by_type_json",
                "spread_bps_json", "book_imbalance_json"
            ]
            
            for field in json_fields:
                if result.get(field) is not None:
                    try:
                        result[field] = json.loads(result[field])
                    except (json.JSONDecodeError, TypeError):
                        result[field] = {}
                else:
                    result[field] = {}
            
            # Rename fields to match expected dashboard format
            result["runtimeSeconds"] = result.pop("runtime_seconds", 0.0)
            result["safety"] = {
                "BOT_MODE": result.pop("bot_mode", "unknown"),
                "apiKeysUsed": result.pop("api_keys_used", 0),
                "realOrdersSent": result.pop("real_orders_sent", 0),
                "realCapitalAtRisk": result.pop("real_capital_at_risk", 0.0),
                "maxDrawdownKillSwitchActive": bool(result.pop("max_drawdown_kill_switch_active", 0)),
                "authenticatedClientsPresent": bool(result.pop("authenticated_clients_present", 0)),
                "orderExecutionPathPresent": bool(result.pop("order_execution_path_present", 0)),
            }
            result["clock"] = result.pop("clock_sync_json", {})
            result["latency"] = {
                **result.pop("latency_json", {}),
                "legacyGlobalClampedLagMs": result.pop("legacy_global_clamped_lag_ms"),
                "legacySemantics": "localReceiveMs-minus-E; fallback-o.T; negative-clamped; mixed-streams",
                "timestampAvailability": {
                    "aggTrade": {"E": "eventTime", "T": "tradeTime"},
                    "bookTicker": {"E": "eventTime", "T": "transactionTime"},
                    "depth": {"E": "eventTime", "T": "transactionTime"},
                    "forceOrder": {"E": "eventTime", "T": "orderTradeTime"},
                    "markPrice": {
                        "E": "eventTime",
                        "transactionTime": "NOT_AVAILABLE",
                        "T": "nextFundingTime_not_latency",
                    },
                },
            }
            result["processing"] = result.pop("processing_json", {})
            result["detectors"] = result.pop("detectors_json", {})
            result["dataQuality"] = result.pop("data_quality_json", {})
            result["eventsByType"] = result.pop("events_by_type_json", {})
            result["spreadBps"] = result.pop("spread_bps_json", {})
            result["bookImbalance"] = result.pop("book_imbalance_json", {})
            
            # Remove internal fields (keep snapshotTimestamp for freshness checks)
            result["snapshotTimestamp"] = result.pop("timestamp", None)
            result.pop("id", None)
            result.pop("legacy_global_clamped_lag_ms", None)

            return result
    
    def latest_observations(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get latest market observations for feature engineering.
        
        Args:
            limit: Maximum number of observations to return
            
        Returns:
            List of observation dictionaries, most recent first
        """
        if not self._initialized:
            return []
        
        with self._get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM market_observations
                WHERE is_valid = 1
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            
            observations = []
            for row in rows:
                columns = [description[0] for description in cursor.description]
                obs = dict(zip(columns, row))
                
                # Parse JSON fields
                if obs.get("payload_json"):
                    try:
                        obs["payload"] = json.loads(obs["payload_json"])
                    except (json.JSONDecodeError, TypeError):
                        obs["payload"] = {}
                else:
                    obs["payload"] = {}
                
                if obs.get("normalized_json"):
                    try:
                        obs["normalized"] = json.loads(obs["normalized_json"])
                    except (json.JSONDecodeError, TypeError):
                        obs["normalized"] = {}
                else:
                    obs["normalized"] = None
                
                # Remove internal fields
                obs.pop("id", None)
                obs.pop("payload_json", None)
                obs.pop("normalized_json", None)
                
                observations.append(obs)
            
            return observations
    
    def store_prospective_setup(
        self, candidate_key: str, setup_record: Dict[str, Any],
        detected_at_ms: int, run_id: Optional[str] = None
    ) -> None:
        """Register (REPLACE) a prospective setup at first detection."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO prospective_setups"
                " (candidate_key, symbol, family, direction,"
                " market_state, rules_version, capability_tier,"
                " detected_at_ms, score, setup_json, lifecycle, run_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(candidate_key),
                    str(setup_record.get("symbol", "")).upper(),
                    setup_record.get("setup_family"),
                    setup_record.get("direction"),
                    setup_record.get("market_state"),
                    setup_record.get("rules_version"),
                    setup_record.get("capability_tier"),
                    int(detected_at_ms),
                    setup_record.get("score"),
                    json.dumps(setup_record, default=str),
                    setup_record.get("lifecycle"),
                    run_id,
                ),
            )

    def prospective_setups(self) -> List[Dict[str, Any]]:
        """All registered prospective setups."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT candidate_key, symbol, family, direction,"
                " market_state, rules_version, capability_tier,"
                " detected_at_ms, score, setup_json, lifecycle, run_id"
                " FROM prospective_setups"
                " ORDER BY detected_at_ms DESC"
            )
            rows = cursor.fetchall()
        result = []
        for row in rows:
            try:
                setup_json = json.loads(row[9]) if row[9] else {}
            except (json.JSONDecodeError, TypeError):
                setup_json = {}
            result.append({
                "candidate_key": row[0],
                "symbol": row[1],
                "family": row[2],
                "direction": row[3],
                "market_state": row[4],
                "rules_version": row[5],
                "capability_tier": row[6],
                "detected_at_ms": row[7],
                "score": row[8],
                "setup_json": setup_json,
                "lifecycle": row[10],
                "run_id": row[11],
            })
        return result

    def store_prospective_outcome(
        self, candidate_key: str, symbol: str, horizon: str,
        observed_at_ms: int, outcome: Dict[str, Any],
        run_id: Optional[str] = None
    ) -> None:
        """Append one forward outcome observation (idempotent per key)."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO prospective_outcomes"
                " (candidate_key, symbol, horizon, observed_at_ms,"
                " mark_return_pct, detected_price, current_price,"
                " outcome_state, reason, run_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(candidate_key),
                    str(symbol).upper(),
                    str(horizon),
                    int(observed_at_ms),
                    outcome.get("mark_return_pct"),
                    outcome.get("detected_price"),
                    outcome.get("current_price"),
                    outcome.get("outcome_state"),
                    outcome.get("reason", ""),
                    run_id,
                ),
            )
            cursor.execute(
                "DELETE FROM prospective_outcomes"
                " WHERE candidate_key = ? AND id NOT IN ("
                "   SELECT id FROM prospective_outcomes"
                "   WHERE candidate_key = ?"
                "   ORDER BY observed_at_ms DESC"
                "   LIMIT 500"
                ")",
                (str(candidate_key), str(candidate_key)),
            )

    def prospective_outcomes(
        self, candidate_key: Optional[str] = None,
        horizon: Optional[str] = None, limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Forward outcome observations, newest first."""
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            sql = (
                "SELECT candidate_key, symbol, horizon, observed_at_ms,"
                " mark_return_pct, detected_price, current_price,"
                " outcome_state, reason, run_id FROM prospective_outcomes"
            )
            params: List[Any] = []
            clauses: List[str] = []
            if candidate_key:
                clauses.append("candidate_key = ?")
                params.append(str(candidate_key))
            if horizon:
                clauses.append("horizon = ?")
                params.append(str(horizon))
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY observed_at_ms DESC LIMIT ?"
            params.append(max(int(limit), 1))
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [
            {
                "candidate_key": row[0],
                "symbol": row[1],
                "horizon": row[2],
                "observed_at_ms": row[3],
                "mark_return_pct": row[4],
                "detected_price": row[5],
                "current_price": row[6],
                "outcome_state": row[7],
                "reason": row[8] or "",
                "run_id": row[9],
            }
            for row in rows
        ]

    def prospective_outcome_keys(self) -> List[Tuple[str, str]]:
        """Distinct (candidate_key, horizon) pairs with stored outcomes.

        Used to rebuild in-memory outcome dedup after a restart without
        scanning full outcome payloads.
        """
        if not self._initialized:
            self.init_db()
        with self._get_cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT candidate_key, horizon"
                " FROM prospective_outcomes"
            )
            rows = cursor.fetchall()
        return [(str(r[0]), str(r[1])) for r in rows]

    def research_retention_cleanup(
        self, retention_days: Dict[str, int]
    ) -> Dict[str, int]:
        """Bounded retention cleanup for prospective tables."""
        cleaned: Dict[str, int] = {}
        with self._get_cursor() as cursor:
            for table, days in retention_days.items():
                if table not in ("prospective_setups", "prospective_outcomes"):
                    continue
                table_cutoff = int(
                    (time.time() - 86400 * max(int(days), 1)) * 1000
                )
                cursor.execute(
                    f"DELETE FROM {table} WHERE detected_at_ms < ?"
                    if table == "prospective_setups"
                    else f"DELETE FROM {table} WHERE observed_at_ms < ?",
                    (table_cutoff,),
                )
                cleaned[table] = cursor.rowcount
        return cleaned

    def storage_info(self) -> Dict[str, Any]:
        """Storage facts for the dashboard system page (path, size, row counts)."""
        info: Dict[str, Any] = {
            "db_path": str(self.db_path),
            "exists": self.db_path.exists(),
            "size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
            "rows": {},
        }
        if not self._initialized:
            return info
        try:
            with self._get_cursor() as cursor:
                for table in ("telemetry_snapshots", "market_observations",
                              "rejected_observations", "price_samples",
                              "return_features", "discovery_snapshots",
                              "universe_events", "rank_snapshots",
                              "flow_features", "flow_buckets",
                              "book_features", "oi_samples", "oi_features",
                              "structure_features", "state_features",
                              "state_transitions", "opportunity_candidates",
                              "opportunity_events", "prospective_setups",
                              "prospective_outcomes"):
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    info["rows"][table] = cursor.fetchone()[0]
        except Exception:
            info["rows"] = {}
        return info

    def get_rejection_stats(self) -> Dict[str, Any]:
        """Get rejection statistics for telemetry.
        
        Returns:
            Dictionary with rejection counts and rates
        """
        if not self._initialized:
            return {
                "total_rejected": 0,
                "rejection_rate": 0.0,
                "by_reason": {},
                "by_stream": {}
            }
        
        with self._get_cursor() as cursor:
            # Total rejected
            cursor.execute("SELECT COUNT(*) FROM rejected_observations")
            total_rejected = cursor.fetchone()[0]
            
            # By reason
            cursor.execute("""
                SELECT rejection_reason, COUNT(*) 
                FROM rejected_observations 
                GROUP BY rejection_reason
            """)
            by_reason = dict(cursor.fetchall())
            
            # By stream type
            cursor.execute("""
                SELECT stream_type, COUNT(*) 
                FROM rejected_observations 
                GROUP BY stream_type
            """)
            by_stream = dict(cursor.fetchall())
            
            # Get total observations for rate calculation
            cursor.execute("SELECT COUNT(*) FROM market_observations WHERE is_valid = 1")
            total_valid = cursor.fetchone()[0]
            
            total_messages = total_valid + total_rejected
            rejection_rate = (
                total_rejected / total_messages 
                if total_messages > 0 
                else 0.0
            )
            
            return {
                "total_rejected": total_rejected,
                "rejection_rate": rejection_rate,
                "by_reason": by_reason,
                "by_stream": by_stream
            }


# Global persistence instance (singleton pattern for ease of use)
_persistence_store: Optional[PersistenceStore] = None


def get_persistence_store() -> PersistenceStore:
    """Get the global persistence store instance."""
    global _persistence_store
    if _persistence_store is None:
        _persistence_store = PersistenceStore()
    return _persistence_store


def init_persistence(db_path: Optional[Union[str, Path]] = None) -> PersistenceStore:
    """Initialize persistence with optional custom path.
    
    Args:
        db_path: Optional custom database path
        
    Returns:
        Initialized PersistenceStore instance
    """
    global _persistence_store
    _persistence_store = PersistenceStore(db_path)
    _persistence_store.init_db()
    return _persistence_store


if __name__ == "__main__":
    # Simple test when run directly
    store = PersistenceStore()
    store.init_db()
    
    # Test storing and retrieving
    test_summary = {
        "runtimeSeconds": 100.0,
        "safety": {
            "BOT_MODE": "observe",
            "apiKeysUsed": 0,
            "realOrdersSent": 0,
            "realCapitalAtRisk": 0.0,
            "maxDrawdownKillSwitchActive": False,
            "authenticatedClientsPresent": False,
            "orderExecutionPathPresent": False,
        },
        "clock": {"offset_ms": 0},
        "latency": {"legacyGlobalClampedLagMs": 50.0},
        "processing": {},
        "detectors": {},
        "dataQuality": {
            "timestampRejected": 0,
            "messagesByStream": {"bookTicker": 100}
        },
        "eventsByType": {},
        "spreadBps": {},
        "bookImbalance": {}
    }
    
    store.store_telemetry_snapshot(test_summary)
    latest = store.latest_telemetry()
    print(f"Stored and retrieved telemetry: {latest is not None}")
    
    store.close()
    print("Persistence store test completed successfully")