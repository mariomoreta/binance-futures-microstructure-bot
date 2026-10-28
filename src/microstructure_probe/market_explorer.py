"""Explorador publico de contratos Binance USD-M + historico paginado.

Objetivo de este modulo: BUSCAR un contrato y VISUALIZAR su historico. No abre
posiciones, no inicia el monitor, no anade simbolos al universo del bot y no
suscribe websockets: solo consultas REST publicas acotadas bajo demanda.

Reutilizacion (antes de consultar Binance):
  - Lectura read-only de la DB de investigacion existente
    (``data/historical/historical.db``: ``historical_klines`` /
    ``historical_mark_klines``) como fuente de velas ya almacenadas.
  - Lectura de la cache aislada del explorador (``data/market-cache``).
  - Cliente REST existente ``HistoryClient`` (limiter por peso, backoff,
    politica 429/418) para adquirir SOLO los tramos faltantes.

Politica explicita de adquisicion:
  - pagina: ``PAGE_LIMIT`` (1000 velas, maximo del endpoint klines)
  - paginas por peticion de UI: ``MAX_PAGES_PER_REQUEST`` (2)
  - concurrencia: ``MAX_CONCURRENCY`` (1, secuencial; sin paralelismo)
  - timeout por peticion: ``REQUEST_TIMEOUT_S`` (20 s)
  - presupuesto rolling: ``MAX_FETCH_REQUESTS_PER_WINDOW`` por minuto,
    contado en el ledger de la cache (compartido entre invocaciones)
  - 429: honorable via ``Retry-After`` con presupuesto acotado; 418 (IP ban)
    aborta inmediatamente. Nunca bucles agresivos.

Unidades y tiempos: todos los tiempos son milisegundos Unix UTC. Los precios y
volumenes se publican como las cadenas exactas del exchange (TEXT), sin
recalcular ni redondear; el cliente decide como presentarlos. Una vela sin
cerrar se marca ``provisional`` y NO publica ``close_time_ms`` (desconocido en
T), nunca un cierre inventado.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .history_client import (
    INTERVAL_MS,
    HistoryClient,
    RateLimitExceeded,
    UpstreamBudgetExceeded,
)

#: Benchmark del contexto compartido (mismo canal de velas, sin colector
#: nuevo). Se define en kline_btc_context y se reexporta aqui por conveniencia.

from .market_cache import (
    CATALOG_TTL_MS,
    MAX_FETCH_REQUESTS_PER_WINDOW,
    MAX_SERIES_LIMIT,
    ROLLING_WINDOW_MS,
    MarketCache,
)

MARKET_SERIES_CONTRACT_VERSION = "market-series/v1"
MARKET_CATALOG_CONTRACT_VERSION = "market-catalog/v1"

from .kline_btc_context import BTC_BENCHMARK_SYMBOL, compute_btc_context
from .kline_indicators import compute_kline_indicators

VENUE = "binance"
MARKET_TYPE = "usd_m_futures"
API_FAMILY = "fapi"

# Temporalidades explorables: solo intervalos de duracion EXACTA en ms. "1M"
# queda fuera porque el calendario de Binance no es un numero fijo de ms y la
# deteccion de huecos seria incorrecta.
EXPLORABLE_INTERVALS: Tuple[str, ...] = ("1m", "5m", "15m", "1h", "4h", "1d")
SOURCES: Tuple[str, ...] = ("klines", "mark_klines")

PAGE_LIMIT = 1000
MAX_PAGES_PER_REQUEST = 2
MAX_CONCURRENCY = 1
REQUEST_TIMEOUT_S = 20.0
DEFAULT_SERIES_BARS = 300
GAP_REPORT_LIMIT = 50

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,32}$")

COVERAGE_STATES = ("NO_COVERAGE", "PARTIAL", "COVERED")
FRESHNESS_STATE = "HISTORICAL_ON_DEMAND"


# --- catalogo ---------------------------------------------------------------


def catalog_entry(entry: Dict[str, Any], fetched_at_ms: int) -> Optional[Dict[str, Any]]:
    """exchangeInfo -> fila de catalogo con elegibilidad explicita."""
    symbol = entry.get("symbol")
    if not symbol:
        return None
    contract_type = entry.get("contractType")
    status = entry.get("status")
    quote_asset = entry.get("quoteAsset")
    reasons: List[str] = []
    if contract_type != "PERPETUAL":
        reasons.append(f"contract_type={contract_type}")
    if status != "TRADING":
        reasons.append(f"status={status}")
    if quote_asset != "USDT":
        reasons.append(f"quote_asset={quote_asset}")
    tick_size: Optional[str] = None
    for filt in entry.get("filters") or []:
        if isinstance(filt, dict) and filt.get("filterType") == "PRICE_FILTER":
            tick_size = filt.get("tickSize")
    onboard = entry.get("onboardDate")
    try:
        onboard_ms = int(onboard) if onboard is not None else None
    except (TypeError, ValueError):
        onboard_ms = None
    return {
        "symbol": str(symbol).upper(),
        "base_asset": entry.get("baseAsset"),
        "quote_asset": quote_asset,
        "margin_asset": entry.get("marginAsset"),
        "contract_type": contract_type,
        "status": status,
        "onboard_ms": onboard_ms,
        "price_precision": entry.get("pricePrecision"),
        "tick_size": tick_size,
        "eligible": not reasons,
        "exclusion_reasons": reasons,
        "fetched_at": int(fetched_at_ms),
    }


def refresh_catalog(cache: MarketCache, client: HistoryClient,
                    now_ms: Optional[int] = None,
                    max_age_ms: int = CATALOG_TTL_MS,
                    force: bool = False) -> Dict[str, Any]:
    """Refresca el catalogo si esta vencido, vacio o forzado. Una peticion."""
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    # Solo hay "diff" si existia un snapshot previo: en el primer refresco no se
    # conoce el estado anterior y publicar altas/bajas seria inventarlo.
    total_before = cache.catalog_count()
    had_snapshot = cache.get_meta("catalog_fetched_at_ms") is not None \
        and total_before > 0
    previous = (cache.read_catalog_snapshot() if had_snapshot else [])
    count = total_before
    fetched_at = cache.get_meta("catalog_fetched_at_ms")
    age = (now - int(fetched_at)) if fetched_at is not None else None
    fresh = bool(count) and age is not None and age <= int(max_age_ms)
    if fresh and not force:
        return {"refreshed": False, "reason": "FRESH_CACHE",
                "entries": count, "fetched_at_ms": fetched_at, "age_ms": age,
                "requests": 0}
    try:
        payload, _ = client.exchange_info()
    except RateLimitExceeded as exc:
        if _gate_records_client(client):
            pass  # ledger por intento ya escrito por la puerta
        else:
            cache.record_fetch(now, None, None, "exchange_info", 1, 0, 1,
                               "rate_limited", str(exc))
        return {"refreshed": False, "reason": "RATE_LIMITED",
                "entries": count, "fetched_at_ms": fetched_at, "age_ms": age,
                "requests": 1, "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001 - se reporta, no se inventa
        if _gate_records_client(client):
            pass  # ledger por intento ya escrito por la puerta
        else:
            cache.record_fetch(now, None, None, "exchange_info", 1, 0, 1,
                               "error", str(exc))
        return {"refreshed": False, "reason": "REFRESH_FAILED",
                "entries": count, "fetched_at_ms": fetched_at, "age_ms": age,
                "requests": 1, "detail": str(exc)}
    entries = [r for r in (catalog_entry(e, now)
                           for e in payload.get("symbols", []) or []) if r]
    cache.replace_catalog(entries, now)
    cache.set_meta("catalog_fetched_at_ms", now)
    cache.set_meta("catalog_entries", len(entries))
    cache.set_meta("catalog_endpoint", "/fapi/v1/exchangeInfo")
    if not _gate_records_client(client):
        cache.record_fetch(now, None, None, "exchange_info", 1, 0, 0, "ok",
                           f"entries={len(entries)}")
    _record_catalog_diff(cache, previous, entries, now)

    return {"refreshed": True, "reason": "REFRESHED", "entries": len(entries),
            "fetched_at_ms": now, "age_ms": 0, "requests": 1}


def _gate_records_client(client: Any) -> bool:
    """True si el cliente lleva puerta del ledger conectada (contabilidad
    por intento ya sustituye al registro agregado legacy)."""
    return getattr(client, "attempt_gate", None) is not None


def _record_catalog_diff(cache: MarketCache, previous: Sequence[Dict[str, Any]],
                         current: Sequence[Dict[str, Any]], now: int) -> int:
    """Episodios observados (listado/baja). No infiere estado operativo.

    Sin snapshot previo no hay diff posible: devolver 0 en vez de declarar 931
    altas como si se hubieran observado.
    """
    if not previous:
        return 0
    before = {str(r["symbol"]): r for r in previous}
    after = {str(r["symbol"]): r for r in current}
    events: List[Tuple[str, str, Any, Any]] = []
    for symbol in sorted(set(after) - set(before)):
        events.append((symbol, "listed", after[symbol].get("contract_type"),
                       after[symbol].get("status")))
    for symbol in sorted(set(before) - set(after)):
        events.append((symbol, "not_listed",
                       before[symbol].get("contract_type"),
                       before[symbol].get("status")))
    for symbol in sorted(set(after) & set(before)):
        old, new = before[symbol], after[symbol]
        if old.get("status") != new.get("status") or \
                old.get("eligible") != new.get("eligible"):
            events.append((symbol, "status_changed", new.get("contract_type"),
                           new.get("status")))
    return cache.record_contract_events(events, now)


def catalog_payload(cache: MarketCache, client: Optional[HistoryClient] = None,
                    query: str = "", limit: int = 50,
                    eligible_only: bool = False, refresh: bool = False,
                    max_age_ms: int = CATALOG_TTL_MS,
                    now_ms: Optional[int] = None,
                    allow_fetch: bool = True) -> Dict[str, Any]:
    """Busqueda de contratos sobre el catalogo cacheado (con refresco acotado)."""
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    entries = cache.catalog_count()
    refresh_info: Dict[str, Any] = {"refreshed": False, "reason": "DISABLED",
                                    "requests": 0}
    fetched_at = cache.get_meta("catalog_fetched_at_ms")
    stale = (fetched_at is None or now - int(fetched_at) > int(max_age_ms))
    if allow_fetch and client is not None and (refresh or stale or entries == 0):
        refresh_info = refresh_catalog(cache, client, now, max_age_ms,
                                       force=refresh or entries == 0)
        fetched_at = cache.get_meta("catalog_fetched_at_ms")
        # La antiguedad se recalcula tras el refresco: informar `stale=True`
        # con un catalogo recien pedido seria falso.
        stale = (fetched_at is None
                 or now - int(fetched_at) > int(max_age_ms))
    rows = cache.read_catalog(query=query, limit=limit,
                              eligible_only=eligible_only)
    total = cache.catalog_count()
    age = (now - int(fetched_at)) if fetched_at is not None else None
    return {
        "contract_version": MARKET_CATALOG_CONTRACT_VERSION,
        "venue": VENUE,
        "market_type": MARKET_TYPE,
        "api_family": API_FAMILY,
        "endpoint": "/fapi/v1/exchangeInfo",
        "spot_included": False,
        "available": total > 0,
        "reason": None if total > 0 else "CATALOG_NOT_CACHED",
        "eligible_only": bool(eligible_only),
        "query": (query or "").strip().upper(),
        "results": rows,
        "result_count": len(rows),
        "truncated": len(rows) >= max(1, min(int(limit), 500)) and total > len(rows),
        "catalog": {"entries": total, "fetched_at_ms": fetched_at,
                    "age_ms": age, "stale": stale,
                    "endpoint": cache.get_meta("catalog_endpoint")},
        "refresh": refresh_info,
        "times": {"unit": "ms", "epoch": "unix_utc"},
        "generated_at_ms": now,
        "notes": [
            "Catalogo de contratos USD-M Futures (fapi). No incluye spot.",
            "eligible = contractType PERPETUAL y status TRADING y quoteAsset"
            " USDT; el resto se muestra con motivos, nunca se oculta.",
            "Buscar o abrir un simbolo no abre posicion, no inicia el monitor"
            " y no lo anade al universo del bot.",
        ],
    }


# --- lectura de almacenamiento existente ------------------------------------


def _read_canonical(path: Path, symbol: str, interval: str, source: str,
                    from_ms: int, to_ms: int,
                    limit: int) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Lee velas ya almacenadas en la DB de investigacion (read-only).

    La lectura es DESC (cola): con mas de ``limit`` velas almacenadas en el
    rango, el rango solicitado (p.ej. amplio para "todo lo almacenado")
    conserva la porcion RECIENTE, no la mas antigua. Se devuelve ASC.
    """
    if not Path(path).exists():
        return [], "CANONICAL_MISSING"
    table = ("historical_klines" if source == "klines"
             else "historical_mark_klines")
    uri = f"file:{Path(path).as_posix()}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=2.0)
    except sqlite3.Error as exc:
        return [], f"CANONICAL_UNREADABLE: {exc}"
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT open_time, open, high, low, close, close_time, trade_count,"
            " fetched_at" + (", base_volume, quote_volume" if source == "klines"
                             else ", NULL AS base_volume, NULL AS quote_volume")
            + f" FROM {table} WHERE symbol=? AND interval=?"
            " AND open_time>=? AND open_time<=? ORDER BY open_time DESC LIMIT ?",
            (str(symbol).upper(), str(interval), int(from_ms), int(to_ms),
             max(1, int(limit))),
        ).fetchall()
        return [dict(r) for r in reversed(rows)], None
    except sqlite3.Error as exc:
        return [], f"CANONICAL_SCHEMA: {exc}"
    finally:
        con.close()


