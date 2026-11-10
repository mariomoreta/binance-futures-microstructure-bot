"""P1-11B historical storage layer (separate research DB).

Separate from the live dashboard DB (``data/microprobe.db``): historical
bootstrap bars live in ``data/historical/historical.db`` so research
backfill can never disturb live/dashboard state. Stdlib sqlite3 only.

Schema v1 tables:
  history_meta            — schema_version + provenance note.
  historical_klines       — regular contract klines (WITH volume fields).
  historical_mark_klines  — mark-price klines (NO volume fields by schema:
                            provenance separation is structural, not a
                            comment).
  historical_coverage     — per (symbol, interval, source): requested_start,
                            actual_start, first/last open, expected/actual
                            counts, coverage ratio. One row per key.
  historical_ingestion_runs — append-only run ledger (params, requests,
                            retries, failures, status) for resume/audit.
  historical_gaps         — missing grid ranges, UNKNOWN/GAP policy input.

Unmanaged rule: missing history is never 0/filled/interpolated here —
gaps are recorded, values are absent.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 3

DEFAULT_HISTORICAL_PATH = Path("data") / "historical" / "historical.db"

# P1-11C prospective research retention defaults (days; configurable).
RESEARCH_RETENTION_DAYS = {"flow_10s": 7, "flow_1m": 90, "book_1m": 90}


def default_path() -> Path:
    """Default historical DB, overridable for hermetic tests."""
    override = os.environ.get("MICROPROBE_HISTORICAL_DB")
    return Path(override) if override else DEFAULT_HISTORICAL_PATH

_SOURCES = ("klines", "mark_klines")


def _connect(db_path: Path,
             max_db_bytes: Optional[int] = None) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL")
    if max_db_bytes is not None and int(max_db_bytes) > 0:
        page_size = int(con.execute("PRAGMA page_size").fetchone()[0])
        max_pages = max(1, int(max_db_bytes) // max(1, page_size))
        con.execute(f"PRAGMA max_page_count={max_pages}")
        con.execute("PRAGMA wal_autocheckpoint=64")
        con.execute(f"PRAGMA journal_size_limit={int(max_db_bytes)}")
    return con


class HistoryStore:
    """Separate historical research store (never the live dashboard DB)."""

    def __init__(self, db_path: Optional[Path] = None,
                 max_db_bytes: Optional[int] = None) -> None:
        resolved = Path(db_path) if db_path is not None else default_path()
        if resolved.resolve() == (Path("data") / "microprobe.db").resolve():
            raise ValueError("historical store must not be the live dashboard DB")
        self.db_path = resolved
        self.max_db_bytes = (int(max_db_bytes)
                             if max_db_bytes is not None else None)
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        return _connect(self.db_path, self.max_db_bytes)

    def init_db(self) -> None:
        con = self._connect()
        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS history_meta"
                " (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS historical_klines"
                " (symbol TEXT NOT NULL, interval TEXT NOT NULL,"
                "  open_time INTEGER NOT NULL, open TEXT NOT NULL,"
                "  high TEXT NOT NULL, low TEXT NOT NULL, close TEXT NOT NULL,"
                "  base_volume TEXT NOT NULL, close_time INTEGER NOT NULL,"
                "  quote_volume TEXT NOT NULL, trade_count INTEGER NOT NULL,"
                "  taker_buy_base TEXT NOT NULL, taker_buy_quote TEXT NOT NULL,"
                "  fetched_at INTEGER NOT NULL,"
                "  PRIMARY KEY (symbol, interval, open_time))"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS historical_mark_klines"
                " (symbol TEXT NOT NULL, interval TEXT NOT NULL,"
                "  open_time INTEGER NOT NULL, open TEXT NOT NULL,"
                "  high TEXT NOT NULL, low TEXT NOT NULL, close TEXT NOT NULL,"
                "  close_time INTEGER NOT NULL, trade_count INTEGER NOT NULL,"
                "  fetched_at INTEGER NOT NULL,"
                "  PRIMARY KEY (symbol, interval, open_time))"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS historical_coverage"
                " (symbol TEXT NOT NULL, interval TEXT NOT NULL,"
                "  source TEXT NOT NULL, requested_start INTEGER NOT NULL,"
                "  actual_start INTEGER, first_open INTEGER, last_open INTEGER,"
                "  expected_bars INTEGER NOT NULL DEFAULT 0,"
                "  actual_bars INTEGER NOT NULL DEFAULT 0,"
                "  coverage_ratio REAL, updated_at INTEGER NOT NULL,"
                "  PRIMARY KEY (symbol, interval, source))"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS historical_ingestion_runs"
                " (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  started_at INTEGER NOT NULL, params_json TEXT NOT NULL,"
                "  requests INTEGER NOT NULL DEFAULT 0,"
                "  retries INTEGER NOT NULL DEFAULT 0,"
                "  failures INTEGER NOT NULL DEFAULT 0,"
                "  status TEXT NOT NULL DEFAULT 'running')"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS historical_gaps"
                " (symbol TEXT NOT NULL, interval TEXT NOT NULL,"
                "  source TEXT NOT NULL, missing_from INTEGER NOT NULL,"
                "  missing_to INTEGER NOT NULL, expected_count INTEGER NOT NULL,"
                "  PRIMARY KEY (symbol, interval, source, missing_from))"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS historical_oi"
                " (symbol TEXT NOT NULL, period TEXT NOT NULL,"
                "  ts INTEGER NOT NULL, sum_oi TEXT NOT NULL,"
                "  sum_oi_value TEXT NOT NULL, fetched_at INTEGER NOT NULL,"
                "  PRIMARY KEY (symbol, period, ts))"
            )
            con.execute(
                "INSERT OR IGNORE INTO history_meta (key, value) VALUES"
                " ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            # P1-11C migration v1 -> v2 (additive; existing rows preserved).
            self._ensure_v2(con)
            # Research linkage migration v2 -> v3 (additive; existing rows
            # keep NULL = UNKNOWN provenance, never backfilled).
            self._ensure_v3(con)
            con.execute(
                "UPDATE history_meta SET value=? WHERE key='schema_version'",
                (str(SCHEMA_VERSION),),
            )
            con.commit()
        finally:
            con.close()
        self._initialized = True

    @staticmethod
    def _ensure_v2(con: sqlite3.Connection) -> None:
        """P1-11C event-study + prospective research tables (idempotent)."""
        con.execute(
            "CREATE TABLE IF NOT EXISTS event_definitions"
            " (definition_name TEXT NOT NULL, definition_version INTEGER NOT NULL,"
            "  parameters_json TEXT NOT NULL, required_features_json TEXT,"
            "  source_requirements_json TEXT, research_status TEXT NOT NULL,"
            "  created_at INTEGER NOT NULL,"
            "  PRIMARY KEY (definition_name, definition_version))"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS event_study_runs"
            " (run_id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  started_at INTEGER NOT NULL, definition_name TEXT NOT NULL,"
            "  definition_version INTEGER NOT NULL, params_json TEXT NOT NULL,"
            "  symbols_json TEXT, requested_start INTEGER, requested_end INTEGER,"
            "  input_source_versions_json TEXT, code_version TEXT,"
            "  event_count INTEGER DEFAULT 0, usable_count INTEGER DEFAULT 0,"
            "  excluded_count INTEGER DEFAULT 0, status TEXT DEFAULT 'running')"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS event_instances"
            " (event_id TEXT PRIMARY KEY, run_id INTEGER,"
            "  definition_name TEXT NOT NULL, definition_version INTEGER NOT NULL,"
            "  symbol TEXT NOT NULL, event_time INTEGER NOT NULL,"
            "  direction TEXT, context TEXT, source_interval TEXT,"
            "  reference_price REAL, reference_source TEXT,"
            "  reference_timestamp INTEGER, features_json TEXT,"
            "  btc_context_json TEXT, formation_start INTEGER,"
            "  formation_end INTEGER, data_quality TEXT, provenance_json TEXT)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_event_instances_def_sym"
            " ON event_instances(definition_name, definition_version, symbol)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS event_feature_snapshots"
            " (event_id TEXT PRIMARY KEY, snapshot_json TEXT NOT NULL)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS event_outcomes"
            " (event_id TEXT NOT NULL, horizon TEXT NOT NULL,"
            "  forward_return REAL, mfe REAL, mae REAL,"
            "  time_to_mfe_ms INTEGER, time_to_mae_ms INTEGER,"
            "  invalidation_time INTEGER, path TEXT, path_complete INTEGER,"
            "  gap_crossed INTEGER, usable_for_statistics INTEGER,"
            "  label TEXT, PRIMARY KEY (event_id, horizon))"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_event_outcomes_horizon"
            " ON event_outcomes(horizon, usable_for_statistics)"
        )
        # Prospective research buckets (compact; retention-bounded).
        con.execute(
            "CREATE TABLE IF NOT EXISTS research_flow_10s"
            " (symbol TEXT NOT NULL, bucket_start INTEGER NOT NULL,"
            "  bucket_end INTEGER NOT NULL, bucket_size_s INTEGER NOT NULL,"
            "  buy_notional REAL NOT NULL, sell_notional REAL NOT NULL,"
            "  delta REAL NOT NULL, delta_ratio REAL,"
            "  buy_base REAL NOT NULL, sell_base REAL NOT NULL,"
            "  base_volume REAL NOT NULL, notional_volume REAL NOT NULL,"
            "  trade_count INTEGER NOT NULL, buy_trades INTEGER NOT NULL,"
            "  sell_trades INTEGER NOT NULL, price_open REAL, price_high REAL,"
            "  price_low REAL, price_close REAL, first_event_ms INTEGER,"
            "  last_event_ms INTEGER, data_quality TEXT,"
            "  PRIMARY KEY (symbol, bucket_start))"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS research_flow_1m"
            " (symbol TEXT NOT NULL, bucket_start INTEGER NOT NULL,"
            "  bucket_end INTEGER NOT NULL, bucket_size_s INTEGER NOT NULL,"
            "  buy_notional REAL NOT NULL, sell_notional REAL NOT NULL,"
            "  delta REAL NOT NULL, delta_ratio REAL,"
            "  buy_base REAL NOT NULL, sell_base REAL NOT NULL,"
            "  base_volume REAL NOT NULL, notional_volume REAL NOT NULL,"
            "  trade_count INTEGER NOT NULL, buy_trades INTEGER NOT NULL,"
            "  sell_trades INTEGER NOT NULL, price_open REAL, price_high REAL,"
            "  price_low REAL, price_close REAL, first_event_ms INTEGER,"
            "  last_event_ms INTEGER, data_quality TEXT,"
            "  PRIMARY KEY (symbol, bucket_start))"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS research_book_1m"
            " (symbol TEXT NOT NULL, bucket_start INTEGER NOT NULL,"
            "  bucket_end INTEGER NOT NULL, sample_count INTEGER NOT NULL,"
            "  spread_min REAL, spread_mean REAL, spread_max REAL,"
            "  imb_min REAL, imb_mean REAL, imb_max REAL,"
            "  micro_min REAL, micro_mean REAL, micro_max REAL,"
            "  bid5_mean REAL, ask5_mean REAL, bid20_mean REAL, ask20_mean REAL,"
            "  depth_gaps INTEGER DEFAULT 0, degraded INTEGER DEFAULT 0,"
            "  crossed INTEGER DEFAULT 0, first_event_ms INTEGER,"
            "  last_event_ms INTEGER,"
            "  PRIMARY KEY (symbol, bucket_start))"
        )

    def _ensure(self) -> None:
        if not self._initialized:
            self.init_db()

    @staticmethod
    def _ensure_v3(con: sqlite3.Connection) -> None:
        """Research linkage columns (additive, idempotent).

        run_id: producing execution (NULL = UNKNOWN, never backfilled).
        rules_version: feature/hypothesis versions active at recording.
        as_of_ms: persist-availability wall time at flush — distinct from
          event time (first/last_event_ms) and bucket close; a historical
          query never proves when data was available.
        price_source: venue stream feeding the bucket ("aggTrade" flow,
          "depth20" book). Receive timestamps do not exist in the
          recorder and are NOT fabricated (no such column).
        dataset_id: optional study binding; NULL = UNKNOWN until a study
          run binds the rows (study runs carry input_source_versions).
        """
        for table in ("research_flow_10s", "research_flow_1m",
                      "research_book_1m"):
            row = con.execute("SELECT name FROM sqlite_master WHERE type='table'"
                              " AND name=?", (table,)).fetchone()
            if row is None:
                raise ValueError(
                    "research linkage (v3): missing table %s — refusing"
                    " partial linkage instead of silently skipping it" % table)
            existing = {row[1] for row in con.execute(
                "PRAGMA table_info(%s)" % table).fetchall()}
            for col in ("run_id", "rules_version", "as_of_ms",
                        "price_source", "dataset_id"):
                if col not in existing:
                    typ = "INTEGER" if col == "as_of_ms" else "TEXT"
                    con.execute("ALTER TABLE %s ADD COLUMN %s %s"
                                % (table, col, typ))

    def schema_version(self) -> int:
        self._ensure()
        con = sqlite3.connect(str(self.db_path))
        try:
            row = con.execute(
                "SELECT value FROM history_meta WHERE key='schema_version'"
            ).fetchone()
        finally:
            con.close()
        return int(row[0]) if row else -1

    def upsert_klines(self, symbol: str, interval: str,
                      rows: List[Dict[str, Any]]) -> int:
        """Idempotent upsert of regular-klines rows. Returns rows written."""
        self._ensure()
        now = int(time.time() * 1000)
        payload = [(
            symbol.upper(), interval,
            int(r["open_time"]), str(r["open"]), str(r["high"]),
            str(r["low"]), str(r["close"]), str(r["base_volume"]),
            int(r["close_time"]), str(r["quote_volume"]),
            int(r["trade_count"]), str(r["taker_buy_base"]),
            str(r["taker_buy_quote"]), now,
        ) for r in rows]
        if not payload:
            return 0
        con = self._connect()
        try:
            con.executemany(
                "INSERT OR REPLACE INTO historical_klines"
                " (symbol, interval, open_time, open, high, low, close,"
                "  base_volume, close_time, quote_volume, trade_count,"
                "  taker_buy_base, taker_buy_quote, fetched_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", payload)
            con.commit()
        finally:
            con.close()
        return len(payload)

    def upsert_mark_klines(self, symbol: str, interval: str,
                           rows: List[Dict[str, Any]]) -> int:
        """Idempotent upsert of mark-price klines (no volume fields exist)."""
        self._ensure()
        now = int(time.time() * 1000)
        payload = [(
            symbol.upper(), interval,
            int(r["open_time"]), str(r["open"]), str(r["high"]),
            str(r["low"]), str(r["close"]), int(r["close_time"]),
            int(r.get("trade_count", 0)), now,
        ) for r in rows]
        if not payload:
            return 0
        con = self._connect()
        try:
            con.executemany(
                "INSERT OR REPLACE INTO historical_mark_klines"
                " (symbol, interval, open_time, open, high, low, close,"
                "  close_time, trade_count, fetched_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)", payload)
            con.commit()
        finally:
            con.close()
        return len(payload)

    def load_bars(self, symbol: str, interval: str, source: str,
                  limit: Optional[int] = None) -> List[Dict[str, Any]]:
        self._ensure()
        table = ("historical_klines" if source == "klines"
                 else "historical_mark_klines")
        sql = (f"SELECT * FROM {table} WHERE symbol=? AND interval=?"
               " ORDER BY open_time ASC")
        if limit is not None:
            sql += f" LIMIT {max(int(limit), 1)}"
        con = sqlite3.connect(str(self.db_path))
        try:
            cols = [c[1] for c in con.execute(f"PRAGMA table_info({table})")]
            out = [dict(zip(cols, row)) for row in con.execute(
                sql, (symbol.upper(), interval))]
        finally:
            con.close()
        return out

    def record_coverage(self, symbol: str, interval: str, source: str,
                        requested_start: int, actual_start: Optional[int],
                        first_open: Optional[int], last_open: Optional[int],
                        expected_bars: int, actual_bars: int) -> None:
        self._ensure()
        ratio = (actual_bars / expected_bars) if expected_bars > 0 else None
        con = self._connect()
        try:
            con.execute(
                "INSERT OR REPLACE INTO historical_coverage"
                " (symbol, interval, source, requested_start, actual_start,"
                "  first_open, last_open, expected_bars, actual_bars,"
                "  coverage_ratio, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (symbol.upper(), interval, source, int(requested_start),
                 actual_start, first_open, last_open, int(expected_bars),
                 int(actual_bars), ratio, int(time.time() * 1000)))
            con.commit()
        finally:
            con.close()

    def get_coverage(self, symbol: str, interval: str,
                     source: str) -> Optional[Dict[str, Any]]:
        self._ensure()
        con = sqlite3.connect(str(self.db_path))
        try:
            cols = [c[1] for c in
                    con.execute("PRAGMA table_info(historical_coverage)")]
            row = con.execute(
                "SELECT * FROM historical_coverage WHERE symbol=? AND"
                " interval=? AND source=?",
                (symbol.upper(), interval, source)).fetchone()
        finally:
            con.close()
        return dict(zip(cols, row)) if row else None

    def coverage_summary(self) -> List[Dict[str, Any]]:
        self._ensure()
        con = sqlite3.connect(str(self.db_path))
        try:
            cols = [c[1] for c in
                    con.execute("PRAGMA table_info(historical_coverage)")]
            out = [dict(zip(cols, row)) for row in con.execute(
                "SELECT * FROM historical_coverage"
                " ORDER BY symbol, interval, source")]
        finally:
            con.close()
        return out

    def start_run(self, params: Dict[str, Any]) -> int:
        self._ensure()
        con = self._connect()
        try:
            cur = con.execute(
                "INSERT INTO historical_ingestion_runs"
                " (started_at, params_json) VALUES (?, ?)",
                (int(time.time() * 1000), json.dumps(params)))
            run_id = int(cur.lastrowid)
            con.commit()
        finally:
            con.close()
        return run_id

    def finish_run(self, run_id: int, requests: int, retries: int,
                   failures: int, status: str) -> None:
        self._ensure()
        con = self._connect()
        try:
            con.execute(
                "UPDATE historical_ingestion_runs SET requests=?, retries=?,"
                " failures=?, status=? WHERE id=?",
                (int(requests), int(retries), int(failures), str(status),
                 int(run_id)))
            con.commit()
        finally:
            con.close()

    def record_gaps(self, symbol: str, interval: str, source: str,
                    gaps: List[Tuple[int, int, int]]) -> None:
        """Persist missing grid ranges (missing_from, missing_to, count)."""
        self._ensure()
        if not gaps:
            return
        con = self._connect()
        try:
            con.executemany(
                "INSERT OR REPLACE INTO historical_gaps"
                " (symbol, interval, source, missing_from, missing_to,"
                "  expected_count) VALUES (?,?,?,?,?,?)",
                [(symbol.upper(), interval, source, int(a), int(b), int(c))
                 for (a, b, c) in gaps])
            con.commit()
        finally:
            con.close()

    def get_gaps(self, symbol: str, interval: str,
                 source: str) -> List[Dict[str, Any]]:
        self._ensure()
        con = sqlite3.connect(str(self.db_path))
        try:
            rows = con.execute(
                "SELECT missing_from, missing_to, expected_count FROM"
                " historical_gaps WHERE symbol=? AND interval=? AND source=?"
                " ORDER BY missing_from",
                (symbol.upper(), interval, source)).fetchall()
        finally:
            con.close()
        return [{"missing_from": a, "missing_to": b, "expected_count": c}
                for (a, b, c) in rows]

    def upsert_oi(self, symbol: str, period: str,
                  rows: List[Dict[str, Any]]) -> int:
        """Idempotent upsert of openInterestHist rows (as-served only)."""
        self._ensure()
        now = int(time.time() * 1000)
        payload = [(
            symbol.upper(), period, int(r["ts"]), str(r["sum_oi"]),
            str(r["sum_oi_value"]), now,
        ) for r in rows]
        if not payload:
            return 0
        con = self._connect()
        try:
            con.executemany(
                "INSERT OR REPLACE INTO historical_oi"
                " (symbol, period, ts, sum_oi, sum_oi_value, fetched_at)"
                " VALUES (?,?,?,?,?,?)", payload)
            con.commit()
        finally:
            con.close()
        return len(payload)

    def load_oi(self, symbol: str, period: str) -> List[Dict[str, Any]]:
        self._ensure()
        con = sqlite3.connect(str(self.db_path))
        try:
            rows = con.execute(
                "SELECT symbol, period, ts, sum_oi, sum_oi_value, fetched_at"
                " FROM historical_oi WHERE symbol=? AND period=?"
                " ORDER BY ts ASC", (symbol.upper(), period)).fetchall()
        finally:
            con.close()
        return [{"symbol": s, "period": p, "ts": t, "sum_oi": o,
                 "sum_oi_value": v, "fetched_at": f}
                for (s, p, t, o, v, f) in rows]

    def close(self) -> None:
        self._initialized = True

    # ---------------- P1-11C event studies ----------------

    def upsert_event_definition(self, definition: Dict[str, Any]) -> None:
        self._ensure()
        con = self._connect()
        try:
            self._ensure_v2(con)
            con.execute(
                "INSERT OR REPLACE INTO event_definitions"
                " (definition_name, definition_version, parameters_json,"
                "  required_features_json, source_requirements_json,"
                "  research_status, created_at) VALUES (?,?,?,?,?,?,?)",
                (str(definition["definition_name"]),
                 int(definition.get("definition_version", 1)),
                 json.dumps(definition.get("parameters", {})),
                 json.dumps(definition.get("required_features", [])),
                 json.dumps(definition.get("source_requirements", {})),
                 str(definition.get("research_status",
                                    "DESCRIPTIVE_RESEARCH_ONLY_HYPOTHESIS")),
                 int(definition.get("created_at", int(time.time() * 1000)))))
            con.commit()
        finally:
            con.close()

    def start_event_run(self, params: Dict[str, Any]) -> int:
        self._ensure()
        con = self._connect()
        try:
            self._ensure_v2(con)
            cur = con.execute(
                "INSERT INTO event_study_runs (started_at, definition_name,"
                " definition_version, params_json, symbols_json,"
                " requested_start, requested_end, input_source_versions_json,"
                " code_version, status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (int(time.time() * 1000),
                 str(params.get("definition", params.get("definition_name", "?"))),
                 int(params.get("version", params.get("definition_version", 1))),
                 json.dumps(params),
                 json.dumps(params.get("symbols",
                                       [params.get("symbol")] if params.get("symbol") else [])),
                 params.get("start"), params.get("end"),
                 json.dumps({"history_schema": 2}),
                 params.get("code_version", "p1-11c"),
                 "running"))
            run_id = int(cur.lastrowid)
            con.commit()
        finally:
            con.close()
        return run_id

    def store_event_instances(self, run_id: int, definition: Dict[str, Any],
                              events: List[Dict[str, Any]]) -> int:
        self._ensure()
        if not events:
            return 0
        con = self._connect()
        try:
            self._ensure_v2(con)
            payload = []
            for e in events:
                feat = e.get("features", {})
                payload.append((
                    str(e["event_id"]), int(run_id),
                    str(e.get("definition_name")), int(e.get("definition_version", 1)),
                    str(e.get("symbol")).upper(), int(e.get("event_time")),
                    str(e.get("direction", "")), str(e.get("context", "")),
                    str(e.get("source_interval", "")),
                    float(e["reference_price"]) if e.get("reference_price") is not None else None,
                    str(e.get("reference_source", "")),
                    int(e.get("reference_timestamp")) if e.get("reference_timestamp") is not None else None,
                    json.dumps(feat),
                    json.dumps(feat.get("btc_context", {})),
                    int(e.get("formation_window_start")) if e.get("formation_window_start") is not None else None,
                    int(e.get("formation_window_end")) if e.get("formation_window_end") is not None else None,
                    "FORMATION_GAP" if e.get("formation_gap") else "OK",
                    json.dumps(e.get("provenance", {})),
                ))
            con.executemany(
                "INSERT OR REPLACE INTO event_instances (event_id, run_id,"
                " definition_name, definition_version, symbol, event_time,"
                " direction, context, source_interval, reference_price,"
                " reference_source, reference_timestamp, features_json,"
                " btc_context_json, formation_start, formation_end,"
                " data_quality, provenance_json)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", payload)
            con.executemany(
                "INSERT OR REPLACE INTO event_feature_snapshots"
                " (event_id, snapshot_json) VALUES (?,?)",
                [(str(e["event_id"]), json.dumps(e.get("features", {}))) for e in events])
            con.commit()
        finally:
            con.close()
        return len(payload)

    def store_event_outcomes(self, run_id: int, outcomes: List[Dict[str, Any]],
                             horizon: str) -> int:
        del run_id
        self._ensure()
        if not outcomes:
            return 0
        con = self._connect()
        try:
            self._ensure_v2(con)
            con.executemany(
                "INSERT OR REPLACE INTO event_outcomes (event_id, horizon,"
                " forward_return, mfe, mae, time_to_mfe_ms, time_to_mae_ms,"
                " invalidation_time, path, path_complete, gap_crossed,"
                " usable_for_statistics, label) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(str(o.get("event_id")), str(horizon),
                  o.get("forward_return"), o.get("mfe"), o.get("mae"),
                  o.get("time_to_mfe_ms"), o.get("time_to_mae_ms"),
                  o.get("invalidation_time"), str(o.get("path", "UNKNOWN")),
                  1 if o.get("path_complete") else 0,
                  1 if o.get("gap_crossed") else 0,
                  1 if o.get("usable_for_statistics") else 0,
                  o.get("label"))
                 for o in outcomes])
            con.commit()
        finally:
            con.close()
        return len(outcomes)

    def finish_event_run(self, run_id: int, event_count: int,
                         usable_count: int) -> None:
        self._ensure()
        con = self._connect()
        try:
            self._ensure_v2(con)
            con.execute(
                "UPDATE event_study_runs SET event_count=?, usable_count=?,"
                " excluded_count=?, status='done' WHERE run_id=?",
                (int(event_count), int(usable_count),
                 max(int(event_count) - int(usable_count), 0), int(run_id)))
            con.commit()
        finally:
            con.close()

    def event_summary(self, definition: str,
                      version: int = 1) -> List[Dict[str, Any]]:
        self._ensure()
        con = sqlite3.connect(str(self.db_path))
        try:
            try:
                rows = con.execute(
                    "SELECT o.horizon, COUNT(*) n_total,"
                    " SUM(o.usable_for_statistics) n_usable,"
                    " AVG(o.forward_return) mean_fwd"
                    " FROM event_outcomes o JOIN event_instances e"
                    " ON o.event_id=e.event_id"
                    " WHERE e.definition_name=? AND e.definition_version=?"
                    " GROUP BY o.horizon",
                    (str(definition), int(version))).fetchall()
            except sqlite3.OperationalError:
                return []
        finally:
            con.close()
        return [{"horizon": r[0], "n_total": r[1], "n_usable": r[2],
                 "mean_forward_return": r[3]} for r in rows]

    # ---------------- P1-11C prospective research buckets ----------------

    def store_research_flow(self, table: str,
                            rows: List[Dict[str, Any]]) -> int:
        if table not in ("research_flow_10s", "research_flow_1m"):
            raise ValueError(f"bad research table {table}")
        self._ensure()
        if not rows:
            return 0
        con = self._connect()
        try:
            self._ensure_v2(con)
            con.executemany(
                f"INSERT OR REPLACE INTO {table} (symbol, bucket_start,"
                " bucket_end, bucket_size_s, buy_notional, sell_notional, delta,"
                " delta_ratio, buy_base, sell_base, base_volume, notional_volume,"
                " trade_count, buy_trades, sell_trades, price_open, price_high,"
                " price_low, price_close, first_event_ms, last_event_ms,"
                " data_quality, run_id, rules_version, as_of_ms, price_source,"
                " dataset_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                " ?,?,?,?,?)",
                [(str(r["symbol"]).upper(), int(r["bucket_start"]),
                  int(r["bucket_end"]), int(r.get("bucket_size_s", 10)),
                  float(r.get("buy_notional", 0.0)), float(r.get("sell_notional", 0.0)),
                  float(r.get("delta", 0.0)), r.get("delta_ratio"),
                  float(r.get("buy_base", 0.0)), float(r.get("sell_base", 0.0)),
                  float(r.get("base_volume", 0.0)), float(r.get("notional_volume", 0.0)),
                  int(r.get("trade_count", 0)), int(r.get("buy_trades", 0)),
                  int(r.get("sell_trades", 0)), r.get("price_open"),
                  r.get("price_high"), r.get("price_low"), r.get("price_close"),
                  r.get("first_event_ms"), r.get("last_event_ms"),
                  str(r.get("data_quality", "OK")), r.get("run_id"),
                  r.get("rules_version"), r.get("as_of_ms"),
                  r.get("price_source"), r.get("dataset_id"))
                 for r in rows])
            con.commit()
        finally:
            con.close()
        return len(rows)

    def store_research_book(self, rows: List[Dict[str, Any]]) -> int:
        self._ensure()
        if not rows:
            return 0
        con = self._connect()
        try:
            self._ensure_v2(con)
            con.executemany(
                "INSERT OR REPLACE INTO research_book_1m (symbol, bucket_start,"
                " bucket_end, sample_count, spread_min, spread_mean, spread_max,"
                " imb_min, imb_mean, imb_max, micro_min, micro_mean, micro_max,"
                " bid5_mean, ask5_mean, bid20_mean, ask20_mean, depth_gaps,"
                " degraded, crossed, first_event_ms, last_event_ms,"
                " run_id, rules_version, as_of_ms, price_source, dataset_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                " ?,?,?,?,?)",
                [(str(r["symbol"]).upper(), int(r["bucket_start"]),
                  int(r["bucket_end"]), int(r.get("sample_count", 0)),
                  r.get("spread_min"), r.get("spread_mean"), r.get("spread_max"),
                  r.get("imb_min"), r.get("imb_mean"), r.get("imb_max"),
                  r.get("micro_min"), r.get("micro_mean"), r.get("micro_max"),
                  r.get("bid5_mean"), r.get("ask5_mean"),
                  r.get("bid20_mean"), r.get("ask20_mean"),
                  int(r.get("depth_gaps", 0)), int(r.get("degraded", 0)),
                  int(r.get("crossed", 0)), r.get("first_event_ms"),
                  r.get("last_event_ms"), r.get("run_id"),
                  r.get("rules_version"), r.get("as_of_ms"),
                  r.get("price_source"), r.get("dataset_id")) for r in rows])
            con.commit()
        finally:
            con.close()
        return len(rows)

    def research_counts(self) -> Dict[str, int]:
        self._ensure()
        con = sqlite3.connect(str(self.db_path))
        try:
            out = {}
            for t in ("research_flow_10s", "research_flow_1m", "research_book_1m"):
                try:
                    out[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except sqlite3.OperationalError:
                    out[t] = 0
        finally:
            con.close()
        return out

    def research_retention_cleanup(self,
                                   retention_days: Optional[Dict[str, int]] = None,
                                   now_ms: Optional[int] = None) -> Dict[str, int]:
        from .history_store import RESEARCH_RETENTION_DAYS as _DEF
        ret = retention_days or dict(_DEF)
        now = int(now_ms) if now_ms is not None else int(time.time() * 1000)
        self._ensure()
        con = self._connect()
        out: Dict[str, int] = {}
        try:
            self._ensure_v2(con)
            for table, key in (("research_flow_10s", "flow_10s"),
                               ("research_flow_1m", "flow_1m"),
                               ("research_book_1m", "book_1m")):
                cutoff = now - int(ret.get(key, 90)) * 86_400_000
                try:
                    cur = con.execute(f"DELETE FROM {table} WHERE bucket_start < ?",
                                      (cutoff,))
                    out[table] = cur.rowcount or 0
                except sqlite3.OperationalError:
                    out[table] = 0
            con.commit()
        finally:
            con.close()
        return out
