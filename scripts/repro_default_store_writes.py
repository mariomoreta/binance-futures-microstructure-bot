"""ETAPA 1.2 negative control: reproduce Route-A contamination on TEMP stores.

Runs the exact pre-fix test bodies that reach the default persistence
factory (test_probe x5, test_host_telemetry x2, test_p14b_3 x3), with
``probe.get_persistence_store`` intercepted to a TEMPORARY PersistenceStore.
Counts the rows those bodies write (observations/rejections) and the
factory call count, proving the contamination mechanism WITHOUT touching
the canonical DB (hashes before/after are asserted equal inside).

Companion proof: the PREFIX audit ran the same bodies with a RAISING
factory and the suite stayed green (61 swallowed attempts) -- green does
not mean pure.

Usage (from repo root)::

    python scripts/repro_default_store_writes.py [--out path]

Stdlib only. Exit 0 when rows>0 were captured on temp AND canonical
hashes are unchanged; exit 1 otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
TESTS = ROOT / "tests"
CANON = [
    ROOT / "data" / "microprobe.db",
    ROOT / "data" / "historical" / "historical.db",
    ROOT / "logs" / "probe_runtime.json",
]
DEFAULT_OUT = ROOT / "docs" / "evidence" / "REPRO_DEFAULT_STORE_WRITES.json"

TARGETS = [
    "test_probe.ProbeTest.test_future_or_stale_payload_is_discarded",
    "test_probe.ProbeTest.test_latency_is_separated_by_stream_and_e_from_t",
    "test_probe.ProbeTest"
    ".test_mark_price_next_funding_time_is_not_transaction_time",
    "test_probe.ProbeTest"
    ".test_processing_latency_uses_high_resolution_monotonic_clock",
    "test_probe.ProbeTest.test_final_summary_aggregates_data_quality_and_safety",
    "test_host_telemetry.TestProbeByteCounting.test_exact_bytes_per_stream",
    "test_host_telemetry.TestProbeByteCounting"
    ".test_rejected_messages_still_count_bytes",
    "test_p14b_3_transport_freshness.TestAcceptedTrafficAccounting"
    ".test_accepted_message_updates_freshness",
    "test_p14b_3_transport_freshness.TestAcceptedTrafficAccounting"
    ".test_rejected_message_does_not_update_freshness",
    "test_p14b_3_transport_freshness.TestAcceptedTrafficAccounting"
    ".test_burst_of_rejects_leaves_freshness_frozen",
]


def sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if str(TESTS) not in sys.path:
        sys.path.insert(0, str(TESTS))

    before = [sha256(p) for p in CANON]

    from microstructure_probe import probe as probe_mod
    from microstructure_probe.persistence import PersistenceStore

    tmpdir = tempfile.mkdtemp(prefix="repro_route_a_")
    temp_db = Path(tmpdir) / "intercepted.db"
    temp_store = PersistenceStore(db_path=temp_db)
    temp_store.init_db()
    calls = []

    def intercepted(*a, **k):
        calls.append(1)
        return temp_store

    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    for target in TARGETS:
        suite.addTests(loader.loadTestsFromName(target))
    with mock.patch.object(probe_mod, "get_persistence_store",
                           side_effect=intercepted):
        result = unittest.TextTestRunner(verbosity=1).run(suite)

    observations = temp_store.latest_observations(limit=10000)
    rejections = temp_store.get_rejection_stats()
    temp_store.close()
    after = [sha256(p) for p in CANON]

    evidence = {
        "tests_run": result.testsRun,
        "tests_ok": result.wasSuccessful(),
        "factory_calls_intercepted": len(calls),
        "temp_observations_written": len(observations),
        "temp_rejections_written": rejections.get("total_rejected"),
        "temp_rejection_by_reason": rejections.get("by_reason"),
        "canonical_hashes_before": before,
        "canonical_hashes_after": after,
        "canonical_untouched": before == after,
    }
    out = Path(args.out)
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    reproduced = (result.wasSuccessful() and len(calls) > 0
                  and (len(observations) > 0
                       or (rejections.get("total_rejected") or 0) > 0)
                  and before == after)
    return 0 if reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
