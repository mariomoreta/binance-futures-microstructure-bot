from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter, defaultdict
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Callable

import websockets

from .clock import ClockSynchronizer, corrected_lag_ms
from .config import ProbeConfig
from .detectors import EventDetectors
from .metrics import order_book_imbalance, spread_bps
from .persistence import PersistenceStore, get_persistence_store
from .returns import ReturnEngine, SymbolPriceSeries
from .telemetry import RunningDistribution
from .universe import SymbolUniverse
from .persistence import PersistenceStore, get_persistence_store

LOGGER = logging.getLogger("microstructure_probe")
BASE_URL = "wss://fstream.binance.com"


def expected_stream_names(config: ProbeConfig) -> tuple[str, ...]:
    symbols = [symbol.lower() for symbol in config.symbols]
    return tuple(
        ["!forceOrder@arr", "!markPrice@arr@1s"]
        + [f"{symbol}@aggTrade" for symbol in symbols]
        + [f"{symbol}@bookTicker" for symbol in symbols]
        + [f"{symbol}@depth20@100ms" for symbol in symbols]
    )


@dataclass
class RuntimeStats:
    started_monotonic: float
    messages_by_stream: Counter[str] = field(default_factory=Counter)
    events_by_type: Counter[str] = field(default_factory=Counter)
    first_seen_monotonic: dict[str, float] = field(default_factory=dict)
    last_seen_monotonic: dict[str, float] = field(default_factory=dict)
    max_inter_message_ms: dict[str, float] = field(default_factory=dict)
    reconnects: Counter[str] = field(default_factory=Counter)
    websocket_errors: Counter[str] = field(default_factory=Counter)
    connection_attempts: Counter[str] = field(default_factory=Counter)
    connection_successes: Counter[str] = field(default_factory=Counter)
    connection_started: dict[str, float] = field(default_factory=dict)
    connection_observation_started: float | None = None
    connection_seconds: defaultdict[str, float] = field(
        default_factory=lambda: defaultdict(float)
    )
    parse_errors: int = 0
    payload_errors: int = 0
    rejected_timestamp: int = 0
    rejected_timestamp_by_stream: Counter[str] = field(default_factory=Counter)
    depth_sequence_gaps: Counter[str] = field(default_factory=Counter)
    depth_last_update_id: dict[str, int] = field(default_factory=dict)
    spread_bps: dict[str, float] = field(default_factory=dict)
    book_imbalance: dict[str, float] = field(default_factory=dict)

    @property
    def discarded_clock_skew(self) -> int:
        """Nombre de compatibilidad para la metrica historica."""
        return self.rejected_timestamp


def build_stream_urls(config: ProbeConfig) -> dict[str, str]:
    symbols = [symbol.lower() for symbol in config.symbols]
    public_streams = [
        stream
        for symbol in symbols
        for stream in (f"{symbol}@bookTicker", f"{symbol}@depth20@100ms")
    ]
    market_streams = ["!forceOrder@arr", "!markPrice@arr@1s"] + [
        f"{symbol}@aggTrade" for symbol in symbols
    ]
    return {
        "public": f"{BASE_URL}/public/stream?streams={'/'.join(public_streams)}",
        "market": f"{BASE_URL}/market/stream?streams={'/'.join(market_streams)}",
    }


