"""Contexto BTC compartido market-btc-context/v1: causalidad y reglas duras.

Lo que se pinza aqui:
  * formulas exactas hand-calculated (ret_btc sobre la MISMA rejilla);
  * alineacion POR TIEMPO: reordenar los arreglos no cambia ningun valor;
  * sin lookahead: perturbar velas del futuro no cambia la fila t;
  * huecos/falta de BTC/retardo → UNKNOWN con motivo BTC_*, nunca cero ni
    arrastre silencioso de valores viejos;
  * token==BTC → sin bloque (no hay comparacion consigo mismo);
  * base comun declarada para la comparacion normalizada (calculada aqui, no
    en el navegador); los huecos cortan la serie, no se interpolan;
  * integracion series_payload: campo aditivo `context_btc` con client=None
    (0 upstream REST) y sin bloque cuando el token es BTC.
"""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from microstructure_probe import kline_btc_context as BC  # noqa: E402
from microstructure_probe import kline_indicators as KI  # noqa: E402
from microstructure_probe import market_explorer as MX  # noqa: E402
from microstructure_probe.market_cache import MarketCache  # noqa: E402

STEP = 3_600_000  # 1h
T0 = (1_700_000_000_000 // STEP) * STEP  # alineado a la rejilla


def _bar(open_time: int, close: float) -> dict:
    return {
        "open_time": open_time,
        "open": str(close - 0.5),
        "high": str(close + 0.5),
        "low": str(close - 0.6),
        "close": str(close),
        "base_volume": "10.0",
        "quote_volume": "1000.0",
        "trade_count": 50,
        "close_time": open_time + STEP - 1,
    }


def _row(block: dict, open_time: int) -> dict:
    for row in block["series"]:
        if row["open_time_ms"] == open_time:
            return row
    raise AssertionError(f"no row for {open_time}")


def _token_indicators(token_bars: list) -> list:
    return KI.compute_kline_indicators(
        token_bars, STEP, T0 + 7 * STEP, "MINAUSDT", "1h", "klines")["series"]


class FormulaTest(unittest.TestCase):
    def test_ret_btc_exact_over_common_grid(self) -> None:
        token = [_bar(T0 + i * STEP, 1.0 + 0.01 * i) for i in range(6)]
        btc = [_bar(T0 + i * STEP, 50 * (1.02 ** i)) for i in range(6)]
        block = BC.compute_btc_context(
            token, btc, STEP, T0 + 6 * STEP, "MINAUSDT", "1h", "klines",
            token_indicators=_token_indicators(token))
        row = _row(block, T0 + 5 * STEP)
        expected = 10000.0 * math.log((50 * 1.02 ** 5) / (50 * 1.02 ** 1))
        self.assertAlmostEqual(
            row["values"]["ret_btc_bps_5"], expected, places=4)
        token_velocity = _row({"series": _token_indicators(token)},
                              T0 + 5 * STEP)["values"]["velocity_bps_5"]
        self.assertAlmostEqual(
            row["values"]["ret_diff_bps_5"], token_velocity - expected,
            places=4)

    def test_alignment_by_time_not_by_position(self) -> None:
        token = [_bar(T0 + i * STEP, 1.0 + 0.01 * i) for i in range(6)]
        btc = [_bar(T0 + i * STEP, 50 * (1.02 ** i)) for i in range(6)]
        straight = BC.compute_btc_context(
            token, btc, STEP, T0 + 6 * STEP, "MINAUSDT", "1h", "klines")
        shuffled = BC.compute_btc_context(
            list(reversed(token)), list(reversed(btc)), STEP,
            T0 + 6 * STEP, "MINAUSDT", "1h", "klines")
        self.assertEqual(straight["series"], shuffled["series"])

    def test_no_lookahead_future_bars_do_not_change_history(self) -> None:
        token = [_bar(T0 + i * STEP, 1.0 + 0.01 * i) for i in range(6)]
        btc = [_bar(T0 + i * STEP, 50 * (1.02 ** i)) for i in range(6)]
        block_base = BC.compute_btc_context(
            token, btc, STEP, T0 + 6 * STEP, "MINAUSDT", "1h", "klines",
            token_indicators=_token_indicators(token))
        # Perturbar el futuro de BTC y del token: velas posteriores al NOW
        # no estan cerradas y no entran en ninguna fila.
        future = list(btc) + [_bar(T0 + 9 * STEP, 1234.0)]
        token_future = list(token) + [_bar(T0 + 9 * STEP, 9.0)]
        block_after = BC.compute_btc_context(
            token_future, future, STEP, T0 + 6 * STEP, "MINAUSDT", "1h",
            "klines", token_indicators=_token_indicators(token))
        for open_time in (T0 + 4 * STEP, T0 + 5 * STEP):
            self.assertEqual(_row(block_base, open_time),
                             _row(block_after, open_time))


class UnknownReasonTest(unittest.TestCase):
    def test_no_btc_at_all_is_unknown_not_zero(self) -> None:
        token = [_bar(T0 + i * STEP, 1.0 + 0.01 * i) for i in range(6)]
        block = BC.compute_btc_context(
            token, [], STEP, T0 + 6 * STEP, "MINAUSDT", "1h", "klines",
            token_indicators=_token_indicators(token))
        for row in block["series"]:
            self.assertEqual(row["unknown"]["ret_btc_bps_5"], "BTC_MISSING")
            self.assertNotIn("ret_diff_bps_5", row["values"])
        self.assertEqual(block["normalized"], None)

    def test_btc_gap_inside_window(self) -> None:
        token = [_bar(T0 + i * STEP, 1.0 + 0.01 * i) for i in range(6)]
        btc = [_bar(T0 + i * STEP, 50 + i) for i in (0, 1, 2, 3, 5)]
        block = BC.compute_btc_context(
            token, btc, STEP, T0 + 6 * STEP, "MINAUSDT", "1h", "klines")
        row = _row(block, T0 + 5 * STEP)
        self.assertEqual(row["unknown"]["ret_btc_bps_5"], "BTC_GAP_IN_WINDOW")
        gaps = block["context"]["timeframe"]["gaps"]
        self.assertEqual(gaps, [[T0 + 4 * STEP, T0 + 4 * STEP]])

    def test_btc_lagging_row_not_dragged(self) -> None:
        token = [_bar(T0 + i * STEP, 1.0 + 0.01 * i) for i in range(6)]
        # BTC conocido SOLO hasta t+3: las filas t+4/t+5 quedan BTC_LAGGING.
        btc = [_bar(T0 + i * STEP, 50 + i) for i in range(4)]
        block = BC.compute_btc_context(
            token, btc, STEP, T0 + 6 * STEP, "MINAUSDT", "1h", "klines")
        self.assertEqual(_row(block, T0 + 3 * STEP)["unknown"]["ret_btc_bps_5"],
                         "BTC_INSUFICIENT_CANDLES")
        self.assertEqual(_row(block, T0 + 4 * STEP)["unknown"]["ret_btc_bps_5"],
                         "BTC_LAGGING")
        self.assertEqual(_row(block, T0 + 5 * STEP)["unknown"]["ret_btc_bps_5"],
                         "BTC_LAGGING")
        self.assertTrue(block["context"]["freshness"]["lagging"])

    def test_token_unknown_takes_precedence_in_diff(self) -> None:
        token = [_bar(T0 + i * STEP, 1.0 + 0.01 * i) for i in (0, 1, 3, 4, 5)]
        btc = [_bar(T0 + i * STEP, 50 + i) for i in range(6)]
        block = BC.compute_btc_context(
            token, btc, STEP, T0 + 6 * STEP, "MINAUSDT", "1h", "klines",
            token_indicators=_token_indicators(token))
        row = _row(block, T0 + 5 * STEP)
        self.assertEqual(row["unknown"]["ret_diff_bps_5"], "GAP_IN_WINDOW")

    def test_invalid_btc_price_is_unknown(self) -> None:
        token = [_bar(T0 + i * STEP, 1.0 + 0.01 * i) for i in range(6)]
        btc = [_bar(T0 + i * STEP, 50 + i) for i in range(5)] + \
            [_bar(T0 + 5 * STEP, -1.0)]
        block = BC.compute_btc_context(
            token, btc, STEP, T0 + 6 * STEP, "MINAUSDT", "1h", "klines")
        self.assertEqual(_row(block, T0 + 5 * STEP)["unknown"].get(
            "ret_btc_bps_5"), "INVALID_PRICE")


class BlockShapeTest(unittest.TestCase):
    def test_same_symbol_emits_nothing(self) -> None:
        bars = [_bar(T0 + i * STEP, 100.0 + i) for i in range(6)]
        self.assertIsNone(BC.compute_btc_context(
            bars, bars, STEP, T0 + 6 * STEP, "BTCUSDT", "1h", "klines"))

    def test_identity_and_header(self) -> None:
        token = [_bar(T0 + i * STEP, 1.0 + 0.01 * i) for i in range(6)]
        btc = [_bar(T0 + i * STEP, 50 + i) for i in range(6)]
        block = BC.compute_btc_context(
            token, btc, STEP, T0 + 6 * STEP, "MINAUSDT", "1h", "klines",
            btc_sources=["cache", "ws_kline"],
            btc_subscription={"shared": True, "live": True},
            rest_upstream_requests=0)
        self.assertEqual(block["contract_version"], "market-btc-context/v1")
        self.assertEqual(block["identity"]["symbol"], "MINAUSDT")
        self.assertEqual(block["context"]["symbol"], "BTCUSDT")
        self.assertEqual(block["context"]["sources"], ["cache", "ws_kline"])
        self.assertTrue(block["context"]["subscription"]["shared"])
        self.assertEqual(
            block["context"]["acquisition"]["rest_upstream_requests"], 0)
        self.assertEqual(block["context"]["horizon_candles"], 5)
        self.assertEqual(
            block["context"]["timeframe"]["present_grid"],
            len([r for r in block["series"]
                 if "ret_btc_bps_5" in r["values"]]))

    def test_normalized_base_is_common_and_no_interpolation(self) -> None:
        token = [_bar(T0 + i * STEP, 1.0 + 0.01 * i) for i in range(6)]
        btc = [_bar(T0 + i * STEP, 50 + i) for i in (0, 1, 2, 3, 5)]
        block = BC.compute_btc_context(
            token, btc, STEP, T0 + 6 * STEP, "MINAUSDT", "1h", "klines")
        normalized = block["normalized"]
        self.assertEqual(normalized["base_open_time_ms"], T0)
        times = [p["open_time_ms"] for p in normalized["series"]]
        self.assertNotIn(T0 + 4 * STEP, times)  # hueco BTC: fila omitida
        self.assertAlmostEqual(normalized["series"][0]["btc_pct"], 0.0)
        expected = 100.0 * ((50 + 5) / 50.0 - 1.0)
        self.assertAlmostEqual(
            normalized["series"][-1]["btc_pct"], expected, places=4)


class SeriesPayloadIntegrationTest(unittest.TestCase):
    def test_payload_includes_context_from_cache_without_upstream(self) -> None:
        cache = MarketCache(temp_dir() / "btc_ctx.db")
        cache.init_db()
        now = T0 + 7 * STEP
        token_bars = [_bar_publish(cache, "SOLUSDT", T0 + i * STEP, 1 + 0.01 * i)
                      for i in range(6)]
        _ = token_bars
        for i in range(6):
            _bar_publish(cache, "BTCUSDT", T0 + i * STEP, 50 + i)
        payload = MX.series_payload(cache, None, "SOLUSDT", "1h",
                                    from_ms=T0 - STEP, to_ms=T0 + 6 * STEP,
                                    allow_fetch=False, bars=10, now_ms=now)
        block = payload["context_btc"]
        self.assertIsNotNone(block)
        self.assertEqual(block["contract_version"], "market-btc-context/v1")
        self.assertEqual(block["identity"]["symbol"], "SOLUSDT")
        self.assertEqual(block["context"]["sources"], ["cache"])
        self.assertEqual(block["context"]["acquisition"]["mode"], "cache")
        row = _row(block, T0 + 5 * STEP)
        self.assertIn("ret_btc_bps_5", row["values"])
        self.assertNotIn("ret_btc_bps_5", row["unknown"])

    def test_payload_omits_context_for_btc_token(self) -> None:
        cache = MarketCache(temp_dir() / "btc_ctx_btc.db")
        cache.init_db()
        for i in range(6):
            _bar_publish(cache, "BTCUSDT", T0 + i * STEP, 50 + i)
        payload = MX.series_payload(cache, None, "BTCUSDT", "1h",
                                    from_ms=T0, to_ms=T0 + 5 * STEP,
                                    allow_fetch=False, bars=10,
                                    now_ms=T0 + 7 * STEP)
        self.assertIsNone(payload["context_btc"])


def _bar_publish(cache: MarketCache, symbol: str, open_time: int,
                 close: float) -> dict:
    bar = {
        "open_time": open_time,
        "open": str(close - 0.5),
        "high": str(close + 0.5),
        "low": str(close - 0.6),
        "close": str(close),
        "base_volume": "10.0",
        "quote_volume": "1000.0",
        "trade_count": 50,
        "close_time": open_time + STEP - 1,
        "fetched_at": open_time,
    }
    cache.upsert_klines(symbol, "1h", "klines", [bar], open_time)
    return bar


def temp_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="test-btc-context-"))


if __name__ == "__main__":
    unittest.main()