def _normalize_stored_row(row: Dict[str, Any], storage: str) -> Dict[str, Any]:
    return {
        "open_time": int(row["open_time"]),
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "close": row.get("close"),
        "base_volume": row.get("base_volume"),
        "quote_volume": row.get("quote_volume"),
        "trade_count": row.get("trade_count"),
        "close_time": row.get("close_time"),
        "fetched_at": row.get("fetched_at"),
        "storage": storage,
    }


def read_stored(cache: MarketCache, symbol: str, interval: str, source: str,
                from_ms: int, to_ms: int,
                history_db: Optional[Path] = None,
                limit: int = MAX_SERIES_LIMIT) -> Tuple[List[Dict[str, Any]],
                                                        Dict[str, Any]]:
    """Une velas canonicas + cache, deduplicando por tiempo de apertura.

    Se conserva la fila con ``fetched_at`` mas reciente (misma procedencia:
    Binance klines). El origen se conserva para trazabilidad. Ambas lecturas
    son de COLA (newest-first + reversa): con mas de ``limit`` velas en el
    rango, se conservan las ``limit`` mas RECIENTES del rango pedido; con
    menos, el resultado es identico al de una lectura ASC.
    """
    canonical, canonical_error = _read_canonical(
        Path(history_db) if history_db is not None
        else _default_history_db(), symbol, interval, source, from_ms, to_ms,
        limit)
    cached = cache.read_klines(symbol, interval, source, from_ms, to_ms, limit,
                               newest_first=True)
    canonical = list(reversed(canonical))
    cached = list(reversed(cached))
    merged: Dict[int, Dict[str, Any]] = {}
    for row in canonical:
        item = _normalize_stored_row(row, "canonical")
        merged[item["open_time"]] = item
    for row in cached:
        item = _normalize_stored_row(row, "cache")
        old = merged.get(item["open_time"])
        if old is None:
            merged[item["open_time"]] = item
            continue
        old_at = int(old.get("fetched_at") or 0)
        new_at = int(item.get("fetched_at") or 0)
        if new_at >= old_at:
            item["also_canonical"] = True
            merged[item["open_time"]] = item
        else:
            old["also_cached"] = True
    bars = [merged[k] for k in sorted(merged)]
    if len(bars) > limit:
        bars = bars[-limit:]
    return bars[:limit], {"canonical_error": canonical_error,
                          "canonical_rows": len(canonical),
                          "cache_rows": len(cached)}


