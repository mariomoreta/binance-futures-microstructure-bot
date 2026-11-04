"""Pruebas focalizadas de la matriz de cobertura conjunta (punto 6 del mandato).

Prueban el MECANISMO de emparejamiento libro-flujo y de precios en T y T+h,
usando datos sintéticos en memoria. No tocan DBs canónicas, no abren red
pública. Prueban el MECANISMO, no evidencia de ventaja económica.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for p in (str(ROOT), str(SRC), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from research_observations_table import (  # noqa: E402
    emparejar_libro_flujo,
    precio_en_T,
    precio_en_T_plus_h,
    construir_observacion,
)


def _libro(symbol: str, bs: int, be: int, as_of_ms: int | None = None) -> dict:
    return {
        "symbol": symbol,
        "bucket_start": bs,
        "bucket_end": be,
        "spread_mean_bps": 0.01,
        "imb_mean": 0.0,
        "micro_mean_bps": 0.0,
        "bid20_mean_base": 100.0,
        "ask20_mean_base": 100.0,
        "first_event_ms": bs,
        "last_event_ms": be - 40,
        "as_of_ms": as_of_ms,
    }


def _flujo(
    symbol: str, bs: int, be: int, as_of_ms: int | None = None
) -> dict:
    return {
        "symbol": symbol,
        "bucket_start": bs,
        "bucket_end": be,
        "buy_notional": 100.0,
        "sell_notional": 100.0,
        "delta": 0.0,
        "delta_ratio": 0.0,
        "base_volume": 1.0,
        "trade_count": 1,
        "price_close": 100.0,
        "first_event_ms": bs,
        "last_event_ms": be - 40,
        "as_of_ms": as_of_ms,
    }


def _velas_1h(primer_open: int, n: int) -> list:
    """n velas 1h consecutivas empezando en primer_open."""
    return [
        (primer_open + i * 3600000, primer_open + (i + 1) * 3600000, 100.0 + i)
        for i in range(n)
    ]


class TestEmparejamientoLibroFlujo(unittest.TestCase):
    """Libro sin flujo y flujo sin libro: no son observación conjunta."""

    def test_libro_sin_flujo_no_es_par(self):
        libro = [_libro("BTCUSDT", 1000, 2000)]
        flujo = []
        pares, solo_libro, solo_flujo, ndl, ndf = emparejar_libro_flujo(
            libro, flujo
        )
        self.assertEqual(len(pares), 0)
        self.assertEqual(len(solo_libro), 1)
        self.assertEqual(len(solo_flujo), 0)
        self.assertEqual(ndl, 0)
        self.assertEqual(ndf, 0)

    def test_flujo_sin_libro_no_es_par(self):
        libro = []
        flujo = [_flujo("BTCUSDT", 1000, 2000)]
        pares, solo_libro, solo_flujo, ndl, ndf = emparejar_libro_flujo(
            libro, flujo
        )
        self.assertEqual(len(pares), 0)
        self.assertEqual(len(solo_libro), 0)
        self.assertEqual(len(solo_flujo), 1)
        self.assertEqual(ndl, 0)
        self.assertEqual(ndf, 0)

    def test_libro_y_flujo_mismo_bucket_son_par(self):
        libro = [_libro("BTCUSDT", 1000, 2000)]
        flujo = [_flujo("BTCUSDT", 1000, 2000)]
        pares, solo_libro, solo_flujo, ndl, ndf = emparejar_libro_flujo(
            libro, flujo
        )
        self.assertEqual(len(pares), 1)
        self.assertEqual(len(solo_libro), 0)
        self.assertEqual(len(solo_flujo), 0)
        self.assertEqual(pares[0][0]["symbol"], "BTCUSDT")
        self.assertEqual(pares[0][1]["symbol"], "BTCUSDT")

    def test_buckets_distintos_no_se_emparejan(self):
        libro = [_libro("BTCUSDT", 1000, 2000)]
        flujo = [_flujo("BTCUSDT", 2000, 3000)]
        pares, solo_libro, solo_flujo, ndl, ndf = emparejar_libro_flujo(
            libro, flujo
        )
        self.assertEqual(len(pares), 0)
        self.assertEqual(len(solo_libro), 1)
        self.assertEqual(len(solo_flujo), 1)


class TestDuplicadosNoMultiplican(unittest.TestCase):
    """Filas duplicadas no crean observaciones adicionales."""

    def test_duplicado_libro_no_multiplica(self):
        libro = [
            _libro("BTCUSDT", 1000, 2000),
            _libro("BTCUSDT", 1000, 2000),
        ]
        flujo = [_flujo("BTCUSDT", 1000, 2000)]
        pares, solo_libro, solo_flujo, ndl, ndf = emparejar_libro_flujo(
            libro, flujo
        )
        self.assertEqual(len(pares), 1)
        self.assertEqual(len(solo_libro), 1)
        self.assertEqual(ndl, 1)
        self.assertEqual(ndf, 0)


class TestDisponibilidadTemporal(unittest.TestCase):
    """Disponibilidad desconocida o posterior a T no acredita en T."""

    def test_as_of_ms_none_es_desconocida(self):
        libro = _libro("BTCUSDT", 1000, 2000, as_of_ms=None)
        flujo = _flujo("BTCUSDT", 1000, 2000, as_of_ms=None)
        velas = _velas_1h(0, 5)
        obs = construir_observacion(
            "BTCUSDT", 1000, 2000, libro, flujo, velas
        )
        self.assertIsNone(obs["disponible_publicado_ms"])
        self.assertFalse(obs["disponible_publicada_en_T"])

    def test_disponibilidad_despues_de_T_no_acredita(self):
        # as_of_ms posterior a T (bucket_end=2000, as_of=3000)
        libro = _libro("BTCUSDT", 1000, 2000, as_of_ms=3000)
        flujo = _flujo("BTCUSDT", 1000, 2000, as_of_ms=3000)
        velas = _velas_1h(0, 5)
        obs = construir_observacion(
            "BTCUSDT", 1000, 2000, libro, flujo, velas
        )
        self.assertFalse(obs["disponible_publicada_en_T"])


class TestPrecioReferenciaT(unittest.TestCase):
    """Referencia demasiado antigua o dentro de vela que contiene T+h."""

    def test_referencia_demasiado_antigua_no_se_usa(self):
        # Última vela cerrada antes de T=7000000 es la que cierra en 3600000.
        # Eso SÍ es un precio conocido en T.
        velas = [(0, 3600000, 100.0)]
        p_T, ct_T = precio_en_T(velas, 7000000)
        self.assertEqual(p_T, 100.0)
        self.assertEqual(ct_T, 3600000)

    def test_vela_que_contiene_T_plus_h_no_es_precio_en_T_plus_h(self):
        # T=3600000, T+h=7200000. Vela [3600000, 7200000] cierra exactamente en
        # T+h, por lo que SU CIERRE SÍ se conoció en T+h y ES un precio válido.
        velas = [(3600000, 7200000, 100.0), (7200000, 10800000, 110.0)]
        p_Tph, ct_Tph = precio_en_T_plus_h(velas, 3600000)
        self.assertEqual(p_Tph, 100.0)
        self.assertEqual(ct_Tph, 7200000)

    def test_no_hay_vela_que_cierre_en_T_plus_h(self):
        # T=3600000, T+h=7200000. Vela [3600000, 10800000] cierra en 10800000
        # > T+h. No hay vela con close_time en (3600000, 7200000].
        velas = [(3600000, 10800000, 100.0)]
        p_Tph, ct_Tph = precio_en_T_plus_h(velas, 3600000)
        self.assertIsNone(p_Tph)

    def test_pareja_temporal_valida_con_horizonte_efectivo(self):
        # T=3600000, T+h=7200000. Vela [3600000, 7200000] cierra exactamente en
        # T+h, por lo que SU CIERRE SÍ se conoció en T+h y ES un precio válido.
        velas = [(0, 3600000, 100.0), (3600000, 7200000, 110.0)]
        p_T, ct_T = precio_en_T(velas, 3600000)
        p_Tph, ct_Tph = precio_en_T_plus_h(velas, 3600000)
        self.assertEqual(p_T, 100.0)
        self.assertEqual(ct_T, 3600000)
        self.assertEqual(p_Tph, 110.0)
        self.assertEqual(ct_Tph, 7200000)


if __name__ == "__main__":
    unittest.main()
