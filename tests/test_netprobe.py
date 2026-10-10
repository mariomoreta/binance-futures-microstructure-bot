"""P1-14B.5 independent diagnostic probe — deterministic tests.

All network interaction is faked (scripted messages, failing connects,
controlled clocks). No live Binance dependency. Run: python run_tests.py
"""

from __future__ import annotations

import asyncio
import json
import socket
import tempfile
from pathlib import Path
from unittest import TestCase

from src.microstructure_probe.netprobe import (
    ALLOWED_HOST,
    ReferenceTracker,
    classify_connect_error,
    resolve_out_path,
    run_reference,
    stream_event_time,
    validate_target,
)


def _btc_ticker(e_ms, price="100.0"):
    return json.dumps({"stream": "btcusdt@bookTicker",
                       "data": {"E": e_ms, "s": "BTCUSDT", "b": price,
                                "a": "100.01", "u": 1}})


def _mark_array(e_ms):
    return json.dumps({"stream": "!markPrice@arr@1s",
                       "data": [{"s": "BTCUSDT", "E": e_ms, "p": "100.0"},
                                {"s": "ETHUSDT", "E": e_ms, "p": "200.0"}]})


class FakeClock:
    def __init__(self, wall_ms=1_800_000_000_000.0, mono_s=1000.0):
        self.wall = wall_ms
        self.mono = mono_s

    def wall_ms(self):
        return float(self.wall)

    def mono_s(self):
        return float(self.mono)


class FakeClosed(Exception):
    pass


