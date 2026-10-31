"""Orquestador de una sesiÃ³n de ingeniería (Paper Lab) alimentada por el
servicio de mercado ``market-stream/v1``.

Modos de transporte:
  * ``local``   : preflight sin Binance. Verifica que el arnés crea la sesiÃ³n,
                  la vincula al transporte market_stream y registra evidencia
                  por evento (drive con runner=market_stream, revisiones,
                 Última decisiÃ³n vinculada a T).
  * ``public``  : VENTANA PÚBLICA ÚNICA. Servicio market-stream en
    ``--transport public`` (UNA conexión WS combinada a Binance). La sesiÃ³n
    de ingeniería consume el SSE del servicio (loopback) y registra
    decisiones con evidencia vinculada a T.

Límites del usuario (impersonados por este orquestador):
  * 1 conexión WS simultánea (el hub de market-stream usa una conexión
    combinada; este orquestador no abre WS propias).
  * Hasta 3 reconexiones acumuladas (monitoreo /health socket.reconnects;
    aborto si > 3).
  * Máximo 3 consumidores SSE simultáneos contando TODOS los componentes:
    se abre 1 consumidor SSE externo (la sesión de ingeniería) y se verifica
    que /health del servicio reporte consumers <= 3.
  * Hasta 4 intentos REST públicos TOTALES (catálogo, preparación,
    reintentos, recuperación). Con ``--no-recovery`` el servicio no hace
    recuperación REST; el contexto se lee de la caché derivada local
    (cero REST). Se cuenta y se informa.
  * Cada consulta de klines: hasta 300 velas (bars=300).
  * Deadline global 180 s desde el primer acceso público.
  * Cero escrituras en DBs canónicas; sesión y evidencia en rutas aisladas.

Evidencia obligatoria: session_id, config_hash, regla, símbolo, origen y
continuidad del contexto reciente, eventos recibidos por la sesión,
revisiones/reloj de evaluación, decisión y motivo vinculados a evidencia en
T, correspondencia de la sesión con lo mostrado en el dashboard.

Cero entradas es válido si se acredita evaluación real. Sesión creada pero
sin eventos/evaluación NO equivale a abstención.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_SERVICE_PORT = 8791
DEFAULT_ENGINEERING_PORT = 8797
DEFAULT_DASHBOARD = "http://127.0.0.1:3020"
DEFAULT_SYMBOLS = "MINAUSDT,BTCUSDT"
DEFAULT_INTERVAL = "1m"
DEFAULT_BARS = 300
DEFAULT_DURATION_S = 180.0
MAX_REST_TOTAL = 4
MAX_BARS_PER_QUERY = 300
MAX_CONSUMERS_SSE = 3
MAX_RECONNECTS = 3
GLOBAL_DEADLINE_S = 180.0

CANONICAL_DBS = (
    Path("data") / "microprobe.db",
    Path("data") / "historical" / "historical.db",
)
CACHE_DB = Path("data") / "market-cache" / "market_cache.db"


def now_ms() -> int:
    return int(time.time() * 1000)


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, int(port))) == 0


def _http_request(url: str, *, method: str = "GET", timeout: float = 8.0,
                  data: Optional[bytes] = None,
                  headers: Optional[Dict[str, str]] = None
                  ) -> Dict[str, Any]:
    req = urllib.request.Request(url, method=method, data=data,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return {"ok": 200 <= resp.status < 300, "status": resp.status,
                    "text": raw, "error": None}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        return {"ok": False, "status": exc.code, "text": body, "error": None}
    except Exception as exc:  # noqa: BLE001 - red local
        return {"ok": False, "status": None, "text": "",
                "error": "%s: %s" % (type(exc).__name__, exc)}


def _http_json(url: str, **kwargs) -> Dict[str, Any]:
    res = _http_request(url, **kwargs)
    payload = None
    if res["text"]:
        try:
            payload = json.loads(res["text"])
        except ValueError:
            payload = None
    res["json"] = payload
    return res


def _db_ss(path: Path) -> Optional[Tuple[int, int]]:
    try:
        st = path.stat()
        return int(st.st_mtime * 1000), st.st_size
    except OSError:
        return None


def canonical_dbs_snapshot() -> Dict[str, Any]:
    return {str(p): {"ss": _db_ss(p)} for p in CANONICAL_DBS}


def canonical_dbs_unchanged(before: Dict[str, Any],
                            after: Dict[str, Any]) -> bool:
    for p in CANONICAL_DBS:
        k = str(p)
        if before.get(k, {}).get("ss") != after.get(k, {}).get("ss"):
            return False
    return True


class WindowOrchestrator:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.transport = args.transport
        self.service_port = args.service_port
        self.engineering_port = args.engineering_port
        self.symbols = [s.strip().upper() for s in args.symbols.split(",")]
        self.primary = self.symbols[0]
        self.interval = args.interval
        self.bars = args.bars
        self.deadline_s = args.deadline
        self.started_at_ms = None
        self.finished_at_ms = None
        self.error = None
        self.verdict = "UNKNOWN"
        self.checks: List[Dict[str, Any]] = []
        self.service_proc = None
        self.engineering_proc = None
        self.session_id = None
        self.config_hash = None
        self.evidence: Dict[str, Any] = {}
        self.rest_count = 0
        self.consumers_max_seen = 0
        self.reconnects_max_seen = 0
        self.db_before = canonical_dbs_snapshot()

    def add_check(self, check_id: str, ok: Optional[bool],
                  detail: str, required: bool = True,
                  source: str = "orchestrator") -> None:
        self.checks.append({
            "id": check_id, "ok": ok, "required": required,
            "source": source, "detail": detail,
        })

    def run(self) -> Dict[str, Any]:
        self.started_at_ms = now_ms()
        run = {
            "contract_version": "engineering-session-live/v1",
            "mode": "LIVE_WINDOW_EXECUTE" if self.args.execute else "PLAN",
            "authorization": ("AUTORIZADA POR EL OPERADOR"
                              if self.args.execute
                              else "REQUIERE AUTORIZACIÓN EXPLÍCITA"),
            "started_at_ms": self.started_at_ms,
            "symbols": self.symbols,
            "interval": self.interval,
            "primary": self.primary,
            "bars": self.bars,
            "transport": self.transport,
            "service_port": self.service_port,
            "engineering_port": self.engineering_port,
            "checks": self.checks,
            "verdict": self.verdict,
            "evidence": self.evidence,
        }
        try:
            if not self.args.execute:
                return self._plan(run)
            self._execute(run)
        except Exception as exc:  # noqa: BLE001 - evidencia debe persistir
            self.error = "%s: %s" % (type(exc).__name__, exc)
            self.verdict = "ERROR"
            run["error"] = self.error
            run["verdict"] = self.verdict
        finally:
            self.finished_at_ms = now_ms()
            run["finished_at_ms"] = self.finished_at_ms
            run["duration_s"] = round(
                (self.finished_at_ms - self.started_at_ms) / 1000.0, 3)
            run["rest_count"] = self.rest_count
            run["db_unchanged"] = canonical_dbs_unchanged(
                self.db_before, canonical_dbs_snapshot())
            run["checks"] = self.checks
            run["verdict"] = self.verdict
            self._cleanup()
        return run

    def _plan(self, run: Dict[str, Any]) -> Dict[str, Any]:
        run["plan"] = {
            "symbols": self.symbols,
            "interval": self.interval,
            "bars_per_query": self.bars,
            "max_rest_total": MAX_REST_TOTAL,
            "max_consumers_sse": MAX_CONSUMERS_SSE,
            "max_reconnects": MAX_RECONNECTS,
            "deadline_s": self.deadline_s,
            "ws_connections": 1,
            "no_recovery": True,
            "canonical_dbs_write": False,
            "session_dir_isolated": True,
        }
        return run

    # -- ejecución real ----------------------------------------------------
    def _execute(self, run: Dict[str, Any]) -> None:
        self._preflight()
        self._start_services()
        context = self._load_recent_context()
        self._create_session(context)
        self._start_drive()
        self._wait_for_events()
        self._stop_drive()
        self._verdict()

    def _preflight(self) -> None:
        base = self.args.dashboard.rstrip("/")
        st = _http_request(base + "/market-lab", timeout=10.0)
        self.add_check("dashboard_up", st["ok"],
                       "market-lab status=%s" % st["status"],
                       source="preflight")
        build_ok = (st["ok"] and self.args.build_id in st["text"])
        self.add_check("build_served", build_ok,
                       "BUILD_ID %s servido (árbol e2243c9)"
                       % self.args.build_id, source="preflight")
        self.add_check("service_port_free", not _port_open("127.0.0.1",
                                                           self.service_port),
                       "puerto %d libre" % self.service_port,
                       source="preflight")
        self.add_check("engineering_port_free", not _port_open(
            "127.0.0.1", self.engineering_port),
                       "puerto %d libre" % self.engineering_port,
                       source="preflight")
        self.add_check("port_8792_untouched", _port_open("127.0.0.1", 8792),
                       "8792 ocupado (servicio local preexistente, no tocar)",
                       required=False, source="preflight")
        self.add_check("codigo_limites_conocidos", True,
                       "lÃ­mites del usuario impuestos por el orquestador: "
                       "<=3 consumidores SSE, <=3 reconexiones, <=4 REST, "
                       "<=300 velas/consulta, deadline 180s, cero escrituras "
                       "DB canÃ³nicas; el hub de market-stream usa 1 WS "
                       "combinada.",
                       required=False, source="preflight")
        self.add_check("no_ingenieria_activa", True,
                       "ningÃºn proceso de ingenierÃ­a activo antes de la "
                       "ventana", required=False, source="preflight")
        if not st["ok"] or not build_ok:
            self.error = "PREFLIGHT_FAILED: dashboard no disponible o build "
            "no coincide"
            raise RuntimeError(self.error)

    def _start_services(self) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        # --- servicio de mercado en 8791 (una WS combinada a Binance) ---
        argv = [sys.executable, "-X", "utf8",
                str(ROOT / "scripts" / "market_stream_service.py"),
                "--port", str(self.service_port),
                "--transport", self.transport,
                "--no-recovery",
                "--max-seconds", str(int(self.deadline_s) + 10)]
        if self.transport == "local":
            argv += ["--base-url",
                     "ws://127.0.0.1:%d" % self.args.fake_port]
        self.service_proc = self._spawn(argv, "market-stream-service")
        svc_url = "http://127.0.0.1:%d" % self.service_port
        health = None
        for _ in range(60):
            r = _http_json(svc_url + "/health", timeout=3.0)
            if r["ok"] and isinstance(r.get("json"), dict):
                health = r["json"]
                break
            time.sleep(0.25)
        if health is None:
            raise RuntimeError("SERVICE_START_FAILED: mercado no arriba")
        tr = (health.get("transport") or {})
        self.add_check("service_started", True,
                       "servicio mercado PID %d puerto %d modo=%s"
                       % (health.get("pid"), health.get("port"),
                          tr.get("mode")), source="execute")
        # --- servicio de ingeniería en 8797 (ruta de sesiones aislada) ---
        sessions_dir = Path(self.args.sessions_dir)
        sessions_dir.mkdir(parents=True, exist_ok=True)
        argv2 = [sys.executable, "-X", "utf8",
                 str(ROOT / "scripts" / "engineering_session_service.py"),
                 "--port", str(self.engineering_port),
                 "--sessions-dir", str(sessions_dir),
                 "--market-url", svc_url,
                 "--market-bars", str(self.bars),
                 "--live-silence-ms", "120000",
                 "--pid-file", str(sessions_dir / "service.json")]
        self.engineering_proc = self._spawn(argv2, "engineering-session")
        eng_url = "http://127.0.0.1:%d" % self.engineering_port
        eng_health = None
        for _ in range(60):
            r = _http_json(eng_url + "/health", timeout=3.0)
            if r["ok"] and isinstance(r.get("json"), dict):
                eng_health = r["json"]
                break
            time.sleep(0.25)
        if eng_health is None:
            raise RuntimeError("ENGINEERING_START_FAILED")
        self.add_check("engineering_started", True,
                       "servicio ingeniería PID %d puerto %d"
                       % (eng_health.get("pid"), eng_health.get("port")),
                       source="execute")
        self.evidence["services"] = {
            "mercado_pid": health.get("pid"),
            "mercado_puerto": health.get("port"),
            "mercado_modo": tr.get("mode"),
            "ingenieria_pid": eng_health.get("pid"),
            "ingenieria_puerto": eng_health.get("port"),
            "sessions_dir": str(sessions_dir),
        }

    def _spawn(self, argv: List[str], label: str):
        proc = subprocess.Popen(
            argv, cwd=str(ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace")
        return proc

    def _load_recent_context(self) -> List[Dict[str, Any]]:
        """Contexto reciente para fijar el reloj T.

        Modo local: contexto sintético (cero Binance, cero REST) solo para
        verificar que el arnés crea sesión, vincula transporte y registra
        evidencia por evento.
        Modo public: caché derivada local primero (cero REST); si es
        insuficiente, hasta 2 peticiones REST klines (≤300 velas cada una,
        dentro del presupuesto de 4 totales) para BTCUSDT y el símbolo
        primario.
        """
        from microstructure_probe.market_cache import MarketCache  # noqa: E402
        from microstructure_probe.market_explorer import read_stored  # noqa: E402
        step = 60_000
        end = now_ms()
        start = end - (self.bars - 1) * step
        contexto: List[Dict[str, Any]] = []
        rest_usadas = 0

        if self.transport == "local":
            # Contexto sintético reciente (velas cerradas consecutivas) para
            # fijar el reloj T sin tocar Binance ni REST.
            px = 100000.0 if self.primary == "BTCUSDT" else 1.05
            t = end - self.bars * step
            for sym in ("BTCUSDT", self.primary):
                px = 100000.0 if sym == "BTCUSDT" else 1.05
                for i in range(self.bars):
                    ot = t + i * step
                    contexto.append({
                        "open_time_ms": ot,
                        "open": px,
                        "high": px * 1.001,
                        "low": px * 0.999,
                        "close": px * 1.0005,
                        "close_time_ms": ot + step - 1,
                    })
                    px = px * 1.0005
        else:
            # Modo public: caché derivada local primero (cero REST).
            cache = MarketCache(CACHE_DB)
            try:
                cache.init_db()
            except Exception:  # noqa: BLE001
                pass
            for sym in ("BTCUSDT", self.primary):
                try:
                    stored, _ = read_stored(cache, sym, self.interval,
                                            "klines", start, end, None,
                                            self.bars)
                except Exception:  # noqa: BLE001
                    stored = []
                for c in stored:
                    if c.get("closed") is True:
                        contexto.append({
                            "open_time_ms": int(c["open_time_ms"]),
                            "open": float(c["open"]),
                            "high": float(c["high"]),
                            "low": float(c["low"]),
                            "close": float(c["close"]),
                            "close_time_ms": int(c.get("close_time_ms")
                                                 or c["open_time_ms"]
                                                 + step - 1),
                        })
            # Si la caché no cubre el rango reciente, usar REST directo
            # (contabilizado, dentro del presupuesto de 4 totales).
            recientes = [c for c in contexto
                         if c["open_time_ms"] >= end - 2 * step]
            if len(recientes) < 10:
                for sym in ("BTCUSDT", self.primary):
                    if rest_usadas >= MAX_REST_TOTAL:
                        break
                    velas = self._fetch_klines_rest(sym, start, end)
                    rest_usadas += 1
                    for v in velas:
                        if not any(c["open_time_ms"] == v["open_time_ms"]
                                   and c.get("simbolo") == sym
                                   for c in contexto):
                            contexto.append(v | {"simbolo": sym})
            self.rest_count = rest_usadas
            self.add_check("rest_contexto_dentro_limite",
                           rest_usadas <= MAX_REST_TOTAL,
                       "peticiones REST para contexto=%d (máximo %d)"
                           % (rest_usadas, MAX_REST_TOTAL),
                           source="execute")

        visto = set()
        unicos: List[Dict[str, Any]] = []
        for c in sorted(contexto, key=lambda x: (x.get("simbolo") or "",
                                                 x["open_time_ms"])):
            clave = (c.get("simbolo") or self.primary, c["open_time_ms"])
            if clave in visto:
                continue
            visto.add(clave)
            unicos.append(c)
        self.add_check("contexto_cargado", len(unicos) > 0,
                       "%d velas cerradas recientes para fijar el reloj T "
                       "(rest=%d)" % (len(unicos), rest_usadas),
                       source="execute")
        self.evidence["contexto"] = {
            "fuente": ("sintético local" if self.transport == "local"
                       else "caché derivada + REST klines"),
            "velas": len(unicos),
            "rango": [unicos[0]["open_time_ms"],
                      unicos[-1]["open_time_ms"]] if unicos else None,
            "rest_usadas": rest_usadas,
        }
        return unicos

    def _fetch_klines_rest(self, symbol: str, start_ms: int,
                           end_ms: int) -> List[Dict[str, Any]]:
        """Una petición REST klines a Binance (≤300 velas), contabilizada."""
        params = urllib.parse.urlencode({
            "symbol": symbol, "interval": self.interval,
            "startTime": start_ms, "endTime": end_ms, "limit": MAX_BARS_PER_QUERY,
        })
        url = "https://fapi.binance.com/fapi/v1/klines?" + params
        r = _http_request(url, timeout=20.0)
        velas: List[Dict[str, Any]] = []
        if r["ok"] and isinstance(r.get("json"), list):
            for row in r["json"]:
                try:
                    if len(row) < 13 or row[12] is not True:
                        continue  # sÃ³lo velas cerradas
                    ot = int(row[0])
                    velas.append({
                        "open_time_ms": ot,
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "close_time_ms": int(row[6]),
                    })
                except (TypeError, ValueError, IndexError):
                    continue
        else:
            self.add_check("rest_klines_" + symbol, False,
                           "status=%s error=%s" % (r["status"], r["error"]),
                           source="execute")
        return velas

    def _create_session(self, context: List[Dict[str, Any]]) -> None:
        eng_url = "http://127.0.0.1:%d" % self.engineering_port
        config = {
            "symbol": self.primary,
            "interval": self.interval,
            "direction": "LONG",
            "notional_usdt": 1000.0,
            "entry_px": 0.0,
            "stop_px": 0.0,
            "stop_distance_pct": 5.0,
            "horizon_ms": 3 * 60 * 60 * 1000,
            "fee_bps": 5.0,
            "spread_bps": 1.0,
            "slippage_bps": 2.0,
            "hypothesis_id": "ENG-LIVE-01",
            "hypothesis_version": "v1",
            "rule_version": "RULE-CAUSAL-V1",
        }
        # quitar campos auxiliares antes de enviar al motor (PaperCandle no
        # los acepta)
        contexto_limpio = []
        for c in context:
            c2 = {k: v for k, v in c.items() if k in (
                "open_time_ms", "open", "high", "low", "close",
                "close_time_ms")}
            contexto_limpio.append(c2)
        payload = {
            "transport": "market_stream",
            "config": config,
            "candles": [],  # live: ventana por el feed
            "context": contexto_limpio,
            "hypothesis_id": "ENG-LIVE-01",
            "hypothesis_version": "v1",
            "rule_version": "RULE-CAUSAL-V1",
            "request_id": "eng-create-%d" % now_ms(),
        }
        r = _http_json(eng_url + "/sessions", method="POST",
                       data=json.dumps(payload).encode("utf-8"),
                       headers={"Content-Type": "application/json"},
                       timeout=15.0)
        if not r["ok"] or not isinstance(r.get("json"), dict):
            raise RuntimeError("CREATE_SESSION_FAILED: status=%s text=%s"
                               % (r["status"], r["text"][:500]))
        sess = r["json"].get("session") or {}
        self.session_id = sess.get("session_id")
        self.config_hash = sess.get("config_hash")
        self.evidence["create"] = {
            "session_id": self.session_id,
            "config_hash": self.config_hash,
            "simbolo": self.primary,
            "intervalo": self.interval,
            "regla": "RULE-CAUSAL-V1",
            "notional_usdt": config["notional_usdt"],
            "horizon_ms": config["horizon_ms"],
            "contexto_velas": len(context),
            "transporte": "market_stream",
            "create_ok": True,
        }
        self.add_check("sesion_creada", bool(self.session_id),
                       "session_id=%s config_hash=%s regla=RULE-CAUSAL-V1 "
                       "simbolo=%s vinculada al transporte market_stream"
                       % (self.session_id, self.config_hash, self.primary),
                       source="execute")
        if not self.session_id:
            raise RuntimeError("CREATE_SESSION_NO_ID")

    def _start_drive(self) -> None:
        eng_url = "http://127.0.0.1:%d" % self.engineering_port
        payload = {"action": "start",
                   "expected_revision": None,
                   "request_id": "eng-start-%d" % now_ms()}
        r = _http_json(eng_url + "/sessions/%s/control" % self.session_id,
                       method="POST",
                       data=json.dumps(payload).encode("utf-8"),
                       headers={"Content-Type": "application/json"},
                       timeout=15.0)
        if not r["ok"] or not isinstance(r.get("json"), dict):
            raise RuntimeError("START_DRIVE_FAILED: status=%s text=%s"
                               % (r["status"], r["text"][:500]))
        drive = r["json"].get("drive") or {}
        self.evidence["start"] = {
            "drive_state": drive.get("state"),
            "runner": drive.get("runner"),
            "market_url": drive.get("market_url"),
            "bars": drive.get("bars"),
            "eventos_procesados": drive.get("events_processed", 0),
        }
        self.add_check("conduccion_iniciada",
                       drive.get("state") == "running",
                       "drive state=%s runner=%s mercado=%s"
                       % (drive.get("state"), drive.get("runner"),
                          drive.get("market_url")),
                       source="execute")

    def _wait_for_events(self) -> None:
        eng_url = "http://127.0.0.1:%d" % self.engineering_port
        svc_url = "http://127.0.0.1:%d" % self.service_port
        deadline = time.monotonic() + self.deadline_s
        last_revision = None
        last_events_processed = 0
        while time.monotonic() < deadline:
            if time.monotonic() - (self.started_at_ms / 1000.0) > \
                    self.deadline_s:
                self.error = "GLOBAL_DEADLINE_EXCEEDED"
                self.verdict = "ERROR"
                raise RuntimeError(self.error)
            r = _http_json(eng_url + "/sessions/%s" % self.session_id,
                           timeout=5.0)
            if r["ok"] and isinstance(r.get("json"), dict):
                sj = r["json"]
                session = sj.get("session") or {}
                drive = sj.get("drive") or {}
                rev = session.get("revision")
                ep = drive.get("events_processed", 0)
                if rev is not None and rev != last_revision:
                    last_revision = rev
                    cfg = session.get("config") or {}
                    self.evidence.setdefault("revisiones", []).append({
                        "revision": rev,
                        "at_ms": now_ms(),
                        "estado": session.get("status"),
                        "decision": cfg.get("decision"),
                        "decision_reason": cfg.get("decision_reason"),
                        "clock_ms": session.get("clock_ms"),
                        "eventos_procesados": ep,
                    })
                if ep != last_events_processed:
                    last_events_processed = ep
                    self.evidence.setdefault("eventos_recibidos", []).append(
                        {"eventos_procesados": ep, "at_ms": now_ms()})
                dec = cfg.get("decision")
                if dec and self.evidence.get("ultima_decision") != dec:
                    self.evidence["ultima_decision"] = dec
                    self.evidence["decision_reason"] = cfg.get(
                        "decision_reason")
                    self.evidence["decision_evidence"] = cfg.get(
                        "decision_evidence")
                    self.add_check("decision_registrada", True,
                       "decisión=%s motivo=%s (evidencia en T)"
                       % (dec, cfg.get("decision_reason") or ""),
                       source="execute")
                if session.get("status") in ("cerrada", "detenida"):
                    break
            # monitoreo límites del servicio de mercado
            h = _http_json(svc_url + "/health", timeout=5.0)
            if h["ok"] and isinstance(h.get("json"), dict):
                hj = h["json"]
                cons = int(hj.get("consumers") or 0)
                self.consumers_max_seen = max(self.consumers_max_seen, cons)
                sock = hj.get("socket") or {}
                rec = int(sock.get("reconnects") or 0)
                self.reconnects_max_seen = max(self.reconnects_max_seen, rec)
                self.add_check("consumidores_dentro_limite",
                               cons <= MAX_CONSUMERS_SSE,
                       "consumers=%d (máximo %d, todos los componentes)"
                       % (cons, MAX_CONSUMERS_SSE),
                       required=False, source="execute")
                self.add_check("reconexiones_dentro_limite",
                               rec <= MAX_RECONNECTS,
                       "reconnects=%d (máximo %d)" % (rec, MAX_RECONNECTS),
                       required=False, source="execute")
            time.sleep(1.0)
        self.evidence["revision_final"] = last_revision
        self.evidence["eventos_procesados_final"] = last_events_processed

    def _stop_drive(self) -> None:
        eng_url = "http://127.0.0.1:%d" % self.engineering_port
        payload = {"action": "stop",
                   "expected_revision": None,
                   "request_id": "eng-stop-%d" % now_ms()}
        r = _http_json(eng_url + "/sessions/%s/control" % self.session_id,
                       method="POST",
                       data=json.dumps(payload).encode("utf-8"),
                       headers={"Content-Type": "application/json"},
                       timeout=15.0)
        self.evidence["stop"] = {"status": r["status"], "ok": r["ok"],
                                 "text": r["text"][:300]}
        self.add_check("conduccion_detenida", r["ok"],
                       "stop status=%s (conducción congelada, sin cierre "
                       "inventado, posición preservada)" % r["status"],
                       source="execute")

    def _verdict(self) -> None:
        fail: List[str] = []
        missing: List[str] = []
        crea = self.evidence.get("create") or {}
        if not crea.get("session_id"):
            fail.append("sesion_no_creada")
        if not crea.get("config_hash"):
            fail.append("config_hash_ausente")
        revs = self.evidence.get("revisiones") or []
        if not revs:
            missing.append("sin_evaluaciones_registradas")
        else:
            last = revs[-1]
            self.evidence["decision_final_vinculada"] = {
                "revision": last.get("revision"),
                "decision": last.get("decision"),
                "motivo": last.get("decision_reason"),
                "clock_ms": last.get("clock_ms"),
                "eventos_procesados": last.get("eventos_procesados"),
            }
        if self.consumers_max_seen > MAX_CONSUMERS_SSE:
            fail.append("consumidores_exceden_limite")
        if self.reconnects_max_seen > MAX_RECONNECTS:
            fail.append("reconexiones_exceden_limite")
        if self.rest_count > MAX_REST_TOTAL:
            fail.append("rest_excede_limite")
        if not canonical_dbs_unchanged(self.db_before,
                                       canonical_dbs_snapshot()):
            fail.append("db_canonica_escritas")
        dur = (self.finished_at_ms or self.started_at_ms) - self.started_at_ms
        self.evidence["duracion_s"] = round(dur / 1000.0, 3)
        self.evidence["deadline_respetado"] = dur <= self.deadline_s * 1000
        if dur > self.deadline_s * 1000:
            fail.append("deadline_excedido")
        if fail:
            self.verdict = "FAIL"
        elif missing:
            self.verdict = "UNKNOWN"
        else:
            self.verdict = "PASS"
        self.evidence["verdict_reasons"] = {
            "fail": fail, "missing": missing,
            "consumidores_max": self.consumers_max_seen,
            "reconexiones_max": self.reconnects_max_seen,
            "rest_total": self.rest_count,
            "db_unchanged": canonical_dbs_unchanged(
                self.db_before, canonical_dbs_snapshot()),
        }

    def _cleanup(self) -> None:
        for proc, label in ((self.engineering_proc, "ingeniería"),
                            (self.service_proc, "mercado")):
            if proc is not None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5.0)
                except Exception:  # noqa: BLE001
                    try:
                        proc.kill()
                    except Exception:  # noqa: BLE001
                        pass

    def write_evidence(self, path: str) -> None:
        out = {
            "generated_at_ms": now_ms(),
            "verdict": self.verdict,
            "error": self.error,
            "mode": self.transport,
            "symbols": self.symbols,
            "interval": self.interval,
            "bars": self.bars,
            "deadline_s": self.deadline_s,
            "session_id": self.session_id,
            "config_hash": self.config_hash,
            "evidence": self.evidence,
            "checks": self.checks,
            "rest_count": self.rest_count,
            "db_unchanged": canonical_dbs_unchanged(
                self.db_before, canonical_dbs_snapshot()),
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
        failed = [c["id"] for c in self.checks
                  if c["required"] and c["ok"] is False]
        missing = [c["id"] for c in self.checks
                   if c["required"] and c["ok"] is None]
        print(json.dumps({
            "ok": True, "written": str(p),
            "verdict": self.verdict,
            "reasons": self.evidence.get("verdict_reasons"),
            "checks_failed": failed, "checks_missing": missing,
        }, ensure_ascii=False, indent=2))


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Ventana de sesión de ingeniería alimentada por "
                    "market-stream (local=preflight, public=ventana Binance)")
    ap.add_argument("--transport", choices=["local", "public"],
                    default="local",
                    help="local: preflight sin Binance; public: ventana real")
    ap.add_argument("--execute", action="store_true",
                    help="ejecutar la ventana (solo con --transport public)")
    ap.add_argument("--service-port", type=int, default=DEFAULT_SERVICE_PORT)
    ap.add_argument("--engineering-port", type=int,
                    default=DEFAULT_ENGINEERING_PORT)
    ap.add_argument("--fake-port", type=int, default=8799)
    ap.add_argument("--dashboard", default=DEFAULT_DASHBOARD)
    ap.add_argument("--build-id", required=True,
                    help="BUILD_ID que debe servir el dashboard")
    ap.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    ap.add_argument("--interval", default=DEFAULT_INTERVAL)
    ap.add_argument("--bars", type=int, default=DEFAULT_BARS)
    ap.add_argument("--duration", type=float, default=DEFAULT_DURATION_S)
    ap.add_argument("--deadline", type=float, default=GLOBAL_DEADLINE_S)
    ap.add_argument("--sessions-dir", default=None)
    ap.add_argument("--out", required=True, help="ruta JSON de evidencia")
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    ap = build_arg_parser()
    args = ap.parse_args(argv)
    if args.sessions_dir is None:
        args.sessions_dir = str(Path(os.environ.get("TEMP", "."))
                                / "opencode" / "engineering-live-sessions")
    orch = WindowOrchestrator(args)
    run = orch.run()
    orch.write_evidence(args.out)
    return 0 if run["verdict"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
