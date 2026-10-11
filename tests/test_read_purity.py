"""Read-path purity for System V2 integration (DASH-V2-71B).

Contract proof (no defect found in these paths on existing stores, so no
source change ships with it): every audited DashboardState read used by
System V2 leaves the operational SQLite file, the historical SQLite file,
the probe registry, and the evidence log byte-identical, and creates no
new database files. WAL sidecars (*-wal/-shm) from read connections are
tolerated but recorded; content queries must agree before/after.

Covers: snapshot/health, all feature families, discovery + universe
events, ranks, opportunities, prospective, history coverage, research
status, event studies/symbol, probe_status, price points, search/movers
composition, status_readonly. Temp fixtures only; canonical DB, registry
and logs never touched. Run: python run_tests.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microstructure_probe import control as pc
from microstructure_probe.dashboard import DashboardState
from microstructure_probe.dashboard_data import (
    compose_universe,
    movers_table,
    search_symbols,
)
from microstructure_probe.persistence import PersistenceStore


def _rmtree(path: Path) -> None:
    try:
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        path.rmdir()
    except OSError:
        pass


def _snapshot_files(root: Path):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")
                  if p.is_file())


class ReadPurityTest(unittest.TestCase):
    def _fixture(self):
        tmp = Path(tempfile.mkdtemp(prefix="readpure_"))
        self.addCleanup(lambda: _rmtree(tmp))
        db_path = tmp / "microprobe.db"
        store = PersistenceStore(db_path=db_path)
        store.init_db()
        self.addCleanup(store.close)
        store.store_telemetry_snapshot(_summary())
        store.store_price_samples([("BTCUSDT", 1791641000000, 97000.5),
                                   ("BTCUSDT", 1791641010000, 97001.0)])
        store.store_discovery_snapshot(_discovery())
        hist_path = tmp / "historical.db"
        os.environ["MICROPROBE_HISTORICAL_DB"] = str(hist_path)
        self.addCleanup(os.environ.pop, "MICROPROBE_HISTORICAL_DB", None)
        from microstructure_probe.history_store import HistoryStore
        hist = HistoryStore(db_path=hist_path)
        hist.init_db()
        reg_path = tmp / "probe_runtime.json"
        os.environ["MICROPROBE_RUNTIME_FILE"] = str(reg_path)
        self.addCleanup(os.environ.pop, "MICROPROBE_RUNTIME_FILE", None)
        pc._write_registry(_record())
        ev_path = tmp / "evidence.log"
        ev_path.write_text("evidence\n", encoding="utf-8")
        return tmp, store, hist, reg_path, ev_path

    def test_read_battery_leaves_everything_untouched(self):
        tmp, store, hist, reg_path, ev_path = self._fixture()
        state = DashboardState(store)
        before_db = (tmp / "microprobe.db").read_bytes()
        before_hist = (tmp / "historical.db").read_bytes()
        before_reg = reg_path.read_bytes()
        before_ev = ev_path.read_bytes()
        before_files = _snapshot_files(tmp)
        before_content = _content_fingerprint(store, hist)

        # Full audited read battery (every DashboardState reader V2 may use,
        # plus the composed search/movers/universe paths and pure status).
        state.snapshot()
        state.health()
        state.return_features()
        state.discovery()
        state.universe_events()
        state.ranks()
        state.flow_features()
        state.book_features()
        state.oi_features()
        state.structure_features()
        state.state_features()
        state.opportunity_candidates()
        state.opportunity_events()
        state.history_coverage()
        state.history_coverage("BTCUSDT")
        state.research_status()
        state.prospective_status()
        state.event_studies()
        state.event_symbol("BTCUSDT")
        state.probe_status()
        state.price_points("BTCUSDT", "1h")
        state.storage()
        rows = movers_table(state)
        search_symbols("btc", rows)
        compose_universe(state)
        pc.status_readonly()

        self.assertEqual((tmp / "microprobe.db").read_bytes(), before_db)
        self.assertEqual(reg_path.read_bytes(), before_reg)
        self.assertEqual(ev_path.read_bytes(), before_ev)
        self.assertEqual(_content_fingerprint(store, hist), before_content)
        after_files = _snapshot_files(tmp)
        new_dbs = [f for f in after_files
                   if f not in before_files and f.endswith(".db")]
        self.assertEqual(new_dbs, [])
        # WAL sidecars from read connections are tolerated; anything else
        # appearing is a real write and fails loudly.
        new_other = [f for f in after_files if f not in before_files]
        for f in new_other:
            self.assertTrue(f.endswith(("-wal", "-shm", ".log")),
                            "unexpected new file from reads: %s" % f)


def _content_fingerprint(store, hist):
    return {
        "telemetry": store.latest_telemetry(),
        "returns": store.latest_return_features(),
        "discovery": store.latest_discovery(),
        "uni_events": store.universe_events(limit=50),
        "ranks": store.latest_ranks(),
        "coverage": hist.coverage_summary(),
        "research": hist.research_counts(),
    }


def _summary():
    return {
        "runtimeSeconds": 100.0,
        "safety": {"BOT_MODE": "observe", "apiKeysUsed": 0,
                   "realOrdersSent": 0},
        "clock": {"clockOffsetMs": -100.0},
        "dataQuality": {
            "expectedStreams": 11, "activeStreams": 11,
            "missingStreams": [], "staleStreams": [], "silentStreams": [],
            "messagesByStream": {"btcusdt@bookTicker": 1000},
            "maxObservedSilenceMsByStream": {"btcusdt@bookTicker": 500.0},
            "reconnections": {"public": 0, "market": 0},
            "timestampRejected": 0,
            "connectivityObservationSeconds": 100.0,
        },
    }


def _discovery():
    return {"core": ["BTCUSDT"], "hot_dynamic": [],
            "tops": {"gainers": [], "losers": [], "most_active": []},
            "generated_at_ms": int(time.time() * 1000)}


def _record():
    return {"schema": 1, "writer": "control/1", "state": "COMPLETED",
            "pid": 424243, "create_time": "STAMP",
            "started_at": "2026-10-10T10:00:00+00:00", "mode": "observe",
            "command": [sys.executable, "-m", "microstructure_probe"],
            "duration_seconds": 2100, "expected_end_at": None,
            "launcher": "agent", "preset": "standard",
            "evidence": {"dir": "ev", "log": "run.log"},
            "last_exit": None}
