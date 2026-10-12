from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import Counter, defaultdict
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Callable

import websockets

from .book import BookEngine
from .classifier import ClassifierEngine, RULES_VERSION as CLASSIFIER_VERSION
from .clock import ClockSynchronizer, corrected_lag_ms
from .opportunity import OPPORTUNITY_RULES_VERSION, OpportunityEngine
from .universe_manager import UniverseManager
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
from .prospective import ProspectiveRecorder
from .research_recorder import ResearchRecorder
from .returns import ReturnEngine, SymbolPriceSeries
from .telemetry import RunningDistribution
from .universe import SymbolUniverse
from .persistence import PersistenceStore, get_persistence_store

LOGGER = logging.getLogger("microstructure_probe")
BASE_URL = "wss://fstream.binance.com"
# Streams whose silence is normal (event-driven, no cadence): never reported
# as missing, never stale. forceOrder publishes only when liquidations occur.
EVENT_DRIVEN_STREAMS = frozenset({"!forceOrder@arr"})


def expected_stream_names(config: ProbeConfig,
                            extra_symbols: tuple = ()) -> tuple[str, ...]:
    symbols = [symbol.lower() for symbol in config.symbols]
    extra = [symbol.lower() for symbol in extra_symbols
             if str(symbol).upper() not in config.symbols]
    return tuple(
        ["!forceOrder@arr", "!markPrice@arr@1s"]
        + [f"{symbol}@aggTrade" for symbol in symbols]
        + [f"{symbol}@bookTicker" for symbol in symbols]
        + [f"{symbol}@depth20@100ms" for symbol in symbols]
        + [f"{symbol}@aggTrade" for symbol in extra]
        + [f"{symbol}@bookTicker" for symbol in extra]
        + [f"{symbol}@depth20@100ms" for symbol in extra]
    )


def build_hot_stream_urls(symbols: tuple = ()) -> dict[str, str]:
    """Managed HOT connection group (P1-12B): per-symbol deep streams only.

    markPrice (!arr) and forceOrder (!arr) are global array feeds already
    carried by the canonical market connection — never duplicated here.
    Empty input yields no connections (most conservative state).
    """
    syms = [str(symbol).lower() for symbol in dict.fromkeys(
        str(s).upper() for s in symbols)]
    if not syms:
        return {}
    hot_public = [stream for symbol in syms
                  for stream in (f"{symbol}@bookTicker",
                                 f"{symbol}@depth20@100ms")]
    hot_market = [f"{symbol}@aggTrade" for symbol in syms]
    return {
        "hot-public": f"{BASE_URL}/public/stream?streams={'/'.join(hot_public)}",
        "hot-market": f"{BASE_URL}/market/stream?streams={'/'.join(hot_market)}",
    }


# LOCAL_POLICY thresholds (P1-14B.3 freshness watchdog). No Binance-doc
# claims: tuned against observed healthy maxima (cadenced silence ~4.5 s,
# silence flag at stale_after_seconds=10 s) vs the abort scale (minutes).
# A connection whose streams deliver no guard-accepted (hence fresh)
# message for this long is open-but-stale and gets one forced reconnect
# through the normal retry path. hot-market carries aggTrade only, which
# is legitimately sparse on quiet symbols, so it gets the longer budget.
_FRESHNESS_RECONNECT_AFTER_MS = 90_000
_HOT_MARKET_FRESHNESS_AFTER_MS = 300_000
_FORCED_RECONNECT_COOLDOWN_S = 120.0
_FRESHNESS_GRACE_S = 120.0


# LOCAL_POLICY (P1-14B.5): receipt-silence budget for the diagnostic
# connection-health classifier. Above the worst healthy cadenced silence
# (~4.5 s) and the 10 s silence flag, far below the 90 s watchdog budget:
# separates SILENT (nothing arriving) from FLOWING_STALE (arriving but old).
_CONNECTION_SILENCE_MS = 30_000


def _connection_for_stream(stream: Any, core_symbols: Any,
                           hot_active: Any) -> str | None:
    """Map a stream name to its owning connection (pure, testable).

    Returns public/market/hot-public/hot-market, or None for streams that
    cannot be attributed (unknown symbols — conservatively unwatched).
    Global array feeds (!markPrice, !forceOrder) always ride market.
    """
    name = str(stream or "")
    if name in ("!markPrice@arr@1s", "!forceOrder@arr"):
        return "market"
    if "@" not in name:
        return None
    symbol, _, kind = name.partition("@")
    symbol = symbol.upper()
    try:
        hot = {str(s).upper() for s in (hot_active or ())}
        core = {str(s).upper() for s in (core_symbols or ())}
    except TypeError:
        return None
    if symbol in hot:
        if kind in ("bookTicker", "depth20@100ms"):
            return "hot-public"
        if kind == "aggTrade":
            return "hot-market"
        return None
    if symbol in core:
        if kind in ("bookTicker", "depth20@100ms"):
            return "public"
        if kind == "aggTrade":
            return "market"
        return None
    return None


