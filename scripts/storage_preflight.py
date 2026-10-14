"""Storage preflight for observation runs (read-only, measuring only).

Reports database paths/sizes/row-counts, log-tree size/file-counts,
retention constants taken from code (never guessed), disk-free space,
and --compare growth measured between two snapshots (never estimated).
Missing/unreadable inputs are reported as UNKNOWN, never zero-filled.

Hardening rules (tested in tests/test_storage_preflight_hardening.py):
- --out colliding with databases, sidecars, inputs, the registry, this
  script, or data//research inputs (resolved-link equivalence included)
  is REFUSED with exit 2 and nothing is written.
- SQLite reads NEVER touch canonical files: every database is copied to
  a temp dir (main file + -wal when present; -shm is transient and never
  copied) and only the copy is opened (mode=ro). WAL-mode readers attach
  shared memory next to the file they open, so opening canonical files
  in place is forbidden here by construction.
- DB/WAL/SHM bytes are measured separately; growth compares components
  with root identity + measurement timestamps; UNKNOWN never becomes 0.

Writes JSON only to --out (default: temp dir). Never writes databases,
never starts services, never touches the network.

Usage:
  python scripts/storage_preflight.py [--root .] [--out preflight.json]
  python scripts/storage_preflight.py --compare prior.json --out now.json
Exit 0 with a warnings[] list (informational; blocking stays with the
supervisor gates and the acceptance list in docs/OBSERVATION_RUN_CYCLE.md);
exit 2 when --out is protected or the invocation is unusable.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

WARN_FREE_BYTES = 1_000_000_000
PROTECTED_SUFFIXES = (".db", ".db-wal", ".db-shm", ".db-journal")
CAP_TABLES = {"market_observations": "max_observations",
              "rejected_observations": "max_rejections",
              "telemetry_snapshots": "max_snapshots"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def _sidecar_sizes(path: Path) -> dict:
    """Separate byte counts for the main file, -wal and -shm siblings."""
    out = {"db": None, "wal": None, "shm": None}
    for key, suffix in (("db", ""), ("wal", "-wal"), ("shm", "-shm")):
        sib = path if suffix == "" else Path(str(path) + suffix)
        try:
            out[key] = sib.stat().st_size if sib.exists() else None
        except OSError:
            out[key] = None
    present = [v for v in out.values() if v is not None]
    out["total"] = sum(present) if present else None
    return out


def measured_copy_read(src_db: Path, workdir: Path,
                       tables: list | None = None) -> dict:
    """Row counts read from a TEMP COPY (canonical never opened).

    Copies the main file plus -wal when present (-shm is transient shared
    memory and is never copied) into workdir, opens ONLY the copy with
    mode=ro, and returns {table: count}. The source directory is only
    read (stat/copy); nothing is created beside the source by
    construction. Raises with an explicit error when unreadable.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    if not src_db.exists():
        raise FileNotFoundError("source database absent: %s" % src_db)
    copy = workdir / src_db.name
    shutil.copy2(src_db, copy)
    wal = Path(str(src_db) + "-wal")
    if wal.exists():
        shutil.copy2(wal, Path(str(copy) + "-wal"))
    con = sqlite3.connect("file:%s?mode=ro" % copy, uri=True, timeout=5)
    try:
        names = [r[0] for r in con.execute(
            "select name from sqlite_master where type='table' "
            "order by name")]
        if tables is None:
            tables = names
        counts = {}
        for t in tables:
            try:
                counts[t] = con.execute(
                    'select count(*) from "%s"' % t.replace('"', '')
                ).fetchone()[0]
            except Exception:
                counts[t] = None
        return counts
    finally:
        con.close()


def _refuse_out(out: Path, root: Path, compare: Path | None) -> str | None:
    """Reason to refuse --out, or None when writable. Resolved (links)."""
    try:
        ro = out.resolve()
    except OSError:
        ro = out.absolute()
    try:
        rr = root.resolve()
    except OSError:
        rr = root.absolute()
    me = Path(__file__).resolve()
    if ro == me:
        return "refused: --out is this script itself"
    for protected in (rr / "data", rr / "binance_case_study"):
        try:
            if ro == protected or protected in ro.parents:
                return "refused: --out inside protected tree %s" % protected
        except OSError:
            continue
    if ro.suffix in (".db",) or ro.name.endswith(("-wal", "-shm")) \
            or str(ro).endswith(PROTECTED_SUFFIXES):
        return "refused: --out looks like a database/sidecar"
    if ro == (rr / "logs" / "probe_runtime.json"):
        return "refused: --out is the canonical registry"
    if compare is not None:
        try:
            rc = compare.resolve()
        except OSError:
            rc = compare.absolute()
        if ro == rc:
            return "refused: --out equals the --compare input (would destroy the base)"
    return None


