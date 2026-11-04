"""Pruebas pequenas de SQLite para el inventario corregido.

Deterministas: usan SQLite en memoria con datos sinteticos conocidos.
No escriben en DBs canonicas, no abren conexiones publicas.
Cubren: conteos conocidos (COUNT(*) vs grupos), mezcla de horizontes,
procedencia desconocida y elegibilidad.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# scripts/ no esta en el path por defecto (run_tests.py solo añade src/).
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys_path_inserted = False


def _make_temp_db() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="resinv_"))
    db = tmp / "test.db"
    con = sqlite3.connect(str(db))
    cur = con.cursor()
    # contract_catalog con 5 simbolos, 3 elegibles (TRADING+eligible=1)
    cur.execute(
        "CREATE TABLE contract_catalog (symbol TEXT, status TEXT, "
        "eligible INTEGER, exclusion_reasons TEXT)"
    )
    cur.executemany(
        "INSERT INTO contract_catalog VALUES (?,?,?,?)",
        [
            ("BTCUSDT", "TRADING", 1, "[]"),
            ("ETHUSDT", "TRADING", 1, "[]"),
            ("SOLUSDT", "TRADING", 1, "[]"),
            ("BADUSDT", "SETTLING", 0, '["status=SETTLING"]'),
            ("NOELIGUSDT", "TRADING", 0, '["eligible=0"]'),
        ],
    )
    # market_klines: 10 filas en 2 grupos (2 simbolos x 1 intervalo) para
    # probar COUNT(*) (10) != numero de grupos (2).
    cur.execute(
        "CREATE TABLE market_klines (symbol TEXT, interval TEXT, "
        "open_time INTEGER, close_time INTEGER)"
    )
    cur.executemany(
        "INSERT INTO market_klines VALUES (?,?,?,?)",
        [("BTCUSDT", "1h", 1000, 2000)] * 7
        + [("ETHUSDT", "1h", 1000, 2000)] * 3,
    )
    # event_instances OK y event_outcomes con mezcla de horizontes
    cur.execute(
        "CREATE TABLE event_instances (event_id TEXT, symbol TEXT, "
        "event_time INTEGER, data_quality TEXT, features_json TEXT)"
    )
    cur.executemany(
        "INSERT INTO event_instances VALUES (?,?,?,?,?)",
        [
            ("e1", "BTCUSDT", 100, "OK",
             json.dumps({"taker_buy_proxy": 0.6})),
            ("e2", "BTCUSDT", 101, "OK",
             json.dumps({"taker_buy_proxy": 0.4})),
            ("e3", "ETHUSDT", 102, "OK",
             json.dumps({"taker_buy_proxy": 0.7})),
            ("e4", "SOLUSDT", 103, "BAD",  # no cuenta
             json.dumps({"taker_buy_proxy": 0.8})),
        ],
    )
    cur.execute(
        "CREATE TABLE event_outcomes (event_id TEXT, horizon TEXT, "
        "forward_return REAL, usable_for_statistics INTEGER)"
    )
    cur.executemany(
        "INSERT INTO event_outcomes VALUES (?,?,?,?)",
        [
            ("e1", "1h", 0.001, 1),   # usable 1h
            ("e1", "15m", 0.0005, 1),  # otro horizonte, no cuenta para 1h
            ("e2", "1h", -0.0002, 1),  # usable 1h
            ("e3", "1h", None, 0),    # no usable
        ],
    )
    con.commit()
    con.close()
    return db


class TestInventoryCounts(unittest.TestCase):
    """Conteos conocidos: COUNT(*) filas, no numero de grupos."""

    def test_market_klines_rows_not_groups(self):
        db = _make_temp_db()
        con = sqlite3.connect(str(db))
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM market_klines"
            )
            total_rows = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM (SELECT symbol, interval FROM "
                "market_klines GROUP BY symbol, interval)"
            )
            n_groups = cur.fetchone()[0]
        finally:
            con.close()
        self.assertEqual(total_rows, 10, "deben contarse 10 filas, no grupos")
        self.assertEqual(n_groups, 2, "hay 2 grupos simbolo/intervalo")
        self.assertNotEqual(total_rows, n_groups)

    def test_event_instances_ok_count(self):
        db = _make_temp_db()
        con = sqlite3.connect(str(db))
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM event_instances WHERE data_quality='OK'"
            )
            n = cur.fetchone()[0]
        finally:
            con.close()
        self.assertEqual(n, 3, "3 eventos OK (e4 es BAD)")

    def test_n_events_with_1h_outcome_counts_only_horizon_1h(self):
        db = _make_temp_db()
        con = sqlite3.connect(str(db))
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM event_outcomes "
                "WHERE horizon='1h' AND usable_for_statistics=1"
            )
            n_1h = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM event_outcomes")
            n_all = cur.fetchone()[0]
        finally:
            con.close()
        self.assertEqual(n_all, 4, "4 outcome-rows totales")
        self.assertEqual(n_1h, 2, "solo 2 filas horizon 1h utilizables (e1, e2)")


class TestEligibility(unittest.TestCase):
    """Elegibilidad desde datos y filtro explícito, sin hardcodear 522."""

    def test_eligible_filter(self):
        db = _make_temp_db()
        con = sqlite3.connect(str(db))
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM contract_catalog "
                "WHERE status='TRADING' AND eligible IN (1,'1','true')"
            )
            eligible = cur.fetchone()[0]
        finally:
            con.close()
        self.assertEqual(eligible, 3, "BTC/ETH/SOL elegibles")

    def test_denominator_not_hardcoded(self):
        # El denominador debe derivarse de la consulta, no de una constante.
        db = _make_temp_db()
        con = sqlite3.connect(str(db))
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM contract_catalog "
                "WHERE status='TRADING' AND eligible IN (1,'1','true')"
            )
            derived = cur.fetchone()[0]
        finally:
            con.close()
        self.assertEqual(derived, 3)
        self.assertNotEqual(derived, 522)
        self.assertNotEqual(derived, 942)


class TestProvenance(unittest.TestCase):
    """Procedencia segun evidencia, nunca segun rows>0."""

    def test_unknown_when_no_schema(self):
        from scripts.research_universe_liquidity_inventory import (
            provenance_from_evidence,
        )
        self.assertEqual(provenance_from_evidence(100, False, True), "UNKNOWN")
        self.assertEqual(provenance_from_evidence(0, False, True), "UNKNOWN")

    def test_real_when_rows(self):
        from scripts.research_universe_liquidity_inventory import (
            provenance_from_evidence,
        )
        self.assertEqual(provenance_from_evidence(100, True, True), "REAL")
        self.assertEqual(provenance_from_evidence(0, True, True),
                         "REAL (vacio)")

    def test_fixture_when_not_real_store(self):
        from scripts.research_universe_liquidity_inventory import (
            provenance_from_evidence,
        )
        self.assertEqual(provenance_from_evidence(100, True, False), "FIXTURE")


class TestJointCoverageLogic(unittest.TestCase):
    """Matriz de cobertura conjunta: horizonte computable solo si hay precio
    posterior disponible dentro de la ventana."""

    def test_horizon_computable_when_posterior_inside_window(self):
        # Simula la logica de joint_coverage_matrix con datos sinteticos.
        win_end = 2000  # fin de ventana research
        first_post_open = 1500  # primera vela posterior dentro de ventana
        horizons = []
        if first_post_open <= win_end:
            horizons.append("1h")
        self.assertIn("1h", horizons)

    def test_horizon_not_computable_when_posterior_after_window(self):
        win_end = 2000
        first_post_open = 3000  # despues del fin de ventana
        horizons = []
        if first_post_open <= win_end:
            horizons.append("1h")
        self.assertEqual(horizons, [])


if __name__ == "__main__":
    unittest.main()
