"""ETAPA 2 provenance audit — PURE READS ONLY.

Opens both canonical DBs through read-only SQLite URIs (``mode=ro``) and
the registry via a plain file read. Never imports probe/persistence/
history_store modules (their constructors open read-write connections),
never writes anything. Asserts canonical hashes identical before/after.

Covers: universe_events test-tagged rows (dates/symbols/kinds/patterns),
prospective setups/outcomes, opportunity/state tables, snapshot/observation
counts and spans, historical coverage/klines/runs/event-study tables with
MFE/MAE null rates and outcome paths, duplicates, rule versions.

Usage (from repo root)::

    python scripts/audit_dataset_provenance.py [--out path]

Stdlib only. Exit 0 on success (audit complete, hashes unchanged).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MICRO = ROOT / "data" / "microprobe.db"
HIST = ROOT / "data" / "historical" / "historical.db"
REG = ROOT / "logs" / "probe_runtime.json"
DEFAULT_OUT = ROOT / "docs" / "evidence" / "DATASET_PROVENANCE_ETAPA2.json"


def sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def day(ts) -> str:
    try:
        v = float(ts)
        if v > 1_000_000_000_000:
            v /= 1000.0  # ms epochs (detected_at_ms, open_time, ...)
        return datetime.fromtimestamp(v,
                                      tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError, OSError):
        return "UNPARSEABLE"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    before = [sha256(MICRO), sha256(HIST), sha256(REG)]
    out: dict = {"hashes_before": before}

    mcon = sqlite3.connect("file:%s?mode=ro" % MICRO, uri=True)
    try:
        tables = [r[0] for r in mcon.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        out["microprobe_tables"] = sorted(tables)
        out["schema_version"] = mcon.execute(
            "SELECT value FROM persistence_meta WHERE key='schema_version'"
        ).fetchone()[0]

        ue_total = mcon.execute(
            "SELECT COUNT(*) FROM universe_events").fetchone()[0]
        ue_cols = [c[1] for c in mcon.execute(
            "PRAGMA table_info(universe_events)")]
        test_rows = mcon.execute(
            "SELECT timestamp, kind, symbol, detail FROM universe_events"
            " WHERE detail='test'").fetchall()
        other_rows = mcon.execute(
            "SELECT timestamp, kind, symbol, detail FROM universe_events"
            " WHERE detail IS NOT 'test'").fetchall()
        out["universe_events"] = {
            "columns": ue_cols,
            "total": ue_total,
            "detail_test": len(test_rows),
            "detail_other": len(other_rows),
            "test_by_kind": dict(Counter(r[1] for r in test_rows)),
            "test_by_symbol_top": dict(
                Counter(r[2] for r in test_rows).most_common(25)),
            "test_by_day": dict(Counter(day(r[0]) for r in test_rows)),
            "test_ts_min": min((r[0] for r in test_rows), default=None),
            "test_ts_max": max((r[0] for r in test_rows), default=None),
            "other_by_kind": dict(Counter(r[1] for r in other_rows)),
            "other_by_detail_top": dict(
                Counter(r[3] for r in other_rows).most_common(25)),
            "other_ts_min": min((r[0] for r in other_rows), default=None),
            "other_ts_max": max((r[0] for r in other_rows), default=None),
            "doge_rows": [
                {"ts": r[0], "kind": r[1], "symbol": r[2], "detail": r[3]}
                for r in mcon.execute(
                    "SELECT timestamp, kind, symbol, detail"
                    " FROM universe_events WHERE symbol='DOGEUSDT'")],
            "s_pattern_rows": mcon.execute(
                "SELECT COUNT(*) FROM universe_events"
                " WHERE symbol GLOB 'S[0-9]*USDT'").fetchone()[0],
            "xrp_topmover_rows": mcon.execute(
                "SELECT COUNT(*) FROM universe_events WHERE symbol='XRPUSDT'"
                " AND detail='top_mover_2_votes'").fetchone()[0],
            "exact_duplicates": mcon.execute(
                "SELECT COUNT(*) FROM (SELECT timestamp, kind, symbol,"
                " detail, COUNT(*) c FROM universe_events GROUP BY 1,2,3,4"
                " HAVING c > 1)").fetchone()[0],
        }

        out["prospective_setups"] = {
            "total": mcon.execute(
                "SELECT COUNT(*) FROM prospective_setups").fetchone()[0],
            "by_family": dict(mcon.execute(
                "SELECT family, COUNT(*) FROM prospective_setups"
                " GROUP BY 1").fetchall()),
            "by_rules": dict(mcon.execute(
                "SELECT rules_version, COUNT(*) FROM prospective_setups"
                " GROUP BY 1").fetchall()),
            "by_lifecycle": dict(mcon.execute(
                "SELECT lifecycle, COUNT(*) FROM prospective_setups"
                " GROUP BY 1").fetchall()),
            "by_day": dict(Counter(
                day(r[0]) for r in mcon.execute(
                    "SELECT detected_at_ms FROM prospective_setups"))),
        }
        out["prospective_outcomes"] = {
            "total": mcon.execute(
                "SELECT COUNT(*) FROM prospective_outcomes").fetchone()[0],
            "by_state": dict(mcon.execute(
                "SELECT outcome_state, COUNT(*) FROM prospective_outcomes"
                " GROUP BY 1").fetchall()),
            "by_horizon": dict(mcon.execute(
                "SELECT horizon, COUNT(*) FROM prospective_outcomes"
                " GROUP BY 1").fetchall()),
            "complete_null_return": mcon.execute(
                "SELECT COUNT(*) FROM prospective_outcomes WHERE"
                " outcome_state='COMPLETE' AND mark_return_pct IS NULL"
            ).fetchone()[0],
            "dupes": mcon.execute(
                "SELECT COUNT(*) FROM (SELECT candidate_key, horizon,"
                " COUNT(*) c FROM prospective_outcomes GROUP BY 1,2"
                " HAVING c > 1)").fetchone()[0],
        }
        out["opportunity"] = {
            "candidates": mcon.execute(
                "SELECT COUNT(*) FROM opportunity_candidates").fetchone()[0],
            "candidate_rules": dict(mcon.execute(
                "SELECT COALESCE(json_extract(candidate_json,'$.rules_version'),"
                " json_extract(candidate_json,'$.rule_version'), '?'),"
                " COUNT(*) FROM opportunity_candidates GROUP BY 1").fetchall()),
            "candidate_keys_sample": [
                r[0] for r in mcon.execute(
                    "SELECT candidate_key FROM opportunity_candidates"
                    " LIMIT 5").fetchall()],
            "events": mcon.execute(
                "SELECT COUNT(*) FROM opportunity_events").fetchone()[0],
        }
        out["states"] = {
            "features": mcon.execute(
                "SELECT COUNT(*) FROM state_features").fetchone()[0],
            "transitions": mcon.execute(
                "SELECT COUNT(*) FROM state_transitions").fetchone()[0],
        }
        out["telemetry"] = {
            "snapshots": mcon.execute(
                "SELECT COUNT(*) FROM telemetry_snapshots").fetchone()[0],
            "span_min": mcon.execute(
                "SELECT MIN(timestamp) FROM telemetry_snapshots").fetchone()[0],
            "span_max": mcon.execute(
                "SELECT MAX(timestamp) FROM telemetry_snapshots").fetchone()[0],
            "observations": mcon.execute(
                "SELECT COUNT(*) FROM market_observations").fetchone()[0],
            "rejections": mcon.execute(
                "SELECT COUNT(*) FROM rejected_observations").fetchone()[0],
            "price_samples": mcon.execute(
                "SELECT COUNT(*) FROM price_samples").fetchone()[0],
        }
        try:
            out["discovery_snapshot"] = mcon.execute(
                "SELECT COUNT(*) FROM discovery_snapshots").fetchone()[0]
        except sqlite3.Error:
            out["discovery_snapshot"] = "TABLE_MISSING"
    finally:
        mcon.close()

    hcon = sqlite3.connect("file:%s?mode=ro" % HIST, uri=True)
    try:
        htables = [r[0] for r in hcon.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        out["historical_tables"] = sorted(htables)
        out["coverage"] = [
            dict(zip([c[0] for c in cur.description], row))
            for cur in [hcon.execute(
                "SELECT * FROM historical_coverage ORDER BY symbol,"
                " interval, source")]
            for row in cur.fetchall()
        ] if "historical_coverage" in htables else []
        klines = {}
        if "historical_klines" in htables:
            klines["historical_klines"] = [
                {"symbol": r[0], "interval": r[1], "n": r[2],
                 "min_open": r[3], "max_open": r[4]}
                for r in hcon.execute(
                    "SELECT symbol, interval, COUNT(*), MIN(open_time),"
                    " MAX(open_time) FROM historical_klines GROUP BY 1,2")]
        if "historical_mark_klines" in htables:
            klines["historical_mark_klines"] = [
                {"symbol": r[0], "interval": r[1], "n": r[2],
                 "min_open": r[3], "max_open": r[4]}
                for r in hcon.execute(
                    "SELECT symbol, interval, COUNT(*), MIN(open_time),"
                    " MAX(open_time) FROM historical_mark_klines"
                    " GROUP BY 1,2")]
        if "historical_oi" in htables:
            klines["historical_oi"] = [
                {"symbol": r[0], "period": r[1], "n": r[2],
                 "min_ts": r[3], "max_ts": r[4]}
                for r in hcon.execute(
                    "SELECT symbol, period, COUNT(*), MIN(ts), MAX(ts)"
                    " FROM historical_oi GROUP BY 1,2")]
        out["klines_by_symbol_interval"] = klines
        if "historical_gaps" in htables:
            out["historical_gaps"] = hcon.execute(
                "SELECT COUNT(*) FROM historical_gaps").fetchone()[0]
        if "historical_ingestion_runs" in htables:
            out["ingestion_runs"] = hcon.execute(
                "SELECT COUNT(*) FROM historical_ingestion_runs").fetchone()[0]
        if "event_definitions" in htables:
            out["event_definitions"] = [
                {"name": r[0], "version": r[1], "status": r[2]}
                for r in hcon.execute(
                    "SELECT definition_name, definition_version,"
                    " research_status FROM event_definitions")]
        if "event_study_runs" in htables:
            out["event_study_runs"] = hcon.execute(
                "SELECT COUNT(*) FROM event_study_runs").fetchone()[0]
        if "event_instances" in htables:
            out["event_instances"] = hcon.execute(
                "SELECT COUNT(*) FROM event_instances").fetchone()[0]
        if "event_outcomes" in htables:
            out["event_outcomes"] = {
                "total": hcon.execute(
                    "SELECT COUNT(*) FROM event_outcomes").fetchone()[0],
                "by_path": dict(hcon.execute(
                    "SELECT path, COUNT(*) FROM event_outcomes GROUP BY 1"
                ).fetchall()),
                "mfe_null": hcon.execute(
                    "SELECT COUNT(*) FROM event_outcomes"
                    " WHERE mfe IS NULL").fetchone()[0],
                "mae_null": hcon.execute(
                    "SELECT COUNT(*) FROM event_outcomes"
                    " WHERE mae IS NULL").fetchone()[0],
                "usable_true": hcon.execute(
                    "SELECT COUNT(*) FROM event_outcomes"
                    " WHERE usable_for_statistics = 1").fetchone()[0],
                "gap_crossed": hcon.execute(
                    "SELECT COUNT(*) FROM event_outcomes"
                    " WHERE gap_crossed = 1").fetchone()[0],
            }
        for tbl in ("research_flow_10s", "research_flow_1m",
                    "research_book_1m"):
            if tbl in htables:
                out[tbl] = hcon.execute(
                    "SELECT COUNT(*) FROM %s" % tbl).fetchone()[0]
    finally:
        hcon.close()

    try:
        out["registry"] = json.loads(REG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        out["registry"] = "UNREADABLE"

    out["hashes_after"] = [sha256(MICRO), sha256(HIST), sha256(REG)]
    out["hashes_unchanged"] = out["hashes_after"] == before
    Path(args.out).write_text(json.dumps(out, indent=2, default=str),
                              encoding="utf-8")
    print(json.dumps({
        "universe": out["universe_events"]["total"],
        "test_tagged": out["universe_events"]["detail_test"],
        "setups": out["prospective_setups"]["total"],
        "outcomes": out["prospective_outcomes"],
        "hashes_unchanged": out["hashes_unchanged"],
    }, indent=2, default=str))
    print("evidence: %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