def _default_history_db() -> Path:
    from .history_store import default_path as history_default_path
    return history_default_path()


# --- adquisicion acotada de faltantes ---------------------------------------


class LedgerAttemptGate:
    """Presupuesto upstream compartido: UNA reserva por intento HTTP.

    Proceso de cada intento (incluidos reintentos y paginas):
      1. ``before_send`` (HistoryClient lo llama ANTES del transporte):
         reserva transaccional de 1 intento en ``market_fetch_ledger`` con
         execution_id. Denegada -> fila ``budget_blocked`` (requests=0) y
         ``UpstreamBudgetExceeded``: el intento muere sin abrir socket.
      2. Transporte real (solo si la reserva fue concedida).
      3. ``after_send``: la fila reservada se cierra con el resultado real
         (ok / http_429_retry_N / http_5xx_retry_N / connection_error / ...).

    El limite sigue siendo la ventana rolling del ledger (compartida entre
    procesos que apuntan a la misma cache), no el contador en memoria del
    cliente, que solo mide la instancia propia.
    """

    def __init__(self, cache: MarketCache, execution_id: Optional[str],
                 max_requests: int = MAX_FETCH_REQUESTS_PER_WINDOW) -> None:
        self.cache = cache
        self.execution_id = execution_id
        self.max_requests = int(max_requests)

    def before_send(self, entry: Dict[str, Any]) -> None:
        attempt = {
            "endpoint": entry.get("endpoint"),
            "symbol": entry.get("symbol"),
            "interval": entry.get("interval"),
            "range": entry.get("range"),
            "page": entry.get("page"),
            "retry": entry.get("retry"),
        }
        row_id = self.cache.reserve_fetch_attempt(
            int(time.time() * 1000), symbol=entry.get("symbol"),
            detail=json.dumps(attempt, sort_keys=True),
            max_requests=self.max_requests, execution_id=self.execution_id,
        )
        if row_id is None:
            entry["result"] = "budget_blocked"
            usage = self.cache.window_usage(max_requests=self.max_requests)
            raise UpstreamBudgetExceeded(
                f"bloqueado ANTES del transporte: {usage['used_in_window']}"
                f" upstream en la ventana compartida, limite"
                f" {self.max_requests}"
            )
        entry["_ledger_row_id"] = row_id

    def after_send(self, entry: Dict[str, Any]) -> None:
        row_id = entry.pop("_ledger_row_id", None)
        if row_id is None:
            return
        detail = {
            "endpoint": entry.get("endpoint"),
            "symbol": entry.get("symbol"),
            "interval": entry.get("interval"),
            "range": entry.get("range"),
            "page": entry.get("page"),
            "retry": entry.get("retry"),
            "result": entry.get("result"),
            "duration_ms": entry.get("duration_ms"),
        }
        self.cache.complete_fetch_row(
            int(row_id), status=str(entry.get("result")),
            retries=int(entry.get("retry") or 0),
            note=json.dumps(detail, sort_keys=True),
            detail=json.dumps(detail, sort_keys=True),
        )