def _db_report(path: Path, warnings: list) -> dict:
    files = _sidecar_sizes(path)
    if files["db"] is None:
        return {"path": str(path), "status": "UNKNOWN (absent)",
                "files": files, "bytes": None, "tables": None}
    work = Path(tempfile.mkdtemp(prefix="preflight_read_"))
    try:
        try:
            counts = measured_copy_read(path, work)
        except Exception as e:
            return {"path": str(path),
                    "status": "UNKNOWN (%s)" % str(e)[:120],
                    "files": files, "bytes": files["total"],
                    "tables": None}
    finally:
        shutil.rmtree(work, ignore_errors=True)
    unreadable = sorted(t for t, c in counts.items() if c is None)
    if unreadable:
        warnings.append("%s: %d unreadable tables (%s)" % (
            path.name, len(unreadable), ",".join(unreadable[:5])))
    if (files["wal"] or 0) > 0 or files["shm"] is not None:
        warnings.append(
            "%s: WAL sidecars present (wal=%sB/shm=%sB): readers attach "
            "shared memory; this tool measured a temp copy, canonical "
            "untouched" % (path.name, files["wal"], files["shm"]))
    return {"path": str(path), "status": "measured", "files": files,
            "bytes": files["total"], "tables": counts}


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


def _cap_warnings(micro: dict, retention: dict, warnings: list) -> None:
    caps = retention.get("operational_row_caps")
    tables = micro.get("tables") or {}
    if not isinstance(caps, dict):
        return
    for table, cap_name in CAP_TABLES.items():
        try:
            cap = int(caps.get(cap_name, ""))
            count = tables.get(table)
        except (TypeError, ValueError):
            continue
        if count is not None and count >= cap:
            warnings.append(
                "%s at retention cap %d/%d: oldest rows pruned, growth "
                "bounded here" % (table, count, cap))


def _component_delta(name: str, old, new) -> dict:
    if old is None or new is None:
        return {"base_bytes": old, "now_bytes": new,
                "delta": "UNKNOWN (missing measure, never zero-filled)"}
    return {"base_bytes": old, "now_bytes": new, "delta": new - old}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=None)
    ap.add_argument("--compare", default=None)
    args = ap.parse_args(argv)
    root = Path(args.root)
    data = root / "data"
    logs = root / "logs"
    compare = Path(args.compare) if args.compare else None

    out = Path(args.out) if args.out else \
        Path(tempfile.mkdtemp(prefix="preflight_")) / "preflight.json"
    refusal = _refuse_out(out, root, compare)
    if refusal is not None:
        print("error: %s" % refusal, file=sys.stderr)
        return 2

    warnings: list = []
    micro = _db_report(data / "microprobe.db", warnings)
    hist = _db_report(data / "historical" / "historical.db", warnings)
    log_bytes, log_files = _du(logs) if logs.exists() else (None, None)
    try:
        usage = shutil.disk_usage(str(root))
        disk = {"total": usage.total, "free": usage.free}
    except OSError:
        disk = {"total": None, "free": None}

    if micro["bytes"] is None:
        warnings.append("microprobe.db absent/unreadable: run state UNKNOWN")
    if hist["bytes"] is None:
        warnings.append("historical.db absent/unreadable: research coverage UNKNOWN")
    if disk["free"] is not None and disk["free"] < WARN_FREE_BYTES:
        warnings.append("disk free < 1GB: runs may stall; free space first")
    warnings.append("logs/ has no rotation cap in code: growth uncapped, prune manually")
    if log_bytes is None:
        warnings.append("logs/ absent: no history to measure")

    retention = _retention_from_code()
    _cap_warnings(micro, retention, warnings)

    try:
        root_resolved = str(root.resolve())
    except OSError:
        root_resolved = str(root.absolute())
    report: dict = {
        "label": "STORAGE-PREFLIGHT — measured only, never estimated",
        "root": str(root),
        "root_resolved": root_resolved,
        "measured_at": _utc_now() + " (measurement time, not market time)",
        "operational_db": micro,
        "historical_db": hist,
        "logs": {"path": str(logs),
                 "bytes": log_bytes, "files": log_files,
                 "largest": _top_files(logs) if logs.exists() else [],
                 "rotation_cap": "NONE in code (uncapped)"},
        "disk": disk,
        "retention_from_code": retention,
        "growth": "UNKNOWN (no --compare snapshot supplied)",
        "warnings": warnings,
    }
    if compare is not None:
        try:
            prior = json.loads(compare.read_text(encoding="utf-8"))
        except Exception as e:
            report["growth"] = "UNKNOWN (illegible-compare-base: %s)" % str(e)[:120]
            warnings.append("compare base illegible: growth UNKNOWN")
        else:
            try:
                base_root = prior.get("root_resolved", prior.get("root"))
            except AttributeError:
                base_root = None
            comps = {}
            for key, sub in (("operational_db", "bytes"),
                             ("historical_db", "bytes"),
                             ("logs", "bytes")):
                old = (prior.get(key) or {}).get(sub) \
                    if isinstance(prior.get(key), dict) else None
                new = (report.get(key) or {}).get(sub) \
                    if isinstance(report.get(key), dict) else None
                comps[key] = _component_delta(key, old, new)
            base_measured = prior.get("measured_at") \
                if isinstance(prior, dict) else None
            report["growth"] = {
                "components": comps,
                "roots_differ": base_root != root_resolved,
                "base_root": base_root,
                "now_root": root_resolved,
                "base_measured_at": base_measured,
                "now_measured_at": report["measured_at"],
                "basis": "measured per-component delta vs --compare file",
            }
            if base_root != root_resolved:
                warnings.append("compare roots differ: growth across "
                                "different trees, interpret with care")
    report["warnings"] = warnings
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print("dbs=%s/%s logs=%s files=%s free=%s warnings=%d out=%s" % (
        micro["bytes"], hist["bytes"], log_bytes, log_files,
        disk["free"], len(warnings), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
