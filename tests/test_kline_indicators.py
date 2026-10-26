"""Indicadores compartidos market-indicators/v1: formulas y reglas duras.

Lo que se pinza aqui:
  * formulas exactas con valores hand-calculated (sin magia);
  * sin lookahead: tocar velas posteriores no cambia el valor de la vela t;
  * solo velas cerradas: la vela en formacion queda fuera del bloque, nunca
    se publica un indicador por close incompleto;
  * huecos/warmup/volumen ausente -> UNKNOWN con reason, nunca cero inventado;
  * el bloque es versionado, lleva identidad propia y declara lo declinado
    (flujo, spread, profundidad, OI y contexto BTC) con su motivo;
  * integracion de series_payload: el payload del CLI/BFF lleva el bloque,
    y el navegador no recalcula nada.
"""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from microstructure_probe import kline_indicators as KI  # noqa: E402
from microstructure_probe import market_explorer as MX  # noqa: E402
from microstructure_probe.market_cache import MarketCache  # noqa: E402

STEP = 3_600_000  # 1h
T0 = 1_700_000_000_000


def _bar(open_time: int, close: float, high=None, low=None, open_=None,
         base_volume="10.0"):
    return {
        "open_time": open_time,
        "open": open_ if open_ is not None else str(close - 0.5),
        "high": high if high is not None else str(close + 0.5),
        "low": low if low is not None else str(close - 0.6),
        "close": str(close),
        "base_volume": base_volume,
        "quote_volume": "1000.0",
        "trade_count": 50,
        "close_time": open_time + STEP - 1,
        "fetched_at": open_time,
    }


def _row(block: dict, open_time: int) -> dict:
    for row in block["series"]:
        if row["open_time_ms"] == open_time:
            return row
    raise AssertionError(f"no row for {open_time}")


class FormulaTest(unittest.TestCase):
    def test_log_return_exact(self) -> None:
        bars = [_bar(T0, 100.0), _bar(T0 + STEP, 101.0)]
        block = KI.compute_kline_indicators(bars, STEP, T0 + 2 * STEP)
        row = _row(block, T0 + STEP)
        self.assertNotIn("log_return_bps", row["unknown"])
        self.assertAlmostEqual(
            row["values"]["log_return_bps"],
            10000.0 * math.log(101.0 / 100.0), places=4)
        # La primera vela del bloque declara warmup como UNKNOWN.
        first = _row(block, T0)
        self.assertEqual(first["unknown"]["log_return_bps"],
                         "NO_PREVIOUS_CANDLE")
        self.assertNotIn("log_return_bps", first["values"])

    def test_velocity_over_five_contiguous_candles(self) -> None:
        closes = [100.0, 101.0, 102.0, 103.0, 104.0]
        bars = [_bar(T0 + i * STEP, c) for i, c in enumerate(closes)]
        block = KI.compute_kline_indicators(bars, STEP, T0 + 5 * STEP)
        expected = 10000.0 * math.log(104.0 / 100.0)
        self.assertAlmostEqual(_row(block, T0 + 4 * STEP)["values"]["velocity_bps_5"],
                               expected, places=4)
        self.assertAlmostEqual(_row(block, T0 + 4 * STEP)["values"]["log_return_bps"],
                               10000.0 * math.log(104.0 / 103.0), places=4)

    def test_velocity_gap_inside_window_is_unknown_not_zero(self) -> None:
        # 5 velas con un hueco a mitad de la ventana: velocity UNKNOWN para t.
        times = [0, 1, 3, 4, 5]
        bars = [_bar(T0 + i * STEP, 100.0 + i) for i in times]
        block = KI.compute_kline_indicators(bars, STEP, T0 + 6 * STEP)
        row = _row(block, T0 + 5 * STEP)
        self.assertEqual(row["unknown"]["velocity_bps_5"], "GAP_IN_WINDOW")
        self.assertNotIn("velocity_bps_5", row["values"])
        # Sin ceros inventados en ninguna parte del bloque.
        self.assertFalse(
            any(v == 0 for r in block["series"]
                for v in r["values"].values()))

    def test_velocity_warmup_not_invented(self) -> None:
        bars = [_bar(T0 + i * STEP, 100.0 + i) for i in range(4)]
        block = KI.compute_kline_indicators(bars, STEP, T0 + 5 * STEP)
        self.assertEqual(
            _row(block, T0 + 3 * STEP)["unknown"]["velocity_bps_5"],
            "INSUFICIENT_CANDLES")


