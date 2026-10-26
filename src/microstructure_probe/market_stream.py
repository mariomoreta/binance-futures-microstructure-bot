"""market-stream/v1 — hub de suscripciones kline con reconciliacion.

Reutiliza la politica de conexion ya auditada en ``probe.py`` (timeouts, ping,
backoff) y el cliente REST publico de ``history_client.py``. NO abre
suscripciones del bot, NO toca el trio canonico y NO persiste actualizaciones.

Responsabilidad unica: mantener, por ``(symbol, interval)``, el estado real de la
vela en formacion y de las velas cerradas, con:
  * refcount de consumidores (una sola conexion al exchange, muchos lectores),
  * buffer + reconciliacion entre snapshot y stream (sin huecos ni duplicados),
  * deteccion de velas atrasadas / fuera de orden / invalidas,
  * deteccion de huecos con reparacion REST acotada y honesta.

Todo el estado vive en memoria. Nada se escribe en disco.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import re
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Deque, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .history_client import INTERVAL_MS
from .market_explorer import EXPLORABLE_INTERVALS

STREAM_CONTRACT_VERSION = "market-stream/v1"
VENUE = "binance"
MARKET_TYPE = "usd_m_futures"
WS_BASE_URL = "wss://fstream.binance.com"
WS_ROUTE = "/market"  # los klines pertenecen a Market (no a Public)
SOURCE_WS = "ws_kline"

# Frescura: un socket abierto no es LIVE. Exige datos del simbolo/intervalo
# solicitado y suficientemente recientes.
FRESH_MS = 10_000
STALE_MS = 60_000

# Presupuesto (ver docs/MARKET_STREAM_CONTRACT_V1.md §8).
MAX_SUBSCRIPTIONS = 6
MAX_CONSUMERS_PER_STREAM = 4
MAX_TOTAL_CONSUMERS = 12
RING_SIZE = 300
PENDING_MAX = 256
CONSUMER_QUEUE_MAX = 256
IDLE_GRACE_MS = 30_000
HEARTBEAT_S = 5.0

# Reconexion.
RECONNECT_BASE_S = 1.0
RECONNECT_MAX_S = 30.0
RECONNECT_JITTER = 0.25
RETRY_BUDGET = 20
CONTROL_MIN_INTERVAL_S = 0.5  # <= 2 mensajes/s (limite oficial 10/s)

# Reparacion REST de huecos.
RECOVERY_MAX_PAGES = 2
RECOVERY_PAGE_LIMIT = 500
RECOVERY_MIN_INTERVAL_MS = 15_000
RECOVERY_MAX_PER_MINUTE = 6
RECOVERY_MAX_BARS = RECOVERY_MAX_PAGES * RECOVERY_PAGE_LIMIT

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,32}$")

COUNTER_KEYS = (
    "messages", "applied", "closed", "duplicate", "late", "out_of_order",
    "invalid", "unrouted", "identity_mismatch", "gaps", "gap_recovered_bars",
    "recoveries", "recovery_failures", "dropped_consumers",
)


def now_ms(clock: Callable[[], float] = time.time) -> int:
    return int(clock() * 1000)


def interval_ms(interval: str) -> Optional[int]:
    return INTERVAL_MS.get(str(interval or ""))


def stream_name(symbol: str, interval: str) -> str:
    return f"{symbol.lower()}@kline_{interval}"


def _num(value: Any) -> Optional[float]:
    """Convierte una cadena numerica del exchange sin inventar valores."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def normalize_kline(data: Dict[str, Any], received_ms: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Normaliza un payload ``kline`` del exchange.

    Devuelve ``(candle, None)`` si es utilizable o ``(None, code)`` si debe
    descartarse. Nunca completa OHLC ausente con ceros ni interpolacion.
    """
    if not isinstance(data, dict):
        return None, "invalid"
    if data.get("e") != "kline":
        return None, "unrouted"
    kline = data.get("k")
    if not isinstance(kline, dict):
        return None, "invalid"
    symbol = str(data.get("s") or kline.get("s") or "").upper()
    interval = str(kline.get("i") or "")
    open_ms = _int_or_none(kline.get("t"))
    close_ms = _int_or_none(kline.get("T"))
    event_ms = _int_or_none(data.get("E"))
    closed_raw = kline.get("x")
    if not _SYMBOL_RE.match(symbol) or interval not in EXPLORABLE_INTERVALS:
        return None, "identity_mismatch"
    if open_ms is None or close_ms is None or event_ms is None or not isinstance(closed_raw, bool):
        return None, "invalid"
    step = interval_ms(interval)
    if step is None or close_ms < open_ms:
        return None, "invalid"
    open_px = _num(kline.get("o"))
    high_px = _num(kline.get("h"))
    low_px = _num(kline.get("l"))
    close_px = _num(kline.get("c"))
    if None in (open_px, high_px, low_px, close_px):
        return None, "invalid"
    return {
        "symbol": symbol,
        "interval": interval,
        "interval_ms": step,
        "stream": stream_name(symbol, interval),
        "open_time_ms": open_ms,
        "close_time_ms": (close_ms if closed_raw else None),
        "open": open_px,
        "high": high_px,
        "low": low_px,
        "close": close_px,
        "base_volume": _num(kline.get("v")),
        "quote_volume": _num(kline.get("q")),
        "trade_count": _int_or_none(kline.get("n")),
        "closed": bool(closed_raw),
        "event_ms": event_ms,
        "received_ms": int(received_ms),
        "source": SOURCE_WS,
    }, None


@dataclass
class Consumer:
    """Lector SSE de una suscripcion."""

    id: str
    queue: "asyncio.Queue[Optional[Tuple[str, Dict[str, Any]]]]"
    deliver_from_ms: Optional[int] = None  # None = handshake (buffer)
    closed: bool = False
    sent: int = 0
    dropped: int = 0

    def offer(self, event: str, payload: Dict[str, Any]) -> bool:
        """Encola sin bloquear. False si la cola esta llena (consumidor lento)."""
        if self.closed:
            return False
        try:
            self.queue.put_nowait((event, payload))
        except asyncio.QueueFull:
            self.closed = True
            self.dropped += 1
            try:
                self.queue.put_nowait(None)
            except asyncio.QueueFull:
                pass
            return False
        self.sent += 1
        return True


@dataclass
class Subscription:
    symbol: str
    interval: str
    step_ms: int
    consumers: Dict[str, Consumer] = field(default_factory=dict)
    ring: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=RING_SIZE))
    current: Optional[Dict[str, Any]] = None
    closed_through_ms: Optional[int] = None
    last_open_ms: Optional[int] = None
    last_event_ms: Optional[int] = None
    last_received_ms: Optional[int] = None
    first_message_ms: Optional[int] = None
    pending: Deque[Tuple[str, Dict[str, Any]]] = field(default_factory=deque)
    pending_overflow: bool = False
    counters: Counter = field(default_factory=Counter)
    idle_since_ms: Optional[int] = None
    recovering: bool = False
    recovery_last_ms: Optional[int] = None
    recovery_requests: int = 0
    seq: int = 0

    @property
    def key(self) -> Tuple[str, str]:
        return (self.symbol, self.interval)

    @property
    def stream(self) -> str:
        return stream_name(self.symbol, self.interval)

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq


RecoveryFn = Callable[[str, str, int, int], Awaitable[Dict[str, Any]]]


class KlineStreamHub:
    """Estado autoritativo de las velas suscritas y reparto a consumidores.

    Es agnostico al transporte: el transporte real llama a ``on_message`` con el
    texto crudo del socket; las pruebas hacen lo mismo con JSON simulado.
    """

    def __init__(
        self,
        *,
        recovery: Optional[RecoveryFn] = None,
        clock: Callable[[], float] = time.time,
        max_subscriptions: int = MAX_SUBSCRIPTIONS,
        max_consumers: int = MAX_TOTAL_CONSUMERS,
        max_consumers_per_stream: int = MAX_CONSUMERS_PER_STREAM,
        fresh_ms: int = FRESH_MS,
        stale_ms: int = STALE_MS,
        idle_grace_ms: int = IDLE_GRACE_MS,
        recovery_min_interval_ms: int = RECOVERY_MIN_INTERVAL_MS,
        recovery_max_per_minute: int = RECOVERY_MAX_PER_MINUTE,
    ) -> None:
        self._recovery = recovery
        self._clock = clock
        self.max_subscriptions = int(max_subscriptions)
        self.max_consumers = int(max_consumers)
        self.max_consumers_per_stream = int(max_consumers_per_stream)
        self.fresh_ms = int(fresh_ms)
        self.stale_ms = int(stale_ms)
        self.idle_grace_ms = int(idle_grace_ms)
        self.recovery_min_interval_ms = int(recovery_min_interval_ms)
        self.recovery_max_per_minute = int(recovery_max_per_minute)
        self.subs: Dict[Tuple[str, str], Subscription] = {}
        self.socket_connected = False
        self.socket_since_ms: Optional[int] = None
        self.socket_attempts = 0
        self.socket_reconnects = 0
        self.last_socket_error: Optional[str] = None
        self.force_reconnect = False
        self.changed = asyncio.Event()
        self._recovery_times: Deque[int] = deque()
        self._tasks: Set[asyncio.Task] = set()
        self.started_at_ms = self.now()
        self.rejected_subscriptions = 0
        # Crece en cada alta: permite al transporte distinguir "un consumidor
        # nuevo volvio a pedir el stream" de "sigue vacio".
        self.subscription_generation = 0
        self._consumer_seq = 0

    # --- utilidades -----------------------------------------------------
    def now(self) -> int:
        return now_ms(self._clock)

    def _notify_change(self) -> None:
        self.changed.set()

    def _task(self, coro: Awaitable[Any]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def desired_streams(self) -> List[str]:
        return sorted(sub.stream for sub in self.subs.values() if sub.consumers)

    def wait_change(self, timeout: Optional[float] = None) -> Awaitable[bool]:
        async def _wait() -> bool:
            self.changed.clear()
            try:
                await asyncio.wait_for(self.changed.wait(), timeout)
            except asyncio.TimeoutError:
                return False
            return True

        return _wait()

    # --- ciclo de vida de consumidores ---------------------------------
    def subscribe(self, symbol: str, interval: str, window: Optional[Dict[str, Any]] = None,
                  consumer_id: Optional[str] = None) -> Tuple[Optional[Consumer], Optional[str]]:
        """Alta de un consumidor. Devuelve (consumer, error) sin abrir socket."""
        sym = str(symbol or "").strip().upper()
        itv = str(interval or "").strip()
        if not _SYMBOL_RE.match(sym):
            return None, "INVALID_SYMBOL"
        if itv not in EXPLORABLE_INTERVALS:
            return None, "INVALID_INTERVAL"
        key = (sym, itv)
        sub = self.subs.get(key)
        active = sum(1 for s in self.subs.values() if s.consumers)
        if sub is None:
            if active >= self.max_subscriptions:
                # Liberar suscripciones inactivas (sin consumidores) antes de
                # negar la nueva: no cuestan nada y no estan en uso.
                for stale_key, stale in list(self.subs.items()):
                    if not stale.consumers:
                        self._drop(stale_key)
                active = sum(1 for s in self.subs.values() if s.consumers)
            if active >= self.max_subscriptions:
                self.rejected_subscriptions += 1
                return None, "MAX_SUBSCRIPTIONS"
            sub = Subscription(symbol=sym, interval=itv, step_ms=interval_ms(itv) or 0)
            self.subs[key] = sub
        elif not sub.consumers and active >= self.max_subscriptions:
            for stale_key, stale in list(self.subs.items()):
                if stale_key != key and not stale.consumers:
                    self._drop(stale_key)
            active = sum(1 for s in self.subs.values() if s.consumers)
            if active >= self.max_subscriptions:
                self.rejected_subscriptions += 1
                return None, "MAX_SUBSCRIPTIONS"
        if len(sub.consumers) >= self.max_consumers_per_stream:
            return None, "MAX_CONSUMERS"
        if self.total_consumers() >= self.max_consumers:
            return None, "MAX_CONSUMERS"
        cid = consumer_id or f"{sym}:{itv}:{self.now()}"
        if not consumer_id:
            self._consumer_seq += 1
            cid = f"{sym}:{itv}:{self.now()}:{self._consumer_seq}"
        consumer = Consumer(
            id=cid, queue=asyncio.Queue(maxsize=CONSUMER_QUEUE_MAX),
            deliver_from_ms=None,
        )
        sub.consumers[cid] = consumer
        sub.idle_since_ms = None
        self.subscription_generation += 1
        self._notify_change()
        return consumer, None

    def ready(self, consumer: Consumer, last_snapshot_open_ms: Optional[int]) -> None:
        """Cierra el handshake: fija el punto de entrega y vacia el buffer."""
        sub = self._sub_for(consumer.id)
        if sub is None:
            return
        deliver_from = int(last_snapshot_open_ms) if last_snapshot_open_ms is not None else 0
        consumer.deliver_from_ms = deliver_from
        if sub.pending_overflow:
            self._emit_to(consumer, "gap", {
                "symbol": sub.symbol, "interval": sub.interval,
                "reason": "BUFFER_OVERFLOW",
                "status": "partial", "missing": [], "requests": 0,
                "expected_from_ms": deliver_from or None,
                "expected_to_ms": sub.last_open_ms,
                "note": "buffer de handshake desbordado: puede faltar tramo",
            })
        self._flush_pending(sub)
        if not any(c.deliver_from_ms is None for c in sub.consumers.values()):
            sub.pending.clear()
            sub.pending_overflow = False

    def unsubscribe(self, consumer: Consumer) -> None:
        sub = self._sub_for(consumer.id)
        consumer.closed = True
        if sub is None:
            return
        sub.consumers.pop(consumer.id, None)
        if not sub.consumers:
            sub.idle_since_ms = self.now()
        self._notify_change()

    def total_consumers(self) -> int:
        return sum(len(sub.consumers) for sub in self.subs.values())

    def consumer_status(self, consumer: Consumer) -> Optional[Dict[str, Any]]:
        """Estado actual de la suscripcion que atiende ``consumer``."""
        sub = self._sub_for(consumer.id)
        return self._status_payload(sub) if sub is not None else None

    def _sub_for(self, consumer_id: str) -> Optional[Subscription]:
        for sub in self.subs.values():
            if consumer_id in sub.consumers:
                return sub
        return None

    def subscription_info(self, symbol: str, interval: str) -> Dict[str, Any]:
        """observacion READ-ONLY: consumidores de una suscripcion.

        Sirve para acreditar suscripciones COMPARTIDAS (no se duplica la
        suscripcion del benchmark) sin alterar el refcount.
        """
        sub = self.subs.get((str(symbol or "").strip().upper(),
                             str(interval or "").strip()))
        return {"exists": sub is not None,
                "consumers": len(sub.consumers) if sub is not None else 0}

    def _drop(self, key: Tuple[str, str]) -> None:
        self.subs.pop(key, None)
        self._notify_change()

    def release_idle(self) -> List[str]:
        """Libera suscripciones sin consumidores tras la gracia configurada."""
        now = self.now()
        released: List[str] = []
        for key, sub in list(self.subs.items()):
            if sub.consumers or sub.idle_since_ms is None:
                continue
            if now - sub.idle_since_ms >= self.idle_grace_ms:
                released.append(sub.stream)
                self._drop(key)
        return released

    # --- entrada del transporte ----------------------------------------
    def on_socket_open(self) -> None:
        self.socket_connected = True
        self.socket_since_ms = self.now()
        self.socket_attempts += 1
        self.force_reconnect = False
        # Tras una reconexion hay que reparar lo que pudo cerrarse mientras no
        # habia socket: se marca RECOVERING y se pide REST acotado.
        for sub in self.subs.values():
            if not sub.consumers:
                continue
            if sub.closed_through_ms is not None and \
                    (sub.last_received_ms is None
                     or self.now() - sub.last_received_ms > sub.step_ms):
                self._schedule_recovery(sub, sub.closed_through_ms, self.now(),
                                        reason="RECONNECT")

    def on_socket_closed(self, error: Optional[str] = None) -> None:
        self.socket_connected = False
        self.socket_since_ms = None
        if error:
            self.last_socket_error = error[:300]
            self.socket_reconnects += 1
        for sub in self.subs.values():
            self._emit_status(sub)

    def on_message(self, raw: Any) -> str:
        """Procesa un mensaje crudo del socket. Devuelve un codigo de resultado."""
        received = self.now()
        try:
            payload = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else raw
        except (ValueError, TypeError):
            for sub in self.subs.values():
                sub.counters["invalid"] += 1
            return "invalid"
        if not isinstance(payload, dict):
            return "invalid"
        envelope_stream = payload.get("stream")
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            return "invalid"
        if data.get("e") == "serverShutdown":
            self.force_reconnect = True
            return "server_shutdown"
        candle, error = normalize_kline(data, received)
        if candle is None:
            sub = self._sub_by_stream(str(envelope_stream or "")) or \
                self._sub_by_identity(data)
            if sub is not None:
                sub.counters[error or "invalid"] += 1
            else:
                for candidate in self.subs.values():
                    candidate.counters[error or "invalid"] += 1
                if not self.subs:
                    return error or "invalid"
            return error or "invalid"
        sub = self.subs.get((candle["symbol"], candle["interval"]))
        if envelope_stream and str(envelope_stream) != candle["stream"]:
            # Sobre y payload no coinciden: mensaje corrupto o mal enrutado.
            if sub is not None:
                sub.counters["identity_mismatch"] += 1
            return "identity_mismatch"
        if sub is None or not sub.consumers:
            if sub is not None:
                sub.counters["unrouted"] += 1
            return "unrouted"
        return self._apply(sub, candle, received)

    def _sub_by_stream(self, name: str) -> Optional[Subscription]:
        for sub in self.subs.values():
            if sub.stream == name:
                return sub
        return None

    def _sub_by_identity(self, data: Dict[str, Any]) -> Optional[Subscription]:
        kline = data.get("k") if isinstance(data.get("k"), dict) else {}
        symbol = str(data.get("s") or kline.get("s") or "").upper()
        interval = str(kline.get("i") or "")
        return self.subs.get((symbol, interval))

    def _apply(self, sub: Subscription, candle: Dict[str, Any], received: int) -> str:
        sub.counters["messages"] += 1
        open_ms = int(candle["open_time_ms"])
        if sub.closed_through_ms is not None and open_ms < sub.closed_through_ms:
            sub.counters["late"] += 1
            self._emit_status(sub)
            return "late"
        if sub.last_open_ms == open_ms and sub.last_event_ms is not None \
                and int(candle["event_ms"]) < sub.last_event_ms:
            sub.counters["out_of_order"] += 1
            return "out_of_order"

        previous = sub.current if (sub.current and sub.current["open_time_ms"] == open_ms) else None
        if previous is not None and not candle["closed"] and _same_candle(previous, candle):
            sub.counters["duplicate"] += 1
            sub.last_received_ms = received
            return "duplicate"

        sub.first_message_ms = sub.first_message_ms or received
        sub.last_received_ms = received
        sub.last_event_ms = int(candle["event_ms"])
        sub.last_open_ms = open_ms

        payload = self._public_candle(sub, candle)
        if candle["closed"]:
            self._detect_gap(sub, open_ms)
            sub.closed_through_ms = open_ms + sub.step_ms
            sub.current = None
            sub.ring.append(payload)
            sub.counters["closed"] += 1
            sub.counters["applied"] += 1
            self._publish(sub, "closed", payload)
        else:
            sub.current = payload
            sub.counters["applied"] += 1
            self._publish(sub, "candle", payload)
        self._emit_status(sub)
        return "closed" if candle["closed"] else "applied"

    def _public_candle(self, sub: Subscription, candle: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "symbol": sub.symbol,
            "interval": sub.interval,
            "open_time_ms": int(candle["open_time_ms"]),
            "close_time_ms": candle["close_time_ms"],
            "open": candle["open"],
            "high": candle["high"],
            "low": candle["low"],
            "close": candle["close"],
            "base_volume": candle["base_volume"],
            "quote_volume": candle["quote_volume"],
            "trade_count": candle["trade_count"],
            "closed": bool(candle["closed"]),
            "event_ms": int(candle["event_ms"]),
            "received_ms": int(candle["received_ms"]),
            "source": SOURCE_WS,
            "seq": sub.next_seq(),
        }

    def _publish(self, sub: Subscription, event: str, payload: Dict[str, Any]) -> None:
        handshaking = [c for c in sub.consumers.values() if c.deliver_from_ms is None]
        open_ms = payload.get("open_time_ms")
        if handshaking:
            if len(sub.pending) >= PENDING_MAX:
                sub.pending.popleft()
                sub.pending_overflow = True
            sub.pending.append((event, payload))
        for consumer in sub.consumers.values():
            start = consumer.deliver_from_ms
            if start is None:
                continue
            if open_ms is not None and int(open_ms) < start:
                continue
            self._emit_to(consumer, event, payload)

    def _flush_pending(self, sub: Subscription) -> None:
        if not sub.pending:
            return
        latest: Dict[int, Tuple[str, Dict[str, Any]]] = {}
        for event, payload in sub.pending:
            key = int(payload["open_time_ms"])
            previous = latest.get(key)
            # Cerrada gana sobre provisional.
            if previous is not None and previous[0] == "closed":
                continue
            latest[key] = (event, payload)
        for open_ms in sorted(latest):
            event, payload = latest[open_ms]
            for consumer in sub.consumers.values():
                if consumer.deliver_from_ms is None:
                    continue
                if open_ms < consumer.deliver_from_ms:
                    continue
                self._emit_to(consumer, event, payload)
        sub.pending.clear()
        sub.pending_overflow = False

    def _emit_to(self, consumer: Consumer, event: str, payload: Dict[str, Any]) -> None:
        if consumer.deliver_from_ms is None:
            return
        if not consumer.offer(event, payload):
            sub = self._sub_for(consumer.id)
            if sub is not None:
                sub.counters["dropped_consumers"] += 1
                sub.consumers.pop(consumer.id, None)
                if not sub.consumers:
                    sub.idle_since_ms = self.now()
                self._notify_change()

    def _emit_status(self, sub: Subscription) -> None:
        payload = self._status_payload(sub)
        for consumer in sub.consumers.values():
            if consumer.deliver_from_ms is not None:
                consumer.offer("status", payload)

    def _status_payload(self, sub: Subscription) -> Dict[str, Any]:
        state, age, live = self.state_for(sub)
        return {
            "symbol": sub.symbol,
            "interval": sub.interval,
            "connection": {
                "state": state,
                "socket_connected": self.socket_connected,
                "fresh_ms": self.fresh_ms,
                "stale_ms": self.stale_ms,
            },
            "last_message_ms": sub.last_received_ms,
            "last_kline_open_ms": sub.last_open_ms,
            "closed_through_ms": sub.closed_through_ms,
            "age_ms": age,
            "live": live,
            "recovering": sub.recovering,
            "generated_at_ms": self.now(),
        }

    # --- estado / frescura ---------------------------------------------
    def state_for(self, sub: Subscription) -> Tuple[str, Optional[int], bool]:
        age = (self.now() - sub.last_received_ms) if sub.last_received_ms else None
        if sub.recovering:
            state = "RECOVERING"
        elif sub.last_received_ms is None:
            # Aun sin primer mensaje del simbolo/intervalo: conectando si no hay
            # un fallo de socket registrado; si ya fallo, se declara desconectado.
            state = "CONNECTING" if self.last_socket_error is None else "DISCONNECTED"
        elif not self.socket_connected:
            state = "DISCONNECTED"
        elif age <= self.fresh_ms:
            state = "RECEIVING"
        elif age <= self.stale_ms:
            state = "STALE"
        else:
            state = "DISCONNECTED"
        live = (
            state == "RECEIVING"
            and self.socket_connected
            and age is not None
            and age <= self.fresh_ms
            and sub.last_received_ms is not None
        )
        return state, age, live

    # --- huecos y reparacion -------------------------------------------
    def _detect_gap(self, sub: Subscription, closed_open_ms: int) -> None:
        expected = sub.closed_through_ms
        if expected is None:
            return
        if closed_open_ms <= expected:
            return
        gap_start = expected
        gap_end = closed_open_ms - sub.step_ms
        if gap_end < gap_start:
            return
        sub.counters["gaps"] += 1
        self._publish(sub, "gap", {
            "symbol": sub.symbol, "interval": sub.interval,
            "reason": "MISSING_CLOSED_CANDLES",
            "status": "detected",
            "expected_from_ms": gap_start, "expected_to_ms": gap_end,
            "missing": [[gap_start, gap_end]],
            "requests": 0,
        })
        self._schedule_recovery(sub, gap_start, gap_end, reason="GAP")

    def _schedule_recovery(self, sub: Subscription, start_ms: int, end_ms: int,
                           reason: str = "GAP") -> None:
        if self._recovery is None or sub.recovering:
            return
        now = self.now()
        self._recovery_times = deque(t for t in self._recovery_times
                                     if now - t <= 60_000)
        if len(self._recovery_times) >= self.recovery_max_per_minute:
            self._publish(sub, "gap", {
                "symbol": sub.symbol, "interval": sub.interval, "reason": reason,
                "status": "failed",
                "expected_from_ms": int(start_ms), "expected_to_ms": int(end_ms),
                "missing": [[int(start_ms), int(end_ms)]], "requests": 0,
                "detail": "RECOVERY_BUDGET_EXHAUSTED",
            })
            return
        if sub.recovery_last_ms is not None and \
                now - sub.recovery_last_ms < self.recovery_min_interval_ms:
            return
        span = int(end_ms) - int(start_ms) + sub.step_ms
        if span > RECOVERY_MAX_BARS * sub.step_ms:
            start_ms = int(end_ms) - (RECOVERY_MAX_BARS - 1) * sub.step_ms
        sub.recovering = True
        sub.recovery_last_ms = now
        self._recovery_times.append(now)
        self._emit_status(sub)
        self._task(self._run_recovery(sub, int(start_ms), int(end_ms), reason))

    async def _run_recovery(self, sub: Subscription, start_ms: int, end_ms: int,
                            reason: str) -> None:
        assert self._recovery is not None
        try:
            result = await self._recovery(sub.symbol, sub.interval, start_ms, end_ms)
        except Exception as exc:  # pragma: no cover - defensivo
            result = {"status": "failed", "candles": [], "requests": 0,
                      "missing": [[start_ms, end_ms]], "detail": str(exc)}
        recovered = result.get("candles") or []
        for candle in recovered:
            open_ms = int(candle["open_time_ms"])
            if open_ms < start_ms or open_ms > end_ms:
                continue
            if any(int(existing["open_time_ms"]) == open_ms for existing in sub.ring):
                continue
            payload = {
                "symbol": sub.symbol, "interval": sub.interval,
                "open_time_ms": open_ms,
                "close_time_ms": candle.get("close_time_ms"),
                "open": candle.get("open"), "high": candle.get("high"),
                "low": candle.get("low"), "close": candle.get("close"),
                "base_volume": candle.get("base_volume"),
                "quote_volume": candle.get("quote_volume"),
                "trade_count": candle.get("trade_count"),
                "closed": True,
                "event_ms": candle.get("close_time_ms") or open_ms,
                "received_ms": self.now(),
                "source": "rest_recovery",
                "seq": sub.next_seq(),
            }
            sub.ring.append(payload)
            sub.counters["closed"] += 1
            sub.counters["gap_recovered_bars"] += 1
            sub.closed_through_ms = max(int(sub.closed_through_ms or 0), open_ms + sub.step_ms)
            self._publish(sub, "closed", payload)
        sub.recovering = False
        sub.recovery_requests += int(result.get("requests") or 0)
        sub.counters["recoveries"] += 1
        if result.get("status") == "failed":
            sub.counters["recovery_failures"] += 1
        self._publish(sub, "gap", {
            "symbol": sub.symbol, "interval": sub.interval, "reason": reason,
            "status": result.get("status") or "failed",
            "expected_from_ms": start_ms, "expected_to_ms": end_ms,
            "missing": result.get("missing") or [],
            "requests": int(result.get("requests") or 0),
            "recovered_bars": len(recovered),
            "detail": result.get("detail"),
        })
        self._emit_status(sub)

    # --- metricas -------------------------------------------------------
    def health(self) -> Dict[str, Any]:
        streams = []
        counters: Counter = Counter()
        for sub in sorted(self.subs.values(), key=lambda s: (s.symbol, s.interval)):
            state, age, live = self.state_for(sub)
            counters.update(sub.counters)
            streams.append({
                "symbol": sub.symbol,
                "interval": sub.interval,
                "stream": sub.stream,
                "consumers": len(sub.consumers),
                "state": state,
                "live": live,
                "age_ms": age,
                "last_message_ms": sub.last_received_ms,
                "last_kline_open_ms": sub.last_open_ms,
                "closed_through_ms": sub.closed_through_ms,
                "recovering": sub.recovering,
                "recoveries": sub.counters["recoveries"],
                "gaps": sub.counters["gaps"],
                "ring": len(sub.ring),
                "counters": dict(sub.counters),
            })
        return {
            "contract_version": STREAM_CONTRACT_VERSION,
            "venue": VENUE,
            "market_type": MARKET_TYPE,
            "socket": {
                "connected": self.socket_connected,
                "since_ms": self.socket_since_ms,
                "attempts": self.socket_attempts,
                "reconnects": self.socket_reconnects,
                "last_error": self.last_socket_error,
                "route": WS_ROUTE,
            },
            "consumers": self.total_consumers(),
            "streams": streams,
            "counters": dict(counters),
            "limits": {
                "max_subscriptions": self.max_subscriptions,
                "max_consumers": self.max_consumers,
                "max_consumers_per_stream": self.max_consumers_per_stream,
                "ring_size": RING_SIZE,
                "pending_max": PENDING_MAX,
                "consumer_queue_max": CONSUMER_QUEUE_MAX,
                "fresh_ms": self.fresh_ms,
                "stale_ms": self.stale_ms,
                "recovery_max_pages": RECOVERY_MAX_PAGES,
                "recovery_page_limit": RECOVERY_PAGE_LIMIT,
                "recovery_max_per_minute": self.recovery_max_per_minute,
                "persistence": "MEMORY_ONLY",
            },
            "rejected_subscriptions": self.rejected_subscriptions,
            "started_at_ms": self.started_at_ms,
            "generated_at_ms": self.now(),
            "times": {"unit": "ms", "epoch": "unix_utc"},
        }

    def snapshot_event(self, sub: Subscription, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Envuelve el snapshot REST existente con la identidad del stream."""
        candles = payload.get("candles") or []
        return {
            "symbol": sub.symbol,
            "interval": sub.interval,
            "window": payload.get("requested") or {},
            "candles": candles,
            "observed": payload.get("observed") or {},
            "coverage": payload.get("coverage") or {},
            "volume": payload.get("volume") or {},
            "freshness": payload.get("freshness") or {},
            "source": "cache",
            "generated_at_ms": payload.get("generated_at_ms") or self.now(),
        }