class FakeWS:
    """Async-iterator websocket fake over scripted raws then a terminal error."""

    def __init__(self, raws, clock, step_ms=100.0, terminal=None):
        self._raws = list(raws)
        self._clock = clock
        self._step = step_ms
        self._terminal = terminal if terminal is not None else FakeClosed("closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._raws:
            raise self._terminal
        self._clock.wall += self._step
        self._clock.mono += self._step / 1000.0
        return self._raws.pop(0)


def _connect_script(script, clock, seen):
    """Build a connect fake mirroring websockets.connect: a plain callable
    returning an async context manager (NOT a coroutine)."""
    def fake_connect(*args, **kwargs):
        seen.append(kwargs)
        item = script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item
    return fake_connect


def _sleep_recorder(clock, calls):
    async def fake_sleep(seconds):
        calls.append(seconds)
        clock.mono += seconds
        clock.wall += seconds * 1000.0
    return fake_sleep


# ------------------------------------------------------------------
# Target validation + error classification + event-time extraction
# ------------------------------------------------------------------

class TestTargetValidation(TestCase):
    def test_defaults_accepted(self):
        streams = validate_target(ALLOWED_HOST, ["btcusdt@bookTicker"])
        self.assertEqual(streams, ["btcusdt@bookTicker"])

    def test_foreign_host_refused(self):
        with self.assertRaises(ValueError):
            validate_target("wss://evil.example.com/stream", ["btcusdt@bookTicker"])

    def test_private_streams_refused(self):
        for bad in ("listenKeyABC", "abc@userData", "ACCOUNT_UPDATE"):
            with self.assertRaises(ValueError, msg=bad):
                validate_target(ALLOWED_HOST, [bad])

    def test_empty_and_duplicates_refused(self):
        with self.assertRaises(ValueError):
            validate_target(ALLOWED_HOST, [])
        with self.assertRaises(ValueError):
            validate_target(ALLOWED_HOST, ["a@b", "a@b"])


class TestErrorClassification(TestCase):
    def test_classes(self):
        self.assertEqual(classify_connect_error(socket.gaierror("x")), "dns-error")
        self.assertEqual(classify_connect_error(ConnectionRefusedError()), "tcp-refused")
        self.assertEqual(classify_connect_error(TimeoutError()), "handshake-timeout")
        self.assertTrue(classify_connect_error(FakeClosed("c")).startswith("other:"))
        class FakeConnectionClosed(Exception):
            pass
        self.assertTrue(classify_connect_error(
            FakeConnectionClosed("c")).startswith("ws-closed:"))


class TestEventTimeExtraction(TestCase):
    def test_dict(self):
        self.assertEqual(stream_event_time("btcusdt@bookTicker", {"E": 123}), 123.0)

    def test_array_max(self):
        self.assertEqual(stream_event_time("!markPrice@arr@1s",
                                           [{"E": 5}, {"E": 9}]), 9.0)

    def test_missing_and_malformed(self):
        self.assertIsNone(stream_event_time("s", {}))
        self.assertIsNone(stream_event_time("s", {"E": "abc"}))
        self.assertIsNone(stream_event_time("s", None))


# ------------------------------------------------------------------
# Tracker
# ------------------------------------------------------------------

class TestTracker(TestCase):
    def test_fresh_flow(self):
        clock = FakeClock()
        tr = ReferenceTracker(wall_clock_ms=clock.wall_ms, monotonic=clock.mono_s)
        for i in range(5):
            row = tr.observe("btcusdt@bookTicker", clock.wall - 200.0)
            clock.wall += 100.0
            clock.mono += 0.1
        summ = tr.summary()["btcusdt@bookTicker"]
        self.assertEqual(summ["messages"], 5)
        self.assertEqual(summ["eReorders"], 0)
        self.assertLess(summ["lagMs"]["p50"], 1000.0)

    def test_stale_flow_and_reorder(self):
        clock = FakeClock()
        tr = ReferenceTracker(wall_clock_ms=clock.wall_ms, monotonic=clock.mono_s)
        tr.observe("s", clock.wall - 300_000.0)
        tr.observe("s", clock.wall - 400_000.0)  # older E -> reorder
        summ = tr.summary()["s"]
        self.assertGreater(summ["lagMs"]["max"], 200_000.0)
        self.assertEqual(summ["eReorders"], 1)

    def test_missing_event_time(self):
        clock = FakeClock()
        tr = ReferenceTracker(wall_clock_ms=clock.wall_ms, monotonic=clock.mono_s)
        row = tr.observe("s", None)
        self.assertIsNone(row["lag_ms"])
        self.assertEqual(tr.summary()["s"]["messages"], 1)


# ------------------------------------------------------------------
# run_reference with fakes (no network)
# ------------------------------------------------------------------

class TestRunReference(TestCase):
    def _out(self):
        tmp = Path(tempfile.mkdtemp())
        return tmp / "np.jsonl"

    def test_fresh_capture(self):
        clock = FakeClock()
        # Enough scripted messages to reach the 5 s deadline (0.1 s each):
        # clean duration-reached exit, no reconnect.
        raws = [_btc_ticker(clock.wall - 150.0 + i * 100.0) for i in range(60)]
        seen = []
        final = asyncio.run(run_reference(
            ["btcusdt@bookTicker"], 5.0, self._out(),
            connect=_connect_script([FakeWS(raws, clock)], clock, seen),
            wall_clock_ms=clock.wall_ms, monotonic=clock.mono_s,
            sleep=_sleep_recorder(clock, [])))
        self.assertEqual(final["attempts"], 1)
        self.assertEqual(final["successes"], 1)
        self.assertEqual(final["errors"], {})
        self.assertGreaterEqual(
            final["streams"]["btcusdt@bookTicker"]["messages"], 50)

    def test_stale_capture_recorded_not_hidden(self):
        clock = FakeClock()
        raws = [_btc_ticker(clock.wall - 200_000.0) for _ in range(60)]
        final = asyncio.run(run_reference(
            ["btcusdt@bookTicker"], 5.0, self._out(),
            connect=_connect_script([FakeWS(raws, clock)], clock, []),
            wall_clock_ms=clock.wall_ms, monotonic=clock.mono_s,
            sleep=_sleep_recorder(clock, [])))
        lag = final["streams"]["btcusdt@bookTicker"]["lagMs"]
        self.assertGreater(lag["max"], 100_000.0)

    def test_handshake_failures_classified_and_bounded(self):
        clock = FakeClock()
        raws = [_btc_ticker(clock.wall - 100.0) for _ in range(400)]
        sleeps = []
        final = asyncio.run(run_reference(
            ["btcusdt@bookTicker"], 30.0, self._out(),
            connect=_connect_script(
                [TimeoutError(), TimeoutError(), FakeWS(raws, clock)],
                clock, []),
            wall_clock_ms=clock.wall_ms, monotonic=clock.mono_s,
            sleep=_sleep_recorder(clock, sleeps)))
        self.assertEqual(final["errors"], {"handshake-timeout": 2})
        self.assertEqual(final["successes"], 1)
        self.assertEqual(sleeps[:2], [1.0, 2.0])
        self.assertTrue(all(s <= 30.0 for s in sleeps))

    def test_silent_connection_tracked(self):
        # A truly silent connection yields NO stream rows (honest absence,
        # never zero-filled); attempts/errors still prove it was watched.
        clock = FakeClock()
        final = asyncio.run(run_reference(
            ["btcusdt@bookTicker"], 3.0, self._out(),
            connect=_connect_script([FakeWS([], clock)], clock, []),
            wall_clock_ms=clock.wall_ms, monotonic=clock.mono_s,
            sleep=_sleep_recorder(clock, [])))
        self.assertGreaterEqual(final["attempts"], 1)
        self.assertEqual(final["streams"], {})

    def test_markprice_array_stream(self):
        clock = FakeClock()
        raws = [_mark_array(clock.wall - 300.0)]
        final = asyncio.run(run_reference(
            ["!markPrice@arr@1s"], 3.0, self._out(),
            connect=_connect_script([FakeWS(raws, clock)], clock, []),
            wall_clock_ms=clock.wall_ms, monotonic=clock.mono_s,
            sleep=_sleep_recorder(clock, [])))
        self.assertEqual(final["streams"]["!markPrice@arr@1s"]["messages"], 1)


class TestOutPath(TestCase):
    def test_never_overwrites(self):
        tmp = Path(tempfile.mkdtemp())
        first = tmp / "np.jsonl"
        first.write_text("evidence", encoding="utf-8")
        second = resolve_out_path(str(first), "tag")
        self.assertNotEqual(second, first)
        self.assertTrue(str(second).endswith(".jsonl"))
        self.assertEqual(first.read_text(encoding="utf-8"), "evidence")