def plan_missing_block(bars: Sequence[Dict[str, Any]], from_ms: int, to_ms: int,

                       step: int, pages: int,
                       page_limit: int = PAGE_LIMIT) -> Optional[Tuple[int, int]]:
    """Bloque anterior inmediato a cubrir (scroll-back), acotado por paginas.

    Sin velas almacenadas se pide el bloque mas reciente del rango. Con velas,
    se pide el bloque inmediatamente anterior a la apertura mas antigua (o el
    bloque mas reciente si el rango solicitado sigue por delante de lo
    almacenado).
    """
    max_bars = max(1, int(pages)) * int(page_limit)
    end = int(to_ms)
    if bars:
        newest = int(bars[-1]["open_time"])
        oldest = int(bars[0]["open_time"])
        if end > newest:
            start = max(int(from_ms), end - (max_bars - 1) * step)
        else:
            end = min(int(to_ms), oldest - step)
            start = max(int(from_ms), end - (max_bars - 1) * step)
    else:
        start = max(int(from_ms), end - (max_bars - 1) * step)
    if end < int(from_ms) or start > end:
        return None
    return start, end


def fetch_block(cache: MarketCache, client: HistoryClient, symbol: str,
                interval: str, source: str, start_ms: int, end_ms: int,
                pages: int, now_ms: int,
                page_limit: int = PAGE_LIMIT,
                max_upstream_requests: Optional[int] = None) -> Dict[str, Any]:
    """Adquiere un bloque acotado y lo persiste SOLO en la cache aislada.

    Presupuesto: (1) chequeo rapido de ventana antes de planificar; (2)
    cada intento HTTP reserva 1 cupo en el ledger compartido justo antes
    del transporte (``LedgerAttemptGate``), incluidos reintentos y paginas;
    con puerta activa el ledger por intento ES la contabilidad y no se
    escribe agregado posterior (evita doble conteo).
    """
    max_upstream = max_upstream_requests if max_upstream_requests is not None \
        else MAX_FETCH_REQUESTS_PER_WINDOW
    window_used = cache.requests_in_window(now_ms)
    planned = int(pages)
    if window_used + planned > max_upstream:
        return {"performed": False, "status": "budget_exhausted",
                "error": "RATE_BUDGET_EXHAUSTED", "requests": 0, "pages": 0,
                "retries": 0, "failures": 0,
                "detail": (f"presupuesto de upstream agotado: "
                           f"{window_used} peticiones en la ventana de "
                           f"{ROLLING_WINDOW_MS} ms, límite {max_upstream}"),
                "retry_after_ms": ROLLING_WINDOW_MS}
    gate_capable = hasattr(client, "attempt_gate")
    gate: Optional[LedgerAttemptGate] = None
    if gate_capable:
        gate = LedgerAttemptGate(cache, getattr(client, "execution_id", None),
                                 max_requests=max_upstream)
        client.attempt_gate = gate  # type: ignore[attr-defined]
    before = client.stats.requests
    try:
        rows, meta = client.paginate_klines(
            symbol, interval, start_ms, end_ms, source=source,
            limit=page_limit, max_pages=planned)
    except UpstreamBudgetExceeded as exc:
        # Sin transporte: la reserva fue denegada. La puerta ya escribio la
        # fila auditada (requests=0); no se agrega ningun consumo.
        return {"performed": True, "status": "budget_blocked",
                "error": "BLOCKED_BEFORE_TRANSPORT", "requests": 0,
                "pages_planned": planned,
                "pages": 0,
                "retries": client.stats.retries, "failures": client.stats.failures,
                "detail": str(exc), "retry_after_ms": None}
    except RateLimitExceeded as exc:
        if not gate_capable:
            cache.record_fetch(now_ms, symbol, interval, source, 1, 0, 1,
                               "rate_limited", str(exc))
        return {"performed": True, "status": "rate_limited",
                "error": "RATE_LIMIT_ABORTED", "requests": 1, "pages": 0,
                "retries": client.stats.retries, "failures": client.stats.failures,
                "detail": str(exc), "retry_after_ms": None}
    except Exception as exc:  # noqa: BLE001 - se reporta, no se inventa
        if not gate_capable:
            cache.record_fetch(now_ms, symbol, interval, source, 1, 0, 1,
                               "error", str(exc))
        return {"performed": True, "status": "error", "error": "FETCH_FAILED",
                "requests": 1, "pages": 0,
                "retries": client.stats.retries, "failures": client.stats.failures,
                "detail": str(exc), "retry_after_ms": None}
    from .history import normalize_kline, normalize_mark_kline
    normalize = normalize_kline if source == "klines" else normalize_mark_kline
    bars = [normalize(row) for row in rows if isinstance(row, list) and row]
    stored = cache.upsert_klines(symbol, interval, source, bars, now_ms)
    requests = max(0, client.stats.requests - before)
    if not gate_capable:
        cache.record_fetch(now_ms, symbol, interval, source, requests,
                           retries=0, failures=0, status="ok",
                           note=f"pages={meta.get('pages')} bars={stored}")
    return {"performed": True, "status": "ok", "error": None,
            "requests": requests, "pages": int(meta.get("pages") or 0),
            "bars_stored": stored,
            "skipped_ranges": meta.get("skipped_ranges") or [],
            "retries": 0, "failures": 0, "detail": None,
            "retry_after_ms": None}


