"""Pruebas pequenas de la matriz de cobertura conjunta (joint_coverage_matrix).

Cubren el punto 6 del mandato:
- Ventanas que se solapan pero no contienen parejas válidas.
- Pareja válida y precio futuro indebidamente usado como referencia (no se usa
  el close de una vela horaria que contiene T como si se conociera en T).
- Hueco o resolución incompatible (vela 1m con solo precios 1h, y viceversa).

Usan SQLite en memoria, no tocan DBs canonicas, no abren red publica.
Prueban el MECANISMO de emparejamiento, NO evidencia de ventaja economica.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for p in (str(ROOT), str(SRC), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import research_universe_liquidity_inventory as inv  # noqa: E402


def _mk_con(rows):
    """Crea una SQLite en memoria con tabla market_klines poblada con rows."""
    tmp = Path(tempfile.mkdtemp(prefix="jointcov_"))
    con = sqlite3.connect(str(tmp / "mk.db"))
    con.execute(
        "CREATE TABLE market_klines (symbol TEXT, interval TEXT, "
        "open_time INTEGER, open REAL, high REAL, low REAL, close REAL, "
        "close_time INTEGER, base_volume TEXT, quote_volume TEXT, "
        "trade_count INTEGER, taker_buy_base TEXT, taker_buy_quote TEXT, "
        "fetched_at INTEGER)")
    con.executemany(
        "INSERT INTO market_klines VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    return con


class TestPrecioReferenciaEnT(unittest.TestCase):
    """_vela_cercana_antes_o_en: precio conocido en T (close_time <= T)."""

    def test_vela_cerrada_antes_de_T_es_referencia_valida(self):
        con = _mk_con([
            ("BTCUSDT", "1h", 1000, 100, 101, 99, 101, 3600000, "1", "1", 1, "1", "1", 3600000),
            ("BTCUSDT", "1h", 3600000, 100, 102, 99, 101, 7200000, "1", "1", 1, "1", "1", 7200000),
        ])
        # T = 5000000 (dentro de la vela 3600000-7200000). La ultima vela cerrada
        # antes o en T es la que cierra en 3600000 (precio 101).
        v = inv._vela_cercana_antes_o_en(con, "BTCUSDT", "1h", 5000000)
        self.assertIsNotNone(v)
        self.assertEqual(v["close_time"], 3600000)
        self.assertEqual(v["close"], 101)
        con.close()

    def test_no_hay_vela_cerrada_antes_de_T_retorna_None(self):
        con = _mk_con([
            ("BTCUSDT", "1h", 3600000, 100, 101, 99, 100, 7200000, "1", "1", 1, "1", "1", 7200000),
        ])
        # T = 1000 (antes de la primera vela). No hay vela cerrada antes de T.
        v = inv._vela_cercana_antes_o_en(con, "BTCUSDT", "1h", 1000)
        self.assertIsNone(v)
        con.close()

    def test_no_se_usa_close_de_vela_que_contiene_T(self):
        """Si T cae dentro de una vela horaria, su close NO se conoce en T,
        por lo que no debe usarse como precio de referencia."""
        con = _mk_con([
            ("BTCUSDT", "1h", 3600000, 100, 105, 99, 105, 7200000, "1", "1", 1, "1", "1", 7200000),
        ])
        # T = 5000000 cae dentro de la vela 3600000-7200000. Su close (105)
        # no se conocia en T. No hay otra vela cerrada antes de T.
        v = inv._vela_cercana_antes_o_en(con, "BTCUSDT", "1h", 5000000)
        self.assertIsNone(v)
        con.close()


class TestPrecioObjetivoTmásH(unittest.TestCase):
    """_vela_cubriendo_objetivo: precio en T+h (open_time <= T+h <= close_time)."""

    def test_vela_que_cubre_T_plus_h_es_objetivo_valido(self):
        con = _mk_con([
            ("BTCUSDT", "1h", 7200000, 101, 102, 100, 101, 10800000, "1", "1", 1, "1", "1", 10800000),
        ])
        # T = 7200000, h = 1h -> T+h = 10800000. La vela 7200000-10800000
        # cubre T+h (open_time=7200000 <= 10800000 <= close_time=10800000).
        v = inv._vela_cubriendo_objetivo(con, "BTCUSDT", "1h", 10800000)
        self.assertIsNotNone(v)
        self.assertEqual(v["open_time"], 7200000)
        self.assertEqual(v["close_time"], 10800000)
        con.close()

    def test_vela_que_cierra_antes_de_T_plus_h_no_es_objetivo(self):
        con = _mk_con([
            ("BTCUSDT", "1h", 3600000, 100, 101, 99, 100, 7200000, "1", "1", 1, "1", "1", 7200000),
            ("BTCUSDT", "1h", 10800000, 101, 102, 100, 101, 14400000, "1", "1", 1, "1", "1", 14400000),
        ])
        # T = 7200000, T+h = 10800000. La vela 3600000-7200000 cierra en 7200000
        # (es T, no cubre T+h como objetivo futuro). La vela 10800000-14400000
        # empieza en 10800000 (= T+h), cubre T+h.
        v = inv._vela_cubriendo_objetivo(con, "BTCUSDT", "1h", 10800000)
        self.assertIsNotNone(v)
        self.assertEqual(v["open_time"], 10800000)
        con.close()

    def test_no_hay_vela_que_cubra_T_plus_h_retorna_None(self):
        con = _mk_con([
            ("BTCUSDT", "1h", 3600000, 100, 101, 99, 100, 7200000, "1", "1", 1, "1", "1", 7200000),
        ])
        # T = 7200000, T+h = 10800000. No hay vela con open_time <= 10800000
        # y close_time >= 10800000 (la unica cierra en 7200000 < 10800000).
        v = inv._vela_cubriendo_objetivo(con, "BTCUSDT", "1h", 10800000)
        self.assertIsNone(v)
        con.close()


class TestResolucionIncompatible(unittest.TestCase):
    """No se extrapolan horizontes de un minuto usando velas horarias."""

    def test_intervalo_1m_con_solo_precios_1h_no_empareja_1m(self):
        con = _mk_con([
            ("BTCUSDT", "1h", 3600000, 100, 101, 99, 100, 7200000, "1", "1", 1, "1", "1", 7200000),
        ])
        # Pedir precio objetivo para intervalo 1m en T+h=7200000, pero solo hay
        # velas 1h. No hay velas 1m, por lo que no hay emparejamiento 1m.
        v = inv._vela_cubriendo_objetivo(con, "BTCUSDT", "1m", 7200000)
        self.assertIsNone(v)
        con.close()

    def test_intervalo_1h_con_solo_precios_1m_no_empareja_1h(self):
        con = _mk_con([
            ("BTCUSDT", "1m", 3600000, 100, 101, 99, 100, 3660000, "1", "1", 1, "1", "1", 3660000),
        ])
        # Pedir precio objetivo para intervalo 1h en T+h=7200000, pero solo hay
        # velas 1m. No hay velas 1h, por lo que no hay emparejamiento 1h.
        v = inv._vela_cubriendo_objetivo(con, "BTCUSDT", "1h", 7200000)
        self.assertIsNone(v)
        con.close()


if __name__ == "__main__":
    unittest.main()
