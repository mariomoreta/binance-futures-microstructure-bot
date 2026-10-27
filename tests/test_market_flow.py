"""Pruebas focalizadas del contrato versionado ``market-flow/v1``.

Cubre: cobertura vacia antes del primer evento (sin ceros inventados),
interpretacion buyer-is-maker, delta/ratio en ventana, nota de no-senal,
wrapper de ingest y descarte de eventos tardios/invalidos.
Transporte local exclusivamente: sin conexion a Binance publico.
"""

import unittest

from microstructure_probe.flow import FlowEngine
from microstructure_probe.market_flow import (
    MARKET_FLOW_CONTRACT_VERSION,
    FLOW_AVAILABILITY,
    NO_COVERAGE_BEFORE_FIRST_EVENT,
    compute_flow_block,
    ingest_aggtrade,
)

T0 = 1_700_000_000_000


def _engine_with_trades() -> FlowEngine:
    engine = FlowEngine(symbols=("BTCUSDT",), min_baseline_buckets=5)
    # buyer_is_maker=False -> agresor BUY; True -> agresor SELL.
    engine.ingest("BTCUSDT", T0, 100.0, 1.0, False)   # buy 100
    engine.ingest("BTCUSDT", T0 + 1000, 200.0, 1.0, True, None)  # sell 200
    return engine


class FlowContractCoverageTest(unittest.TestCase):
    def test_no_events_returns_no_coverage_no_zeros(self) -> None:
        engine = FlowEngine(symbols=("BTCUSDT",), min_baseline_buckets=5)
        block = compute_flow_block(engine, "BTCUSDT", T0)
        self.assertEqual(block["contract_version"], MARKET_FLOW_CONTRACT_VERSION)
        self.assertEqual(block["availability"], FLOW_AVAILABILITY)
        self.assertEqual(block["coverage"], NO_COVERAGE_BEFORE_FIRST_EVENT)
        self.assertFalse(block["live"])
        self.assertEqual(block["trades_total"], 0)
        self.assertIsNone(block["freshness_ms"])
        # Horizons vacios (no valores inventados): delta None, no 0.
        for h in block["horizons"].values():
            self.assertIsNone(h["signed_delta"])
            self.assertIsNone(h["delta_ratio"])
            self.assertIsNone(h["buy_notional"])
            self.assertIsNone(h["sell_notional"])

    def test_events_returns_live_coverage(self) -> None:
        engine = _engine_with_trades()
        block = compute_flow_block(engine, "BTCUSDT", T0 + 1000)
        self.assertEqual(block["coverage"], "LIVE")
        self.assertTrue(block["live"])
        self.assertEqual(block["trades_total"], 2)
        self.assertIsNotNone(block["freshness_ms"])

    def test_contract_version_and_identity(self) -> None:
        engine = _engine_with_trades()
        block = compute_flow_block(engine, "BTCUSDT", T0 + 1000)
        self.assertEqual(block["contract_version"], "market-flow/v1")
        self.assertEqual(block["identity"]["symbol"], "BTCUSDT")
        self.assertEqual(block["identity"]["market_type"], "usd_m_futures")
        self.assertEqual(block["identity"]["source"], "aggTrade_local_transport")


class FlowContractAggressorSemanticsTest(unittest.TestCase):
    def test_buyer_is_maker_true_is_aggressive_sell(self) -> None:
        engine = FlowEngine(symbols=("BTCUSDT",), min_baseline_buckets=5)
        engine.ingest("BTCUSDT", T0, 100.0, 2.0, True)  # agresor SELL
        block = compute_flow_block(engine, "BTCUSDT", T0)
        h10 = block["horizons"]["10s"]
        self.assertEqual(h10["buy_notional"], 0.0)
        self.assertEqual(h10["sell_notional"], 200.0)
        self.assertEqual(h10["signed_delta"], -200.0)
        self.assertEqual(h10["delta_ratio"], -1.0)

    def test_buyer_is_maker_false_is_aggressive_buy(self) -> None:
        engine = FlowEngine(symbols=("BTCUSDT",), min_baseline_buckets=5)
        engine.ingest("BTCUSDT", T0, 100.0, 2.0, False)  # agresor BUY
        block = compute_flow_block(engine, "BTCUSDT", T0)
        h10 = block["horizons"]["10s"]
        self.assertEqual(h10["buy_notional"], 200.0)
        self.assertEqual(h10["sell_notional"], 0.0)
        self.assertEqual(h10["signed_delta"], 200.0)
        self.assertEqual(h10["delta_ratio"], 1.0)

    def test_signed_delta_and_ratio(self) -> None:
        engine = _engine_with_trades()
        block = compute_flow_block(engine, "BTCUSDT", T0 + 1000)
        h1m = block["horizons"]["1m"]
        self.assertEqual(h1m["buy_notional"], 100.0)
        self.assertEqual(h1m["sell_notional"], 200.0)
        self.assertEqual(h1m["signed_delta"], -100.0)
        self.assertAlmostEqual(h1m["delta_ratio"], -100.0 / 300.0)
        self.assertAlmostEqual(h1m["buy_pct"], 100.0 / 300.0 * 100.0)
        self.assertAlmostEqual(h1m["sell_pct"], 200.0 / 300.0 * 100.0)

    def test_delta_positive_is_not_bullish_signal(self) -> None:
        # Nota del contrato: delta positivo describe saldo de volumen
        # agresor, nunca es senal alcista automatica.
        engine = FlowEngine(symbols=("BTCUSDT",), min_baseline_buckets=5)
        engine.ingest("BTCUSDT", T0, 100.0, 1.0, False)  # agresor BUY
        block = compute_flow_block(engine, "BTCUSDT", T0)
        self.assertTrue(any("no es senal" in n or "no es señal" in n
                            for n in block["notes"]))


class FlowContractIngestTest(unittest.TestCase):
    def test_ingest_aggtrade_wrapper_accepts_valid(self) -> None:
        engine = FlowEngine(symbols=("BTCUSDT",), min_baseline_buckets=5)
        ok = ingest_aggtrade(engine, "BTCUSDT", T0, 100.0, 1.0, False)
        self.assertTrue(ok)
        self.assertEqual(engine.events_processed, 1)

    def test_ingest_aggtrade_rejects_invalid_maker(self) -> None:
        engine = FlowEngine(symbols=("BTCUSDT",), min_baseline_buckets=5)
        ok = ingest_aggtrade(engine, "BTCUSDT", T0, 100.0, 1.0, "no")  # type: ignore[arg-type]
        self.assertFalse(ok)
        self.assertEqual(engine.events_processed, 0)

    def test_ingest_aggtrade_drops_late(self) -> None:
        engine = FlowEngine(symbols=("BTCUSDT",), min_baseline_buckets=5)
        self.assertTrue(ingest_aggtrade(engine, "BTCUSDT", T0 + 2000,
                                        100.0, 1.0, False))
        ok = ingest_aggtrade(engine, "BTCUSDT", T0 + 1000,
                             100.0, 9.0, False)
        self.assertFalse(ok)
        rec = engine.snapshot_all(T0 + 2000)[0]
        self.assertEqual(rec["horizons"]["1m"]["trades"], 1)
        self.assertEqual(rec["horizons"]["1m"]["buy_notional"], 100.0)


if __name__ == "__main__":
    unittest.main()
