"""Versioned read gates for V2/consumers (read-only, never migrating).

Backend counterpart of the frontend schema gates (historical-2 /
operational-9 at 27b7af5): every consumer declares the schema it was
reviewed against, and absent tables/columns/versions raise an explicit
error naming them (R6) instead of silently degrading. These helpers
never create, migrate, or write databases; they only inspect.

Current backend matrix (pinned by tests/test_corrective_delivery.py):
operational microprobe.db schema v10, historical historical.db schema v3.
Old compat (v9-era reads) is kept ONLY where covered by read-purity
tests; nothing here certifies it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

OPERATIONAL_SCHEMA = "10"
HISTORICAL_SCHEMA = "3"


class ReadGateError(Exception):
    """A versioned read contract is not satisfied. Fail closed."""


def table_names(con) -> List[str]:
    return [r[0] for r in con.execute(
        "select name from sqlite_master where type='table' order by name")]


def require_tables(con, names: List[str], store: str) -> None:
    """Raise ReadGateError naming every absent table (never skip silent)."""
    have = set(table_names(con))
    missing = [n for n in names if n not in have]
    if missing:
        raise ReadGateError(
            "store %s lacks tables: %s" % (store, ",".join(missing)))


def require_columns(con, table: str, columns: List[str],
                    store: str) -> None:
    """Raise ReadGateError naming every absent column."""
    have = {r[1] for r in con.execute(
        'pragma table_info("%s")' % table.replace('"', ''))}
    missing = [c for c in columns if c not in have]
    if missing:
        raise ReadGateError(
            "store %s table %s lacks columns: %s"
            % (store, table, ",".join(missing)))


def meta_value(con, table: str, key: str) -> Optional[str]:
    try:
        row = con.execute(
            'select value from "%s" where key = ?' % table.replace('"', ''),
            (key,)).fetchone()
    except Exception:
        return None
    return row[0] if row else None


def check_operational_version(value: Optional[str]) -> str:
    """Accept exactly v10; anything else (incl. v9, None) fails closed."""
    if value != OPERATIONAL_SCHEMA:
        raise ReadGateError(
            "unsupported operational schema %r (reviewed: %s)"
            % (value, OPERATIONAL_SCHEMA))
    return value


def check_historical_version(value: Optional[str]) -> str:
    """Accept exactly v3; anything else (incl. v2, None) fails closed."""
    if value != HISTORICAL_SCHEMA:
        raise ReadGateError(
            "unsupported historical schema %r (reviewed: %s)"
            % (value, HISTORICAL_SCHEMA))
    return value


def provenance(run_id: Optional[str] = None,
               rules_version: Optional[str] = None,
               as_of_ms: Optional[int] = None,
               source: Optional[str] = None,
               dataset_id: Optional[str] = None) -> Dict[str, Any]:
    """Provenance envelope: absent fields stay UNKNOWN, never invented."""
    return {"run_id": run_id if run_id is not None else "UNKNOWN",
            "rules_version": rules_version if rules_version is not None
            else "UNKNOWN",
            "as_of_ms": as_of_ms if as_of_ms is not None else "UNKNOWN",
            "source": source if source is not None else "UNKNOWN",
            "dataset_id": dataset_id if dataset_id is not None
            else "UNKNOWN"}