# --- cobertura --------------------------------------------------------------


def compute_coverage(bars: Sequence[Dict[str, Any]], from_ms: int, to_ms: int,
                     step: int,
                     earliest_available_ms: Optional[int] = None) -> Dict[str, Any]:
    """Diferencia huecos reales, ausencia de cobertura y fin de historico."""
    opens = sorted(int(b["open_time"]) for b in bars)
    if not opens:
        return {
            "state": "NO_COVERAGE",
            "observed_start_ms": None,
            "observed_end_ms": None,
            "expected_bars": 0,
            "actual_bars": 0,
            "gap_count": None,
            "gaps": [],
            "absent_ranges": [[int(from_ms), int(to_ms)]],
            "exhausted_before": (earliest_available_ms is not None
                                 and int(from_ms) < int(earliest_available_ms)),
            "earliest_available_ms": earliest_available_ms,
            "history_end_ms": None,
            "note": "Sin velas almacenadas en el rango solicitado.",
        }
    first, last = opens[0], opens[-1]
    expected = ((last - first) // step) + 1
    gaps: List[List[int]] = []
    if expected != len(opens):
        have = set(opens)
        cursor = first
        while cursor <= last and len(gaps) < GAP_REPORT_LIMIT:
            if cursor not in have:
                gap_start = cursor
                while cursor <= last and cursor not in have:
                    cursor += step
                gaps.append([gap_start, cursor - step])
            cursor += step
    absent: List[List[int]] = []
    if first > int(from_ms):
        absent.append([int(from_ms), min(first - step, int(to_ms))])
    if last < int(to_ms):
        absent.append([max(last + step, int(from_ms)), int(to_ms)])
    absent = [r for r in absent if r[0] <= r[1]]
    exhausted = (earliest_available_ms is not None
                 and int(from_ms) < int(earliest_available_ms))
    return {
        "state": "COVERED" if not gaps and not absent else "PARTIAL",
        "observed_start_ms": first,
        "observed_end_ms": last,
        "expected_bars": expected,
        "actual_bars": len(opens),
        "gap_count": max(0, expected - len(opens)),
        "gaps": gaps,
        "absent_ranges": absent,
        "exhausted_before": exhausted,
        "earliest_available_ms": earliest_available_ms,
        "history_end_ms": None,
        "note": ("Huecos = puntos de rejilla ausentes dentro del rango"
                 " observado. Ausencia = el rango solicitado excede lo"
                 " almacenado. Ninguno se rellena ni se interpola."),
    }


# --- payload de serie -------------------------------------------------------


def series_payload(cache: MarketCache, client: Optional[HistoryClient] = None,
                   symbol: str = "", interval: str = "", source: str = "klines",
                   from_ms: Optional[int] = None,
                   to_ms: Optional[int] = None,
                   pages: int = MAX_PAGES_PER_REQUEST,
                   allow_fetch: bool = True, page_limit: int = PAGE_LIMIT,
                   bars: int = DEFAULT_SERIES_BARS,
                   probe_earliest: bool = False,
                   now_ms: Optional[int] = None,
                   history_db: Optional[Path] = None,
                   limit: int = MAX_SERIES_LIMIT,
                   max_upstream_requests: Optional[int] = None) -> Dict[str, Any]:
    """Vela a vela, solo lo almacenado o adquirido; nunca simulado."""
    """Vela a vela, solo lo almacenado o adquirido; nunca simulado."""
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    sym = str(symbol or "").strip().upper()
    if not _SYMBOL_RE.match(sym):
        raise ValueError(f"INVALID_SYMBOL: {symbol!r}")
    if interval not in EXPLORABLE_INTERVALS:
        raise ValueError(f"INVALID_INTERVAL: {interval!r}")
    if source not in SOURCES:
        raise ValueError(f"INVALID_SOURCE: {source!r}")
    step = INTERVAL_MS[interval]
    end = int(to_ms) if to_ms is not None else now
    start = int(from_ms) if from_ms is not None else end - (max(1, int(bars)) - 1) * step
    if start > end:
        raise ValueError("INVALID_RANGE: from_ms > to_ms")

    contract = _contract_info(cache, sym)
    stored, storage_info = read_stored(cache, sym, interval, source, start, end,
                                       history_db, limit)
    # Puerta per-intento para TODO lo que este cliente toque en el payload
    # (probe y fetching). En clientes que no son HistoryClient (fakes de
    # prueba) no hay puerta y se conserva el registro agregado legacy.
    resolved_max_upstream = max_upstream_requests if max_upstream_requests \
        is not None else MAX_FETCH_REQUESTS_PER_WINDOW
    if hasattr(client, "attempt_gate") and getattr(client, "attempt_gate") is None:
        client.attempt_gate = LedgerAttemptGate(  # type: ignore[attr-defined]
            cache, getattr(client, "execution_id", None),
            max_requests=resolved_max_upstream)
    fetch_info: Dict[str, Any] = {"allowed": bool(allow_fetch), "performed": False,
                                  "status": "not_requested", "error": None,
                                  "requests": 0, "pages": 0, "retries": 0,
                                  "failures": 0, "detail": None,
                                  "bars_stored": 0,
                                  "retry_after_ms": None}
    if probe_earliest and allow_fetch and client is not None:
        fetch_info = dict(fetch_info)
        probe = _probe_earliest(cache, client, sym, interval, source, now)
        fetch_info["earliest_probe"] = probe
    if allow_fetch and client is not None:
        block = plan_missing_block(stored, start, end, step, pages, page_limit)
        if block is not None:
            fetch_info = fetch_block(cache, client, sym, interval, source,
                                     block[0], block[1], pages, now, page_limit,
                                     max_upstream_requests=max_upstream_requests)
            fetch_info["allowed"] = True
            fetch_info["block"] = [block[0], block[1]]
            stored, storage_info = read_stored(cache, sym, interval, source,
                                              start, end, history_db, limit)
    earliest = _earliest_known(cache, sym, interval, source)
    coverage = compute_coverage(stored, start, end, step, earliest)
    candles = [_public_candle(b, now, step) for b in stored]
    freshness = _freshness(candles, now)
    # Indicadores compartidos versionados:backend = unica autoridad. Sobre las
    # velas cerradas del PROPIO rango del payload; el navegador no recalcula.
    indicators = compute_kline_indicators(stored, step, now, sym, interval,
                                          source)
    # Contexto BTC compartido (market-btc-context/v1): velas cerradas de
    # BTC en la MISMA rejilla e intervalo, leidas del almacen con
    # client=None (sin upstream REST; 0 peticiones). Cuando el token ES
    # BTC el contexto no se emite (no hay comparacion consigo mismo).
    context_btc = None
    if sym != BTC_BENCHMARK_SYMBOL:
        try:
            btc_stored, _ = read_stored(cache, BTC_BENCHMARK_SYMBOL, interval,
                                        source, start, end, history_db, limit)
        except Exception:
            btc_stored = []
        context_btc = compute_btc_context(
            stored, btc_stored, step, now, sym, interval, token_source=source,
            token_indicators=indicators.get("series") if indicators else None,
            btc_sources=(["cache"] if btc_stored else []),
            rest_upstream_requests=0,
        )
    base_asset = (contract or {}).get("base_asset")
    volume_available = source == "klines" and any(
        c["base_volume"] is not None for c in candles)
    return {
        "contract_version": MARKET_SERIES_CONTRACT_VERSION,
        "venue": VENUE,
        "market_type": MARKET_TYPE,
        "api_family": API_FAMILY,
        "source": source,
        "endpoint": ("/fapi/v1/klines" if source == "klines"
                     else "/fapi/v1/markPriceKlines"),
        "symbol": sym,
        "interval": interval,
        "interval_ms": step,
        "contract": contract,
        "requested": {"from_ms": start, "to_ms": end},
        "observed": {
            "start_ms": (int(candles[0]["open_time_ms"]) if candles else None),
            "end_ms": (int(candles[-1]["open_time_ms"]) if candles else None),
        },
        "candles": candles,
        "indicators": indicators,
        "context_btc": context_btc,
        "coverage": coverage,
        "volume": {
            "available": volume_available,
            "base_asset": base_asset,
            "quote_asset": (contract or {}).get("quote_asset"),
            "fields": (["base_volume", "quote_volume"] if source == "klines"
                       else []),
            "reason": None if volume_available
            else ("mark_klines no publica volumen" if source == "mark_klines"
                  else "SIN_VOLUMEN_EN_LO_ALMACENADO"),
        },
        "freshness": freshness,
        "fetch": fetch_info,
        "budget": {
            "used_in_window": cache.requests_in_window(now),
            "max_requests_per_window": resolved_max_upstream,
            "window_ms": ROLLING_WINDOW_MS,
            "max_pages_per_request": MAX_PAGES_PER_REQUEST,
            "max_page_limit": PAGE_LIMIT,
            "concurrency": MAX_CONCURRENCY,
            "enforcement": "ledger_shared_reserve_before_send",
            "execution_id": getattr(client, "execution_id", None)
            if client is not None else None,
        },
        "storage": storage_info,
        "times": {"unit": "ms", "epoch": "unix_utc"},
        "labels": {"mode": "HISTORICAL_ON_DEMAND",
                   "live": False,
                   "banner": "HISTORICO / CONSULTA BAJO DEMANDA"},
        "generated_at_ms": now,
        "notes": [
            "Historico consultado bajo demanda: sin websocket, sin feed"
            " continuo, sin monitor. No es LIVE ni es estado actual.",
            "La vela no cerrada se marca provisional y no publica"
            " close_time_ms (desconocido en T).",
            "Los indicadores versionados (market-indicators/v1)"
            " los calcula el backend solo sobre velas cerradas; sin"
            " senales, sin objetivos y sin marcas de operaciones.",
        ],
    }


def _public_candle(bar: Dict[str, Any], now_ms: int, step: int) -> Dict[str, Any]:
    open_time = int(bar["open_time"])
    provisional = open_time + step > int(now_ms)
    close_time_reported = bar.get("close_time")
    return {
        "open_time_ms": open_time,
        "close_time_ms": None if provisional else close_time_reported,
        "open": _text_or_none(bar.get("open")),
        "high": _text_or_none(bar.get("high")),
        "low": _text_or_none(bar.get("low")),
        "close": _text_or_none(bar.get("close")),
        "base_volume": _text_or_none(bar.get("base_volume")),
        "quote_volume": _text_or_none(bar.get("quote_volume")),
        "trade_count": bar.get("trade_count"),
        "provisional": provisional,
        "fetched_at_ms": bar.get("fetched_at"),
        "storage": bar.get("storage"),
    }


def _text_or_none(value: Any) -> Optional[str]:
    return None if value is None else str(value)


def _freshness(candles: Sequence[Dict[str, Any]], now_ms: int) -> Dict[str, Any]:
    if not candles:
        return {"state": FRESHNESS_STATE, "newest_open_ms": None,
                "newest_close_ms": None, "fetched_at_ms": None, "age_ms": None,
                "provisional": None,
                "note": "Sin velas: no hay frescura que declarar."}
    newest = candles[-1]
    fetched = [int(c["fetched_at_ms"]) for c in candles
               if c.get("fetched_at_ms") is not None]
    fetched_at = max(fetched) if fetched else None
    return {
        "state": FRESHNESS_STATE,
        "newest_open_ms": int(newest["open_time_ms"]),
        "newest_close_ms": newest["close_time_ms"],
        "fetched_at_ms": fetched_at,
        "age_ms": (int(now_ms) - fetched_at) if fetched_at is not None else None,
        "provisional": bool(newest["provisional"]),
        "note": ("Edad medida desde la ultima adquisicion, no desde el"
                 " ultimo precio. No certifica feed vivo."),
    }


def _contract_info(cache: MarketCache, symbol: str) -> Optional[Dict[str, Any]]:
    rows = cache.read_catalog(query=symbol, limit=1, order="symbol")
    for row in rows:
        if row.get("symbol") == symbol:
            return row
    return None


def _earliest_known(cache: MarketCache, symbol: str, interval: str,
                    source: str) -> Optional[int]:
    value = cache.get_meta(f"earliest:{symbol}:{interval}:{source}")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _probe_earliest(cache: MarketCache, client: HistoryClient, symbol: str,
                    interval: str, source: str, now_ms: int) -> Dict[str, Any]:
    """Una peticion acotada para conocer el inicio de historico disponible.

    Con puerta conectada, el intento queda en el ledger per-intento
    (execution_id incluido) y aqui no se agrega ningun registro duplicado.
    """
    known = _earliest_known(cache, symbol, interval, source)
    if known is not None:
        return {"performed": False, "earliest_available_ms": known,
                "requests": 0, "detail": "cached"}
    if cache.requests_in_window(now_ms) + 1 > MAX_FETCH_REQUESTS_PER_WINDOW:
        return {"performed": False, "earliest_available_ms": None, "requests": 0,
                "detail": "budget_exhausted"}
    try:
        first = client.earliest_bar(symbol, interval, source=source)
    except Exception as exc:  # noqa: BLE001
        return {"performed": True, "earliest_available_ms": None, "requests": 1,
                "detail": str(exc)}
    value = int(first[0]) if first else None
    if not _gate_records_client(client):
        cache.record_fetch(now_ms, symbol, interval, source, 1, 0, 0, "ok",
                           "earliest_probe")
    if value is not None:
        cache.set_meta(f"earliest:{symbol}:{interval}:{source}", value)
    return {"performed": True, "earliest_available_ms": value, "requests": 1,
            "detail": None}


def build_client(cache: Optional[MarketCache] = None,
                 execution_id: Optional[str] = None,
                 api_base: Optional[str] = None) -> HistoryClient:
    """Cliente REST publico para el CLI (limiter + politica 429/418 ya probada).

    Con ``cache`` el cliente lleva la puerta del ledger compartido: cada
    intento HTTP (paginas y reintentos) reserva 1 cupo ANTES del transporte
    con ``execution_id``. Sin ``cache`` el control queda per-instancia
    (contador en memoria), alcance declarado y acotado.
    """
    from .history_client import BASE_URL as DEFAULT_BASE_URL
    base_url = DEFAULT_BASE_URL
    if api_base is not None:
        parsed = urllib.parse.urlparse(api_base)
        host = parsed.hostname or ""
        if parsed.scheme != "http" or host not in ("127.0.0.1", "localhost"):
            raise ValueError(
                f"INVALID_API_BASE: solo transporte local loopback http://"
                f" se admite para pruebas ({api_base!r})")
        base_url = api_base.rstrip("/")
    gate = None
    if cache is not None:
        gate = LedgerAttemptGate(cache, execution_id,
                                 max_requests=MAX_FETCH_REQUESTS_PER_WINDOW)
    return HistoryClient(request_timeout=REQUEST_TIMEOUT_S,
                         execution_id=execution_id, attempt_gate=gate,
                         base_url=base_url)
