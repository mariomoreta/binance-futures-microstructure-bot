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
            # Enable foreign key constraints
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
            except Exception:
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
            
            if current_version >= 2:
                self._initialized = True
                return

            if current_version == 1:
                # Migrate v1 -> v2: keep existing rows, add P1-04 tables.
                self._ensure_snapshot_columns(cursor)
                self._create_schema_v2(cursor)
                cursor.execute(
                    "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES (?, ?)",
                    ("schema_version", "2")
                )
                self._initialized = True
                return

            # Create tables for schema v1
            self._create_schema_v1(cursor)
            # Create tables for schema v2
            self._create_schema_v2(cursor)

            # Set schema version
            cursor.execute(
                "INSERT OR REPLACE INTO persistence_meta (key, value) VALUES (?, ?)",
                ("schema_version", "2")
            )
            
            self._initialized = True
    
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
                    events_by_type_json, spread_bps_json, book_imbalance_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                _safe_json(book_imbalance)
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
                              "return_features"):
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