class MarketProbe:
    def __init__(
        self,
        config: ProbeConfig,
        *,
        clock_sync: ClockSynchronizer | None = None,
        wall_clock_ms: Callable[[], float] | None = None,
        monotonic: Callable[[], float] | None = None,
        perf_counter_ns: Callable[[], int] | None = None,
    ) -> None:
        self.config = config
        self._wall_clock_ms = wall_clock_ms or (lambda: time.time_ns() / 1_000_000)
        self._monotonic = monotonic or time.monotonic
        self._perf_counter_ns = perf_counter_ns or time.perf_counter_ns
        self.detectors = EventDetectors(config)
        self.stats = RuntimeStats(started_monotonic=self._monotonic())
        self.clock_sync = clock_sync or ClockSynchronizer(
            sample_count=config.clock_sync.samples,
            interval_seconds=config.clock_sync.interval_seconds,
            request_timeout_seconds=config.clock_sync.request_timeout_seconds,
            wall_clock_ms=self._wall_clock_ms,
        )
        self._stop = asyncio.Event()
        self._legacy_latency = RunningDistribution(config.telemetry_max_samples)
        self._latency: dict[str, dict[str, RunningDistribution]] = defaultdict(dict)
        self._processing: dict[str, dict[str, RunningDistribution]] = defaultdict(dict)
        self._persistence: PersistenceStore | None = None
        # P1-04: explicit symbol universe + mark-price return engine.
        # The engine ingests VALID observations only (see _handle_message).
        self.universe = SymbolUniverse.from_config(
            config,
            reason="P1-04 validated baseline trio; expansion needs transport headroom",
        )
        self._returns = ReturnEngine(symbols=config.symbols)
        self._restore_attempted = False

    @property
    def persistence(self) -> PersistenceStore:
        """Get or create the persistence store (lazy initialization)."""
        if self._persistence is None:
            self._persistence = get_persistence_store()
            self._persistence.init_db()
            self._persistence.configure_sampling(
                dict(self.config.observation_sample_ms))
            self._restore_return_history()
        return self._persistence

    def set_persistence(self, store: PersistenceStore) -> None:
        """Set a custom persistence store (for testing)."""
        self._persistence = store
        self._restore_attempted = False

    @property
    def returns(self) -> ReturnEngine:
        """The mark-price return engine (P1-04)."""
        return self._returns

    def _restore_return_history(self) -> None:
        """Best-effort restart continuity: reload persisted price buckets."""
        if self._restore_attempted or self._persistence is None:
            return
        self._restore_attempted = True
        try:
            for symbol in self.universe.active_symbols():
                samples = self._persistence.load_price_samples(symbol)
                series = self._returns._series.get(symbol)
                if series is None:
                    self._returns._series[symbol] = series = SymbolPriceSeries()
                series.restore([(bucket, price) for _, bucket, price in samples])
        except Exception as exc:
            LOGGER.warning(json.dumps({"kind": "persistence_error", "error": str(exc)}))

    def _distribution(
        self, container: dict[str, dict[str, RunningDistribution]], metric: str, key: str
    ) -> RunningDistribution:
        if key not in container[metric]:
            container[metric][key] = RunningDistribution(self.config.telemetry_max_samples)
        return container[metric][key]

    async def run(self, duration_seconds: float | None = None) -> None:
        urls = build_stream_urls(self.config)
        LOGGER.info(
            json.dumps(
                {
                    "kind": "startup",
                    "BOT_MODE": "observe",
                    "symbols": list(self.config.symbols),
                    "connections": list(urls),
                    "apiKeysUsed": 0,
                    "realOrdersSent": 0,
                    "realCapitalAtRisk": 0,
                }
            )
        )
        await self.clock_sync.sync()
        self.stats.connection_observation_started = self._monotonic()
        tasks = [
            asyncio.create_task(self._connection_loop(name, url), name=f"ws-{name}")
            for name, url in urls.items()
        ]
        tasks.append(asyncio.create_task(self._summary_loop(), name="summary"))
        tasks.append(
            asyncio.create_task(self.clock_sync.run(self._stop), name="clock-sync")
        )
        if duration_seconds is not None:
            tasks.append(
                asyncio.create_task(self._stop_after(duration_seconds), name="duration-stop")
            )
        try:
            await self._stop.wait()
        finally:
            self.log_summary(final=True)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def stop(self) -> None:
        self._stop.set()

    async def _stop_after(self, duration_seconds: float) -> None:
        await asyncio.sleep(duration_seconds)
        self.stop()

    async def _connection_loop(self, name: str, url: str) -> None:
        delay = 1.0
        while not self._stop.is_set():
            connected_at: float | None = None
            try:
                self.stats.connection_attempts[name] += 1
                LOGGER.info(json.dumps({"kind": "connection_attempt", "endpoint": name}))
                async with websockets.connect(
                    url,
                    open_timeout=15,
                    close_timeout=10,
                    ping_interval=180,
                    ping_timeout=600,
                    max_queue=4096,
                ) as websocket:
                    connected_at = self._monotonic()
                    self.stats.connection_started[name] = connected_at
                    self.stats.connection_successes[name] += 1
                    LOGGER.info(json.dumps({"kind": "connected", "endpoint": name}))
                    delay = 1.0
                    async for raw_message in websocket:
                        self._handle_message(raw_message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.stats.reconnects[name] += 1
                self.stats.websocket_errors[name] += 1
                LOGGER.warning(
                    json.dumps(
                        {
                            "kind": "connection_error",
                            "endpoint": name,
                            "error": f"{type(exc).__name__}: {exc}",
                            "retry_seconds": delay,
                        }
                    )
                )
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                delay = min(delay * 2, 30.0)
            finally:
                if connected_at is not None:
                    self.stats.connection_seconds[name] += max(
                        0.0, self._monotonic() - connected_at
                    )
                    self.stats.connection_started.pop(name, None)

    def _handle_message(self, raw_message: str | bytes) -> None:
        processing_start_ns = self._perf_counter_ns()
        received_ms = self._wall_clock_ms()
        try:
            envelope = json.loads(raw_message)
            stream = str(envelope["stream"])
            payload = envelope["data"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            self.stats.parse_errors += 1
            LOGGER.warning(json.dumps({"kind": "invalid_message", "error": str(exc)}))
            return
        parse_end_ns = self._perf_counter_ns()

        now_monotonic = self._monotonic()
        previous_seen = self.stats.last_seen_monotonic.get(stream)
        if previous_seen is not None:
            gap_ms = (now_monotonic - previous_seen) * 1000.0
            self.stats.max_inter_message_ms[stream] = max(
                gap_ms, self.stats.max_inter_message_ms.get(stream, 0.0)
            )
        self.stats.messages_by_stream[stream] += 1
        self.stats.first_seen_monotonic.setdefault(stream, now_monotonic)
        self.stats.last_seen_monotonic[stream] = now_monotonic

        processing_key = self._processing_key(stream, payload)
        legacy_timestamp = self._legacy_timestamp(payload)
        if legacy_timestamp is not None:
            legacy_lag = received_ms - legacy_timestamp
            self._legacy_latency.add(max(0.0, legacy_lag))

        try:
            self._record_timestamp_metrics(stream, payload, received_ms)
            if (
                legacy_timestamp is not None
                and abs(received_ms - legacy_timestamp)
                > self.config.max_event_clock_skew_ms
            ):
                self.stats.rejected_timestamp += 1
                self.stats.rejected_timestamp_by_stream[stream] += 1
                # Persist rejection telemetry (not as valid feature input).
                # Payloads pass through untouched (dict or markPrice list);
                # the store serializes safely and failures never break the probe.
                try:
                    self.persistence.store_rejection_record(
                        symbol=str(payload.get("s", "UNKNOWN")) if isinstance(payload, dict) else "UNKNOWN",
                        stream_type=stream,
                        payload=payload,
                        rejection_reason="timestamp_skew",
                        event_time_ms=int(payload["E"]) if isinstance(payload, dict) and "E" in payload else None,
                        transaction_time_ms=int(payload["T"]) if isinstance(payload, dict) and "T" in payload else None,
                    )
                except Exception as exc:
                    LOGGER.warning(json.dumps({"kind": "persistence_error", "error": str(exc)}))
                rejected_end_ns = self._perf_counter_ns()
                self._record_processing(
                    processing_key,
                    processing_start_ns,
                    parse_end_ns,
                    rejected_end_ns,
                    rejected_end_ns,
                    rejected_end_ns,
                )
                return

            if stream.endswith("@bookTicker"):
                symbol = str(payload["s"])
                self.stats.spread_bps[symbol] = spread_bps(
                    float(payload["b"]), float(payload["a"])
                )
            elif "@depth20@100ms" in stream:
                symbol = str(payload["s"])
                self.stats.book_imbalance[symbol] = order_book_imbalance(
                    payload["b"], payload["a"]
                )
                previous_update = self.stats.depth_last_update_id.get(symbol)
                previous_in_payload = payload.get("pu")
                if (
                    previous_update is not None
                    and previous_in_payload is not None
                    and int(previous_in_payload) != previous_update
                ):
                    self.stats.depth_sequence_gaps[symbol] += 1
                self.stats.depth_last_update_id[symbol] = int(payload["u"])
            metrics_end_ns = self._perf_counter_ns()

            if stream.endswith("@aggTrade"):
                events = self.detectors.aggregate_trade(
                    timestamp_ms=int(payload["T"]),
                    symbol=str(payload["s"]),
                    price=float(payload["p"]),
                    quantity=float(payload["q"]),
                )
            elif stream == "!forceOrder@arr":
                order = payload["o"]
                events = self.detectors.liquidation(
                    timestamp_ms=int(order["T"]),
                    symbol=str(order["s"]),
                    price=float(order.get("ap") or order["p"]),
                    quantity=float(order["q"]),
                    side=str(order["S"]),
                )
            elif stream == "!markPrice@arr@1s":
                events = []
                for item in payload:
                    if str(item.get("s")) not in self.config.symbols:
                        continue
                    events.extend(
                        self.detectors.funding_rate(
                            timestamp_ms=int(item["E"]),
                            symbol=str(item["s"]),
                            price=float(item["p"]),
                            rate=float(item["r"]),
                        )
                    )
                    # P1-04 return engine: VALID mark prices only. This code
                    # runs strictly after the skew guard above, so rejected
                    # observations can never reach the engine.
                    try:
                        self._returns.ingest(
                            str(item["s"]), int(item["E"]), float(item["p"]))
                    except (KeyError, TypeError, ValueError):
                        pass
            else:
                events = []
            detector_end_ns = self._perf_counter_ns()
        except (KeyError, TypeError, ValueError) as exc:
            self.stats.payload_errors += 1
            LOGGER.warning(
                json.dumps({"kind": "invalid_payload", "stream": stream, "error": str(exc)})
            )
            return

        for event in events:
            self.stats.events_by_type[event.event_type] += 1
            LOGGER.info(json.dumps({"kind": "detected_event", **event.as_log_record()}))
        
        # Persist valid market observation for P1-04+ feature engineering.
        # Runs only for messages that passed the skew guard above; rejected
        # messages return early and can only reach rejected_observations.
        # Dict payloads (aggTrade/bookTicker/depth/forceOrder) carry their
        # symbol; markPrice arrays (list) are stored as one MULTI record.
        try:
            if isinstance(payload, dict):
                symbol = str(payload.get("s", "UNKNOWN"))
                event_time_ms = int(payload["E"]) if "E" in payload else None
                transaction_time_ms = int(payload["T"]) if "T" in payload else None
                self.persistence.store_market_observation(
                    symbol=symbol,
                    stream_type=stream,
                    payload=payload,
                    normalized={
                        "symbol": symbol,
                        "stream": stream,
                        "price": payload.get("p") or payload.get("ap"),
                        "quantity": payload.get("q"),
                        "event_time_ms": event_time_ms,
                        "transaction_time_ms": transaction_time_ms,
                    },
                    event_time_ms=event_time_ms,
                    transaction_time_ms=transaction_time_ms,
                    is_valid=True,
                )
            elif isinstance(payload, list):
                self.persistence.store_market_observation(
                    symbol="MULTI",
                    stream_type=stream,
                    payload={"items": payload},
                    normalized={"symbol": "MULTI", "stream": stream, "count": len(payload)},
                    event_time_ms=None,
                    transaction_time_ms=None,
                    is_valid=True,
                )
        except Exception as exc:
            LOGGER.warning(json.dumps({"kind": "persistence_error", "error": str(exc)}))
        
        processing_end_ns = self._perf_counter_ns()
        self._record_processing(
            processing_key,
            processing_start_ns,
            parse_end_ns,
            metrics_end_ns,
            detector_end_ns,
            processing_end_ns,
        )

    def _record_timestamp_metrics(self, stream: str, payload: Any, received_ms: float) -> None:
        if stream == "!markPrice@arr@1s":
            for item in payload:
                symbol = str(item.get("s"))
                if symbol in self.config.symbols and "E" in item:
                    self._record_lags(
                        f"markPrice/{symbol}", received_ms, event_ms=float(item["E"])
                    )
            return

        key = self._processing_key(stream, payload)
        event_ms: float | None = None
        transaction_ms: float | None = None
        if isinstance(payload, dict):
            if "E" in payload:
                event_ms = float(payload["E"])
            if (
                stream.endswith(("@aggTrade", "@bookTicker"))
                or "@depth20@100ms" in stream
            ):
                if "T" in payload:
                    transaction_ms = float(payload["T"])
            elif stream == "!forceOrder@arr":
                order = payload.get("o")
                if isinstance(order, dict) and "T" in order:
                    transaction_ms = float(order["T"])
        self._record_lags(key, received_ms, event_ms=event_ms, transaction_ms=transaction_ms)

    def _record_lags(
        self,
        key: str,
        received_ms: float,
        *,
        event_ms: float | None = None,
        transaction_ms: float | None = None,
    ) -> None:
        offset = self.clock_sync.offset_ms
        if event_ms is not None:
            self._distribution(self._latency, "rawEventLagMs", key).add(
                received_ms - event_ms
            )
            if offset is not None:
                self._distribution(self._latency, "correctedEventLagMs", key).add(
                    corrected_lag_ms(received_ms, event_ms, offset)
                )
        if transaction_ms is not None:
            self._distribution(self._latency, "rawTransactionLagMs", key).add(
                received_ms - transaction_ms
            )
            if offset is not None:
                self._distribution(self._latency, "correctedTransactionLagMs", key).add(
                    corrected_lag_ms(received_ms, transaction_ms, offset)
                )
        if event_ms is not None and transaction_ms is not None:
            self._distribution(self._latency, "exchangeEventMinusTransactionMs", key).add(
                event_ms - transaction_ms
            )

    def _record_processing(
        self,
        key: str,
        start_ns: int,
        parse_end_ns: int,
        metrics_end_ns: int,
        detector_end_ns: int,
        processing_end_ns: int,
    ) -> None:
        values = {
            "parseLatencyMs": (parse_end_ns - start_ns) / 1_000_000,
            "metricsLatencyMs": (metrics_end_ns - parse_end_ns) / 1_000_000,
            "detectorLatencyMs": (detector_end_ns - metrics_end_ns) / 1_000_000,
            "processingLatencyMs": (processing_end_ns - start_ns) / 1_000_000,
        }
        for metric, value in values.items():
            self._distribution(self._processing, metric, key).add(value)

    def _processing_key(self, stream: str, payload: Any) -> str:
        if stream == "!markPrice@arr@1s":
            return "markPrice"
        if stream == "!forceOrder@arr" and isinstance(payload, dict):
            return "forceOrder"
        symbol = payload.get("s") if isinstance(payload, dict) else None
        if stream.endswith("@aggTrade"):
            return f"aggTrade/{symbol or 'UNKNOWN'}"
        if stream.endswith("@bookTicker"):
            return f"bookTicker/{symbol or 'UNKNOWN'}"
        if "@depth20@100ms" in stream:
            return f"depth/{symbol or 'UNKNOWN'}"
        return stream

    @staticmethod
    def _legacy_timestamp(payload: Any) -> int | None:
        if isinstance(payload, list):
            candidates = [
                int(item["E"])
                for item in payload
                if isinstance(item, dict) and "E" in item
            ]
            return max(candidates) if candidates else None
        if not isinstance(payload, dict):
            return None
        if "E" in payload:
            return int(payload["E"])
        order = payload.get("o")
        if isinstance(order, dict) and "T" in order:
            return int(order["T"])
        return None

    async def _summary_loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.summary_interval_seconds)
            self.log_summary(final=False)

    def build_summary(self, *, final: bool) -> dict[str, object]:
        now = self._monotonic()
        runtime = max(0.0, now - self.stats.started_monotonic)
        expected = expected_stream_names(self.config)
        active = [stream for stream in expected if stream in self.stats.last_seen_monotonic]
        silent = sorted(
            stream
            for stream in active
            if now - self.stats.last_seen_monotonic[stream]
            > self.config.stale_after_seconds
        )
        cadence_streams = {
            "!markPrice@arr@1s",
            *(f"{symbol.lower()}@depth20@100ms" for symbol in self.config.symbols),
        }
        stale = sorted(stream for stream in silent if stream in cadence_streams)
        max_silence_ms = {}
        for stream in active:
            current_silence = (now - self.stats.last_seen_monotonic[stream]) * 1000.0
            max_silence_ms[stream] = round(
                max(current_silence, self.stats.max_inter_message_ms.get(stream, 0.0)), 3
            )

        endpoints = build_stream_urls(self.config).keys()
        connectivity_runtime = max(
            0.0,
            now
            - (
                self.stats.connection_observation_started
                if self.stats.connection_observation_started is not None
                else now
            ),
        )
        connected_seconds = {}
        uptime_percent = {}
        for endpoint in endpoints:
            seconds = self.stats.connection_seconds[endpoint]
            if endpoint in self.stats.connection_started:
                seconds += max(0.0, now - self.stats.connection_started[endpoint])
            connected_seconds[endpoint] = round(seconds, 3)
            uptime_percent[endpoint] = round(
                min(
                    100.0,
                    (seconds / connectivity_runtime * 100.0)
                    if connectivity_runtime
                    else 0.0,
                ),
                6,
            )

        return {
            "kind": "final_summary" if final else "summary",
            "runtimeSeconds": round(runtime, 3),
            "safety": {
                "BOT_MODE": "observe",
                "apiKeysUsed": 0,
                "realOrdersSent": 0,
                "realCapitalAtRisk": 0,
                "maxDrawdownKillSwitchActive": False,
                "authenticatedClientsPresent": False,
                "orderExecutionPathPresent": False,
            },
            "clock": self.clock_sync.snapshot(),
            "latency": {
                **self._snapshot_distributions(self._latency),
                "legacyGlobalClampedLagMs": self._legacy_latency.snapshot(),
                "legacySemantics": "localReceiveMs-minus-E; fallback-o.T; negative-clamped; mixed-streams",
                "timestampAvailability": {
                    "aggTrade": {"E": "eventTime", "T": "tradeTime"},
                    "bookTicker": {"E": "eventTime", "T": "transactionTime"},
                    "depth": {"E": "eventTime", "T": "transactionTime"},
                    "forceOrder": {"E": "eventTime", "T": "orderTradeTime"},
                    "markPrice": {
                        "E": "eventTime",
                        "transactionTime": "NOT_AVAILABLE",
                        "T": "nextFundingTime_not_latency",
                    },
                },
            },
            "processing": self._snapshot_distributions(self._processing),
            "detectors": self.detectors.telemetry_snapshot(),
            "dataQuality": {
                "expectedStreams": len(expected),
                "activeStreams": len(active),
                "missingStreams": sorted(set(expected) - set(active)),
                "staleStreams": stale,
                "silentStreams": silent,
                "stalenessCadenceStreams": sorted(cadence_streams),
                "messagesByStream": dict(self.stats.messages_by_stream),
                "maxObservedSilenceMsByStream": max_silence_ms,
                "silenceSemantics": "inter-message silence; not inferred packet loss",
                "depthSequenceGapsBySymbol": {
                    symbol: self.stats.depth_sequence_gaps[symbol]
                    for symbol in self.config.symbols
                },
                "timestampRejected": self.stats.rejected_timestamp,
                "timestampRejectedByStream": dict(self.stats.rejected_timestamp_by_stream),
                "parseErrors": self.stats.parse_errors,
                "payloadErrors": self.stats.payload_errors,
                "websocketErrors": {
                    endpoint: self.stats.websocket_errors[endpoint] for endpoint in endpoints
                },
                "reconnections": {
                    endpoint: self.stats.reconnects[endpoint] for endpoint in endpoints
                },
                "connectionAttempts": {
                    endpoint: self.stats.connection_attempts[endpoint] for endpoint in endpoints
                },
                "connectionSuccesses": {
                    endpoint: self.stats.connection_successes[endpoint] for endpoint in endpoints
                },
                "connectedSecondsByEndpoint": connected_seconds,
                "connectivityObservationSeconds": round(connectivity_runtime, 3),
                "observedUptimePercentByEndpoint": uptime_percent,
            },
            "eventsByType": dict(self.stats.events_by_type),
            "spreadBps": {
                key: round(value, 6) for key, value in self.stats.spread_bps.items()
            },
            "bookImbalance": {
                key: round(value, 6) for key, value in self.stats.book_imbalance.items()
            },
            # P1-04 additive blocks: return-engine stats + persistence write
            # stats (sampling accepted/dropped, in-flight high-water). Never
            # None-guarded callers break: defaults on any persistence gap.
            "returns": self._returns.stats(),
            "persistence": self._persistence_stats(),
        }

    @staticmethod
    def _snapshot_distributions(
        container: dict[str, dict[str, RunningDistribution]]
    ) -> dict[str, dict[str, dict[str, float | int | str | None]]]:
        return {
            metric: {
                key: distribution.snapshot()
                for key, distribution in sorted(values.items())
            }
            for metric, values in sorted(container.items())
        }

    def _persistence_stats(self) -> dict[str, object]:
        """Sampling + queue stats without ever creating the store as a side
        effect (build_summary must stay side-effect free for tests)."""
        if self._persistence is None:
            return {"sample_stats": {"accepted": {}, "dropped": {},
                                     "gate_ms": {},
                                     "inflight": 0, "inflight_high_water": 0}}
        try:
            return {"sample_stats": self._persistence.sample_stats()}
        except Exception:
            return {"sample_stats": {}}

    def log_summary(self, *, final: bool) -> None:
        summary = self.build_summary(final=final)
        # Persist the snapshot for the P1-03 dashboard (fire-and-forget;
        # persistence failures are logged there and never break logging).
        # P1-04: also persist dirty price buckets + latest return features
        # so the dashboard and restarts observe feature state.
        try:
            self.persistence.store_telemetry_snapshot(summary)
            dirty = self._returns.drain_dirty_buckets()
            if dirty:
                self.persistence.store_price_samples(dirty)
            self.persistence.store_return_features(
                self._returns.snapshot_all(self._wall_clock_ms()))
        except Exception as exc:
            LOGGER.warning(json.dumps({"kind": "persistence_error", "error": str(exc)}))
        LOGGER.info(json.dumps(summary, sort_keys=True, allow_nan=False))
