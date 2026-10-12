"""ETAPA 1 isolation barrier: full-suite canonical-write audit.

Runs the canonical unittest suite (same discovery as run_tests.py) with
three verifiable barriers installed:

1. ``probe.get_persistence_store`` / ``persistence.get_persistence_store`` /
   ``persistence.init_persistence`` are replaced by a forbidden factory that
   RECORDS every call (test id + stack) and raises. Hits are recorded even
   when production code swallows the error internally (probe wraps
   persistence writes in try/except logging ``persistence_error``), so a
   green test can still be proven impure.
2. ``sqlite3.connect`` is wrapped: every connection whose resolved path is a
   canonical DB (data/microprobe.db, data/historical/historical.db) is
   recorded with test id + thread + stack, whatever route opened it
   (default factory, HistoryStore default path, direct connects), then
   DELEGATED (recorded, not blocked — see buckets below). Read-only URI
   connects are flagged separately. Temp-store connects are counted.
3. ``control._write_registry`` is wrapped: write attempts resolving to the
   canonical registry (logs/probe_runtime.json) are recorded, then delegated.
4. ``builtins.open`` / ``io.open`` are wrapped: write-mode opens resolving
   under canonical data/ or logs/ trees are recorded with test id + thread
   + stack, then delegated. Read-mode opens are never recorded.

BUCKETS (evidence fields):
- ``blocked``: forbidden-factory calls. The factory RAISES, so the
  underlying canonical write never executes — an attempt with no effect.
  Any nonzero count fails the gate.
- ``canonical_effective``: canonical connects + canonical file writes +
  registry writes that were RECORDED AND DELEGATED (real accesses with
  real effects, however byte-neutral). Must be zero for isolation; any
  entry fails the gate and names the exact route.
- ``residual_ro``: read-only URI connects only (mode=ro, no write
  capability). Reported separately, never mixed into the gate.
- ``preservation``: hashes + data/logs inventories before/after.

Additionally snapshots SHA256 of both DBs + registry and a full inventory
(name/size/mtime) of data/ and logs/ before/after, catching sidecars
(-wal/-shm/-journal), new log files, and PID files.

Exit code is 0 ONLY when: suite green AND zero prohibited hits AND hashes
equal AND inventories equal. Anything else exits 1 with the JSON evidence
pointing at the exact cause.

Read-only / byte-neutral residual accesses (e.g. HistoryStore default-path
reads running idempotent DDL on an existing schema) are recorded in the
``canonical_connects`` list with their stacks and must be dispositioned
explicitly in the audit report -- they are never silently excluded.

Usage (from repo root, no market traffic, no probes started)::

    python scripts/audit_test_isolation.py [--out path] [-q]

Stdlib only. Never writes to canonical resources itself (evidence goes to
--out, default docs/evidence/).
"""

from __future__ import annotations

import argparse
import builtins
import hashlib
import io
import json
import sqlite3
import sys
import threading
import traceback
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
TESTS = ROOT / "tests"
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
CANON_MICROPROBE = (DATA_DIR / "microprobe.db").resolve()
CANON_HISTORICAL = (DATA_DIR / "historical" / "historical.db").resolve()
CANON_REGISTRY = (LOGS_DIR / "probe_runtime.json").resolve()
DEFAULT_OUT = ROOT / "docs" / "evidence" / "TEST_ISOLATION_AUDIT_ETAPA1.json"


def sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def snapshot_hashes() -> dict:
    return {
        "microprobe.db": sha256(CANON_MICROPROBE),
        "historical.db": sha256(CANON_HISTORICAL),
        "probe_runtime.json": sha256(CANON_REGISTRY),
    }


def inventory(directory: Path) -> dict:
    out: dict = {}
    if not directory.exists():
        return out
    for path in sorted(directory.rglob("*")):
        try:
            if path.is_file():
                st = path.stat()
                out[str(path.relative_to(directory))] = {
                    "size": st.st_size,
                    "mtime_ns": st.st_mtime_ns,
                }
        except OSError:
            out[str(path.relative_to(directory))] = {"error": "stat-failed"}
    return out