class RelVolumeTest(unittest.TestCase):
    def test_rel_volume_exact_and_baseline_excludes_current(self) -> None:
        # 11 velas: las 10 primeras con volumen 10, la ultima con 20.
        bars = [_bar(T0 + i * STEP, 100.0 + i) for i in range(10)]
        bars.append(_bar(T0 + 10 * STEP, 110.0, base_volume="20.0"))
        block = KI.compute_kline_indicators(bars, STEP, T0 + 11 * STEP)
        row = _row(block, T0 + 10 * STEP)
        self.assertAlmostEqual(row["values"]["rel_volume_10"], 2.0, places=6)
        # La baseline NUNCA incluye la vela corriente; si contara, el
        # resultado no seria exactamente 2.0.

    def test_missing_current_volume_is_unknown_with_reason(self) -> None:
        bars = [_bar(T0 + i * STEP, 100.0 + i) for i in range(11)]
        bars[-1]["base_volume"] = None
        block = KI.compute_kline_indicators(bars, STEP, T0 + 11 * STEP)
        self.assertEqual(
            _row(block, T0 + 10 * STEP)["unknown"]["rel_volume_10"],
            "MISSING_VOLUME")

    def test_missing_baseline_volume_is_unknown(self) -> None:
        bars = [_bar(T0 + i * STEP, 100.0 + i) for i in range(11)]
        bars[0]["base_volume"] = None
        block = KI.compute_kline_indicators(bars, STEP, T0 + 11 * STEP)
        self.assertEqual(
            _row(block, T0 + 10 * STEP)["unknown"]["rel_volume_10"],
            "MISSING_BASELINE_VOLUME")

    def test_rel_volume_warmup(self) -> None:
        bars = [_bar(T0 + i * STEP, 100.0 + i) for i in range(10)]
        block = KI.compute_kline_indicators(bars, STEP, T0 + 10 * STEP)
        row = _row(block, T0 + 9 * STEP)
        self.assertEqual(row["unknown"]["rel_volume_10"], "INSUFICIENT_CANDLES")


class VwapTest(unittest.TestCase):
    def test_vwap_typical_and_dev_bps_exact(self) -> None:
        # Ventana fija de 10 velas: precios 100..109, volumen 10 en todas.
        bars = [_bar(T0 + i * STEP, 100.0 + i) for i in range(10)]
        block = KI.compute_kline_indicators(bars, STEP, T0 + 10 * STEP)
        totals_t = 0.0
        totals_q = 0.0
        for i in range(10):
            high = 100.0 + i + 0.5
            low = 100.0 + i - 0.6
            close = 100.0 + i
            typical = (high + low + close) / 3.0
            totals_t += typical * 10.0
            totals_q += 10.0
        vwap = totals_t / totals_q
        row = _row(block, T0 + 9 * STEP)
        self.assertAlmostEqual(row["values"]["vwap_typical_10"], vwap,
                               places=4)
        self.assertAlmostEqual(row["values"]["vwap_dev_bps_10"],
                               10000.0 * ((109.0 / vwap) - 1.0), places=3)

    def test_vwap_gap_in_window_is_unknown(self) -> None:
        bars = [_bar(T0 + i * STEP, 100.0 + i) for i in (0, 1, 2, 4)]
        block = KI.compute_kline_indicators(bars, STEP, T0 + 5 * STEP)
        self.assertEqual(
            _row(block, T0 + 4 * STEP)["unknown"]["vwap_typical_10"],
            "GAP_IN_WINDOW")
        self.assertEqual(
            _row(block, T0 + 4 * STEP)["unknown"]["vwap_dev_bps_10"],
            "GAP_IN_WINDOW")


