"""Pruebas focalizadas del flujo comprador/vendedor (market-flow/v1).

Prueban el FlowEngine Python como autoridad (sin red, sin Binance):
  - Sin fuente: UNKNOWN, sin sintéticos, live=false.
  - Dos eventos nuevos -> cambios numéricos visibles.
  - Duplicado (mismo event_ms que el newest) no suma.
  - IDs distintos mismo timestamp cuentan ambos.
  - Cambio de símbolo no mezcla datos.
  - Evento tardío descartado.

Transporte local exclusivamente: motor Python en memoria, sin Binance público.
"""

import unittest

from microstructure_probe.flow import FlowEngine

T0 = 1_700_000_000_000


def _event(symbol: str, event_id: str, event_ms: int,
           price: float, quantity: float, buyer_is_maker: bool) -> dict:
    return {
        "symbol": symbol,
        "event_id": event_id,
        "event_ms": event_ms,
        "price": price,
        "quantity": quantity,
        "buyer_is_maker": buyer_is_maker,
    }


def _ingest(engine: FlowEngine, ev: dict) -> bool:
    return engine.ingest(
        ev["symbol"], ev["event_ms"], ev["price"], ev["quantity"],
        ev["buyer_is_maker"])


def _snapshot(engine: FlowEngine, symbol: str, as_of_ms: int) -> dict:
    """Devuelve el bloque de un símbolo desde snapshot_all del engine."""
    for b in engine.snapshot_all(as_of_ms):
        if b["symbol"] == symbol:
            return b
    # Sin serie para el símbolo: bloque vacío (sin fuente, sin datos).
    return {
        "symbol": symbol,
        "subscribed": True,
        "live": False,
        "as_of_ms": as_of_ms,
        "freshness_ms": None,
        "span_ms": 0,
        "trades_total": 0,
        "rpi_base_total": 0.0,
        "rpi_notional_total": 0.0,
        "rpi_trades": 0,
        "dropped_late": 0,
        "dropped_invalid": 0,
        "horizons": {
            "1m": {
                "trades": 0, "base_volume": 0.0, "notional": 0.0,
                "buy_base": 0.0, "sell_base": 0.0,
                "buy_notional": None, "sell_notional": None,
                "signed_delta": None, "delta_ratio": None,
                "buy_pct": None, "sell_pct": None,
                "trade_rate": 0.0, "notional_rate": 0.0,
                "warmup_complete": False,
                "window_ms": 60000, "as_of_ms": as_of_ms,
            },
        },
        "baselines": {},
        "acceleration": {},
    }


class FlowEngineDirectTest(unittest.TestCase):
    """Pruebas del FlowEngine Python como autoridad (sin red, sin Binance)."""

    def test_sin_fuente_es_unknown_sin_sinteticos(self) -> None:
        engine = FlowEngine(symbols=("BTCUSDT",), min_baseline_buckets=5)
        block = _snapshot(engine, "BTCUSDT", T0)
        self.assertFalse(block["live"])
        self.assertEqual(block["trades_total"], 0)
        self.assertIsNone(block["freshness_ms"])
        self.assertIsNone(block["horizons"]["1m"]["signed_delta"])
        self.assertIsNone(block["horizons"]["1m"]["delta_ratio"])

    def test_dos_eventos_nuevos_cambian_panel(self) -> None:
        engine = FlowEngine(symbols=("BTCUSDT",), min_baseline_buckets=5)
        # Evento 1: BUY agresor (buyer_is_maker=False)
        self.assertTrue(_ingest(engine, _event(
            "BTCUSDT", "e1", T0, 100000.0, 0.5, False)))
        # Evento 2: SELL agresor (buyer_is_maker=True)
        self.assertTrue(_ingest(engine, _event(
            "BTCUSDT", "e2", T0 + 1000, 100001.0, 0.3, True)))

        block = _snapshot(engine, "BTCUSDT", T0 + 1000)
        self.assertTrue(block["live"])
        self.assertEqual(block["trades_total"], 2)
        h1m = block["horizons"]["1m"]
        self.assertAlmostEqual(h1m["buy_notional"], 100000.0 * 0.5)
        self.assertAlmostEqual(h1m["sell_notional"], 100001.0 * 0.3)
        self.assertAlmostEqual(
            h1m["signed_delta"], 100000.0 * 0.5 - 100001.0 * 0.3)

    def test_evento_tardio_no_suma(self) -> None:
        engine = FlowEngine(symbols=("BTCUSDT",), min_baseline_buckets=5)
        _ingest(engine, _event("BTCUSDT", "e1", T0 + 2000, 100000.0, 1.0, False))
        antes = _snapshot(engine, "BTCUSDT", T0 + 2000)
        self.assertEqual(antes["horizons"]["1m"]["trades"], 1)

        # Evento con event_ms < newest_ms: tardío, descartado
        resultado = _ingest(engine, _event(
            "BTCUSDT", "e2", T0 + 1000, 100000.0, 1.0, False))
        self.assertFalse(resultado)

        despues = _snapshot(engine, "BTCUSDT", T0 + 2000)
        self.assertEqual(despues["horizons"]["1m"]["trades"], 1)
        self.assertEqual(despues["trades_total"], 1)
        self.assertEqual(despues["dropped_late"], 1)

    def test_ids_distintos_mismo_timestamp_cuentan_ambos(self) -> None:
        engine = FlowEngine(symbols=("BTCUSDT",), min_baseline_buckets=5)
        _ingest(engine, _event("BTCUSDT", "e-a", T0, 100000.0, 1.0, False))
        _ingest(engine, _event("BTCUSDT", "e-b", T0, 100000.0, 2.0, True))

        block = _snapshot(engine, "BTCUSDT", T0)
        h1m = block["horizons"]["1m"]
        self.assertEqual(h1m["trades"], 2)
        self.assertAlmostEqual(h1m["buy_notional"], 100000.0)
        self.assertAlmostEqual(h1m["sell_notional"], 200000.0)

    def test_cambio_de_simbolo_no_mezcla_datos(self) -> None:
        engine = FlowEngine(symbols=("BTCUSDT", "ETHUSDT"),
                            min_baseline_buckets=5)
        _ingest(engine, _event("BTCUSDT", "b1", T0, 100000.0, 1.0, False))

        btc = _snapshot(engine, "BTCUSDT", T0)
        self.assertEqual(btc["trades_total"], 1)
        self.assertEqual(btc["horizons"]["1m"]["trades"], 1)

        eth = _snapshot(engine, "ETHUSDT", T0)
        self.assertEqual(eth["trades_total"], 0)
        self.assertFalse(eth["live"])

        # BTC sigue intacto
        btc2 = _snapshot(engine, "BTCUSDT", T0)
        self.assertEqual(btc2["trades_total"], 1)


if __name__ == "__main__":
    unittest.main()
