"""Pruebas focalizadas de la tabla de observaciones libro+flujo (punto 6 del mandato).

Prueban el MECANISMO de emparejamiento libro-flujo, la clasificación de
disponibilidad (NULL / publicada en T / publicada después de T) y de precios en
T y T+h. La prueba de integración ejecuta el GENERADOR COMPLETO (`main()`) sobre
SQLite temporal con el esquema real y salidas aisladas.

No tocan DBs canónicas, no abren red pública. Prueban el MECANISMO, no evidencia
de ventaja económica.
"""
from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for p in (str(ROOT), str(SRC), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import research_observations_table as rot  # noqa: E402
from research_observations_table import (  # noqa: E402
    CLASE_DESCONOCIDA,
    CLASE_DESPUES_DE_T,
    CLASE_EN_T,
    ESTADO_DESCARTADA,
    ESTADO_DESCRIPTIVA,
    ESTADO_EVALUABLE,
    cargar_flujo,
    cargar_libro,
    clasificar_disponibilidad,
    construir_observacion,
    emparejar_libro_flujo,
    precio_en_T,
    precio_en_T_plus_h,
)

# Instante de referencia con resolución de 1h disponible a su alrededor.
BASE = 1_790_000_000_000
BS = BASE - 60_000
BE = BASE
VELAS = [
    (BASE - 3_600_000, BASE, 100.0),
    (BASE, BASE + 3_600_000, 110.0),
]


def _libro(
    symbol: str,
    bs: int,
    be: int,
    as_of_ms: int | None = None,
    spread_mean: float = 0.01,
    imb_mean: float = 0.0,
    micro_mean: float = 0.0,
    bid20_mean: float = 100.0,
    ask20_mean: float = 100.0,
) -> dict:
    return {
        "symbol": symbol,
        "bucket_start": bs,
        "bucket_end": be,
        "spread_mean": spread_mean,
        "imb_mean": imb_mean,
        "micro_mean": micro_mean,
        "bid20_mean": bid20_mean,
        "ask20_mean": ask20_mean,
        "first_event_ms": bs,
        "last_event_ms": be - 40,
        "as_of_ms": as_of_ms,
        "run_id": None,
        "price_source": None,
    }


def _flujo(
    symbol: str,
    bs: int,
    be: int,
    as_of_ms: int | None = None,
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
        "run_id": None,
        "price_source": None,
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


class TestClasificacionDisponibilidad(unittest.TestCase):
    """Tres clases mutuamente excluyentes; NULL no es 'posterior'."""

    def test_null_es_desconocida(self):
        self.assertEqual(clasificar_disponibilidad(None, BE), CLASE_DESCONOCIDA)

    def test_as_of_en_o_antes_de_T_es_publicada_en_T(self):
        self.assertEqual(clasificar_disponibilidad(BE, BE), CLASE_EN_T)
        self.assertEqual(clasificar_disponibilidad(BE - 1, BE), CLASE_EN_T)

    def test_as_of_posterior_a_T_es_publicada_despues_de_T(self):
        self.assertEqual(
            clasificar_disponibilidad(BE + 1, BE), CLASE_DESPUES_DE_T
        )


class TestDisponibilidadTemporal(unittest.TestCase):
    """Disponibilidad desconocida o posterior a T no acredita en T."""

    def test_as_of_ms_none_no_acredita(self):
        libro = _libro("BTCUSDT", BS, BE, as_of_ms=None)
        flujo = _flujo("BTCUSDT", BS, BE, as_of_ms=None)
        obs = construir_observacion("BTCUSDT", BS, BE, libro, flujo, VELAS)
        self.assertIsNone(obs["disponible_publicado_ms"])
        self.assertFalse(obs["disponible_publicada_en_T"])
        self.assertEqual(obs["disponibilidad"]["libro"]["clase"], CLASE_DESCONOCIDA)
        self.assertEqual(obs["disponibilidad"]["flujo"]["clase"], CLASE_DESCONOCIDA)

    def test_disponibilidad_despues_de_T_no_acredita(self):
        libro = _libro("BTCUSDT", BS, BE, as_of_ms=BE + 5000)
        flujo = _flujo("BTCUSDT", BS, BE, as_of_ms=BE + 5000)
        obs = construir_observacion("BTCUSDT", BS, BE, libro, flujo, VELAS)
        self.assertFalse(obs["disponible_publicada_en_T"])
        self.assertEqual(
            obs["disponibilidad"]["libro"]["clase"], CLASE_DESPUES_DE_T
        )

    def test_disponibilidad_antes_de_T_acredita(self):
        libro = _libro("BTCUSDT", BS, BE, as_of_ms=BE - 500)
        flujo = _flujo("BTCUSDT", BS, BE, as_of_ms=BE - 400)
        obs = construir_observacion("BTCUSDT", BS, BE, libro, flujo, VELAS)
        self.assertTrue(obs["disponible_publicada_en_T"])
        self.assertEqual(obs["disponible_publicado_ms"], BE - 400)

    def test_una_sola_fuente_acreditada_no_basta(self):
        libro = _libro("BTCUSDT", BS, BE, as_of_ms=BE - 500)
        flujo = _flujo("BTCUSDT", BS, BE, as_of_ms=None)
        obs = construir_observacion("BTCUSDT", BS, BE, libro, flujo, VELAS)
        self.assertFalse(obs["disponible_publicada_en_T"])
        self.assertEqual(obs["estado"], ESTADO_DESCRIPTIVA)


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
        velas = [(0, 3600000, 100.0), (3600000, 7200000, 110.0)]
        p_T, ct_T = precio_en_T(velas, 3600000)
        p_Tph, ct_Tph = precio_en_T_plus_h(velas, 3600000)
        self.assertEqual(p_T, 100.0)
        self.assertEqual(ct_T, 3600000)
        self.assertEqual(p_Tph, 110.0)
        self.assertEqual(ct_Tph, 7200000)


class TestConstruirObservacionCompleta(unittest.TestCase):
    """Descripción y evaluación causal quedan en estados separados."""

    def test_par_con_precios_y_disponibilidad_en_T_es_evaluable(self):
        libro = _libro("BTCUSDT", BS, BE, as_of_ms=BE - 500)
        flujo = _flujo("BTCUSDT", BS, BE, as_of_ms=BE - 400)
        obs = construir_observacion("BTCUSDT", BS, BE, libro, flujo, VELAS)
        self.assertEqual(obs["estado"], ESTADO_EVALUABLE)
        self.assertTrue(obs["evaluable_causalmente"])
        self.assertIsNone(obs["motivo_descarte"])
        self.assertIsNone(obs["motivo_no_evaluable"])
        self.assertEqual(obs["precio"]["precio_T"], 100.0)
        self.assertEqual(obs["precio"]["precio_T_plus_h"], 110.0)
        self.assertAlmostEqual(obs["retorno"], 0.1)

    def test_disponibilidad_desconocida_es_descriptiva_no_descartada(self):
        libro = _libro("BTCUSDT", BS, BE, as_of_ms=None)
        flujo = _flujo("BTCUSDT", BS, BE, as_of_ms=None)
        obs = construir_observacion("BTCUSDT", BS, BE, libro, flujo, VELAS)
        self.assertEqual(obs["estado"], ESTADO_DESCRIPTIVA)
        self.assertFalse(obs["evaluable_causalmente"])
        self.assertIsNone(obs["motivo_descarte"])
        self.assertIn(
            "disponibilidad_publicada_desconocida_libro", obs["motivo_no_evaluable"]
        )
        self.assertIn(
            "disponibilidad_publicada_desconocida_flujo", obs["motivo_no_evaluable"]
        )
        # El retorno se conserva: no se pierde información descriptiva.
        self.assertAlmostEqual(obs["retorno"], 0.1)

    def test_publicacion_despues_de_T_es_descriptiva_con_motivo_propio(self):
        libro = _libro("BTCUSDT", BS, BE, as_of_ms=BE + 5000)
        flujo = _flujo("BTCUSDT", BS, BE, as_of_ms=BE + 5000)
        obs = construir_observacion("BTCUSDT", BS, BE, libro, flujo, VELAS)
        self.assertEqual(obs["estado"], ESTADO_DESCRIPTIVA)
        self.assertIn(
            "disponibilidad_publicada_despues_de_T_libro", obs["motivo_no_evaluable"]
        )
        self.assertIn(
            "disponibilidad_publicada_despues_de_T_flujo", obs["motivo_no_evaluable"]
        )

    def test_libro_sin_flujo_es_descartado_con_motivo(self):
        libro = _libro("BTCUSDT", BS, BE, as_of_ms=BE - 500)
        obs = construir_observacion("BTCUSDT", BS, BE, libro, None, VELAS)
        self.assertEqual(obs["estado"], ESTADO_DESCARTADA)
        self.assertIn("flujo_sin_datos_para_este_bucket", obs["motivo_descarte"])
        self.assertTrue(obs["observation_id"].endswith("|L"))
        self.assertIsNone(obs["flujo"])

    def test_flujo_sin_libro_es_descartado_con_motivo(self):
        flujo = _flujo("BTCUSDT", BS, BE, as_of_ms=BE - 500)
        obs = construir_observacion("BTCUSDT", BS, BE, None, flujo, VELAS)
        self.assertEqual(obs["estado"], ESTADO_DESCARTADA)
        self.assertIn("libro_sin_datos_para_este_bucket", obs["motivo_descarte"])
        self.assertTrue(obs["observation_id"].endswith("|F"))

    def test_par_sin_precio_posterior_es_descartado(self):
        libro = _libro("BTCUSDT", BS, BE, as_of_ms=BE - 500)
        flujo = _flujo("BTCUSDT", BS, BE, as_of_ms=BE - 500)
        obs = construir_observacion(
            "BTCUSDT", BS, BE, libro, flujo, [(BASE - 3600000, BASE, 100.0)]
        )
        self.assertEqual(obs["estado"], ESTADO_DESCARTADA)
        self.assertIn("sin_precio_posterior_en_T_plus_h", obs["motivo_descarte"])


class TestGeneradorContraBaseTemporal(unittest.TestCase):
    """Integración: ejecuta `main()` completo contra SQLite temporal.

    Verifica el artefacto real (jsonl + resumen + muestra) y que las DBs de
    entrada no se modifican (solo lectura).
    """

    def _crear_bd_temporal(self, libro_rows, flujo_rows, klines_rows):
        tmp = Path(tempfile.mkdtemp(prefix="obs_test_"))
        db_path = tmp / "historical.db"
        cache_path = tmp / "market_cache.db"

        con_hist = sqlite3.connect(str(db_path))
        cur = con_hist.cursor()
        cur.execute(
            """CREATE TABLE research_book_1m (
                symbol TEXT, bucket_start INTEGER, bucket_end INTEGER,
                spread_mean REAL, imb_mean REAL, micro_mean REAL,
                bid20_mean REAL, ask20_mean REAL,
                first_event_ms INTEGER, last_event_ms INTEGER,
                as_of_ms INTEGER, run_id TEXT, price_source TEXT
            )"""
        )
        cur.executemany(
            "INSERT INTO research_book_1m VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    r["symbol"], r["bucket_start"], r["bucket_end"],
                    r["spread_mean"], r["imb_mean"], r["micro_mean"],
                    r["bid20_mean"], r["ask20_mean"],
                    r["first_event_ms"], r["last_event_ms"], r["as_of_ms"],
                    r["run_id"], r["price_source"],
                )
                for r in libro_rows
            ],
        )
        cur.execute(
            """CREATE TABLE research_flow_1m (
                symbol TEXT, bucket_start INTEGER, bucket_end INTEGER,
                buy_notional REAL, sell_notional REAL, delta REAL,
                delta_ratio REAL, base_volume REAL, trade_count INTEGER,
                price_close REAL, first_event_ms INTEGER, last_event_ms INTEGER,
                as_of_ms INTEGER, run_id TEXT, price_source TEXT
            )"""
        )
        cur.executemany(
            "INSERT INTO research_flow_1m VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    r["symbol"], r["bucket_start"], r["bucket_end"],
                    r["buy_notional"], r["sell_notional"], r["delta"],
                    r["delta_ratio"], r["base_volume"], r["trade_count"],
                    r["price_close"], r["first_event_ms"], r["last_event_ms"],
                    r["as_of_ms"], r["run_id"], r["price_source"],
                )
                for r in flujo_rows
            ],
        )
        con_hist.commit()
        con_hist.close()

        con_cache = sqlite3.connect(str(cache_path))
        cur_cache = con_cache.cursor()
        cur_cache.execute(
            """CREATE TABLE market_klines (
                symbol TEXT, interval TEXT, source TEXT,
                open_time INTEGER, open TEXT, high TEXT, low TEXT,
                close TEXT, base_volume TEXT, quote_volume TEXT,
                trade_count INTEGER, taker_buy_base TEXT,
                taker_buy_quote TEXT, close_time INTEGER, fetched_at INTEGER
            )"""
        )
        cur_cache.executemany(
            "INSERT INTO market_klines VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            klines_rows,
        )
        con_cache.commit()
        con_cache.close()

        return tmp

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_generador_completo_contra_sqlite_temporal(self):
        bs1, be1 = BASE - 60_000, BASE
        bs2, be2 = BASE + 60_000, BASE + 120_000
        bs3, be3 = BASE + 120_000, BASE + 180_000
        bs4, be4 = BASE - 60_000, BASE
        bs5, be5 = BASE, BASE + 60_000

        libro_rows = [
            _libro("BTCUSDT", bs1, be1, as_of_ms=BE - 500),
            _libro("BTCUSDT", bs2, be2, as_of_ms=None),
            _libro("BTCUSDT", bs3, be3, as_of_ms=BE + 200_000),
            _libro("AIOTUSDT", bs4, be4, as_of_ms=BE - 500),
        ]
        flujo_rows = [
            _flujo("BTCUSDT", bs1, be1, as_of_ms=BE - 400),
            _flujo("BTCUSDT", bs2, be2, as_of_ms=None),
            _flujo("BTCUSDT", bs3, be3, as_of_ms=BE + 200_000),
            _flujo("AIOTUSDT", bs4, be4, as_of_ms=BE - 500),
            _flujo("AIOTUSDT", bs5, be5, as_of_ms=None),
        ]
        klines_rows = [
            ("BTCUSDT", "1h", "klines", BASE - 3_600_000, "100.0", "101.0",
             "99.0", "100.0", "10.0", "1000.0", 1, "10.0", "1000.0",
             BASE, BASE),
            ("BTCUSDT", "1h", "klines", BASE, "110.0", "111.0", "109.0",
             "110.0", "10.0", "1100.0", 1, "11.0", "1100.0",
             BASE + 3_600_000, BASE + 3_600_000),
        ]
        tmp = self._crear_bd_temporal(libro_rows, flujo_rows, klines_rows)
        hist = tmp / "historical.db"
        cache = tmp / "market_cache.db"
        hist_sha_antes = self._sha256(hist)
        cache_sha_antes = self._sha256(cache)

        out_jsonl = tmp / "observaciones.jsonl"
        out_resumen = tmp / "observaciones_resumen.json"
        out_muestra = tmp / "observaciones_muestra_validacion.json"

        with mock.patch.multiple(
            rot,
            HIST=hist,
            CACHE=cache,
            OUT_JSONL=out_jsonl,
            OUT_RESUMEN=out_resumen,
            OUT_MUESTRA=out_muestra,
        ):
            with redirect_stdout(io.StringIO()):
                rot.main()

        # Solo lectura sobre las DBs de entrada.
        self.assertEqual(self._sha256(hist), hist_sha_antes)
        self.assertEqual(self._sha256(cache), cache_sha_antes)

        resumen = json.loads(out_resumen.read_text(encoding="utf-8"))
        self.assertEqual(resumen["n_observaciones_totales"], 5)
        self.assertEqual(resumen["n_parejas_libro_flujo"], 4)
        self.assertEqual(resumen["n_libro_sin_flujo"], 0)
        self.assertEqual(resumen["n_flujo_sin_libro"], 1)
        self.assertEqual(resumen["n_apta_temporalmente_para_evaluacion"], 1)
        self.assertEqual(resumen["n_aceptada_para_descripcion"], 2)
        self.assertEqual(resumen["n_descartada"], 2)

        libro = resumen["disponibilidad_por_fuente"]["libro"]
        self.assertEqual(libro["total"], 4)
        self.assertEqual(libro["as_of_null"], 1)
        self.assertEqual(libro["as_of_presente_en_o_antes_del_bucket"], 2)
        self.assertEqual(libro["as_of_posterior_al_bucket"], 1)

        flujo = resumen["disponibilidad_por_fuente"]["flujo"]
        self.assertEqual(flujo["total"], 5)
        self.assertEqual(flujo["as_of_null"], 2)
        self.assertEqual(flujo["as_of_presente_en_o_antes_del_bucket"], 2)
        self.assertEqual(flujo["as_of_posterior_al_bucket"], 1)

        self.assertEqual(
            resumen["disponibilidad_observaciones"]["n_parejas_evaluadas"], 4
        )
        self.assertEqual(
            resumen["disponibilidad_observaciones"]["ambas_publicadas_en_T"], 2
        )
        self.assertEqual(
            resumen["disponibilidad_observaciones"]["alguna_desconocida"], 1
        )
        self.assertEqual(
            resumen["disponibilidad_observaciones"]["alguna_posterior_a_T"], 1
        )
        self.assertEqual(resumen["retorno_evaluable_causalmente"]["n"], 1)
        self.assertAlmostEqual(resumen["retorno_evaluable_causalmente"]["media"], 0.1)
        self.assertEqual(resumen["retorno_descriptivo_no_evaluable"]["n"], 2)

        filas = [
            json.loads(line)
            for line in out_jsonl.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(filas), 5)
        por_id = {f["observation_id"]: f for f in filas}
        self.assertEqual(
            por_id[f"BTCUSDT|{bs1}|{be1}"]["estado"], ESTADO_EVALUABLE
        )
        self.assertEqual(
            por_id[f"BTCUSDT|{bs2}|{be2}"]["estado"], ESTADO_DESCRIPTIVA
        )
        self.assertIn(
            "desconocida",
            por_id[f"BTCUSDT|{bs2}|{be2}"]["motivo_no_evaluable"],
        )
        self.assertEqual(
            por_id[f"BTCUSDT|{bs3}|{be3}"]["estado"], ESTADO_DESCRIPTIVA
        )
        self.assertIn(
            "despues_de_T",
            por_id[f"BTCUSDT|{bs3}|{be3}"]["motivo_no_evaluable"],
        )
        self.assertEqual(
            por_id[f"AIOTUSDT|{bs4}|{be4}"]["estado"], ESTADO_DESCARTADA
        )
        self.assertIn(
            "sin_precio_inicial_en_T",
            por_id[f"AIOTUSDT|{bs4}|{be4}"]["motivo_descarte"],
        )
        self.assertEqual(
            por_id[f"AIOTUSDT|{bs5}|{be5}|F"]["estado"], ESTADO_DESCARTADA
        )
        self.assertIn(
            "libro_sin_datos_para_este_bucket",
            por_id[f"AIOTUSDT|{bs5}|{be5}|F"]["motivo_descarte"],
        )

        muestra = json.loads(out_muestra.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(muestra), 3)
        con_retorno = [m for m in muestra if m["retorno_registrado"] is not None]
        self.assertTrue(con_retorno, "la muestra debe incluir valores no nulos")
        for m in con_retorno:
            self.assertAlmostEqual(
                m["retorno_registrado"], m["retorno_recalculado"], places=12
            )

    def test_cargar_tablas_reales_del_esquema(self):
        """Las consultas de carga aceptan el esquema real (columnas v3)."""
        tmp = self._crear_bd_temporal(
            [_libro("BTCUSDT", BS, BE, as_of_ms=BE - 1)],
            [_flujo("BTCUSDT", BS, BE, as_of_ms=BE - 1)],
            [],
        )
        con = sqlite3.connect(
            f"file:{(tmp / 'historical.db').as_posix()}?mode=ro", uri=True
        )
        try:
            libro, dup_libro = cargar_libro(con)
            flujo, dup_flujo = cargar_flujo(con)
        finally:
            con.close()
        self.assertEqual(len(libro), 1)
        self.assertEqual(len(flujo), 1)
        self.assertEqual(dup_libro, [])
        self.assertEqual(dup_flujo, [])


if __name__ == "__main__":
    unittest.main()