class NoLookaheadAndProvisionalTest(unittest.TestCase):
    def test_future_candles_do_not_change_value_at_t(self) -> None:
        bars = [_bar(T0 + i * STEP, 100.0 + i) for i in range(12)]
        now = T0 + 12 * STEP  # velas 0..11 ya cerradas
        anchor = T0 + 10 * STEP
        mutado = [dict(b) for b in bars]
        # Perturbacion de TODO lo posterior a la vela anclada: el valor de
        # esa vela, y de las anteriores, no cambia.
        for b in mutado:
            if b["open_time"] > anchor:
                b["close"] = "999.77"
                b["base_volume"] = "999.0"
        reference = KI.compute_kline_indicators(bars, STEP, now)
        altered = KI.compute_kline_indicators(mutado, STEP, now)
        rows_ref = [r for r in reference["series"]
                    if r["open_time_ms"] <= anchor]
        rows_alt = [r for r in altered["series"]
                    if r["open_time_ms"] <= anchor]
        self.assertEqual(rows_ref, rows_alt)
        # La fila anclada esta calculada y no cero.
        vals = [r for r in rows_ref if r["open_time_ms"] == anchor][0]["values"]
        self.assertIn("vwap_typical_10", vals)

    def test_provisional_candle_is_excluded(self) -> None:
        # La ultima vela sigue en formacion respecto a `now` y no entra.
        bars = [_bar(T0 + i * STEP, 100.0 + i) for i in range(3)]
        block = KI.compute_kline_indicators(bars, STEP, T0 + 2 * STEP)
        self.assertEqual([r["open_time_ms"] for r in block["series"]],
                         [T0, T0 + STEP])
        self.assertEqual(block["provisional_policy"]["included"], False)
        self.assertEqual(block["provisional_policy"]["reason"],
                         "PROVISIONAL_EXCLUDED")

    def test_equal_boundary_counts_as_closed(self) -> None:
        bars = [_bar(T0, 100.0)]
        # open_time + step == now: ya cerro (regla compartida con
        # _public_candle).
        block = KI.compute_kline_indicators(bars, STEP, T0 + STEP)
        self.assertEqual(len(block["series"]), 1)

    def test_empty_and_garbage_inputs_stay_versioned(self) -> None:
        # Vacio: bloque valido, sin filas.
        block = KI.compute_kline_indicators([], STEP, T0 + STEP)
        self.assertEqual(block["contract_version"],
                         "market-indicators/v1")
        self.assertEqual(block["availability"], "CLOSED_CANDLES_ONLY")
        self.assertEqual(block["series"], [])
        # Basura tolerada: fila no-dict y open_time no-entero no rompen.
        block = KI.compute_kline_indicators(
            [None, {"open_time": "x"}], STEP, T0 + STEP)
        self.assertEqual(block["series"], [])
        # Vela minima sin datos: fila con UNKNOWN, sin excepcion ni ceros.
        block = KI.compute_kline_indicators(
            [{"open_time": T0}], STEP, T0 + STEP)
        self.assertEqual(len(block["series"]), 1)
        row = block["series"][0]
        self.assertTrue(
            all(name in row["unknown"] for name in block["supported"]))


