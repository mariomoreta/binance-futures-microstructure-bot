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

SCHEMA_VERSION = 1

DEFAULT_HISTORICAL_PATH = Path("data") / "historical" / "historical.db"


def default_path() -> Path:
    """Default historical DB, overridable for hermetic tests."""
    override = os.environ.get("MICROPROBE_HISTORICAL_DB")
    return Path(override) if override else DEFAULT_HISTORICAL_PATH

_SOURCES = ("klines", "mark_klines")


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL")
    return con


class HistoryStore:
    """Separate historical research store (never the live dashboard DB)."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        resolved = Path(db_path) if db_path is not None else default_path()
        if resolved.resolve() == (Path("data") / "microprobe.db").resolve():
            raise ValueError("historical store must not be the live dashboard DB")
        self.db_path = resolved
        self._initialized = False

    def init_db(self) -> None:
        con = _connect(self.db_path)
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
            con.commit()
        finally:
            con.close()
        self._initialized = True

    def _ensure(self) -> None:
        if not self._initialized:
            self.init_db()

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
        con = _connect(self.db_path)
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
        con = _connect(self.db_path)
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
        con = _connect(self.db_path)
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
        con = _connect(self.db_path)
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
        con = _connect(self.db_path)
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
        con = _connect(self.db_path)
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
        con = _connect(self.db_path)
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