def classify_connection_health(
    *,
    socket_up: bool,
    ever_attempted: bool,
    now_wall_ms: float,
    last_receipt_wall_ms: Any = None,
    last_accepted_wall_ms: Any = None,
    budget_ms: float = _FRESHNESS_RECONNECT_AFTER_MS,
    silence_ms: float = _CONNECTION_SILENCE_MS,
) -> dict:
    """Diagnostic connection health (P1-14B.5, pure, testable).

    Separates the RAW socket state from the diagnostic verdict — an open
    socket never implies a healthy stream. States (diagnostic vocabulary,
    disjoint from P1-12A market states and P1-13A lifecycles):
      UNAVAILABLE   -- never attempted (no evidence at all)
      RECONNECTING  -- wanted but socket down after ≥1 attempt
      FLOWING_FRESH -- socket up, guard-accepted traffic within budget
      FLOWING_STALE -- socket up, receipts recent, nothing accepted in budget
      SILENT        -- socket up, no receipts within the silence budget
    Missing timestamps stay None (never zero-filled); ages computed only
    from present values, else None.
    """
    try:
        now = float(now_wall_ms)
    except (TypeError, ValueError):
        now = float("nan")
    try:
        receipt = float(last_receipt_wall_ms) if last_receipt_wall_ms is not None else None
    except (TypeError, ValueError):
        receipt = None
    try:
        accepted = float(last_accepted_wall_ms) if last_accepted_wall_ms is not None else None
    except (TypeError, ValueError):
        accepted = None
    try:
        budget = float(budget_ms)
    except (TypeError, ValueError):
        budget = float(_FRESHNESS_RECONNECT_AFTER_MS)
    try:
        silence = float(silence_ms)
    except (TypeError, ValueError):
        silence = float(_CONNECTION_SILENCE_MS)
    socket = "CONNECTED" if socket_up else "DOWN"
    if not socket_up:
        health = "RECONNECTING" if ever_attempted else "UNAVAILABLE"
        receipt_age = None
        accepted_age = None
    else:
        receipt_age = now - receipt if receipt is not None else None
        accepted_age = now - accepted if accepted is not None else None
        if accepted_age is not None and accepted_age <= budget:
            health = "FLOWING_FRESH"
        elif receipt_age is not None and receipt_age <= silence:
            health = "FLOWING_STALE"
        else:
            health = "SILENT"
    return {
        "socket": socket,
        "health": health,
        "budget_ms": budget,
        "silence_ms": silence,
        "lastReceiptMs": receipt,
        "lastAcceptedMs": accepted,
        "receiptAgeMs": receipt_age,
        "acceptedAgeMs": accepted_age,
    }
    return None


