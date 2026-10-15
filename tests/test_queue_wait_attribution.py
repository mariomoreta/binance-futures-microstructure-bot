"""Lag attribution: iteration stamps split received-E into dispatch + yield.

2026-10-15 (pilot probe-20261015T000730Z post-mortem) + 2026-10-16 review
correction: the stamps run AFTER `async for` yields, so they do NOT
measure socket arrival or pre-yield library/TCP wait. Honest names:

- dispatchDelayMs = loop-iteration -> handler entry (local dispatch ONLY);
- yieldLagMs = exchange event -> loop iteration (exchange + network +
  TCP + library queue COMBINED; never isolated network latency).

Proven on TEMP stores exclusively (RealReceivePathTest drives the real
_connection_loop with a fake websocket and controlled pre-yield
delays). The skew threshold is untouched. No live traffic.
Run: python run_tests.py
"""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_detectors import test_config
from test_probe import make_isolated_probe


def _agg(symbol="BTCUSDT", event_ms=99000, txn_ms=98900):
    return {"stream": "btcusdt@aggTrade",
            "data": {"E": event_ms, "T": txn_ms, "s": symbol,
                     "p": "100", "q": "1"}}


def _probe(case, **kwargs):
    return make_isolated_probe(
        case, test_config(), clock_sync=None,
        wall_clock_ms=lambda: 100000.0, monotonic=lambda: 100.0,
        perf_counter_ns=lambda: 5_000_000_000, **kwargs)


class DispatchYieldAttributionTest(unittest.TestCase):
    def test_decomposition_identity_on_fixture(self) -> None:
        probe = _probe(self)
        probe._handle_message(
            json.dumps(_agg()), iter_ms=99750.0,
            iter_mono_ns=4_750_000_000)
        latency = probe.build_summary(final=True)["latency"]
        key = "aggTrade/BTCUSDT"
        raw = latency["rawEventLagMs"][key]["p50"]
        dispatch = latency["dispatchDelayMs"][key]["p50"]
        yield_lag = latency["yieldLagMs"][key]["p50"]
        self.assertEqual(raw, 1000.0)
        self.assertEqual(dispatch, 250.0)
        self.assertEqual(yield_lag, 750.0)
        self.assertAlmostEqual(dispatch + yield_lag, raw)
        # Exchange-side component untouched by local dispatch.
        self.assertEqual(
            latency["exchangeEventMinusTransactionMs"][key]["p50"], 100.0)

    def test_unknown_iteration_never_recorded_as_zero(self) -> None:
        probe = _probe(self)
        probe._handle_message(json.dumps(_agg()))
        latency = probe.build_summary(final=True)["latency"]
        key = "aggTrade/BTCUSDT"
        self.assertEqual(latency["rawEventLagMs"][key]["p50"], 1000.0)
        self.assertNotIn("dispatchDelayMs", latency)
        self.assertNotIn("yieldLagMs", latency)

    def test_rejected_message_keeps_attribution_and_counts(self) -> None:
        probe = _probe(self)
        old = _agg(event_ms=90000, txn_ms=89900)
        probe._handle_message(
            json.dumps(old), iter_ms=99750.0,
            iter_mono_ns=4_750_000_000)
        self.assertEqual(probe.stats.discarded_clock_skew, 1)
        self.assertEqual(probe.stats.rejected_timestamp, 1)
        latency = probe.build_summary(final=True)["latency"]
        key = "aggTrade/BTCUSDT"
        # 10000 = 250 dispatch + 9750 yield: dominated by everything
        # upstream of the iteration here, measured — not assumed.
        self.assertEqual(latency["rawEventLagMs"][key]["p50"], 10000.0)
        self.assertEqual(latency["dispatchDelayMs"][key]["p50"], 250.0)
        self.assertEqual(latency["yieldLagMs"][key]["p50"], 9750.0)

    def test_skew_threshold_untouched(self) -> None:
        probe = _probe(self)
        self.assertEqual(probe.config.max_event_clock_skew_ms, 5000)
        probe._handle_message(json.dumps(_agg(event_ms=95000)))
        self.assertEqual(probe.stats.rejected_timestamp, 0)
        probe._handle_message(json.dumps(_agg(event_ms=94999)))
        self.assertEqual(probe.stats.rejected_timestamp, 1)

    def test_markprice_array_records_per_symbol_attribution(self) -> None:
        probe = _probe(self)
        payload = {"stream": "!markPrice@arr@1s", "data": [
            {"s": "BTCUSDT", "E": 99000}]}
        probe._handle_message(
            json.dumps(payload), iter_ms=99750.0,
            iter_mono_ns=4_750_000_000)
        latency = probe.build_summary(final=True)["latency"]
        key = "markPrice/BTCUSDT"
        self.assertEqual(latency["dispatchDelayMs"][key]["p50"], 250.0)
        self.assertEqual(latency["yieldLagMs"][key]["p50"], 750.0)