def _same_candle(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    for key in ("open", "high", "low", "close", "base_volume", "quote_volume"):
        if a.get(key) != b.get(key):
            return False
    return True


# --- transporte real ----------------------------------------------------


class BinanceKlineTransport:
    """Conexion unica (modo combinado) con reconexion y control de suscripciones.

    Reutiliza la politica auditada de ``probe._connection_loop``: timeouts y ping
    equivalentes, backoff exponencial; anade jitter y presupuesto de reintentos.
    """

    def __init__(
        self,
        hub: KlineStreamHub,
        *,
        base_url: str = WS_BASE_URL,
        route: str = WS_ROUTE,
        connect: Optional[Callable[..., Any]] = None,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        rng: Optional[Callable[[], float]] = None,
        max_streams: int = MAX_SUBSCRIPTIONS,
    ) -> None:
        self.hub = hub
        self.base_url = base_url.rstrip("/")
        self.route = route
        self._connect = connect
        self._sleep = sleep
        self._rng = rng or random.random
        self.max_streams = int(max_streams)
        self.consecutive_failures = 0
        self.stop_reason: Optional[str] = None

    def build_url(self, streams: Sequence[str]) -> str:
        joined = "/".join(sorted(streams)[: self.max_streams])
        return f"{self.base_url}{self.route}/stream?streams={joined}"

    def backoff_seconds(self, attempt: int) -> float:
        base = min(RECONNECT_MAX_S, RECONNECT_BASE_S * (2 ** max(0, attempt - 1)))
        jitter = 1 + (self._rng() * 2 - 1) * RECONNECT_JITTER
        return max(0.2, base * jitter)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            desired = self.hub.desired_streams()
            if not desired:
                if self.hub.socket_connected:
                    self.hub.on_socket_closed()
                self.hub.changed.clear()
                try:
                    await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_S)
                except asyncio.TimeoutError:
                    pass
                continue
            url = self.build_url(desired)
            try:
                await self._run_socket(url, stop, desired)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.consecutive_failures += 1
                self.hub.on_socket_closed(f"{type(exc).__name__}: {exc}")
                if self.consecutive_failures >= RETRY_BUDGET:
                    self.stop_reason = "RETRY_BUDGET_EXHAUSTED"
                    await self._park_until_new_consumer(stop)
                    self.consecutive_failures = 0
                    continue
                await self._sleep(self.backoff_seconds(self.consecutive_failures))
            else:
                self.consecutive_failures = 0
                if self.stop_reason == "SERVER_SHUTDOWN":
                    # Corte ordenado por el exchange: reconectar ya, sin backoff.
                    self.hub.force_reconnect = False
                    self.stop_reason = None
                    continue
                await self._sleep(self.backoff_seconds(1))

    async def _park_until_new_consumer(self, stop: asyncio.Event) -> None:
        """Deja de reintentar hasta que aparezca un consumidor nuevo."""
        generation = self.hub.subscription_generation
        while not stop.is_set():
            if self.hub.subscription_generation != generation:
                return
            try:
                await asyncio.wait_for(stop.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass

    async def _run_socket(self, url: str, stop: asyncio.Event,
                          desired: Sequence[str]) -> None:
        connect = self._connect or _default_connect
        ws = await connect(url)
        try:
            self.hub.on_socket_open()
            current: Set[str] = set(desired)
            reader = asyncio.ensure_future(self._reader(ws))
            control = asyncio.ensure_future(self._control(ws, current))
            stopper = asyncio.ensure_future(stop.wait())
            try:
                done, pending = await asyncio.wait(
                    {reader, control, stopper},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                if reader in done:
                    exc = reader.exception()
                    if exc is not None:
                        raise exc
                    if self.hub.force_reconnect:
                        self.stop_reason = "SERVER_SHUTDOWN"
                        return
                    raise ConnectionError("socket closed by peer")
                if stopper in done:
                    return
                if control in done:
                    exc = control.exception()
                    if exc is not None:
                        raise exc
            finally:
                for task in (reader, control, stopper):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(reader, control, stopper, return_exceptions=True)
        finally:
            self.hub.on_socket_closed()
            await _close(ws)

    async def _reader(self, ws: Any) -> None:
        async for raw in ws:
            self.hub.on_message(raw)
            if self.hub.force_reconnect:
                return

    async def _control(self, ws: Any, current: Set[str]) -> None:
        while True:
            await self.hub.wait_change()
            desired = set(self.hub.desired_streams())
            added = sorted(desired - current)
            removed = sorted(current - desired)
            if added:
                await ws.send(json.dumps({
                    "method": "SUBSCRIBE", "params": added,
                    "id": int(time.time() * 1000) % 100000,
                }))
            if removed:
                await ws.send(json.dumps({
                    "method": "UNSUBSCRIBE", "params": removed,
                    "id": int(time.time() * 1000) % 100000,
                }))
            current.clear()
            current.update(desired)
            if not desired:
                return
            await self._sleep(CONTROL_MIN_INTERVAL_S)


async def _default_connect(url: str) -> Any:
    import websockets  # import local: el hub no depende del transporte

    return await websockets.connect(
        url, open_timeout=15, close_timeout=10,
        ping_interval=180, ping_timeout=600, max_queue=2048,
    )


async def _close(ws: Any) -> None:
    close = getattr(ws, "close", None)
    if close is None:
        return
    try:
        result = close()
        if asyncio.iscoroutine(result):
            await result
    except Exception:  # pragma: no cover - cierre defensivo
        pass


def build_recovery(client: Any) -> RecoveryFn:
    """Reparacion REST acotada usando el cliente publico existente.

    Solo velas cerradas, maximo ``RECOVERY_MAX_PAGES`` paginas de
    ``RECOVERY_PAGE_LIMIT``. Un fallo o un tramo incompleto se publica como
    hueco: no se reintenta en bucle ni se rellena con interpolacion.
    """

    async def _recover(symbol: str, interval: str, start_ms: int,
                       end_ms: int) -> Dict[str, Any]:
        def _run() -> Dict[str, Any]:
            before = getattr(getattr(client, "stats", None), "requests", 0)
            try:
                rows, info = client.paginate_klines(
                    symbol, interval, int(start_ms), int(end_ms),
                    source="klines", limit=RECOVERY_PAGE_LIMIT,
                    max_pages=RECOVERY_MAX_PAGES,
                )
            except Exception as exc:
                return {"status": "failed", "candles": [], "requests": 0,
                        "missing": [[int(start_ms), int(end_ms)]],
                        "detail": f"{type(exc).__name__}: {exc}"}
            requests = max(0, getattr(getattr(client, "stats", None), "requests", 0) - before)
            candles: List[Dict[str, Any]] = []
            for row in rows or []:
                if not isinstance(row, (list, tuple)) or len(row) < 7:
                    continue
                candles.append({
                    "open_time_ms": int(row[0]),
                    "close_time_ms": int(row[6]),
                    "open": _num(row[1]),
                    "high": _num(row[2]),
                    "low": _num(row[3]),
                    "close": _num(row[4]),
                    "base_volume": _num(row[5]),
                    "quote_volume": _num(row[7]) if len(row) > 7 else None,
                    "trade_count": _int_or_none(row[8]) if len(row) > 8 else None,
                })
            skipped = [list(map(int, rng)) for rng in (info or {}).get("skipped_ranges") or []]
            if not candles:
                status = "failed"
            elif skipped:
                status = "partial"
            else:
                status = "complete"
            return {
                "status": status,
                "candles": candles,
                "requests": requests,
                "missing": skipped,
                "detail": None if status != "failed" else "SIN_VELAS_EN_RANGO",
            }

        return await asyncio.to_thread(_run)

    return _recover