def guess_test(stack) -> str:
    for frame in reversed(stack):
        filename = frame.filename.replace("\\", "/")
        if "/tests/test_" in filename and frame.name.startswith("test"):
            return "%s.%s:%d" % (
                Path(frame.filename).stem, frame.name, frame.lineno)
    for frame in reversed(stack):
        filename = frame.filename.replace("\\", "/")
        if "/tests/test_" in filename:
            return "%s.%s:%d" % (
                Path(frame.filename).stem, frame.name, frame.lineno)
    return "UNKNOWN"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args(argv)

    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    import microstructure_probe.control as control_mod
    import microstructure_probe.persistence as persistence_mod
    import microstructure_probe.probe as probe_mod

    hits: list[dict] = []
    canonical_connects: list[dict] = []
    registry_attempts: list[dict] = []
    file_write_attempts: list[dict] = []
    counters = {"temp_connects": 0, "memory_connects": 0, "other_connects": 0}

    def record(kind: str, extra: dict) -> None:
        stack = traceback.extract_stack(limit=14)[:-1]
        entry = {
            "kind": kind,
            "test": guess_test(stack),
            "thread": threading.current_thread().name,
            "extra": extra,
            "stack": [
                {"file": f.filename, "line": f.lineno, "func": f.name}
                for f in stack[-8:]
            ],
        }
        hits.append(entry)
        if kind == "registry_write_canonical":
            registry_attempts.append(entry)
        if kind == "file_write_canonical":
            file_write_attempts.append(entry)

    def is_canonical_tree(path_str: str) -> str | None:
        try:
            p = Path(path_str)
            if not p.is_absolute():
                p = ROOT / p
            rp = p.resolve()
            try:
                rp.relative_to(DATA_DIR.resolve())
                return "data"
            except ValueError:
                pass
            try:
                rp.relative_to(LOGS_DIR.resolve())
                return "logs"
            except ValueError:
                return None
        except Exception:
            return None

    def forbidden_factory(name: str):
        def _forbidden(*a, **k):
            record("default_factory_call", {"factory": name})
            raise AssertionError(
                "canonical persistence factory forbidden under audit: %s" % name)
        return _forbidden

    real_connect = sqlite3.connect

    def guarded_connect(database=None, *a, **k):
        db = k.get("database", database)
        try:
            if isinstance(db, str) and db.startswith("file:"):
                if "mode=ro" in db:
                    record("sqlite_connect_readonly_uri", {"database": db})
                else:
                    record("sqlite_connect_uri", {"database": db})
            elif isinstance(db, (str, Path)) and str(db) != ":memory:":
                resolved = Path(str(db)).resolve()
                if resolved == CANON_MICROPROBE:
                    stack = traceback.extract_stack(limit=14)[:-1]
                    canonical_connects.append({
                        "db": "microprobe.db",
                        "test": guess_test(stack),
                        "thread": threading.current_thread().name,
                        "stack": [
                            {"file": f.filename, "line": f.lineno,
                             "func": f.name} for f in stack[-8:]
                        ],
                    })
                elif resolved == CANON_HISTORICAL:
                    stack = traceback.extract_stack(limit=14)[:-1]
                    canonical_connects.append({
                        "db": "historical.db",
                        "test": guess_test(stack),
                        "thread": threading.current_thread().name,
                        "stack": [
                            {"file": f.filename, "line": f.lineno,
                             "func": f.name} for f in stack[-8:]
                        ],
                    })
                else:
                    counters["temp_connects"] += 1
            elif str(db) == ":memory:":
                counters["memory_connects"] += 1
            else:
                counters["other_connects"] += 1
        except Exception:
            pass
        return real_connect(database, *a, **k)

    real_write_registry = control_mod._write_registry

    def guarded_write_registry(record_arg) -> None:
        try:
            if control_mod.registry_path().resolve() == CANON_REGISTRY:
                record("registry_write_canonical", {})
        except Exception:
            pass
        return real_write_registry(record_arg)

    real_builtin_open = builtins.open
    real_io_open = io.open

    def guarded_open(file, mode="r", *a, **k):
        try:
            if isinstance(file, (str, Path)):
                m = str(mode)
                if any(c in m for c in ("w", "a", "x", "+")):
                    tree = is_canonical_tree(str(file))
                    if tree is not None:
                        record("file_write_canonical",
                               {"path": str(file), "mode": m,
                                "tree": tree, "via": "open"})
        except Exception:
            pass
        return real_builtin_open(file, mode, *a, **k)

    def guarded_io_open(file, mode="r", *a, **k):
        try:
            if isinstance(file, (str, Path)):
                m = str(mode)
                if any(c in m for c in ("w", "a", "x", "+")):
                    tree = is_canonical_tree(str(file))
                    if tree is not None:
                        record("file_write_canonical",
                               {"path": str(file), "mode": m,
                                "tree": tree, "via": "io.open"})
        except Exception:
            pass
        return real_io_open(file, mode, *a, **k)

    hashes_before = snapshot_hashes()
    data_before = inventory(DATA_DIR)
    logs_before = inventory(LOGS_DIR)

    orig_probe_factory = probe_mod.get_persistence_store
    orig_persist_factory = persistence_mod.get_persistence_store
    orig_init_persist = persistence_mod.init_persistence
    probe_mod.get_persistence_store = forbidden_factory(
        "microstructure_probe.probe.get_persistence_store")
    persistence_mod.get_persistence_store = forbidden_factory(
        "microstructure_probe.persistence.get_persistence_store")
    persistence_mod.init_persistence = forbidden_factory(
        "microstructure_probe.persistence.init_persistence")
    sqlite3.connect = guarded_connect
    control_mod._write_registry = guarded_write_registry
    builtins.open = guarded_open
    io.open = guarded_io_open
    try:
        verbosity = 1
        suite = unittest.TestLoader().discover(start_dir=str(TESTS))
        result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
        suite_ok = result.wasSuccessful()
        failures = [str(t) for t, _ in result.failures]
        errors = [str(t) for t, _ in result.errors]
        tests_run = result.testsRun
    finally:
        probe_mod.get_persistence_store = orig_probe_factory
        persistence_mod.get_persistence_store = orig_persist_factory
        persistence_mod.init_persistence = orig_init_persist
        sqlite3.connect = real_connect
        control_mod._write_registry = real_write_registry
        builtins.open = real_builtin_open
        io.open = real_io_open

    hashes_after = snapshot_hashes()
    data_after = inventory(DATA_DIR)
    logs_after = inventory(LOGS_DIR)

    def diff_inv(before: dict, after: dict) -> dict:
        added = sorted(k for k in after if k not in before)
        removed = sorted(k for k in before if k not in after)
        changed = sorted(
            k for k in before if k in after and before[k] != after[k])
        return {"added": added, "removed": removed, "changed": changed}

    prohibited = [h for h in hits if h["kind"] != "sqlite_connect_readonly_uri"]
    readonly_uri = [h for h in hits if h["kind"] == "sqlite_connect_readonly_uri"]
    blocked = [h for h in prohibited if h["kind"] == "default_factory_call"]
    canonical_effective = (
        [{"bucket": "connect", **h} for h in canonical_connects]
        + [{"bucket": "file", **h} for h in file_write_attempts]
        + [{"bucket": "registry", **h} for h in registry_attempts])
    evidence = {
        "barrier": "audit_test_isolation ETAPA1",
        "suite": {"tests_run": tests_run, "ok": suite_ok,
                  "failures": failures, "errors": errors},
        "prohibited_hits": prohibited,
        "prohibited_hit_count": len(prohibited),
        "prohibited_by_kind": {},
        "buckets": {
            "blocked": blocked,
            "blocked_count": len(blocked),
            "canonical_effective": canonical_effective,
            "canonical_effective_count": len(canonical_effective),
            "residual_ro": readonly_uri,
            "residual_ro_count": len(readonly_uri),
        },
        "canonical_connects": canonical_connects,
        "canonical_connect_count": len(canonical_connects),
        "readonly_uri_connects": readonly_uri,
        "registry_write_attempts": registry_attempts,
        "file_write_attempts": file_write_attempts,
        "connect_counters": counters,
        "hashes_before": hashes_before,
        "hashes_after": hashes_after,
        "hashes_equal": hashes_before == hashes_after,
        "data_inventory_diff": diff_inv(data_before, data_after),
        "logs_inventory_diff": diff_inv(logs_before, logs_after),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    from collections import Counter
    evidence["prohibited_by_kind"] = dict(
        Counter(h["kind"] for h in prohibited))
    out_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    print("tests=%d ok=%s prohibited=%s blocked=%d effective=%d ro=%d "
          "file_writes=%d hashes_equal=%s data_diff=%s logs_diff=%s" % (
              tests_run, suite_ok, evidence["prohibited_by_kind"],
              len(blocked), len(canonical_effective), len(readonly_uri),
              len(file_write_attempts),
              hashes_before == hashes_after,
              evidence["data_inventory_diff"],
              evidence["logs_inventory_diff"]))
    print("evidence: %s" % out_path)
    clean = (suite_ok and not prohibited and not canonical_effective
             and hashes_before == hashes_after
             and not evidence["data_inventory_diff"]["added"]
             and not evidence["data_inventory_diff"]["removed"]
             and not evidence["data_inventory_diff"]["changed"]
             and not evidence["logs_inventory_diff"]["added"]
             and not evidence["logs_inventory_diff"]["removed"]
             and not evidence["logs_inventory_diff"]["changed"])
    # NOTE: residual_ro (read-only URIs) is reported separately and never
    # flips this gate: mode=ro connections cannot write. Everything else
    # canonical flips it: blocked attempts, effective connects/writes.
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