class _FakeWebSocket:
    """Async-CM fake mirroring websockets.connect yield semantics."""

    def __init__(self, raws, pre_yield_delay=0.0, on_exhausted=None):
        self._raws = list(raws)
        self._delay = pre_yield_delay
        self._n = 0
        self._on_exhausted = on_exhausted

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._raws:
            # End the connection loop cleanly instead of reconnect-spinning
            # (a real server close is not an instant-reconnect storm here).
            if self._on_exhausted is not None:
                self._on_exhausted()
            raise StopAsyncIteration
        self._n += 1
        if self._n == 2 and self._delay:
            # Controlled upstream-of-iteration delay (stands in for
            # network/TCP/library wait: indistinguishable at this layer
            # by construction, must land in yieldLagMs, never dispatch).
            await asyncio.sleep(self._delay)
        return self._raws.pop(0)


class RealReceivePathTest(unittest.TestCase):
    def _run_loop(self, raws, pre_yield_delay=0.0):
        tmp = tempfile.mkdtemp(prefix="realpath_")
        self.addCleanup(lambda: _rmtree(Path(tmp)))
        os.environ["MICROPROBE_RUNTIME_FILE"] = str(
            Path(tmp) / "probe_runtime.json")
        self.addCleanup(os.environ.pop, "MICROPROBE_RUNTIME_FILE", None)
        probe = make_isolated_probe(self, test_config())

        async def drive():
            ws = _FakeWebSocket(raws, pre_yield_delay,
                                on_exhausted=probe._stop.set)
            with mock.patch(
                    "microstructure_probe.probe.websockets.connect",
                    return_value=ws):
                await asyncio.wait_for(
                    probe._connection_loop("market", "ws://fake"),
                    timeout=30)
        asyncio.run(drive())
        return probe

    def test_controlled_preyield_delay_lands_in_yield_not_dispatch(
            self) -> None:
        import time
        now = int(time.time() * 1000)
        raws = [json.dumps(_agg(event_ms=now - 60, txn_ms=now - 61))
                for _ in range(3)]
        probe = self._run_loop(raws, pre_yield_delay=0.3)
        latency = probe.build_summary(final=True)["latency"]
        key = "aggTrade/BTCUSDT"
        self.assertEqual(
            probe.stats.messages_by_stream.get("btcusdt@aggTrade", 0), 3)
        dispatch = latency["dispatchDelayMs"][key]
        yield_lag = latency["yieldLagMs"][key]
        # The 300ms controlled delay sits upstream of the iteration:
        # visible in yieldLagMs (max), fresh messages stay fresh (min),
        # local dispatch stays sub-ms typical (p50). A single dispatch
        # sample may inflate under OS preemption, so no absolute max cap:
        # exactness is proven deterministically by the fixture tests.
        self.assertLess(dispatch["p50"], 50.0)
        self.assertGreaterEqual(yield_lag["max"], 250.0)
        # The controlled 300ms pre-yield delay must separate the delayed
        # message from the immediate ones (setup latency ages every E
        # equally, so absolute freshness is not asserted here).
        self.assertGreaterEqual(
            yield_lag["max"] - yield_lag["min"], 200.0)
        self.assertAlmostEqual(
            latency["rawEventLagMs"][key]["mean"],
            dispatch["mean"] + yield_lag["mean"], delta=5.0)
        self.assertEqual(probe.stats.rejected_timestamp, 0)


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


if __name__ == "__main__":
    unittest.main()
