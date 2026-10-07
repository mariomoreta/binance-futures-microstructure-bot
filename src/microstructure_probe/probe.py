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

from .book import BookEngine
from .clock import ClockSynchronizer, corrected_lag_ms
from .market_structure import MarketStructureEngine
from .config import ProbeConfig
from .detectors import EventDetectors
from .discovery import (
    CORE_SYMBOLS,
    TIER_CORE,
    TIER_DISCOVERY,
    TIER_HOT,
    DiscoveryClient,
    select_hot,
    top_movers,
)
from .flow import FlowEngine
from .metrics import order_book_imbalance, spread_bps
from .momentum import RANK_METRICS, VELOCITY_HORIZONS, RankTracker
from .open_interest import OpenInterestPoller, OpenInterestTracker
from .persistence import PersistenceStore, get_persistence_store
from .returns import ReturnEngine, SymbolPriceSeries
from .telemetry import RunningDistribution
from .universe import SymbolUniverse
from .persistence import PersistenceStore, get_persistence_store

LOGGER = logging.getLogger("microstructure_probe")
BASE_URL = "wss://fstream.binance.com"
# Streams whose silence is normal (event-driven, no cadence): never reported
# as missing, never stale. forceOrder publishes only when liquidations occur.
EVENT_DRIVEN_STREAMS = frozenset({"!forceOrder@arr"})


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
        # P1-06: aggressive trade-flow engine. Ingests EVERY valid aggTrade
        # on the post-skew-guard path (see _handle_message), independent of
        # the raw-observation sampling gate — sampling never defines flow
        # accuracy. Only subscribed (allowed) symbols are tracked.
        self._flow = FlowEngine(
            symbols=config.symbols,
            min_baseline_buckets=config.volume.minimum_buckets,
            latency_max_samples=config.telemetry_max_samples,
        )
        # P1-07: order-book engine (every valid depth snapshot, pre-sampling)
        # + open-interest tracker/poller (bounded public REST, own cadence).
        # Only subscribed (allowed) symbols are tracked; HOT stays proposed.
        self._book = BookEngine(
            symbols=config.symbols,
            latency_max_samples=config.telemetry_max_samples,
        )
        self._oi = OpenInterestTracker(
            symbols=config.symbols,
            stale_after_ms=config.open_interest.stale_after_seconds * 1000,
        )
        self._oi_poller = OpenInterestPoller(
            symbols=config.symbols,
            interval_seconds=config.open_interest.interval_seconds,
            timeout_seconds=config.open_interest.request_timeout_seconds,
            wall_clock_ms=self._wall_clock_ms,
            latency_max_samples=config.telemetry_max_samples,
        )
        # P1-08: VWAP/volatility/range/structure over peer-engine state.
        # Stateless compute (no new ingest path, no new endpoint): VWAP
        # from flow aggregates, vol/range/structure from the persisted
        # 10s mark-price buckets. Only subscribed symbols are evaluated.
        self._structure = MarketStructureEngine(
            symbols=config.symbols,
            latency_max_samples=config.telemetry_max_samples,
        )
        # P1-05: discovery + momentum/rank state. Core symbols are pinned
        # benchmarks; the HOT set is proposed only (no dynamic WS resubscribe
        # in this task — see docs).
        self._rank_tracker = RankTracker()
        self._hot_dynamic: tuple = ()
        self._hot_state: dict = {"appear": {}, "absent": {}}
        self._discovery_info: dict = {
            "enabled": bool(config.discovery.enabled),
            "last_scan_ms": None,
            "eligible": 0,
            "filtered": 0,
            "seen": 0,
            "error": None,
        }
        self._discovery_client: DiscoveryClient | None = None

    @property
    def persistence(self) -> PersistenceStore:
        """Get or create the persistence store (lazy initialization)."""
        if self._persistence is None:
            self._persistence = get_persistence_store()
            self._persistence.init_db()
            self._persistence.configure_sampling(
                dict(self.config.observation_sample_ms))
            self._restore_return_history()
            self._restore_flow_history()
            self._restore_oi_history()
        return self._persistence

    def set_persistence(self, store: PersistenceStore) -> None:
        """Set a custom persistence store (for testing)."""
        self._persistence = store
        self._restore_attempted = False

    @property
    def returns(self) -> ReturnEngine:
        """The mark-price return engine (P1-04)."""
        return self._returns

    @property
    def flow(self) -> FlowEngine:
        """The aggressive trade-flow engine (P1-06)."""
        return self._flow

    @property
    def book(self) -> BookEngine:
        """The order-book intelligence engine (P1-07)."""
        return self._book

    @property
    def oi(self) -> OpenInterestTracker:
        """The open-interest tracker (P1-07)."""
        return self._oi

    @property
    def oi_poller(self) -> OpenInterestPoller:
        """The bounded OI REST scheduler (P1-07)."""
        return self._oi_poller

    @property
    def structure(self) -> MarketStructureEngine:
        """VWAP/volatility/range/structure compute (P1-08)."""
        return self._structure

    def set_oi_fetcher(self, fetch_fn) -> None:
        """Replace the OI REST fetcher (tests only — never live traffic)."""
        self._oi_poller = OpenInterestPoller(
            symbols=self.config.symbols,
            interval_seconds=self.config.open_interest.interval_seconds,
            timeout_seconds=self.config.open_interest.request_timeout_seconds,
            wall_clock_ms=self._wall_clock_ms,
            latency_max_samples=self.config.telemetry_max_samples,
            fetch_fn=fetch_fn,
        )

    def _restore_oi_history(self) -> None:
        """Best-effort restart continuity: reload timestamped OI samples.

        Anchors honor actual fetch times, so a restart gap simply ages
        history out via tolerance — never fabricated, never double-counted
        (samples are idempotent per symbol+fetch_ms).
        """
        if self._persistence is None:
            return
        try:
            all_rows = []
            for symbol in self.config.symbols:
                all_rows.extend(
                    self._persistence.load_oi_samples(
                        symbol=symbol, limit=2000))
            self._oi.restore_samples(all_rows)
        except Exception as exc:
            LOGGER.warning(json.dumps({"kind": "persistence_error", "error": str(exc)}))

    def _restore_flow_history(self) -> None:
        """Best-effort restart continuity: reload completed flow buckets.

        Only CLOSED buckets restore (live trailing windows restart empty by
        design); bucket primary keys make re-emission idempotent, so a
        restart can never double-count.
        """
        if self._persistence is None:
            return
        try:
            all_rows = []
            for symbol in self.config.symbols:
                all_rows.extend(
                    self._persistence.load_flow_buckets(
                        symbol=symbol, limit=2400))
            self._flow.restore_buckets(all_rows)
        except Exception as exc:
            LOGGER.warning(json.dumps({"kind": "persistence_error", "error": str(exc)}))

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
        if self.config.discovery.enabled:
            tasks.append(
                asyncio.create_task(self._discovery_loop(), name="discovery")
            )
        if self.config.open_interest.enabled:
            tasks.append(
                asyncio.create_task(self._oi_loop(), name="open-interest")
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
                # P1-07 book engine: EVERY valid depth snapshot lands here,
                # BEFORE and INDEPENDENT of the raw-observation sampling gate.
                # Post-skew-guard only (rejected messages return early above).
                # Invalid books are counted inside the engine and never
                # guessed; the message still flows to stats/persistence
                # untouched. Engine failures must never break that path.
                try:
                    self._book.ingest(
                        symbol=str(payload["s"]),
                        event_time_ms=int(payload["E"]),
                        update_id=payload.get("u"),
                        prev_update_id=payload.get("pu"),
                        bids=payload.get("b"),
                        asks=payload.get("a"),
                    )
                except (KeyError, TypeError, ValueError):
                    pass
            metrics_end_ns = self._perf_counter_ns()

            if stream.endswith("@aggTrade"):
                events = self.detectors.aggregate_trade(
                    timestamp_ms=int(payload["T"]),
                    symbol=str(payload["s"]),
                    price=float(payload["p"]),
                    quantity=float(payload["q"]),
                )
                # P1-06 flow engine: EVERY valid aggTrade lands here, BEFORE
                # and INDEPENDENT of the raw-observation sampling gate below.
                # This code runs strictly after the skew guard, so rejected
                # observations can never reach the engine. Missing/non-bool
                # `m` is counted invalid-side inside the engine and never
                # guessed; the message still flows to detectors/persistence
                # untouched. Engine failures must never break that path.
                try:
                    self._flow.ingest(
                        symbol=str(payload["s"]),
                        event_time_ms=int(payload["E"]),
                        price=float(payload["p"]),
                        quantity=float(payload["q"]),
                        buyer_is_maker=payload.get("m"),
                        normal_quantity=payload.get("nq"),
                    )
                except (KeyError, TypeError, ValueError):
                    pass
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

    @property
    def discovery_client(self) -> DiscoveryClient:
        """Lazily created public-REST client (injectable for tests)."""
        if self._discovery_client is None:
            self._discovery_client = DiscoveryClient()
        return self._discovery_client

    def set_discovery_client(self, client: DiscoveryClient) -> None:
        """Inject a fake discovery client (tests only — never live traffic)."""
        self._discovery_client = client

    async def run_discovery_scan(self) -> dict:
        """One bounded discovery scan: fetch, filter, select HOT, persist.

        Public REST only; failures are recorded and never break the probe.
        Returns the compact snapshot dict (also persisted + logged).
        """
        cfg = self.config.discovery
        info = self._discovery_info
        try:
            candidates, counts = await asyncio.to_thread(
                self.discovery_client.scan, cfg.min_quote_volume_usdt)
            dynamic, events, self._hot_state = select_hot(
                candidates,
                core=tuple(self.universe.active_symbols()) or CORE_SYMBOLS,
                dynamic_slots=cfg.hot_dynamic_slots,
                prior_dynamic=self._hot_dynamic,
                state=self._hot_state,
                min_votes=cfg.min_votes,
            )
            self._hot_dynamic = tuple(dynamic)
            tops = top_movers(candidates, cfg.top_n)
            now_ms = int(self._wall_clock_ms())
            snapshot = {
                "generated_at_ms": now_ms,
                "eligible_count": counts["eligible"],
                "seen_count": counts["symbols_seen"],
                "filtered_count": counts["symbols_seen"] - counts["eligible"],
                "core": list(self.universe.active_symbols()),
                "hot_dynamic": list(dynamic),
                "hot_full": list(self.universe.active_symbols()) + list(dynamic),
                "tops": tops,
                "top_n": cfg.top_n,
                "min_quote_volume_usdt": cfg.min_quote_volume_usdt,
            }
            try:
                self.persistence.store_discovery_snapshot(snapshot)
                for event in events:
                    self.persistence.log_universe_event(
                        event["kind"], event["symbol"], event.get("reason", ""))
            except Exception as exc:
                LOGGER.warning(json.dumps(
                    {"kind": "persistence_error", "error": str(exc)}))
            info.update({"last_scan_ms": now_ms,
                         "eligible": counts["eligible"],
                         "filtered": counts["symbols_seen"] - counts["eligible"],
                         "seen": counts["symbols_seen"],
                         "error": None})
            LOGGER.info(json.dumps({"kind": "discovery_scan",
                                    "eligible": counts["eligible"],
                                    "hot_dynamic": list(dynamic),
                                    "events": events}))
            return snapshot
        except Exception as exc:
            info["error"] = f"{type(exc).__name__}: {exc}"
            LOGGER.warning(json.dumps(
                {"kind": "discovery_error", "error": str(exc)}))
            return {"error": str(exc)}

    async def _discovery_loop(self) -> None:
        # First scan immediately so the dashboard has discovery state early.
        await self.run_discovery_scan()
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.config.discovery.interval_seconds)
            except asyncio.TimeoutError:
                pass
            if not self._stop.is_set():
                await self.run_discovery_scan()

    async def _oi_loop(self) -> None:
        """Bounded OI poll scheduler: one round per tick, off the WS loop.

        REST runs in a worker thread (never blocks websocket processing);
        failures are counted in the poller and logged, then the loop
        continues on cadence. Stops with the probe.
        """
        # First round immediately so OI state exists early in the run.
        await self._oi_poll_round()
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._oi_poller.interval_seconds)
            except asyncio.TimeoutError:
                pass
            if not self._stop.is_set():
                await self._oi_poll_round()

    async def _oi_poll_round(self) -> None:
        try:
            outcome = await asyncio.to_thread(
                self._oi_poller.poll_once, self._oi)
        except Exception as exc:
            LOGGER.warning(json.dumps(
                {"kind": "oi_poll_error", "error": str(exc)}))
            return
        LOGGER.info(json.dumps({"kind": "oi_poll", **outcome,
                                "failures": self._oi_poller.failures}))

    def build_summary(self, *, final: bool) -> dict[str, object]:
        now = self._monotonic()
        runtime = max(0.0, now - self.stats.started_monotonic)
        expected = expected_stream_names(self.config)
        active = [stream for stream in expected if stream in self.stats.last_seen_monotonic]
        # Event-driven streams (forceOrder: liquidations only) are NEVER
        # missing: silence is their normal state, not absence.
        missing = sorted(set(expected) - set(active) - EVENT_DRIVEN_STREAMS)
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
                "missingStreams": missing,
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
            # P1-05 additive block: discovery scan state (HOT proposal only;
            # websocket subscriptions are unchanged — see docs).
            "discovery": {
                "enabled": self._discovery_info["enabled"],
                "last_scan_ms": self._discovery_info["last_scan_ms"],
                "seen": self._discovery_info["seen"],
                "eligible": self._discovery_info["eligible"],
                "filtered": self._discovery_info["filtered"],
                "hot_dynamic": list(self._hot_dynamic),
                "error": self._discovery_info["error"],
            },
            # P1-06 additive block: flow engine counters + latency (the
            # engine consumed every valid aggTrade pre-sampling). Full
            # per-symbol features persist via store_flow_features for the
            # dashboard; the summary carries counters only.
            "flow": self._flow.stats(),
            # P1-07 additive blocks: book engine counters + latency (every
            # valid depth snapshot pre-sampling) and OI poll/tracker state.
            # Full per-symbol records persist via store_book_features /
            # store_oi_features for the dashboard.
            "book": self._book.stats(),
            "openInterest": {
                "tracker": self._oi.stats(),
                "poll": self._oi_poller.stats(),
            },
            # P1-08 additive block: structure compute counters + latency
            # (stateless evaluation over flow + return state). Full
            # per-symbol records persist via store_structure_features.
            "structure": self._structure.stats(),
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
        # P1-05: enrich rows with tier + momentum + ranks (additive only;
        # P1-04 return/anchor keys untouched) and persist rank vectors.
        # P1-06 (additive): persist compact flow state — latest features per
        # symbol for the dashboard plus completed buckets for restart
        # continuity. Raw trades are NEVER persisted per-trade; the engine
        # already consumed every valid event pre-sampling in _handle_message.
        try:
            self.persistence.store_telemetry_snapshot(summary)
            dirty = self._returns.drain_dirty_buckets()
            if dirty:
                self.persistence.store_price_samples(dirty)
            as_of_ms = self._wall_clock_ms()
            flow_buckets = self._flow.drain_completed_buckets()
            if flow_buckets:
                self.persistence.store_flow_buckets(flow_buckets)
            flow_rows_list = self._flow.snapshot_all(as_of_ms)
            self.persistence.store_flow_features(flow_rows_list)
            rows = self._returns.snapshot_all(as_of_ms)
            momentum_rows = []
            for row in rows:
                symbol = str(row.get("symbol", "UNKNOWN"))
                momentum = self._returns.momentum(symbol, as_of_ms)
                row["momentum"] = momentum
                row["tier"] = (TIER_CORE if symbol in self.universe.active_symbols()
                               else TIER_HOT if symbol in self._hot_dynamic
                               else TIER_DISCOVERY)
                momentum_rows.append((symbol, {
                    "velocity_1m": momentum["velocity"].get("1m"),
                    "velocity_5m": momentum["velocity"].get("5m"),
                    "acceleration_1m": momentum["acceleration"].get("1m"),
                }))
            ranks = self._rank_tracker.evaluate(as_of_ms, momentum_rows)
            for row in rows:
                symbol = str(row.get("symbol", "UNKNOWN"))
                row["ranks"] = {metric: vec.get(symbol, {})
                                for metric, vec in ranks.items()}
            for metric, vec in ranks.items():
                if vec:
                    self.persistence.store_rank_snapshot(metric, vec)
            self.persistence.store_return_features(rows)
            # P1-07 (additive): persist compact book + OI state. Latest
            # book snapshot per symbol for the dashboard (never restored
            # as live — the book restarts empty until fresh depth lands);
            # OI samples (bounded, timestamped) + latest OI features with
            # 1m price returns for joint context.
            self.persistence.store_book_features(
                self._book.snapshot_all(as_of_ms))
            oi_new = self._oi.drain_new_samples()
            if oi_new:
                self.persistence.store_oi_samples(oi_new)
            price_returns_1m = {}
            for row in rows:
                symbol = str(row.get("symbol", "UNKNOWN"))
                returns = row.get("returns")
                price_returns_1m[symbol] = (
                    returns.get("1m") if isinstance(returns, dict) else None)
            self.persistence.store_oi_features(
                self._oi.snapshot_all(as_of_ms, price_returns_1m))
            # P1-08 (additive): evaluate VWAP/volatility/range/structure
            # over peer-engine state (flow rows + return rows + 10s
            # buckets) and persist one compact record per symbol. No new
            # ingest path, no new endpoint; restart continuity is inherited
            # (buckets restore, flow windows warm live).
            flow_rows = {str(f.get("symbol", "UNKNOWN")): f
                         for f in flow_rows_list
                         if isinstance(f, dict)}
            price_rows = {str(r.get("symbol", "UNKNOWN")): r
                          for r in rows if isinstance(r, dict)}
            structure_rows = []
            for symbol in sorted(set(flow_rows) | set(price_rows)):
                structure_rows.append(self._structure.snapshot_symbol(
                    symbol, as_of_ms,
                    flow_rows.get(symbol), price_rows.get(symbol),
                    self._returns.buckets(symbol)))
            self.persistence.store_structure_features(structure_rows)
        except Exception as exc:
            LOGGER.warning(json.dumps({"kind": "persistence_error", "error": str(exc)}))
        LOGGER.info(json.dumps(summary, sort_keys=True, allow_nan=False))
