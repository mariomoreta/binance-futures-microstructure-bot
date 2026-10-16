"""Reproduce OFFLINE-EVAL-V1 inputs + replay + aggregation (read-only canonicals).

Isolated: reads canonical DBs read-only, writes ONLY the caller-given
--out-dir (default fresh temp). Verifies per-symbol input_hash against the
published artifact and re-aggregates byte-identically.

Usage:
  python scripts/reproduce_offline_eval.py --out-dir <tmp> [--check-only]

check-only: verify the committed artifact parses + pinned sha (no DB needed).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "frontend" / "src" / "data" / "offline-eval-v1.json"
PINNED_SHA = "c051e88841754668a02a6d92db02ccdcb97fd16e45a08671022a370576287b3a"
CUTOFF = 1790010000000
HORIZON = 3600000
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
CAL = {"BTCUSDT": "docs/evidence/FUNDING_CALENDAR_BTCUSDT_V1.json",
       "ETHUSDT": "docs/evidence/FUNDING_CALENDAR_ETHUSDT_V1.json",
       "SOLUSDT": "docs/evidence/FUNDING_CALENDAR_SOLUSDT_V1.json"}


def _sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def check_only() -> int:
    raw = ARTIFACT.read_bytes()
    print("artifact_sha256=%s" % hashlib.sha256(raw).hexdigest())
    if hashlib.sha256(raw).hexdigest() != PINNED_SHA:
        print("PIN MISMATCH", file=sys.stderr)
        return 1
    doc = json.loads(raw.decode("utf-8"))
    assert doc["artifact_version"] == "OFFLINE-EVAL-V1"
    assert doc["schema_version"] == 1
    print("artifact OK: %s cells=%d symbols" % (doc["artifact_version"], len(doc["symbols"])))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args(argv)
    if args.check_only:
        return check_only()
    out = Path(args.out_dir) if args.out_dir else Path(tempfile.mkdtemp(prefix="oev_repro_"))
    out.mkdir(parents=True, exist_ok=True)

    def run(*cmd: str) -> None:
        r = subprocess.run(list(cmd), capture_output=True, text=True)
        sys.stdout.write(r.stdout)
        if r.returncode != 0:
            sys.stderr.write(r.stderr)
            raise SystemExit("command failed: %s" % (" ".join(cmd),))

    spec = {"cutoff_ms": CUTOFF, "horizon_ms": HORIZON, "symbols": {}}
    for sym in SYMBOLS:
        d = out / sym.lower().replace("usdt", "")
        d.mkdir(parents=True, exist_ok=True)
        run(sys.executable, "scripts/export_engine_inputs.py", "--symbols", sym,
            "--interval", "15m", "--out-dir", str(d))
        run(sys.executable, "scripts/select_eval_events.py", "--events", str(d / "events.json"),
            "--cutoff-ms", str(CUTOFF), "--horizon-ms", str(HORIZON),
            "--dev-out", str(d / "dev.json"), "--oos-out", str(d / "oos.json"),
            "--report", str(d / "selection.json"))
        dev = json.loads((d / "dev.json").read_text())
        oos = json.loads((d / "oos.json").read_text())
        (d / "admitted.json").write_text(json.dumps(dev + oos))
        run(sys.executable, "scripts/run_family_evaluation.py", "--events", str(d / "admitted.json"),
            "--candles", str(d / "candles.json"), "--calendar", CAL[sym],
            "--cutoff-ms", str(CUTOFF), "--out", str(d / "manifest.json"),
            "--formation-method", "PROPOSED-P1-11C-map-v1")
        spec["symbols"][sym] = {"manifest": str(d / "manifest.json"), "meta": str(d / "meta.json"),
                                "selection": str(d / "selection.json"), "calendar": CAL[sym]}
    inputs = out / "inputs.json"
    inputs.write_text(json.dumps(spec))
    rebuilt = out / "rebuilt.json"
    run(sys.executable, "scripts/aggregate_offline_eval.py", "--inputs", str(inputs), "--out", str(rebuilt))
    a, b = ARTIFACT.read_bytes(), rebuilt.read_bytes()
    print("published=%s" % hashlib.sha256(a).hexdigest())
    print("rebuilt  =%s" % hashlib.sha256(b).hexdigest())
    if a != b:
        print("REBUILD DIFFERS (content, not just bytes)", file=sys.stderr)
        return 1
    # input_hash cross-check per symbol
    doc = json.loads(a.decode("utf-8"))
    for sym in SYMBOLS:
        m = json.loads(Path(spec["symbols"][sym]["manifest"]).read_text())
        assert m["input_hash"] == doc["symbols"][sym]["input_hash"], sym
        print("%s input_hash=%s OK" % (sym, m["input_hash"]))
    print("REPRODUCTION OK (replay from canonical DB, byte-identical artifact)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
