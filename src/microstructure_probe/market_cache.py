"""Cache aislada del explorador de mercado (Binance USD-M, REST publico).

Directorio aislado e ignorado por git (``data/market-cache/``; ``data/`` ya
esta en ``.gitignore``). NUNCA es la DB operativa (``data/microprobe.db``) ni
la DB de investigacion (``data/historical/historical.db``): el explorador
reutiliza esas fuentes en modo lectura y escribe lo adquirido solo aqui.

Tablas (schema v1):
  cache_meta        — clave/valor JSON: catalogo (fetched_at, entries, endpoint)
                      y limites de historico por (symbol, interval, source).
  contract_catalog  — contratos USD-M con identidad, tipo, estado y
                      elegibilidad explicita (reasons, nunca silenciosa).
  market_klines     — velas adquiridas bajo demanda (precios como TEXT para
                      preservar el valor exacto publicado por el exchange).
  market_fetch_ledger — ledger append-only de peticiones para presupuesto
                      (rolling window) y auditoria. Sin el no hay rate limit
                      compartido entre invocaciones del CLI. Con
                      ``reserve_fetch_attempt`` cada intento upstream se
                      RESERVA (transaccion BEGIN IMMEDIATE) antes de enviarlo,
                      de forma que el limite es compartido entre procesos
                      concurrentes; las filas dan execution_id para reconstruir
                      el consumo por ejecucion. Filas historicas sin
                      execution_id quedan NULL (= UNKNOWN: no se reescriben).
  contract_events   — episodios de contrato observados en el catalogo
                      (listado/baja) para trazabilidad, sin inferir estado.

Regla de datos desconocidos: lo ausente queda ausente (NULL/UNKNOWN). Nunca
ceros, nunca relleno, nunca interpolacion.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA_VERSION = 1

DEFAULT_CACHE_DIR = Path("data") / "market-cache"
DEFAULT_CACHE_DB = DEFAULT_CACHE_DIR / "market_cache.db"

# Politica de cache y presupuesto (documentada y verificable).
CATALOG_TTL_MS = 6 * 60 * 60 * 1000        # 6 h: no refrescar mas seguido
ROLLING_WINDOW_MS = 60_000                 # ventana de presupuesto
MAX_FETCH_REQUESTS_PER_WINDOW = 30         # peticiones/kline por minuto (todas las invocaciones)
MAX_SERIES_LIMIT = 5000                    # tope duro de velas devueltas al cliente
# Presupuesto TOTAL de la corrida: compartido entre /time, klines, catalogo,
# reintentos y recuperacion. NO se reinicia al pasar la ventana movil de 60 s;
# se atribuye persistentemente al run_id (execution_id) en el ledger y solo
# comienza en cero para un run_id nuevo.
# Propuesta de minimo viable (no cubierta por la autorizacion previa de 4):
# 5 intentos de tiempo + 2 de klines = 7.
MAX_FETCH_REQUESTS_PER_RUN = 7


def default_path() -> Path:
    """Cache por defecto, sobreescribible para pruebas herméticas."""
    override = os.environ.get("MICROPROBE_MARKET_CACHE_DB")
    return Path(override) if override else DEFAULT_CACHE_DB


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


class MarketCache:
    """Cache del explorador. Aislada de DBs canonicas por construccion."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        resolved = Path(db_path) if db_path is not None else default_path()
        forbidden = {
            (Path("data") / "microprobe.db").resolve(),
            (Path("data") / "historical" / "historical.db").resolve(),
        }
        if resolved.resolve() in forbidden:
            raise ValueError("market cache must not be a canonical database")
        self.db_path = resolved
        self._initialized = False

    # --- esquema ---------------------------------------------------------

    def _con(self) -> sqlite3.Connection:
        con = _connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def init_db(self) -> None:
        con = self._con()
        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS cache_meta"
                " (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS contract_catalog"
                " (symbol TEXT PRIMARY KEY, base_asset TEXT, quote_asset TEXT,"
                "  margin_asset TEXT, contract_type TEXT, status TEXT,"
                "  onboard_ms INTEGER, price_precision INTEGER, tick_size TEXT,"
                "  eligible INTEGER NOT NULL DEFAULT 0,"
                "  exclusion_reasons TEXT NOT NULL DEFAULT '[]',"
                "  fetched_at INTEGER NOT NULL)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_contract_catalog_base"
                " ON contract_catalog (base_asset)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS market_klines"
                " (symbol TEXT NOT NULL, interval TEXT NOT NULL,"
                "  source TEXT NOT NULL, open_time INTEGER NOT NULL,"
                "  open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL,"
                "  close TEXT NOT NULL, base_volume TEXT, quote_volume TEXT,"
                "  trade_count INTEGER, close_time INTEGER,"
                "  fetched_at INTEGER NOT NULL,"
                "  PRIMARY KEY (symbol, interval, source, open_time))"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS market_fetch_ledger"
                " (id INTEGER PRIMARY KEY AUTOINCREMENT, at_ms INTEGER NOT NULL,"
                "  symbol TEXT, interval TEXT, source TEXT,"
                "  requests INTEGER NOT NULL DEFAULT 0,"
                "  retries INTEGER NOT NULL DEFAULT 0,"
                "  failures INTEGER NOT NULL DEFAULT 0,"
                "  status TEXT NOT NULL DEFAULT 'ok', note TEXT)"
            )
            # Migracion acotada: vinculo de ejecucion por fila del intento.
            # Las filas historicas quedan NULL (= UNKNOWN, no se reescriben).
            for column, decl in (("execution_id", "TEXT"), ("detail", "TEXT")):
                try:
                    con.execute(
                        f"ALTER TABLE market_fetch_ledger ADD COLUMN"
                        f" {column} {decl}"
                    )
                except sqlite3.OperationalError as exc:
                    if "duplicate column" not in str(exc).lower():
                        raise
            con.execute(
                "CREATE TABLE IF NOT EXISTS contract_events"
                " (id INTEGER PRIMARY KEY AUTOINCREMENT, at_ms INTEGER NOT NULL,"
                "  symbol TEXT NOT NULL, kind TEXT NOT NULL,"
                "  contract_type TEXT, status TEXT, note TEXT)"
            )
            con.execute(
                "INSERT OR IGNORE INTO cache_meta (key, value) VALUES"
                " ('schema_version', ?)", (str(SCHEMA_VERSION),)
            )
            con.commit()
            self._initialized = True
        finally:
            con.close()

    # --- meta ------------------------------------------------------------

    def get_meta(self, key: str) -> Optional[Any]:
        con = self._con()
        try:
            row = con.execute("SELECT value FROM cache_meta WHERE key=?",
                              (key,)).fetchone()
            if row is None:
                return None
            try:
                return json.loads(row["value"])
            except (TypeError, ValueError):
                return row["value"]
        finally:
            con.close()

    def set_meta(self, key: str, value: Any) -> None:
        con = self._con()
        try:
            con.execute(
                "INSERT INTO cache_meta (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )
            con.commit()
        finally:
            con.close()

    # --- catalogo --------------------------------------------------------

    def replace_catalog(self, entries: Sequence[Dict[str, Any]],
                        fetched_at_ms: int) -> int:
        """Reemplaza el catalogo cacheado y registra el refresco."""
        con = self._con()
        try:
            con.execute("BEGIN")
            if entries:
                con.executemany(
                    "INSERT INTO contract_catalog (symbol, base_asset,"
                    " quote_asset, margin_asset, contract_type, status,"
                    " onboard_ms, price_precision, tick_size, eligible,"
                    " exclusion_reasons, fetched_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
                    " ON CONFLICT(symbol) DO UPDATE SET"
                    "  base_asset=excluded.base_asset,"
                    "  quote_asset=excluded.quote_asset,"
                    "  margin_asset=excluded.margin_asset,"
                    "  contract_type=excluded.contract_type,"
                    "  status=excluded.status,"
                    "  onboard_ms=excluded.onboard_ms,"
                    "  price_precision=excluded.price_precision,"
                    "  tick_size=excluded.tick_size,"
                    "  eligible=excluded.eligible,"
                    "  exclusion_reasons=excluded.exclusion_reasons,"
                    "  fetched_at=excluded.fetched_at",
                    [(
                        str(e.get("symbol")), e.get("base_asset"),
                        e.get("quote_asset"), e.get("margin_asset"),
                        e.get("contract_type"), e.get("status"),
                        e.get("onboard_ms"), e.get("price_precision"),
                        e.get("tick_size"), 1 if e.get("eligible") else 0,
                        json.dumps(e.get("exclusion_reasons") or []),
                        int(fetched_at_ms),
                    ) for e in entries if e.get("symbol")],
                )
            con.commit()
            return len(entries)
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def read_catalog(self, query: str = "", limit: int = 50,
                     eligible_only: bool = False,
                     order: str = "relevance") -> List[Dict[str, Any]]:
        con = self._con()
        try:
            q = (query or "").strip().upper()
            where: List[str] = []
            params: List[Any] = []
            if q:
                where.append("(symbol LIKE ? OR UPPER(COALESCE(base_asset,''))"
                             " LIKE ?)")
                params.extend([f"%{q}%", f"%{q}%"])
            if eligible_only:
                where.append("eligible = 1")
            clause = (" WHERE " + " AND ".join(where)) if where else ""
            if order == "symbol":
                order_clause = " ORDER BY symbol ASC"
            else:
                order_clause = (" ORDER BY (symbol = ?) DESC, eligible DESC,"
                                " symbol ASC")
                params.append(q)
            params.append(max(1, min(int(limit), 500)))
            rows = con.execute(
                "SELECT symbol, base_asset, quote_asset, margin_asset,"
                " contract_type, status, onboard_ms, price_precision, tick_size,"
                " eligible, exclusion_reasons, fetched_at"
                f" FROM contract_catalog{clause}{order_clause} LIMIT ?",
                params,
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for row in rows:
                item = _row_to_dict(row)
                try:
                    reasons = json.loads(item.get("exclusion_reasons") or "[]")
                except (TypeError, ValueError):
                    reasons = []
                item["exclusion_reasons"] = reasons
                item["eligible"] = bool(item.get("eligible"))
                out.append(item)
            return out
        finally:
            con.close()

    def read_catalog_snapshot(self) -> List[Dict[str, Any]]:
        """Catalogo completo, sin el tope de la busqueda (para el diff).

        `read_catalog` limita a 500 filas por ser una API de busqueda; comparar
        un catalogo de 931+ contratos con solo 500 produciria altas y bajas
        falsas.
        """
        con = self._con()
        try:
            rows = con.execute(
                "SELECT symbol, contract_type, status, eligible, base_asset,"
                " quote_asset FROM contract_catalog ORDER BY symbol ASC"
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for row in rows:
                item = _row_to_dict(row)
                item["eligible"] = bool(item.get("eligible"))
                out.append(item)
            return out
        finally:
            con.close()

    def catalog_count(self) -> int:
        con = self._con()
        try:
            row = con.execute(
                "SELECT COUNT(*) n, SUM(eligible) e FROM contract_catalog"
            ).fetchone()
            return int(row["n"] or 0)
        finally:
            con.close()

    def record_contract_events(self, rows: Iterable[Tuple[str, str, Any, Any]],
                               at_ms: int) -> int:
        """Registra episodios (listado/baja) sin inferir estado."""
        payload = [(int(at_ms), str(s), str(k), t, st, None)
                   for (s, k, t, st) in rows]
        if not payload:
            return 0
        con = self._con()
        try:
            con.executemany(
                "INSERT INTO contract_events (at_ms, symbol, kind,"
                " contract_type, status, note) VALUES (?,?,?,?,?,?)", payload)
            con.commit()
            return len(payload)
        finally:
            con.close()

    # --- velas -----------------------------------------------------------

    def upsert_klines(self, symbol: str, interval: str, source: str,
                      bars: Sequence[Dict[str, Any]], fetched_at_ms: int) -> int:
        if not bars:
            return 0
        payload = [(
            str(symbol).upper(), str(interval), str(source),
            int(b["open_time"]), str(b.get("open")), str(b.get("high")),
            str(b.get("low")), str(b.get("close")), b.get("base_volume"),
            b.get("quote_volume"), b.get("trade_count"), b.get("close_time"),
            int(fetched_at_ms),
        ) for b in bars if b.get("open_time") is not None]
        con = self._con()
        try:
            con.execute("BEGIN")
            con.executemany(
                "INSERT INTO market_klines (symbol, interval, source, open_time,"
                " open, high, low, close, base_volume, quote_volume,"
                " trade_count, close_time, fetched_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(symbol, interval, source, open_time) DO UPDATE SET"
                "  open=excluded.open, high=excluded.high, low=excluded.low,"
                "  close=excluded.close, base_volume=excluded.base_volume,"
                "  quote_volume=excluded.quote_volume,"
                "  trade_count=excluded.trade_count,"
                "  close_time=excluded.close_time,"
                "  fetched_at=excluded.fetched_at",
                payload,
            )
            con.commit()
            return len(payload)
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def read_klines(self, symbol: str, interval: str, source: str,
                    from_ms: Optional[int] = None,
                    to_ms: Optional[int] = None,
                    limit: int = MAX_SERIES_LIMIT,
                    newest_first: bool = False) -> List[Dict[str, Any]]:
        con = self._con()
        try:
            where = ["symbol = ?", "interval = ?", "source = ?"]
            params: List[Any] = [str(symbol).upper(), str(interval), str(source)]
            if from_ms is not None:
                where.append("open_time >= ?")
                params.append(int(from_ms))
            if to_ms is not None:
                where.append("open_time <= ?")
                params.append(int(to_ms))
            direction = "DESC" if newest_first else "ASC"
            params.append(max(1, int(limit)))
            rows = con.execute(
                "SELECT open_time, open, high, low, close, base_volume,"
                " quote_volume, trade_count, close_time, fetched_at"
                " FROM market_klines WHERE " + " AND ".join(where)
                + f" ORDER BY open_time {direction} LIMIT ?",
                params,
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            con.close()

    def coverage_bounds(self, symbol: str, interval: str, source: str) -> Dict[str, Any]:
        con = self._con()
        try:
            row = con.execute(
                "SELECT COUNT(*) n, MIN(open_time) first_open,"
                " MAX(open_time) last_open, MAX(fetched_at) fetched_at"
                " FROM market_klines WHERE symbol=? AND interval=? AND source=?",
                (str(symbol).upper(), str(interval), str(source)),
            ).fetchone()
            return {"count": int(row["n"] or 0),
                    "first_open_ms": row["first_open"],
                    "last_open_ms": row["last_open"],
                    "fetched_at_ms": row["fetched_at"]}
        finally:
            con.close()

    # --- presupuesto -----------------------------------------------------

    def record_fetch(self, at_ms: int, symbol: Optional[str],
                     interval: Optional[str], source: Optional[str],
                     requests: int, retries: int = 0, failures: int = 0,
                     status: str = "ok", note: Optional[str] = None,
                     execution_id: Optional[str] = None,
                     detail: Optional[str] = None) -> None:
        con = self._con()
        try:
            con.execute(
                "INSERT INTO market_fetch_ledger (at_ms, symbol, interval,"
                " source, requests, retries, failures, status, note,"
                " execution_id, detail)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (int(at_ms), symbol, interval, source, int(requests),
                 int(retries), int(failures), str(status), note,
                 execution_id, detail),
            )
            con.commit()
        finally:
            con.close()

    def reserve_fetch_attempt(self, at_ms: int, symbol: Optional[str],
                              detail: Optional[str],
                              max_requests: int = MAX_FETCH_REQUESTS_PER_WINDOW,
                              window_ms: int = ROLLING_WINDOW_MS,
                              attempts: int = 1,
                              execution_id: Optional[str] = None,
                              run_max_requests: Optional[int] = None,
                              ) -> Optional[int]:
        """Reserva ``attempts`` upstream en la ventana compartida.

        Chequeo e insercion en UNA transaccion (BEGIN IMMEDIATE), de modo que
        dos procesos concurrentes que comparten el archivo del ledger
        nunca pasan ambos si el limite no alcanza. En denegacion queda una
        fila ``budget_blocked`` con ``requests=0`` (auditoria sin consumo).
        Devuelve el id de fila reservado, o None si la reserva fue denegada.

        Cuando ``run_max_requests`` se indica, ademas se valida el presupuesto
        TOTAL de la corrida, atribuido persistentemente al ``execution_id``
        (run_id) en el ledger: ``SUM(requests)`` de reservas previas de esa
        corrida. Se comparte entre /time, klines, catalogo, reintentos y
        recuperacion y NO se reinicia al pasar la ventana movil de 60 s. La
        reserva de ambos cupos (ventana y corrida) es atomica en la misma
        transaccion: si alguno se agota, no se envia nada.
        """
        con = self._con()
        try:
            try:
                con.execute("BEGIN IMMEDIATE")
                # 1) Limite general de ventana movil (30 por 60 s).
                row = con.execute(
                    "SELECT COALESCE(SUM(requests), 0) n FROM"
                    " market_fetch_ledger WHERE at_ms > ?",
                    (int(at_ms) - int(window_ms),),
                ).fetchone()
                used = int(row["n"] or 0)
                # 2) Presupuesto total de la corrida (no se reinicia por
                #    ventana; solo comienza en cero para un run_id nuevo).
                run_total = 0
                if run_max_requests is not None and execution_id is not None:
                    rrow = con.execute(
                        "SELECT COALESCE(SUM(requests), 0) n FROM"
                        " market_fetch_ledger WHERE execution_id = ?",
                        (execution_id,),
                    ).fetchone()
                    run_total = int(rrow["n"] or 0)
                if used + int(attempts) > int(max_requests) or \
                        (run_max_requests is not None and
                         run_total + int(attempts) > int(run_max_requests)):
                    blocked = {
                        "status": "blocked_pre_send",
                        "used_in_window": used,
                        "max_requests": int(max_requests),
                        "requested": int(attempts),
                        "run_used": run_total,
                        "run_max_requests": (
                            int(run_max_requests)
                            if run_max_requests is not None else None),
                    }
                    con.execute(
                        "INSERT INTO market_fetch_ledger (at_ms, symbol,"
                        " requests, retries, failures, status, note,"
                        " execution_id, detail)"
                        " VALUES (?,?,0,0,0,'budget_blocked',?,?,?)",
                        (int(at_ms), symbol, json.dumps(blocked, sort_keys=True),
                         execution_id, detail),
                    )
                    con.commit()
                    return None
                con.execute(
                    "INSERT INTO market_fetch_ledger (at_ms, symbol, requests,"
                    " retries, failures, status, note, execution_id, detail)"
                    " VALUES (?,?,?,0,0,'reserved',?,?,?)",
                    (int(at_ms), symbol, int(attempts), None, execution_id,
                     detail),
                )
                new_id = int(con.execute(
                    "SELECT last_insert_rowid()").fetchone()[0])
                con.commit()
                return new_id
            except BaseException:
                con.rollback()
                raise
        finally:
            con.close()

    def complete_fetch_row(self, row_id: int, status: str,
                           retries: int = 0, failures: int = 0,
                           requests: Optional[int] = None,
                           note: Optional[str] = None,
                           detail: Optional[str] = None) -> None:
        """Cierra la fila reservada con el resultado real del intento."""
        con = self._con()
        try:
            if requests is None:
                con.execute(
                    "UPDATE market_fetch_ledger SET status=?, retries=?,"
                    " failures=?, note=? WHERE id=?",
                    (str(status), int(retries), int(failures), note,
                     int(row_id)),
                )
            else:
                con.execute(
                    "UPDATE market_fetch_ledger SET status=?, retries=?,"
                    " failures=?, requests=?, note=? WHERE id=?",
                    (str(status), int(retries), int(failures),
                     int(requests), note, int(row_id)),
                )
            if detail is not None:
                con.execute(
                    "UPDATE market_fetch_ledger SET detail=? WHERE id=?",
                    (detail, int(row_id)),
                )
            con.commit()
        finally:
            con.close()

    def requests_in_window(self, now_ms: int,
                           window_ms: int = ROLLING_WINDOW_MS) -> int:
        con = self._con()
        try:
            row = con.execute(
                "SELECT COALESCE(SUM(requests), 0) n FROM market_fetch_ledger"
                " WHERE at_ms > ?", (int(now_ms) - int(window_ms),),
            ).fetchone()
            return int(row["n"] or 0)
        finally:
            con.close()

    def window_usage(self, now_ms: Optional[int] = None,
                     window_ms: int = ROLLING_WINDOW_MS,
                     max_requests: int = MAX_FETCH_REQUESTS_PER_WINDOW
                     ) -> Dict[str, Any]:
        """Uso corriente de la ventana compartida (para mensajes y payload)."""
        now = int(now_ms if now_ms is not None else time.time() * 1000)
        return {"used_in_window": self.requests_in_window(now, window_ms),
                "max_requests_per_window": int(max_requests),
                "window_ms": int(window_ms)}

    def run_requests_used(self, run_id: str) -> int:
        """Suma de intentos ya reservados contra el presupuesto total de la
        corrida ``run_id``, leída del ledger. No se reinicia al pasar la
        ventana movil; solo comienza en cero para un run_id nuevo."""
        con = self._con()
        try:
            row = con.execute(
                "SELECT COALESCE(SUM(requests), 0) n FROM market_fetch_ledger"
                " WHERE execution_id = ?", (run_id,),
            ).fetchone()
            return int(row["n"] or 0)
        finally:
            con.close()

    def fetch_ledger(self, limit: int = 20) -> List[Dict[str, Any]]:
        con = self._con()
        try:
            rows = con.execute(
                "SELECT id, at_ms, symbol, interval, source, requests, retries,"
                " failures, status, note, execution_id, detail"
                " FROM market_fetch_ledger"
                " ORDER BY id DESC LIMIT ?", (max(1, int(limit)),),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            con.close()

    def fetch_rows_by_execution(self, execution_id: str) -> List[Dict[str, Any]]:
        """Filas del ledger de UNA ejecucion, en orden cronologico exacto."""
        con = self._con()
        try:
            rows = con.execute(
                "SELECT id, at_ms, symbol, interval, source, requests, retries,"
                " failures, status, note, execution_id, detail"
                " FROM market_fetch_ledger WHERE execution_id = ?"
                " ORDER BY id ASC", (execution_id,),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            con.close()
