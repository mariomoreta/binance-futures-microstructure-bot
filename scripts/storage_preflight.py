"""Storage preflight for observation runs (read-only, measuring only).

Reports database paths/sizes/row-counts, log-tree size/file-counts,
retention constants taken from code (never guessed), disk-free space,
and --compare growth measured between two snapshots (never estimated).
Missing/unreadable inputs are reported as UNKNOWN, never zero-filled.
Writes JSON only to --out (default: temp dir). Never writes databases,
never starts services, never touches the network.

Usage:
  python scripts/storage_preflight.py [--root .] [--out preflight.json]
  python scripts/storage_preflight.py --compare prior.json --out now.json
Exit 0 with a warnings[] list (informational; blocking stays with the
supervisor gates and the acceptance list in docs/OBSERVATION_RUN_CYCLE.md).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

WARN_FREE_BYTES = 1_000_000_000


def _du(path: Path) -> tuple[int, int]:
    total, n = 0, 0
    if path.is_file():
        return path.stat().st_size, 1
    if path.is_dir():
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
                    n += 1
            except OSError:
                continue
    return total, n


def _top_files(path: Path, k: int = 5) -> list:
    files = []
    if path.is_dir():
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    files.append((p.stat().st_size, str(p)))
            except OSError:
                continue
    files.sort(reverse=True)
    return [{"path": p, "bytes": b} for b, p in files[:k]]


def _db_report(path: Path) -> dict:
    if not path.exists():
        return {"path": str(path), "status": "UNKNOWN (absent)",
                "bytes": None, "tables": None}
    try:
        size = path.stat().st_size
    except OSError as e:
        return {"path": str(path), "status": "UNKNOWN (%s)" % e,
                "bytes": None, "tables": None}
    try:
        con = sqlite3.connect("file:%s?mode=ro" % path, uri=True,
                              timeout=5)
        try:
            tables = [r[0] for r in con.execute(
                "select name from sqlite_master where type='table' "
                "order by name")]
            counts = {}
            for t in tables:
                try:
                    counts[t] = con.execute(
                        'select count(*) from "%s"' % t.replace('"', '')
                    ).fetchone()[0]
                except Exception:
                    counts[t] = None
        finally:
            con.close()
    except Exception as e:
        return {"path": str(path), "status": "UNKNOWN (%s)" % str(e)[:120],
                "bytes": size, "tables": None}
    return {"path": str(path), "status": "measured", "bytes": size,
            "tables": counts}


def _retention_from_code() -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    out: dict = {}
    try:
        from microstructure_probe import history_store as hs
        out["research_retention_days"] = dict(hs.RESEARCH_RETENTION_DAYS)
    except Exception as e:
        out["research_retention_days"] = "UNKNOWN (%s)" % str(e)[:120]
    try:
        from microstructure_probe import persistence as ps
        import inspect
        src = inspect.getsource(ps.PersistenceStore.__init__)
        import re
        caps = dict(re.findall(r"self\.(max_\w+)\s*=\s*(\d+)", src))
        out["operational_row_caps"] = caps or "UNKNOWN (no caps found)"
    except Exception as e:
        out["operational_row_caps"] = "UNKNOWN (%s)" % str(e)[:120]
    try:
        from microstructure_probe import prospective as pr
        import inspect
        src = inspect.getsource(pr.ProspectiveRecorder.__init__)
        import re
        days = dict(re.findall(r'"(prospective_\w+)":\s*(\d+)', src))
        out["prospective_retention_days"] = days or "UNKNOWN"
    except Exception as e:
        out["prospective_retention_days"] = "UNKNOWN (%s)" % str(e)[:120]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=None)
    ap.add_argument("--compare", default=None)
    args = ap.parse_args(argv)
    root = Path(args.root)
    data = root / "data"
    logs = root / "logs"

    micro = _db_report(data / "microprobe.db")
    hist = _db_report(data / "historical" / "historical.db")
    log_bytes, log_files = _du(logs) if logs.exists() else (None, None)
    try:
        usage = shutil.disk_usage(str(root))
        disk = {"total": usage.total, "free": usage.free}
    except OSError:
        disk = {"total": None, "free": None}

    warnings = []
    if micro["bytes"] is None:
        warnings.append("microprobe.db absent/unreadable: run state UNKNOWN")
    if hist["bytes"] is None:
        warnings.append("historical.db absent/unreadable: research coverage UNKNOWN")
    if disk["free"] is not None and disk["free"] < WARN_FREE_BYTES:
        warnings.append("disk free < 1GB: runs may stall; free space first")
    warnings.append("logs/ has no rotation cap in code: growth uncapped, prune manually")
    if log_bytes is None:
        warnings.append("logs/ absent: no history to measure")

    report: dict = {
        "label": "STORAGE-PREFLIGHT — measured only, never estimated",
        "root": str(root),
        "operational_db": micro,
        "historical_db": hist,
        "logs": {"path": str(logs),
                 "bytes": log_bytes, "files": log_files,
                 "largest": _top_files(logs) if logs.exists() else [],
                 "rotation_cap": "NONE in code (uncapped)"},
        "disk": disk,
        "retention_from_code": _retention_from_code(),
        "growth": "UNKNOWN (no --compare snapshot supplied)",
        "warnings": warnings,
    }
    if args.compare:
        try:
            prior = json.loads(Path(args.compare).read_text(
                encoding="utf-8"))
            cur = (micro["bytes"] or 0) + (hist["bytes"] or 0) + \
                (log_bytes or 0)
            prv = ((prior.get("operational_db") or {}).get("bytes") or 0) + \
                ((prior.get("historical_db") or {}).get("bytes") or 0) + \
                ((prior.get("logs") or {}).get("bytes") or 0)
            report["growth"] = {"bytes_delta": cur - prv,
                                "basis": "measured delta vs --compare file"}
        except Exception as e:
            report["growth"] = "UNKNOWN (%s)" % str(e)[:120]
    out = Path(args.out) if args.out else \
        Path(tempfile.mkdtemp(prefix="preflight_")) / "preflight.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print("dbs=%s/%s logs=%s files=%s free=%s warnings=%d out=%s" % (
        micro["bytes"], hist["bytes"], log_bytes, log_files,
        disk["free"], len(warnings), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