@dataclass
class RuntimeStats:
    started_monotonic: float
    messages_by_stream: Counter[str] = field(default_factory=Counter)
    bytes_by_stream: Counter[str] = field(default_factory=Counter)
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
        persistence_store: PersistenceStore | None = None,
        research_history_store: Any | None = None,
    ) -> None:
        """Optional ``persistence_store`` / ``research_history_store`` are
        hermetic-test injection points (Routes B/C): the probe and its
        owned prospective recorder use them instead of the default
        production stores. When None (production default) behavior is
        unchanged."""
        self.config = config
        # P3 run linkage: unique per probe execution; stamped on every
        # row this run persists (universe events, setups, outcomes,
        # snapshots). Historical rows without one stay NULL = UNKNOWN.
        # Guarantee: UUID4 randomness (122 bits); uniqueness is
        # probabilistic (collision negligible), never claimed absolute;
        # separation relies on inequality of actually stored ids.
        self.run_id = uuid.uuid4().hex
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
        # P1-11C: prospective research recorder (probe-owned, same process).
        # Starts with MarketProbe, drains on exit. Never a second process /
        # registry / launcher. Failures degrade the recorder only.
        self._research = ResearchRecorder(
            enabled=True, history_store=research_history_store,
            run_id=self.run_id,
            rules_version="classifier-%s+opportunity-%s" % (
                CLASSIFIER_VERSION, OPPORTUNITY_RULES_VERSION),
            dataset_id=None)
        if persistence_store is not None:
            self._persistence = persistence_store
            self._restore_attempted = False
        # P1-12A: market-state classifier v0 (observed states with evidence,
        # never signals). Pure evaluation over peer-engine rows each summary;
        # memory (dwell/confirmation) restarts cold by design.
        self._classifier = ClassifierEngine(symbols=config.symbols)
        # P1-13A: research opportunity engine v0 (setups worth studying,
        # never orders or positions). Consumes classifications + the same
        # peer-engine rows; lifecycle memory restarts cold by design.
        self._opportunity = OpportunityEngine()
        # P1-14A: prospective setup evaluator — registers setups at
        # first DETECTED, observes forward outcomes at versioned
        # horizons. Research only; no orders, no P&L claims.
        self._prospective = ProspectiveRecorder(
            db_path=getattr(config, "db_path", None),
            enabled=True,
            store=persistence_store,
            run_id=self.run_id,
        )
        # P1-12B: dynamic universe manager (selection + lifecycle only).
        # CORE is config.symbols (protected); HOT subscriptions ride managed
        # connections that never disturb the canonical pair.
        self._universe = UniverseManager(
            core=tuple(config.symbols),
            budget={k: getattr(config.universe, k) for k in (
                "max_hot_slots", "max_total_streams",
                "max_streams_per_connection", "max_connections",
                "promotion_interval_seconds", "min_dwell_seconds",
                "demotion_cooldown_seconds", "max_discovery_age_seconds",
                "demote_after_missed_scans",
                "max_hot_reconnects_per_hour",
                "clock_skew_tolerance_ms")})
        self._hot_active: tuple = ()
        self._hot_tasks: dict = {}
        self._hot_seen: dict = {}
        self._hot_last_resync: float | None = None
        self._hot_reconnect_marks: dict = {}
        # P1-14B.3 freshness watchdog: receipt != acceptance. Tracks the
        # wall-clock ms of the last guard-ACCEPTED (hence fresh) message
        # per stream; connections with no accepted traffic beyond budget
        # get one forced reconnect through the normal retry path.
        self._last_accepted_ms: dict = {}
        # P1-14B.5: wall-clock receipt stamp per stream (pre-guard). Receipt
        # != acceptance: received-but-rejected traffic keeps this fresh while
        # _last_accepted_ms freezes — the FLOWING_STALE signature.
        self._last_receipt_wall_ms: dict = {}
        self._reconnect_requested: set = set()
        self._last_forced_reconnect_mono: dict = {}
        self._forced_reconnect_counts: dict = {}
        # P1-14B.6 host telemetry stash (probe-owned cadence sampling;
        # build_summary only embeds, never samples — dashboard reads must
        # not shorten the CPU interval).
        self._last_cpu_sample: tuple | None = None
        self._host_stats: dict = {"cpuPercentProc": None, "rssBytes": None,
                                  "cpuCount": None}
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

    @property
    def research(self) -> ResearchRecorder:
        """Prospective flow/book recorder (P1-11C, probe-owned)."""
        return self._research

    @property
    def classifier(self) -> ClassifierEngine:
        """Market-state classifier v0 (P1-12A, observed states only)."""
        return self._classifier

    def opportunity(self) -> OpportunityEngine:
        """Research opportunity engine v0 (P1-13A, research setups only)."""
        return self._opportunity

    @property
    def universe_manager(self) -> UniverseManager:
        """Dynamic universe manager (P1-12B, selection + lifecycle)."""
        return self._universe
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
        # P1-11C: research recorder starts naturally with MarketProbe.
        try:
            self._research.start()
        except Exception:
            pass
        # P1-14A: prospective recorder starts naturally with MarketProbe.
        try:
            self._prospective.start()
        except Exception:
            pass
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
            # P1-11C: recorder drains on exit (partials marked, never complete).
            try:
                self._research.stop_and_drain(timeout=10.0)
            except Exception:
                pass
            # P1-14A: prospective recorder drains on exit.
            try:
                self._prospective.stop_and_drain(timeout=10.0)
            except Exception:
                pass
            self.log_summary(final=True)
            for task in tasks:
                task.cancel()
            for task in list(self._hot_tasks.values()):
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self._hot_tasks:
                await asyncio.gather(*self._hot_tasks.values(),
                                     return_exceptions=True)
                self._hot_tasks = {}

    def stop(self) -> None:
        self._stop.set()

    async def _stop_after(self, duration_seconds: float) -> None:
        await asyncio.sleep(duration_seconds)
        self.stop()

    async def _connection_loop(self, name: str, url) -> None:
        """One reconnecting websocket connection (P1-12B: url may be a
        zero-arg callable, resolved fresh on every (re)connect so managed
        HOT groups restore exactly the desired set after any drop)."""
        delay = 1.0
        while not self._stop.is_set():
            connected_at: float | None = None
            current_url = url() if callable(url) else url
            try:
                self.stats.connection_attempts[name] += 1
                LOGGER.info(json.dumps({"kind": "connection_attempt", "endpoint": name}))
                async with websockets.connect(
                    current_url,
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
                        if self._consume_reconnect_request(name):
                            LOGGER.info(json.dumps(
                                {"kind": "forced_reconnect",
                                 "endpoint": name,
                                 "reason": "freshness-watchdog"}))
                            break
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
        # P1-14B.6: exact received bytes (per-connection network activity).
        try:
            raw_bytes = (len(raw_message.encode("utf-8"))
                         if isinstance(raw_message, str) else len(raw_message))
        except Exception:
            raw_bytes = 0
        self.stats.bytes_by_stream[stream] += raw_bytes
        self.stats.first_seen_monotonic.setdefault(stream, now_monotonic)
        self.stats.last_seen_monotonic[stream] = now_monotonic
        # P1-14B.5: receipt stamp (wall ms, pre-guard) for the diagnostic
        # health classifier. Updated for EVERY received message, including
        # ones the skew guard is about to reject.
        self._last_receipt_wall_ms[stream] = received_ms

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

            # P1-14B.3: acceptance stamp (receipt != acceptance). Only
            # guard-passing messages prove a stream is fresh; rejected
            # (stale) traffic must not refresh freshness.
            self._last_accepted_ms[stream] = received_ms

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
                    self._note_hot_data(str(payload["s"]), "depth")
                except (KeyError, TypeError, ValueError):
                    pass
                # P1-11C research hook (read-only reuse, never alters engine).
                try:
                    _bk = self._book._books.get(str(payload["s"]).upper())  # type: ignore[attr-defined]
                    if _bk is not None and _bk.features is not None:
                        self._research.record_book(
                            str(payload["s"]), int(payload["E"]),
                            _bk.features, _bk.degraded, False,
                            bool(_bk.features.get("crossed")))
                except Exception:
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
                    if self._flow.ingest(
                        symbol=str(payload["s"]),
                        event_time_ms=int(payload["E"]),
                        price=float(payload["p"]),
                        quantity=float(payload["q"]),
                        buyer_is_maker=payload.get("m"),
                        normal_quantity=payload.get("nq"),
                    ):
                        self._note_hot_data(str(payload["s"]), "trade")
                except (KeyError, TypeError, ValueError):
                    pass
                # P1-11C research hook (validated P1-06 semantics reused).
                try:
                    self._research.record_trade(
                        str(payload["s"]), int(payload["E"]),
                        float(payload["p"]), float(payload["q"]),
                        payload.get("m"))
                except Exception:
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
                # P1-12B: returns also ingest for actively subscribed HOT
                # symbols (markPrice arrays are global; the funding detector
                # above stays CORE-configured by design).
                for item in payload:
                    try:
                        sym = str(item.get("s"))
                    except (AttributeError, TypeError, ValueError):
                        continue
                    if sym in self.config.symbols:
                        continue
                    if sym not in self._hot_active:
                        continue
                    try:
                        if self._returns.ingest(
                                sym, int(item["E"]), float(item["p"])):
                            self._note_hot_data(sym, "mark")
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
            # P1-14B.3: probe-owned periodic path only (never dashboard
            # reads) — open-but-stale connections get one forced reconnect.
            self._check_connection_freshness(self._wall_clock_ms())
            # P1-14B.6: same cadence for host telemetry (CPU% needs stable
            # ~30 s intervals; sampling anywhere else would distort it).
            self._sample_host()

    def _sample_host(self) -> dict:
        """Sample process CPU%/RSS (P1-14B.6, bounded, UNKNOWN-safe).

        CPU% derives from os.times() deltas over the sampling interval
        (first call only establishes the baseline -> None). RSS via psapi
        (None on any failure, non-Windows included). NIC and system-wide
        counters are NOT available on this path and stay UNKNOWN by design;
        per-connection byte rates (bytesByStream) cover network activity.
        """
        try:
            from .telemetry import cpu_percent_proc, process_cpu_times, process_rss_bytes
            import os as _os
            cur = process_cpu_times()
            ncpu = _os.cpu_count() or None
            cpu = cpu_percent_proc(self._last_cpu_sample, cur, ncpu)
            if cur is not None:
                self._last_cpu_sample = cur
            self._host_stats = {"cpuPercentProc": cpu,
                                "rssBytes": process_rss_bytes(),
                                "cpuCount": ncpu}
        except Exception:
            pass
        return dict(self._host_stats)

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
                # P1-12B: actually-subscribed HOT set + lifecycle states.
                # Proposals (hot_dynamic) may exceed subscriptions; the two
                # are never conflated on the dashboard.
                "hot_subscribed": list(self._hot_active),
                "universe_states": self._universe.states_snapshot(),
                "tops": tops,
                "top_n": cfg.top_n,
                "min_quote_volume_usdt": cfg.min_quote_volume_usdt,
            }
            try:
                self.persistence.store_discovery_snapshot(snapshot)
                for event in events:
                    self.persistence.log_universe_event(
                        event["kind"], event["symbol"],
                        event.get("reason", ""), run_id=self.run_id)
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
            await self._sync_universe_from_scan(candidates, list(dynamic),
                                                   now_ms)
            return snapshot
        except Exception as exc:
            info["error"] = f"{type(exc).__name__}: {exc}"
            LOGGER.warning(json.dumps(
                {"kind": "discovery_error", "error": str(exc)}))
            return {"error": str(exc)}

    def _hot_transport_ok(self) -> bool:
        """Fail-closed promotion gate from HOT-endpoint reconnect pressure.

        Compares hot-endpoint reconnects since the last check; too many in
        the trailing window freezes promotions (demotions still proceed).
        Never raises; unknown counts mean "not ok".
        """
        try:
            cfg = self.config.universe
            window_s = 3600.0
            now = self._monotonic()
            total = (int(self.stats.reconnects.get("hot-public", 0))
                     + int(self.stats.reconnects.get("hot-market", 0)))
            prev_total, prev_ts = self._hot_reconnect_marks.get(
                "marks", (0, now))
            if now - prev_ts >= window_s:
                self._hot_reconnect_marks["marks"] = (total, now)
                prev_total = total
            return (total - prev_total) <= int(
                cfg.max_hot_reconnects_per_hour)
        except Exception:
            return False

    async def _sync_universe_from_scan(self, candidates, hot_dynamic,
                                       now_ms: int) -> None:
        """P1-12B: selection step + subscription sync (scan-driven only).

        Pure selection runs on every scan; transport changes (cancel +
        respawn of exactly the two managed HOT connections) happen only
        when the desired set actually changes. CORE connections are never
        touched here.
        """
        if not self.config.universe.enabled:
            return
        cand_map = {}
        for cand in candidates or []:
            try:
                cand_map[str(cand.symbol).upper()] = {
                    "eligible": bool(cand.eligible),
                    "change_24h_pct": cand.change_24h_pct,
                    "quote_volume_24h": cand.quote_volume_24h,
                    "ticker_close_ms": cand.ticker_close_ms,
                }
            except AttributeError:
                continue
        transport_ok = self._hot_transport_ok()
        try:
            decisions = self._universe.update(
                cand_map, [str(s).upper() for s in hot_dynamic or []],
                int(now_ms), scan_ms=int(now_ms),
                transport_ok=transport_ok)
        except Exception as exc:
            LOGGER.warning(json.dumps(
                {"kind": "universe_error", "error": str(exc)}))
            return
        for event in decisions.get("events", []):
            try:
                self.persistence.log_universe_event(
                    "hot_%s" % event.get("kind", "unknown"),
                    str(event.get("symbol", "?")),
                    str(event.get("reason", "")), run_id=self.run_id)
            except Exception as exc:
                LOGGER.warning(json.dumps(
                    {"kind": "persistence_error", "error": str(exc)}))
        try:
            await self._sync_hot_subscriptions(reason="discovery-scan")
        except Exception as exc:
            LOGGER.warning(json.dumps(
                {"kind": "universe_error", "error": str(exc)}))

    async def _sync_hot_subscriptions(self, reason: str = "") -> None:
        """Reconcile managed HOT connections with the desired set.

        Cancel + respawn exactly the hot-public/hot-market tasks on change;
        drain-then-forget demoted engine state (no closed-bucket loss);
        admit promoted symbols everywhere; confirm unsubscribes for
        cooldown accounting. No-ops when nothing changed.
        """
        desired = self._universe.desired_hot()
        if desired == self._hot_active:
            return
        now_mono = self._monotonic()
        if (self._hot_last_resync is not None
                and now_mono - self._hot_last_resync < 60.0
                and self._hot_tasks):
            LOGGER.info(json.dumps(
                {"kind": "hot_resync_deferred", "reason": reason,
                 "desired": list(desired)}))
            return
        self._hot_last_resync = now_mono
        old, new = set(self._hot_active), set(desired)
        # Drain closed flow buckets first so forget() cannot lose them.
        try:
            drained = self._flow.drain_completed_buckets()
            if drained:
                self.persistence.store_flow_buckets(drained)
        except Exception as exc:
            LOGGER.warning(json.dumps(
                {"kind": "persistence_error", "error": str(exc)}))
        # Cancel exactly the managed tasks (canonical pair untouched).
        for task in list(self._hot_tasks.values()):
            task.cancel()
        if self._hot_tasks:
            await asyncio.gather(*self._hot_tasks.values(),
                                 return_exceptions=True)
            self._hot_tasks = {}
        # Demoted: forget engine memory, finalize recorder buckets,
        # confirm unsubscribe (starts cooldown), drop seen-sets.
        for symbol in sorted(old - new):
            try:
                self._flow.forget(symbol)
                self._book.forget(symbol)
                self._returns.forget(symbol)
                self._oi.forget(symbol)
                self._classifier.forget(symbol)
                self._opportunity.forget(
                    symbol, "hot_demotion",
                    int(self._wall_clock_ms()))
                self._research.finalize_symbol(symbol)
                self._universe.confirm_unsubscribed(
                    [symbol], int(self._wall_clock_ms()))
            except Exception as exc:
                LOGGER.warning(json.dumps(
                    {"kind": "universe_error", "error": str(exc)}))
            self._hot_seen.pop(symbol, None)
            try:
                self.persistence.log_universe_event(
                    "hot_unsubscribed", symbol,
                    reason or "desired-set change", run_id=self.run_id)
            except Exception:
                pass
        # Promoted: admit everywhere (engines create state lazily on first
        # valid post-skew message; OI poller covers CORE + HOT, bounded).
        for symbol in sorted(new - old):
            try:
                self._flow.allow([symbol])
                self._book.allow([symbol])
                self._returns.allow([symbol])
                self._structure.allow([symbol])
                self._oi.allow([symbol])
                self._classifier.allow([symbol])
                self._opportunity.allow([symbol])
                self.persistence.log_universe_event(
                    "hot_subscribed", symbol,
                    reason or "desired-set change", run_id=self.run_id)
            except Exception as exc:
                LOGGER.warning(json.dumps(
                    {"kind": "universe_error", "error": str(exc)}))
        try:
            self._oi_poller.set_hot_symbols(sorted(new))
        except Exception:
            pass
        self._hot_active = desired
        # Spawn managed connections (none when the desired set is empty —
        # the most conservative state: zero extra connections).
        for name, url in build_hot_stream_urls(desired).items():
            self._hot_tasks[name] = asyncio.create_task(
                self._connection_loop(name, url), name=f"ws-{name}")
        LOGGER.info(json.dumps(
            {"kind": "hot_resync", "reason": reason,
             "active": list(self._hot_active)}))

    def _note_hot_data(self, symbol: str, kind: str) -> None:
        """Track first-data / readiness for HOT lifecycle (never raises)."""
        try:
            sym = str(symbol).upper()
            if sym not in self._universe.desired_hot():
                return
            seen = self._hot_seen.setdefault(sym, set())
            seen.add(str(kind))
            now_ms = int(self._wall_clock_ms())
            self._universe.note_first_data(sym, now_ms)
            if {"mark", "trade", "depth"} <= seen:
                self._universe.note_live(sym, now_ms)
        except Exception:
            pass

    def _refresh_hot_health(self, now_ms: int) -> None:
        """Mark silent HOT symbols DEGRADED; audit partial subscriptions."""
        try:
            if not self._hot_active:
                return
            now_mono = self._monotonic()
            for sym in self._hot_active:
                streams = ["%s@aggTrade" % sym.lower(),
                           "%s@bookTicker" % sym.lower(),
                           "%s@depth20@100ms" % sym.lower()]
                lasts = [self.stats.last_seen_monotonic.get(s)
                         for s in streams]
                if all(last is None or
                       now_mono - last > self.config.stale_after_seconds
                       for last in lasts):
                    self._universe.note_degraded(
                        sym, "all HOT streams silent", int(now_ms))
        except Exception:
            pass

    def _consume_reconnect_request(self, name: str) -> bool:
        """One-shot consume of a forced-reconnect request (watchdog)."""
        if name in self._reconnect_requested:
            self._reconnect_requested.discard(name)
            return True
        return False

    def _connection_health(self) -> dict:
        """Per-connection diagnostic health for the summary (P1-14B.5)."""
        out: dict = {}
        try:
            now_ms = self._wall_clock_ms()
            expected = expected_stream_names(self.config, self._hot_active)
            by_conn: dict = {}
            for stream in expected:
                conn = _connection_for_stream(
                    stream, self.config.symbols, self._hot_active)
                if conn is not None:
                    by_conn.setdefault(conn, []).append(stream)
            live = {"public", "market"}
            live.update(name for name in ("hot-public", "hot-market")
                        if name in self._hot_tasks)
            for name in sorted(live):
                streams = by_conn.get(name, [])
                receipts = [self._last_receipt_wall_ms.get(s) for s in streams]
                accepts = [self._last_accepted_ms.get(s) for s in streams]
                receipts = [v for v in receipts if v is not None]
                accepts = [v for v in accepts if v is not None]
                budget = (_HOT_MARKET_FRESHNESS_AFTER_MS
                          if name == "hot-market"
                          else _FRESHNESS_RECONNECT_AFTER_MS)
                out[name] = classify_connection_health(
                    socket_up=name in self.stats.connection_started,
                    ever_attempted=bool(
                        self.stats.connection_attempts.get(name, 0)),
                    now_wall_ms=now_ms,
                    last_receipt_wall_ms=max(receipts) if receipts else None,
                    last_accepted_wall_ms=max(accepts) if accepts else None,
                    budget_ms=budget,
                )
        except Exception as exc:
            LOGGER.warning(json.dumps(
                {"kind": "connection_health_error",
                 "error": f"{type(exc).__name__}: {exc}"}))
        return out

    def _check_connection_freshness(self, now_ms: float) -> list:
        """Freshness watchdog (P1-14B.3): request at most one forced
        reconnect per stale connection. A connection is stale when NONE
        of its streams has a guard-accepted message within budget —
        open-but-stale never triggers the error retry path on its own.
        Cooldown-guarded (no aggressive loops); connection-age graced;
        unattributable streams never fire. Returns fired names.
        """
        fired: list = []
        try:
            now_mono = self._monotonic()
            expected = expected_stream_names(self.config, self._hot_active)
            by_conn: dict = {}
            for stream in expected:
                conn = _connection_for_stream(
                    stream, self.config.symbols, self._hot_active)
                if conn is not None:
                    by_conn.setdefault(conn, []).append(stream)
            live = {"public", "market"}
            live.update(name for name in ("hot-public", "hot-market")
                        if name in self._hot_tasks)
            for name in sorted(live):
                streams = by_conn.get(name, [])
                if not streams:
                    continue
                started = self.stats.connection_started.get(name)
                if started is None or now_mono - started < _FRESHNESS_GRACE_S:
                    continue
                last = self._last_forced_reconnect_mono.get(name)
                if last is not None and now_mono - last < _FORCED_RECONNECT_COOLDOWN_S:
                    continue
                budget = (_HOT_MARKET_FRESHNESS_AFTER_MS
                          if name == "hot-market"
                          else _FRESHNESS_RECONNECT_AFTER_MS)
                freshest = max(
                    [float(self._last_accepted_ms.get(s, float("-inf")))
                     for s in streams])
                if now_ms - freshest > budget:
                    self._reconnect_requested.add(name)
                    self._last_forced_reconnect_mono[name] = now_mono
                    self._forced_reconnect_counts[name] = (
                        self._forced_reconnect_counts.get(name, 0) + 1)
                    LOGGER.info(json.dumps(
                        {"kind": "forced_reconnect_requested",
                         "endpoint": name,
                         "no_fresh_accepted_ms": round(now_ms - freshest, 1)
                         if freshest != float("-inf") else None,
                         "budget_ms": budget}))
                    fired.append(name)
        except Exception as exc:
            LOGGER.warning(json.dumps(
                {"kind": "freshness_watchdog_error",
                 "error": f"{type(exc).__name__}: {exc}"}))
        return fired

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
        expected = expected_stream_names(self.config, self._hot_active)
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
            *(f"{symbol.lower()}@depth20@100ms" for symbol in self._hot_active),
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
            "run_id": self.run_id,
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
                # P1-14B.6 additive: exact received bytes per stream (UTF-8).
                # Complements message counts: SILENT (0 B/s) vs FLOWING at
                # the byte level, per connection attributable via stream map.
                "bytesByStream": dict(self.stats.bytes_by_stream),
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
            # P1-12A additive block: classifier eval counts + state census
            # (observed HYPOTHESIS states with evidence — never signals).
            "states": self._classifier.stats(),
            # P1-13A additive block: opportunity eval counts + open census
            # (research setups with evidence — never orders or positions).
            "opportunities": self._opportunity.stats(),
            # P1-12B additive block: dynamic-universe desired set, lifecycle
            # states, slot/stream budgets, promotion/demotion counters.
            "universe": self._universe.stats(),
             # P1-11C additive block: prospective recorder health (never
             # conflated with engine/feed health). Failure-isolated.
             "research": self._research.status(),
             # P1-14A additive block: prospective setup evaluator
             # (forward outcome observation for research setups).
             "prospective": self._prospective.status(),
             # P1-14B.3 additive block: freshness observability — receipt
             # != acceptance. Connected/message counts never imply health;
             # this block separates them (last guard-accepted ms per
             # stream, pending forced reconnects, forced counts).
             # P1-14B.5 additive: per-connection diagnostic health
             # (socket vs FLOWING_FRESH/FLOWING_STALE/SILENT/RECONNECTING/
             # UNAVAILABLE) with evidence; missing data stays None.
             "freshness": {
                 "lastAcceptedMsByStream": dict(self._last_accepted_ms),
                 "lastReceiptMsByStream": dict(self._last_receipt_wall_ms),
                 "reconnectRequested": sorted(self._reconnect_requested),
                 "forcedReconnects": dict(self._forced_reconnect_counts),
                 "connectionHealth": self._connection_health(),
             },
             # P1-14B.6 additive block: host telemetry (process-scoped only).
             # cpuPercentProc/r/rssBytes are None (UNKNOWN) before the first
             # probe-owned sample or when the OS refuses; NIC and system-wide
             # CPU stay UNKNOWN by design (see _sample_host).
             "host": dict(self._host_stats),
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
        # P1-12B: refresh HOT stream health before snapshotting so silent
        # HOT symbols read DEGRADED (never silently LIVE).
        try:
            self._refresh_hot_health(int(self._wall_clock_ms()))
        except Exception:
            pass
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
            book_rows_list = self._book.snapshot_all(as_of_ms)
            self.persistence.store_book_features(book_rows_list)
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
                oi_rows_list := self._oi.snapshot_all(as_of_ms, price_returns_1m))
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
            # P1-12A (additive): evaluate the market-state classifier over
            # the same peer-engine rows (no new ingest, no new endpoint).
            # Observed states with evidence only — never signals. Restart
            # restarts dwell/confirmation memory cold by design.
            book_rows = {str(b.get("symbol", "UNKNOWN")): b
                         for b in book_rows_list
                         if isinstance(b, dict)}
            oi_rows = {str(o.get("symbol", "UNKNOWN")): o
                       for o in oi_rows_list
                       if isinstance(o, dict)}
            struct_rows = {str(s.get("symbol", "UNKNOWN")): s
                           for s in structure_rows
                           if isinstance(s, dict)}
            state_inputs: dict[str, dict[str, Any]] = {}
            for symbol in sorted(set(flow_rows) | set(price_rows)):
                prow = price_rows.get(symbol) or {}
                frow = flow_rows.get(symbol) or {}
                tier = str(prow.get("tier", "DISCOVERY"))
                state_inputs[symbol] = {
                    "subscribed": bool(frow.get("subscribed", False))
                    or tier in ("CORE", "HOT"),
                    "live": bool(frow.get("live", False))
                    and tier in ("CORE", "HOT"),
                    "tier": tier,
                    "price": prow,
                    "returns": prow,
                    "momentum": prow.get("momentum")
                    if isinstance(prow.get("momentum"), dict) else {},
                    "flow": frow,
                    "book": (book_rows.get(symbol) or {}).get("book")
                    if isinstance((book_rows.get(symbol) or {}).get("book"),
                                  dict) else {},
                    "oi": oi_rows.get(symbol)
                    if isinstance(oi_rows.get(symbol), dict) else {},
                    "structure": struct_rows.get(symbol)
                    if isinstance(struct_rows.get(symbol), dict) else {},
                }
            eval_start_ns = self._perf_counter_ns()
            states = self._classifier.evaluate(state_inputs, as_of_ms)
            eval_ms = (self._perf_counter_ns() - eval_start_ns) / 1_000_000
            self._classifier.note_eval_ms(eval_ms)
            self.persistence.store_state_features(
                [dict(s) for s in states])
            for st in states:
                trans = st.get("transition") or {}
                if trans.get("changed") and trans.get("previous_state") \
                        is not None:
                    reasons = trans.get("reasons") or []
                    self.persistence.log_state_transition(
                        str(st.get("symbol", "UNKNOWN")),
                        trans.get("previous_state"), str(st.get("state")),
                        trans.get("previous_direction"),
                        str(st.get("direction")),
                        "; ".join(str(r) for r in reasons[:3]))
            # P1-13A (additive): evaluate the research opportunity engine
            # over the same peer-engine rows + fresh classifications
            # (states consumed, never recomputed). Research setups only —
            # never orders, entries, or positions. Restart restarts
            # lifecycle memory cold by design.
            states_by_symbol = {str(s.get("symbol", "UNKNOWN")): dict(s)
                                for s in states if isinstance(s, dict)}
            dq_block = summary.get("dataQuality") if isinstance(
                summary, dict) else {}
            stale_streams = set((dq_block or {}).get("staleStreams") or [])
            opp_bundles: dict[str, dict[str, Any]] = {}
            for symbol, inp in state_inputs.items():
                sym = str(symbol).upper()
                degraded = any(sym.lower() in str(st)
                               or str(st) == "!markPrice@arr@1s"
                               for st in stale_streams)
                price_row = inp.get("price") if isinstance(
                    inp.get("price"), dict) else {}
                opp_bundles[sym] = {
                    "tier": inp.get("tier", "DISCOVERY"),
                    "subscribed": inp.get("subscribed", False),
                    "live": inp.get("live", False),
                    "market": "%s USDT-M PERP" % sym,
                    "classification": states_by_symbol.get(sym, {}),
                    "features": {
                        "price": price_row,
                        "current_price": price_row.get("current_price"),
                        "sample_age_ms": price_row.get("sample_age_ms"),
                        "returns": inp.get("returns", {}),
                        "momentum": inp.get("momentum", {}),
                        "flow": inp.get("flow", {}),
                        "book": inp.get("book", {}),
                        "oi": inp.get("oi", {}),
                        "structure": inp.get("structure", {}),
                    },
                    "transport": {
                        "degraded": bool(degraded),
                        "reason": ("stale mandatory stream; setup held "
                                   "INSUFFICIENT_DATA" if degraded else "ok"),
                    },
                }
            opp_start_ns = self._perf_counter_ns()
            opp_matched, _opp_rejected = self._opportunity.evaluate(
                opp_bundles, as_of_ms)
            self._opportunity.note_eval_ms(
                (self._perf_counter_ns() - opp_start_ns) / 1_000_000)
            self.persistence.store_opportunity_candidates(opp_matched)
            watch_need = int(self._opportunity.rules.get("watching_evals", 2))
            active_need = int(self._opportunity.rules.get(
                "active_research_evals", 3))
            for cand in opp_matched:
                evals = int(cand.get("evals_in_lifecycle", 1))
                lifecycle = str(cand.get("lifecycle", ""))
                if (lifecycle == "DETECTED" and evals <= 1) or (
                        lifecycle == "WATCHING" and evals == watch_need) or (
                        lifecycle == "ACTIVE_RESEARCH"
                        and evals == active_need):
                    self.persistence.log_opportunity_event(
                        str(cand.get("candidate_key")),
                        str(cand.get("symbol", "UNKNOWN")),
                        str(cand.get("setup_family", "?")),
                        "-> %s" % lifecycle,
                        str(cand.get("lifecycle_reason", ""))[:300])
            for closed in self._opportunity.drain_closed_events():
                self.persistence.log_opportunity_event(
                    str(closed.get("candidate_key")),
                    str(closed.get("symbol", "UNKNOWN")),
                    str(closed.get("family", "?")),
                    "-> %s" % str(closed.get("transition", "?")),
                    str(closed.get("reason", ""))[:300])
            # P1-14A: register DETECTED setups (with detection mark price).
            # Registration is per-candidate_key, so re-registering the same
            # episode is idempotent.
            for cand in opp_matched:
                sym = str(cand.get("symbol", "")).upper()
                price_row = opp_bundles.get(sym, {}).get(
                    "features", {}).get("price", {})
                mark = price_row.get("current_price")
                lifecycle = str(cand.get("lifecycle", ""))
                evals = int(cand.get("evals_in_lifecycle", 1))
                if lifecycle == "DETECTED" and evals <= 1:
                    self._prospective.register_setup(
                        str(cand.get("candidate_key")),
                        {
                            "setup_family": cand.get("setup_family"),
                            "direction": cand.get("direction"),
                            "market_state": cand.get("market_state"),
                            "rule_version": cand.get("rule_version"),
                            "capability_tier": cand.get("capability_tier"),
                            "symbol": cand.get("symbol"),
                            "ranking": cand.get("ranking", {}),
                            "lifecycle": lifecycle,
                            "evidence_for": cand.get("evidence_for", []),
                            "evidence_against": cand.get(
                                "evidence_against", []),
                            "missing_features": cand.get(
                                "missing_features", []),
                            "data_freshness": cand.get(
                                "data_freshness", {}),
                            "detect_price": float(mark) if mark is not None else None,
                        },
                        as_of_ms,
                    )
            # P1-14B.1: observe forward outcomes once per summary cycle for
            # every evaluated symbol (per the spec Observation section),
            # independent of candidate matches so quiet ticks still mature
            # registered setups; per-symbol so multi-candidate ticks
            # observe once.
            for sym, bundle in opp_bundles.items():
                features = bundle.get("features", {})
                price_row = features.get("price", {}) if isinstance(
                    features, dict) else {}
                mark = price_row.get("current_price") if isinstance(
                    price_row, dict) else None
                # P1-14B.3: carry the quote age so horizons maturing on a
                # stale mark record PENDING (explicit reason) instead of a
                # stale-price COMPLETE. Unknown/malformed age stays fail-open.
                age = price_row.get("sample_age_ms") if isinstance(
                    price_row, dict) else None
                try:
                    age_arg = float(age) if age is not None else None
                except (TypeError, ValueError):
                    age_arg = None
                if mark is not None:
                    self._prospective.observe(
                        str(sym).upper(), as_of_ms, float(mark),
                        mark_age_ms=age_arg)
        except Exception as exc:
            LOGGER.warning(json.dumps({"kind": "persistence_error", "error": str(exc)}))
        LOGGER.info(json.dumps(summary, sort_keys=True, allow_nan=False))