class ContractTest(unittest.TestCase):
    def test_supported_and_declined_lists(self) -> None:
        block = KI.compute_kline_indicators([], STEP, T0)
        self.assertEqual(
            tuple(block["supported"]),
            ("log_return_bps", "velocity_bps_5", "rel_volume_10",
             "vwap_dev_bps_10"))
        declined = {d["name"]: d["reason"] for d in block["declined"]}
        self.assertEqual(declined["flow_delta"], "AGGTRADES_SOURCE_REQUIRED")
        self.assertEqual(declined["spread_bps"], "ORDER_BOOK_SOURCE_REQUIRED")
        self.assertEqual(declined["depth"], "ORDER_BOOK_SOURCE_REQUIRED")
        self.assertEqual(declined["open_interest"], "OI_REST_POLL_REQUIRED")
        self.assertEqual(declined["btc_context"],
                         "SECOND_SYMBOL_KLINES_REQUIRED")
        self.assertTrue(block["identity"]["symbol"] == "")

    def test_definitions_carry_unit_window_and_requires(self) -> None:
        block = KI.compute_kline_indicators([], STEP, T0)
        by_name = {d["name"]: d for d in block["definitions"]}
        self.assertEqual(by_name["log_return_bps"]["unit"], "bps")
        self.assertEqual(by_name["velocity_bps_5"]["window_candles"], 5)
        self.assertEqual(by_name["rel_volume_10"]["unit"], "ratio")
        self.assertEqual(by_name["vwap_typical_10"]["window_candles"], 10)
        for d in block["definitions"]:
            self.assertIn("requires", d)
            self.assertIn("formula", d)


class SeriesPayloadIntegrationTest(unittest.TestCase):
    def test_series_payload_carries_versioned_block(self) -> None:
        import shutil as _shutil
        tmp = Path(tempfile.mkdtemp(prefix="mkt_ind_"))
        self.addCleanup(lambda: _shutil.rmtree(tmp, ignore_errors=True))
        cache = MarketCache(tmp / "cache.db")
        cache.init_db()
        bars = [_bar(T0 + i * STEP, 100.0 + i) for i in range(30)]
        cache.upsert_klines("BTCUSDT", "1h", "klines", bars, T0)
        payload = MX.series_payload(cache, None, symbol="BTCUSDT",
                                    interval="1h", from_ms=T0,
                                    to_ms=T0 + 29 * STEP,
                                    now_ms=T0 + 30 * STEP,
                                    allow_fetch=False)
        block = payload["indicators"]
        self.assertEqual(block["contract_version"],
                         "market-indicators/v1")
        self.assertEqual(block["identity"],
                         {"symbol": "BTCUSDT", "interval": "1h",
                          "interval_ms": STEP, "source": "klines"})
        # 30 velas cerradas en el payload -> 30 filas.
        self.assertEqual(len(block["series"]), 30)
        # La primera fila declara warmup, la ultima esta completa.
        self.assertEqual(block["series"][0]["unknown"]["rel_volume_10"],
                         "INSUFICIENT_CANDLES")
        last = block["series"][-1]
        for name in ("log_return_bps", "velocity_bps_5", "rel_volume_10",
                     "vwap_typical_10", "vwap_dev_bps_10"):
            self.assertNotIn(name, last["unknown"])
        del last, block

    def test_series_payload_no_zero_invented_in_unknowns(self) -> None:
        import shutil as _shutil
        tmp = Path(tempfile.mkdtemp(prefix="mkt_ind_"))
        self.addCleanup(lambda: _shutil.rmtree(tmp, ignore_errors=True))
        cache = MarketCache(tmp / "cache.db")
        cache.init_db()
        candles = [_bar(T0, 100.0), _bar(T0 + 2 * STEP, 102.0)]
        cache.upsert_klines("BTCUSDT", "1h", "klines", candles, T0)
        payload = MX.series_payload(cache, None, symbol="BTCUSDT",
                                    interval="1h", from_ms=T0,
                                    to_ms=T0 + 2 * STEP,
                                    now_ms=T0 + 3 * STEP,
                                    allow_fetch=False)
        rows = payload["indicators"]["series"]
        for row in rows:
            if "log_return_bps" in row["unknown"]:
                self.assertNotIn("log_return_bps", row["values"])
                self.assertFalse(bool(row["values"].get("log_return_bps")))


if __name__ == "__main__":
    unittest.main()
