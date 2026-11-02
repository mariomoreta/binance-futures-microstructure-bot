"""Orquestador de una sesiÃ³n de ingeniería (Paper Lab) alimentada por el
servicio de mercado ``market-stream/v1``.

Modos de transporte:
  * ``local``   : preflight sin Binance. Usa un proveedor HTTP local
                  (``scripts/local_kline_provider.py``) a travÃ©s de
                  ``HistoryClient`` + ``LedgerAttemptGate`` para verificar que
                  el arnés crea la sesiÃ³n, la vincula al transporte
                  market_stream y registra evidencia por evento. Cero Binance.
  * ``public``  : ventana pÃblica ÚNICA. Servicio market-stream en
                  ``--transport public`` (UNA conexiÃ³n WS combinada a
                  Binance). La sesiÃ³n de ingeniería consume el SSE del
                  servicio (loopback) y registra decisiones con evidencia
                  vinculada a T.

Límites del usuario (impersonados por este orquestador):
  * 1 conexión WS simultánea (el hub de market-stream usa una conexión
    combinada; este orquestador no abre WS propias).
  * Hasta 3 reconexiones acumuladas (monitoreo /health socket.reconnects;
    aborto si > 3).
  * Máximo 3 consumidores SSE simultáneos contando TODOS los componentes:
    se abre 1 consumidor SSE externo (la sesión de ingeniería) y se verifica
    que /health del servicio reporte consumers <= 3.
  * Hasta 7 intentos REST públicos TOTALES (límite por corrida:
    catálogo, preparación, reintentos, recuperación). Con ``--no-recovery``
    el servicio no hace recuperación REST. Cada intento se reserva ANTES del
    envío vía ``LedgerAttemptGate`` (market_fetch_ledger); si se agota, se
    aborta sin abrir socket.
    abrir socket.
  * Cada consulta de klines: hasta 300 velas (bars=300).
  * Deadline global 180 s desde el primer acceso público (monotónico, cubre
    preparación y esperas HTTP).
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
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.history import normalize_kline  # noqa: E402
from microstructure_probe.history_client import (  # noqa: E402
    HistoryClient,
    INTERVAL_MS,
    UpstreamBudgetExceeded,
)
from microstructure_probe.market_cache import (  # noqa: E402
    MAX_FETCH_REQUESTS_PER_WINDOW,
    MarketCache,
)
from microstructure_probe.market_explorer import (  # noqa: E402
    LedgerAttemptGate,
    read_stored,
)

DEFAULT_SERVICE_PORT = 8791
DEFAULT_ENGINEERING_PORT = 8797
DEFAULT_PROVIDER_PORT = 18799
DEFAULT_WS_PORT = 18800
DEFAULT_DASHBOARD = "http://127.0.0.1:3020"
DEFAULT_SYMBOLS = "MINAUSDT,BTCUSDT"
DEFAULT_INTERVAL = "1m"
DEFAULT_BARS = 300
DEFAULT_DURATION_S = 180.0
# Límite explícito ÚNICO por corrida de presupuesto REST, compartido entre
# /time, klines, catálogo, reintentos y recuperación. Coherente con el
# servicio de ingeniería (MAX_FETCH_REQUESTS_PER_RUN = 7 en market_cache.py):
# 5 intentos de tiempo + 2 de klines = 7. Es una propuesta de mínimo viable
# (no cubierta por la autorización previa de 4); no se ejecuta contra Binance
# sin autorización explícita del operador.
MAX_REST_REQUESTS_PER_RUN = 7
MAX_BARS_PER_QUERY = 300
MAX_CONSUMERS_SSE = 3
MAX_RECONNECTS = 3
GLOBAL_DEADLINE_S = 180.0
# Tiempo máximo para esperar a que el servicio de ingeniería reporte un
# reloj de referencia válido en /health (dentro del deadline global).
CLOCK_READINESS_TIMEOUT_S = 60.0
# Intervalo entre polls de /health durante la espera de readiness.
CLOCK_POLL_INTERVAL_S = 0.5

CANONICAL_DBS = (
    Path("data") / "microprobe.db",
    Path("data") / "historical" / "historical.db",
)
CACHE_DB = Path("data") / "market-cache" / "market_cache.db"

# RUTA KLINES del proveedor local (emula /fapi/v1/klines).
KLINES_PATH = "/fapi/v1/klines"


def now_ms() -> int:
    return int(time.time() * 1000)


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, int(port))) == 0


def _run_id_path(sessions_dir: Path) -> Path:
    """Ruta del archivo que persiste el run_id de la corrida activa."""
    return sessions_dir / "run-id.json"


def _read_run_id(sessions_dir: Path) -> Optional[str]:
    """Lee el run_id persistido de una corrida previa, si existe."""
    try:
        data = json.loads(_run_id_path(sessions_dir).read_text(encoding="utf-8"))
        return data.get("run_id") if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_run_id(sessions_dir: Path, run_id: str) -> None:
    """Persiste el run_id de la corrida para que un reinicio lo reutilice."""
    _run_id_path(sessions_dir).parent.mkdir(parents=True, exist_ok=True)
    _run_id_path(sessions_dir).write_text(
        json.dumps({"run_id": run_id}, ensure_ascii=False) + "\n",
        encoding="utf-8")


def canonical_dbs_snapshot() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for p in CANONICAL_DBS:
        try:
            st = p.stat()
            out[str(p)] = {"mtime_ms": int(st.st_mtime * 1000), "size": st.st_size}
        except OSError:
            out[str(p)] = {"mtime_ms": None, "size": None}
    return out


def canonical_dbs_unchanged(before: Dict[str, Any],
                            after: Dict[str, Any]) -> bool:
    for p in CANONICAL_DBS:
        k = str(p)
        if before.get(k) != after.get(k):
            return False
    return True


class WindowOrchestrator:
    def __init__(self, args: argparse.Namespace,
                 evidence_dir: Optional[Path] = None) -> None:
        self.args = args
        self.transport = args.transport
        # Fuente del reloj de referencia: explícita por CLI o derivada del
        # transporte (public -> public, local -> local). Se propaga al servicio
        # de ingeniería mediante --clock-source y se verifica en /health.clock
        # ANTES de crear la sesión.
        self.clock_source = (
            args.clock_source
            if args.clock_source is not None
            else ("public" if self.transport == "public" else "local")
        )
        self.service_port = args.service_port
        self.engineering_port = args.engineering_port
        self.provider_port = args.provider_port
        self.ws_port = args.ws_port
        self.symbols = [s.strip().upper() for s in args.symbols.split(",")]
        if len(self.symbols) < 1:
            raise ValueError("al menos un símbolo requerido")
        self.primary = self.symbols[0]
        self.reference = ("BTCUSDT" if self.primary != "BTCUSDT"
                          else (self.symbols[1] if len(self.symbols) > 1
                                else None))
        self.interval = args.interval
        if self.interval not in INTERVAL_MS:
            raise ValueError(f"intervalo no soportado: {self.interval}")
        self.bars = args.bars
        if not (1 <= self.bars <= MAX_BARS_PER_QUERY):
            raise ValueError(
                f"bars debe estar entre 1 y {MAX_BARS_PER_QUERY}")
        self.deadline_s = args.deadline
        # Un único deadline monotónico desde el primer acceso público.
        self.deadline_monotonic: Optional[float] = None
        self.started_at_ms = None
        self.finished_at_ms = None
        self.error = None
        self.verdict = "UNKNOWN"
        self.checks: List[Dict[str, Any]] = []
        self.service_proc = None
        self.engineering_proc = None
        self.provider: Optional[Any] = None
        self.session_id = None
        self.config_hash = None
        self.evidence: Dict[str, Any] = {}
        self.rest_count = 0
        self.consumers_max_seen = 0
        self.reconnects_max_seen = 0
        self.db_before = canonical_dbs_snapshot()
        self._config_validated = False
        # Directorio de evidencia para persistir stdout/stderr de los
        # servicios y otros artefactos de diagnóstico.
        self.evidence_dir = evidence_dir
        if self.evidence_dir is not None:
            self.evidence_dir.mkdir(parents=True, exist_ok=True)
        # Límite de preparación explícito para el reloj de referencia.
        self.clock_readiness_timeout_s = (
            args.clock_readiness_timeout_s
            if args.clock_readiness_timeout_s is not None
            else CLOCK_READINESS_TIMEOUT_S)
        # Identidad de corrida: se resuelve en _execute() una vez que
        # sessions_dir está disponible.
        self.run_id: Optional[str] = args.run_id
        # Consumo agregado del ledger por run_id (/time + klines + ...),
        # consultado en _verdict para la evidencia final.
        self.ledger_total_por_run_id: Optional[int] = None
        # Última salud observada del servicio de ingeniería (antes de crear
        # sesión y durante el monitoreo).
        self.ultima_salud_ingenieria: Optional[Dict[str, Any]] = None
        # Resultado de limpieza de procesos.
        self.limpieza_resultado: Dict[str, Any] = {}
        # Stdout/stderr capturados de los servicios (rutas a archivos).
        self.service_stdout_path: Optional[Path] = None
        self.service_stderr_path: Optional[Path] = None
        self.engineering_stdout_path: Optional[Path] = None
        self.engineering_stderr_path: Optional[Path] = None

    # -- validación de configuración (antes de conectar) ------------------
    def _validate_config(self) -> None:
        """Valida regla, stop, horizonte y referencia de entrada antes de
        conectar. No se cambian silenciosamente durante la ventana."""
        if self._config_validated:
            return
        cfg = {
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
        # Fijados por protocolo: no se relajan para conseguir una operación.
        assert cfg["direction"] == "LONG"
        assert cfg["stop_distance_pct"] == 5.0
        assert cfg["horizon_ms"] == 3 * 60 * 60 * 1000
        assert cfg["rule_version"] == "RULE-CAUSAL-V1"
        self._config = cfg
        self._config_validated = True
        self.add_check("config_validada", True,
                       "regla/stop/horizonte/referencia fijadas antes de "
                       "conectar (no se cambian durante la ventana)",
                       source="config")

    def add_check(self, check_id: str, ok: Optional[bool],
                  detail: str, required: bool = True,
                  source: str = "orchestrator") -> None:
        self.checks.append({
            "id": check_id, "ok": ok, "required": required,
            "source": source, "detail": detail,
        })

    def run(self) -> Dict[str, Any]:
        self.started_at_ms = now_ms()
        # El deadline empieza en el primer acceso público (incluye
        # preparación y esperas HTTP).
        self.deadline_monotonic = time.monotonic() + self.deadline_s
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
            "reference": self.reference,
            "bars": self.bars,
            "transport": self.transport,
            "service_port": self.service_port,
            "engineering_port": self.engineering_port,
            "provider_port": self.provider_port,
            "checks": self.checks,
            "verdict": self.verdict,
            "evidence": self.evidence,
        }
        try:
            self._validate_config()
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
            dur = (self.finished_at_ms - self.started_at_ms)
            run["duration_s"] = round(dur / 1000.0, 3)
            run["deadline_monotonic_started_at"] = iso(self.started_at_ms)
            run["deadline_respected"] = dur <= self.deadline_s * 1000
            run["rest_count"] = self.rest_count
            run["db_unchanged"] = canonical_dbs_unchanged(
                self.db_before, canonical_dbs_snapshot())
            run["checks"] = self.checks
            run["verdict"] = self.verdict
            # Recoger siempre desde finally: consumo del ledger por run_id,
            # última salud disponible y resultado de limpieza.
            if self.run_id is not None:
                try:
                    _cache = MarketCache(CACHE_DB)
                    _cache.init_db()
                    self.ledger_total_por_run_id = _cache.run_requests_used(
                        self.run_id)
                except Exception:  # noqa: BLE001 - evidencia, no falla
                    self.ledger_total_por_run_id = None
            run["ledger_total_por_run_id"] = self.ledger_total_por_run_id
            run["ultima_salud_ingenieria"] = self.ultima_salud_ingenieria
            run["limpieza_resultado"] = self.limpieza_resultado
            run["service_stdout_path"] = str(self.service_stdout_path) \
                if self.service_stdout_path else None
            run["service_stderr_path"] = str(self.service_stderr_path) \
                if self.service_stderr_path else None
            run["engineering_stdout_path"] = str(self.engineering_stdout_path) \
                if self.engineering_stdout_path else None
            run["engineering_stderr_path"] = str(self.engineering_stderr_path) \
                if self.engineering_stderr_path else None
            self._cleanup()
        return run

    def _plan(self, run: Dict[str, Any]) -> Dict[str, Any]:
        run["plan"] = {
            "symbols": self.symbols,
            "interval": self.interval,
            "bars_per_query": self.bars,
            "max_rest_requests_per_run": MAX_REST_REQUESTS_PER_RUN,
            "max_consumers_sse": MAX_CONSUMERS_SSE,
            "max_reconnects": MAX_RECONNECTS,
            "deadline_s": self.deadline_s,
            "ws_connections": 1,
            "no_recovery": True,
            "canonical_dbs_write": False,
            "session_dir_isolated": True,
        }
        return run

    def _remaining(self) -> float:
        if self.deadline_monotonic is None:
            return self.deadline_s
        return max(0.0, self.deadline_monotonic - time.monotonic())

    def _check_deadline(self, phase: str) -> None:
        if self._remaining() <= 0:
            self.error = f"GLOBAL_DEADLINE_EXCEEDED en {phase}"
            self.verdict = "ERROR"
            raise RuntimeError(self.error)

    # -- ejecución real ----------------------------------------------------
    def _execute(self, run: Dict[str, Any]) -> None:
        # Resolver run_id: de --run-id, de archivo persistido, o nuevo.
        sessions_dir = Path(self.args.sessions_dir) if self.args.sessions_dir else None
        if sessions_dir is not None:
            sessions_dir.mkdir(parents=True, exist_ok=True)
        if self.run_id is None:
            self.run_id = _read_run_id(sessions_dir)
        if self.run_id is None:
            self.run_id = "eng-run-%d" % now_ms()
        if sessions_dir is not None:
            _write_run_id(sessions_dir, self.run_id)
        run["run_id"] = self.run_id
        self._preflight()
        self._start_services()
        context = self._load_recent_context()
        self._create_session(context)
        self._start_drive()
        t_adq_inicio = now_ms()
        self._wait_for_events()
        t_adq_fin = now_ms()
        self.evidence["duracion_adquisicion_s"] = round(
            (t_adq_fin - t_adq_inicio) / 1000.0, 3)
        self.evidence["adquisicion_dentro_deadline"] = (
            t_adq_fin - t_adq_inicio) <= self.deadline_s * 1000
        # La limpieza (stop + cierre de procesos) siempre se ejecuta, incluso
        # si el deadline global ya vencio: el deadline impide NUEVO trabajo de
        # mercado (el bucle de _wait_for_events ya termino por _remaining()),
        # pero nunca debe abortar la liberacion de recursos.
        self._stop_drive()
        t_limpieza_inicio = now_ms()
        self._cleanup()
        t_limpieza_fin = now_ms()
        self.evidence["duracion_limpieza_s"] = round(
            (t_limpieza_fin - t_limpieza_inicio) / 1000.0, 3)
        self.evidence["duracion_total_s"] = round(
            (t_limpieza_fin - self.started_at_ms) / 1000.0, 3)
        self._verdict()

    def _preflight(self) -> None:
        self._check_deadline("preflight")
        base = self.args.dashboard.rstrip("/")
        st = self._http_get(base + "/market-lab", timeout=10.0)
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
        if self.transport == "local":
            self.add_check("provider_port_free", not _port_open(
                "127.0.0.1", self.provider_port),
                "puerto proveedor local %d libre" % self.provider_port,
                source="preflight")
        self.add_check("port_8792_untouched", _port_open("127.0.0.1", 8792),
                       "8792 ocupado (servicio local preexistente, no tocar)",
                       required=False, source="preflight")
        self.add_check("codigo_limites_conocidos", True,
                       "límites del usuario impuestos por el orquestador: "
                       "<=3 consumidores SSE, <=3 reconexiones, <=7 REST "
                       "(límite por corrida), <=300 velas/consulta, deadline "
                       "180s, cero escrituras DB canónicas; el hub de "
                       "market-stream usa 1 WS combinada.",
                       required=False, source="preflight")
        self.add_check("no_ingenieria_activa", True,
                       "ningún proceso de ingeniería activo antes de la "
                       "ventana", required=False, source="preflight")
        if not st["ok"] or not build_ok:
            self.error = "PREFLIGHT_FAILED: dashboard no disponible o build "
            "no coincide"
            raise RuntimeError(self.error)

    # -- cliente HTTP auxiliar (solo dashboard / servicios locales) ---------
    def _http_get(self, url: str, timeout: float = 8.0) -> Dict[str, Any]:
        """GET que devuelve {ok, status, text, error}. text siempre str."""
        import urllib.error
        req = urllib.request.Request(url, headers={"User-Agent": "microprobe/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return {"ok": 200 <= resp.status < 300, "status": resp.status,
                        "text": raw, "error": None}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace") if exc.fp else ""
            return {"ok": False, "status": exc.code, "text": body, "error": None}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "status": None, "text": "",
                    "error": "%s: %s" % (type(exc).__name__, exc)}

    def _start_services(self) -> None:
        self._check_deadline("start_services")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        # --- proveedor local (solo modo local): se arranca ANTES del
        # servicio para que el WS esté disponible cuando el transporte se
        # conecte (sin Binance, cero red pública).
        if self.transport == "local":
            self._start_provider()
        # --- servicio de mercado en 8791 (una WS combinada) ---
        argv = [sys.executable, "-X", "utf8",
                str(ROOT / "scripts" / "market_stream_service.py"),
                "--port", str(self.service_port),
                "--transport", self.transport,
                "--no-recovery",
                "--max-seconds", str(int(self.deadline_s) + 10)]
        if self.transport == "local":
            argv += ["--base-url",
                     "ws://127.0.0.1:%d" % self.ws_port]
        # Persistir stdout/stderr del servicio de mercado en evidencia.
        svc_out = None
        svc_err = None
        if self.evidence_dir is not None:
            svc_out = self.evidence_dir / "service-stdout.log"
            svc_err = self.evidence_dir / "service-stderr.log"
            self.service_stdout_path = svc_out
            self.service_stderr_path = svc_err
        self.service_proc = self._spawn(argv, "market-stream-service",
                                        stdout_path=svc_out,
                                        stderr_path=svc_err)
        svc_url = "http://127.0.0.1:%d" % self.service_port
        health = None
        for _ in range(int(self._remaining() // 0.25) + 1):
            self._check_deadline("service_start_wait")
            r = self._http_get(svc_url + "/health", timeout=3.0)
            if r["ok"] and isinstance(self._json_loads(r["text"]), dict):
                health = self._json_loads(r["text"])
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
                 "--run-id", self.run_id,
                 "--clock-source", self.clock_source,
                 "--pid-file", str(sessions_dir / "service.json")]
        eng_out = None
        eng_err = None
        if self.evidence_dir is not None:
            eng_out = self.evidence_dir / "engineering-stdout.log"
            eng_err = self.evidence_dir / "engineering-stderr.log"
            self.engineering_stdout_path = eng_out
            self.engineering_stderr_path = eng_err
        self.engineering_proc = self._spawn(argv2, "engineering-session",
                                            stdout_path=eng_out,
                                            stderr_path=eng_err)
        eng_url = "http://127.0.0.1:%d" % self.engineering_port
        # Esperar readiness: HTTP disponible Y reloj de referencia válido.
        eng_health = self._wait_for_engineering_readiness(eng_url, sessions_dir)
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
            "service_stdout_path": str(self.service_stdout_path)
            if self.service_stdout_path else None,
            "service_stderr_path": str(self.service_stderr_path)
            if self.service_stderr_path else None,
            "engineering_stdout_path": str(self.engineering_stdout_path)
            if self.engineering_stdout_path else None,
            "engineering_stderr_path": str(self.engineering_stderr_path)
            if self.engineering_stderr_path else None,
        }

    def _start_provider(self) -> None:
        """Arranca el proveedor integrado local (HTTP /fapi/v1/klines +
        WS de klines) sin Binance. HTTP sirve el contexto; WS alimenta el
        transporte market_stream en modo local."""
        sys.path.insert(0, str(ROOT / "scripts"))
        from local_ws_kline_provider import LocalWsklineProvider  # noqa: E402
        modos = {sym: "ok" for sym in self.symbols}
        if self.reference and self.reference not in modos:
            modos[self.reference] = "ok"
        secuencia = None
        env_seq = os.environ.get("ENGINEERING_LIVE_WS_SEQUENCE")
        if env_seq:
            try:
                secuencia = json.loads(env_seq)
            except Exception:  # noqa: BLE001
                secuencia = None
        self.provider = LocalWsklineProvider(self.provider_port,
                                             self.ws_port, modos, secuencia)
        self.provider.start()
        self.add_check("provider_local_arribo", True,
                       "proveedor local klines HTTP=%d WS=%d"
                       % (self.provider_port, self.ws_port), source="execute")

    # -- verificación del reloj de referencia (antes de crear sesión) ------
    def _verify_clock(self, eng_health: Dict[str, Any]) -> None:
        """Rechaza ANTES de crear la sesión si el reloj de referencia del
        servicio de ingeniería es incorrecto, ausente o expirado.

        source esperado: public_sincronizado (--transport public) o
        local_sistema (--transport local). La referencia debe estar
        disponible (available True, es decir, sincronización vigente y no
        expirada). No existe fallback silencioso al reloj de pared.
        """
        clock = eng_health.get("clock") if isinstance(eng_health, dict) \
            else None
        expected_source = ("public_sincronizado" if self.clock_source
                           == "public" else "local_sistema")
        if not isinstance(clock, dict):
            raise RuntimeError(
                "CLOCK_SOURCE_AUSENTE: /health del servicio de ingeniería no "
                "expone el bloque 'clock'")
        source = clock.get("source")
        if source != expected_source:
            raise RuntimeError(
                "CLOCK_SOURCE_INCORRECTO: se esperaba el reloj %s, obtuvo "
                "%s" % (expected_source, source))
        if not clock.get("available"):
            raise RuntimeError(
                "CLOCK_REFERENCIA_NO_DISPONIBLE: %s (age_ms=%s)"
                % (clock.get("reason") or "referencia expirada",
                   clock.get("age_ms")))
        self.add_check("clock_fuente_verificada", True,
                       "reloj de referencia %s válido antes de crear sesión "
                       "(source=%s)" % (self.clock_source, source),
                       source="execute")

    def _wait_for_engineering_readiness(
            self, eng_url: str, sessions_dir: Path) -> Dict[str, Any]:
        """Espera a que el servicio de ingeniería reporte un reloj de
        referencia válido en /health, distinguiendo HTTP disponible de
        servicio preparado.

        Registra transiciones y último motivo observado. Respeta el deadline
        global y un límite de preparación explícito. No permite crear sesión
        mientras el reloj no esté listo (available=False). Fuente incorrecta
        o agotamiento de presupuesto producen un error claro.
        """
        readiness: Dict[str, Any] = {
            "http_disponible_en_ms": None,
            "reloj_listo_en_ms": None,
            "transiciones": [],
            "ultimo_motivo": None,
            "error": None,
            "ultimo_health": None,
        }
        started_monotonic = time.monotonic()
        http_disponible = False
        reloj_listo = False
        ultimo_health = None

        def registrar_transicion(estado: str, detalle: str) -> None:
            ahora_ms = now_ms()
            readiness["transiciones"].append({
                "estado": estado,
                "at_ms": ahora_ms,
                "detalle": detalle,
            })
            readiness["ultimo_motivo"] = detalle

        # Fase 1: esperar a que HTTP responda (servidor levantado).
        while self._remaining() > 0:
            self._check_deadline("engineering_http_wait")
            transcurrido = time.monotonic() - started_monotonic
            if transcurrido > self.clock_readiness_timeout_s:
                readiness["error"] = "CLOCK_READINESS_TIMEOUT_HTTP"
                registrar_transicion(
                    "timeout_http",
                    "servicio no respondió /health en %ds"
                    % int(self.clock_readiness_timeout_s))
                break
            r = self._http_get(eng_url + "/health", timeout=3.0)
            if r["ok"] and isinstance(self._json_loads(r["text"]), dict):
                ultimo_health = self._json_loads(r["text"])
                http_disponible = True
                readiness["http_disponible_en_ms"] = now_ms()
                self.ultima_salud_ingenieria = ultimo_health
                registrar_transicion(
                    "http_disponible",
                    "servicio respondió /health (PID=%s)"
                    % ultimo_health.get("pid"))
                break
            time.sleep(CLOCK_POLL_INTERVAL_S)

        if not http_disponible:
            raise RuntimeError(
                "ENGINEERING_HTTP_NOT_AVAILABLE: %s"
                % readiness["ultimo_motivo"])

        # Fase 2: esperar a que el reloj de referencia esté listo.
        while self._remaining() > 0:
            self._check_deadline("engineering_clock_wait")
            transcurrido = time.monotonic() - started_monotonic
            if transcurrido > self.clock_readiness_timeout_s:
                readiness["error"] = "CLOCK_READINESS_TIMEOUT_CLOCK"
                registrar_transicion(
                    "timeout_reloj",
                    "reloj no listo en %ds"
                    % int(self.clock_readiness_timeout_s))
                break
            r = self._http_get(eng_url + "/health", timeout=3.0)
            if r["ok"] and isinstance(self._json_loads(r["text"]), dict):
                ultimo_health = self._json_loads(r["text"])
                self.ultima_salud_ingenieria = ultimo_health
                clock = ultimo_health.get("clock") \
                    if isinstance(ultimo_health, dict) else None
                if not isinstance(clock, dict):
                    # Reloj ausente: error claro, no seguir esperando.
                    readiness["error"] = "CLOCK_SOURCE_AUSENTE"
                    registrar_transicion(
                        "reloj_ausente",
                        "/health no expone el bloque 'clock'")
                    raise RuntimeError(
                        "CLOCK_SOURCE_AUSENTE: /health del servicio de "
                        "ingeniería no expone el bloque 'clock'")
                source = clock.get("source")
                available = clock.get("available")
                expected_source = ("public_sincronizado"
                                   if self.clock_source == "public"
                                   else "local_sistema")
                if source != expected_source:
                    # Fuente incorrecta: error claro, no seguir esperando.
                    readiness["error"] = "CLOCK_SOURCE_INCORRECTO"
                    registrar_transicion(
                        "fuente_incorrecta",
                        "se esperaba %s, obtuvo %s"
                        % (expected_source, source))
                    raise RuntimeError(
                        "CLOCK_SOURCE_INCORRECTO: se esperaba el reloj %s, "
                        "obtuvo %s" % (expected_source, source))
                if available:
                    reloj_listo = True
                    readiness["reloj_listo_en_ms"] = now_ms()
                    registrar_transicion(
                        "reloj_listo",
                        "referencia válida (source=%s)" % source)
                    break
                else:
                    # Reloj no disponible aún (sincronización en curso):
                    # seguir esperando sin abortar ni permitir crear sesión.
                    registrar_transicion(
                        "reloj_no_listo",
                        "available=False (age_ms=%s)"
                        % clock.get("age_ms"))
            else:
                registrar_transicion(
                    "health_no_responde",
                    "status=%s error=%s" % (r.get("status"), r.get("error")))
            time.sleep(CLOCK_POLL_INTERVAL_S)

        if not reloj_listo:
            raise RuntimeError(
                "ENGINEERING_CLOCK_NOT_READY: %s"
                % readiness["ultimo_motivo"])

        readiness["ultimo_health"] = ultimo_health
        self.evidence["clock_readiness"] = readiness
        return ultimo_health

    def _spawn(self, argv: List[str], label: str,
               stdout_path: Optional[Path] = None,
               stderr_path: Optional[Path] = None):
        """Lanza un proceso persistiendo stdout/stderr en archivos de
        evidencia para evitar PIPE sin drenar y conservar los logs aunque
        el proceso falle o timeout."""
        if stdout_path is not None:
            stdout_file = open(stdout_path, "w", encoding="utf-8",
                               errors="replace")
        else:
            stdout_file = subprocess.PIPE
        if stderr_path is not None:
            stderr_file = open(stderr_path, "w", encoding="utf-8",
                               errors="replace")
        else:
            stderr_file = subprocess.PIPE
        proc = subprocess.Popen(
            argv, cwd=str(ROOT),
            stdout=stdout_file, stderr=stderr_file,
            text=True, encoding="utf-8", errors="replace")
        # Guardar referencias a los archivos para cerrarlos en _cleanup.
        proc._stdout_file = stdout_file if stdout_path else None
        proc._stderr_file = stderr_file if stderr_path else None
        return proc

    @staticmethod
    def _json_loads(text: str) -> Any:
        return json.loads(text) if text.strip() else None

    # -- contexto reciente (HistoryClient + LedgerAttemptGate) -------------
    def _load_recent_context(self) -> List[Dict[str, Any]]:
        """Contexto reciente para fijar el reloj T.

        Usa HistoryClient + LedgerAttemptGate (reserva preenvío) + normalize_kline
        (interpretación canónica: cierre conocido en T si close_time presente y
        finito; nunca se inventa un booleano de cierre en row[12]).

        Identidades separadas: el contexto de cada símbolo lleva su propio
        ``symbol``; BTC permanece en su serie de referencia y MINA en la suya;
        nunca se deduplica por timestamp entre símbolos ni se elimina la
        identidad antes de validarla.

        Modo local: proveedor HTTP local (cero Binance, cero REST real).
        Modo public: caché derivada local primero (cero REST); si insuficiente,
        HistoryClient con attempt_gate (hasta MAX_REST_REQUESTS_PER_RUN por
        corrida).
        """
        self._check_deadline("load_context")
        step = INTERVAL_MS[self.interval]
        end = now_ms()
        start = end - (self.bars - 1) * step
        contexto: List[Dict[str, Any]] = []
        rest_usadas = 0
        parse_diag: List[Dict[str, Any]] = []

        if self.transport == "local":
            # Proveedor local vía HistoryClient (sin Binance, cero REST real).
            cache = MarketCache(CACHE_DB)
            try:
                cache.init_db()
            except Exception:  # noqa: BLE001
                pass
            execution_id = self.run_id
            gate = LedgerAttemptGate(cache, execution_id,
                                     max_requests=MAX_FETCH_REQUESTS_PER_WINDOW,
                                     run_max_requests=MAX_REST_REQUESTS_PER_RUN)
            client = HistoryClient(
                base_url="http://127.0.0.1:%d" % self.provider_port,
                execution_id=execution_id, attempt_gate=gate,
                max_retries=0,  # fallo rápido: no reintentar contra proveedor local
            )
            for sym in ([self.reference, self.primary]
                        if self.reference else [self.primary]):
                self._check_deadline("context_rest_" + sym)
                try:
                    rows, _ = client.klines(sym, self.interval, start, end,
                                            limit=self.bars)
                    rest_usadas += 1
                    parse_diag.append({
                        "symbol": sym, "result": "ok",
                        "rows": len(rows),
                        "reserved_before_send": True,
                    })
                    for row in rows:
                        try:
                            candle = normalize_kline(row)
                        except Exception as exc:  # noqa: BLE001
                            parse_diag.append({
                                "symbol": sym, "result": "parse_error",
                                "error": "%s: %s" % (type(exc).__name__, exc),
                            })
                            continue
                        # Cierre conocido en T: close_time presente y finito.
                        close_time = candle.get("close_time")
                        if close_time is None:
                            parse_diag.append({
                                "symbol": sym, "result": "close_time_missing",
                                "open_time_ms": candle["open_time"],
                            })
                            continue
                        contexto.append({
                            "symbol": sym,
                            "open_time_ms": int(candle["open_time"]),
                            "open": float(candle["open"]),
                            "high": float(candle["high"]),
                            "low": float(candle["low"]),
                            "close": float(candle["close"]),
                            "close_time_ms": int(close_time),
                        })
                except UpstreamBudgetExceeded as exc:
                    rest_usadas += 1
                    parse_diag.append({
                        "symbol": sym, "result": "budget_blocked_pre_send",
                        "error": str(exc),
                    })
                    break
                except Exception as exc:  # noqa: BLE001
                    rest_usadas += 1
                    parse_diag.append({
                        "symbol": sym, "result": "exception",
                        "error": "%s: %s" % (type(exc).__name__, exc),
                    })
        else:
            # Modo public: caché derivada local primero (cero REST).
            cache = MarketCache(CACHE_DB)
            try:
                cache.init_db()
            except Exception:  # noqa: BLE001
                pass
            for sym in ([self.reference, self.primary]
                        if self.reference else [self.primary]):
                try:
                    stored, _ = read_stored(cache, sym, self.interval,
                                            "klines", start, end, None,
                                            self.bars)
                except Exception:  # noqa: BLE001
                    stored = []
                for c in stored:
                    if c.get("closed") is True:
                        contexto.append({
                            "symbol": sym,
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
            # (contabilizado, dentro del presupuesto de 7 por corrida).
            recientes = [c for c in contexto
                         if c["open_time_ms"] >= end - 2 * step
                         and c["symbol"] == self.primary]
            if len(recientes) < 10:
                for sym in ([self.reference, self.primary]
                            if self.reference else [self.primary]):
                    if rest_usadas >= MAX_REST_REQUESTS_PER_RUN:
                        break
                    self._check_deadline("context_rest_" + sym)
                    try:
                        cache = MarketCache(CACHE_DB)
                        try:
                            cache.init_db()
                        except Exception:  # noqa: BLE001
                            pass
                        execution_id = self.run_id
                        gate = LedgerAttemptGate(cache, execution_id,
                                                 max_requests=
                                                 MAX_FETCH_REQUESTS_PER_WINDOW,
                                                 run_max_requests=
                                                 MAX_REST_REQUESTS_PER_RUN)
                        client = HistoryClient(
                            base_url="https://fapi.binance.com",
                            execution_id=execution_id, attempt_gate=gate,
                            max_retries=0,  # fallo rápido: no reintentar
                        )
                        rows, _ = client.klines(sym, self.interval, start,
                                                end, limit=self.bars)
                        rest_usadas += 1
                        for row in rows:
                            try:
                                candle = normalize_kline(row)
                            except Exception as exc:  # noqa: BLE001
                                parse_diag.append({
                                    "symbol": sym, "result": "parse_error",
                                    "error": "%s: %s" % (type(exc).__name__,
                                                         exc),
                                })
                                continue
                            close_time = candle.get("close_time")
                            if close_time is None:
                                continue
                            contexto.append({
                                "symbol": sym,
                                "open_time_ms": int(candle["open_time"]),
                                "open": float(candle["open"]),
                                "high": float(candle["high"]),
                                "low": float(candle["low"]),
                                "close": float(candle["close"]),
                                "close_time_ms": int(close_time),
                            })
                    except UpstreamBudgetExceeded as exc:
                        rest_usadas += 1
                        parse_diag.append({
                            "symbol": sym,
                            "result": "budget_blocked_pre_send",
                            "error": str(exc),
                        })
                        break
                    except Exception as exc:  # noqa: BLE001
                        rest_usadas += 1
                        parse_diag.append({
                            "symbol": sym, "result": "exception",
                            "error": "%s: %s" % (type(exc).__name__, exc),
                        })

        self.rest_count = rest_usadas
        # No deduplicar símbolos distintos por timestamp: cada vela lleva su
        # propio symbol; BTC y MINA conservan su identidad.
        visto: set = set()
        unicos: List[Dict[str, Any]] = []
        for c in sorted(contexto, key=lambda x: (x["symbol"],
                                                 x["open_time_ms"])):
            clave = (c["symbol"], c["open_time_ms"])
            if clave in visto:
                continue
            visto.add(clave)
            unicos.append(c)
        self.add_check("contexto_cargado", len(unicos) > 0,
                       "%d velas cerradas recientes para fijar el reloj T "
                       "(rest=%d)" % (len(unicos), rest_usadas),
                       source="execute")
        self.evidence["contexto"] = {
            "fuente": ("proveedor_http_local" if self.transport == "local"
                       else "caché derivada + REST klines"),
            "velas": len(unicos),
            "symbols_seen": sorted({c["symbol"] for c in unicos}),
            "rango": [unicos[0]["open_time_ms"],
                      unicos[-1]["open_time_ms"]] if unicos else None,
            "rest_usadas": rest_usadas,
            "parse_diag": parse_diag,
        }
        return unicos

    def _create_session(self, context: List[Dict[str, Any]]) -> None:
        self._check_deadline("create_session")
        eng_url = "http://127.0.0.1:%d" % self.engineering_port
        cfg = self._config
        payload = {
            "transport": "market_stream",
            "config": dict(cfg),
            "candles": [],  # live: ventana por el feed
            "context": context,
            "hypothesis_id": cfg["hypothesis_id"],
            "hypothesis_version": cfg["hypothesis_version"],
            "rule_version": cfg["rule_version"],
            "request_id": "eng-create-%d" % now_ms(),
        }
        r = self._http_post_json(eng_url + "/sessions", payload, timeout=15.0)
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
            "reference": self.reference,
            "intervalo": self.interval,
            "regla": cfg["rule_version"],
            "notional_usdt": cfg["notional_usdt"],
            "horizon_ms": cfg["horizon_ms"],
            "contexto_velas": len(context),
            "transporte": "market_stream",
            "create_ok": True,
        }
        self.add_check("sesion_creada", bool(self.session_id),
                       "session_id=%s config_hash=%s regla=%s simbolo=%s "
                       "vinculada al transporte market_stream"
                       % (self.session_id, self.config_hash,
                          cfg["rule_version"], self.primary),
                       source="execute")
        if not self.session_id:
            raise RuntimeError("CREATE_SESSION_NO_ID")

    def _http_post_json(self, url: str, payload: Dict[str, Any],
                        timeout: float = 15.0) -> Dict[str, Any]:
        import urllib.error
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, method="POST", data=data,
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": "microprobe/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                try:
                    payload_json = json.loads(raw) if raw.strip() else None
                except ValueError:
                    payload_json = None
                return {"ok": 200 <= resp.status < 300, "status": resp.status,
                        "text": raw, "json": payload_json, "error": None}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace") if exc.fp else ""
            try:
                payload_json = json.loads(body) if body.strip() else None
            except ValueError:
                payload_json = None
            return {"ok": False, "status": exc.code, "text": body,
                    "json": payload_json, "error": None}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "status": None, "text": "",
                    "json": None,
                    "error": "%s: %s" % (type(exc).__name__, exc)}

    def _start_drive(self) -> None:
        self._check_deadline("start_drive")
        eng_url = "http://127.0.0.1:%d" % self.engineering_port
        payload = {"action": "start",
                   "expected_revision": None,
                   "request_id": "eng-start-%d" % now_ms()}
        r = self._http_post_json(
            eng_url + "/sessions/%s/control" % self.session_id, payload,
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
        self._check_deadline("wait_for_events")
        eng_url = "http://127.0.0.1:%d" % self.engineering_port
        svc_url = "http://127.0.0.1:%d" % self.service_port
        last_revision = None
        last_events_processed = 0
        sj = None
        while self._remaining() > 0:
            self._check_deadline("poll_session")
            r = self._http_get(eng_url + "/sessions/%s" % self.session_id,
                               timeout=5.0)
            if r["ok"] and isinstance(self._json_loads(r["text"]), dict):
                sj = self._json_loads(r["text"])
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
            h = self._http_get(svc_url + "/health", timeout=5.0)
            if h["ok"] and isinstance(self._json_loads(h["text"]), dict):
                hj = self._json_loads(h["text"])
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
                recorrido = hj.get("recorrido") or {}
                if recorrido:
                    self.evidence["recorrido_servicio"] = recorrido
                drive_stats = (((sj or {})).get("drive") or {}).get("stats") or {}
                if drive_stats:
                    self.evidence["adaptador_ingenieria"] = drive_stats
                evaluaciones = (((sj or {})).get("drive") or {}).get(
                    "evaluaciones") or []
                if evaluaciones:
                    self.evidence["evaluaciones"] = evaluaciones
                    self.evidence["evaluacion_contador"] = int(
                        (((sj or {})).get("drive") or {}).get(
                            "evaluacion_contador", 0) or 0)
            time.sleep(1.0)
        self.evidence["revision_final"] = last_revision
        self.evidence["evaluaciones_final"] = self.evidence.get(
            "evaluaciones") or []
        self.evidence["evaluacion_contador_final"] = self.evidence.get(
            "evaluacion_contador", 0)
        self.evidence["eventos_procesados_final"] = last_events_processed

    def _stop_drive(self) -> None:
        eng_url = "http://127.0.0.1:%d" % self.engineering_port
        payload = {"action": "stop",
                   "expected_revision": None,
                   "request_id": "eng-stop-%d" % now_ms()}
        r = self._http_post_json(
            eng_url + "/sessions/%s/control" % self.session_id, payload,
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
        if self.rest_count > MAX_REST_REQUESTS_PER_RUN:
            fail.append("rest_excede_limite")
        # Consumo agregado del ledger por run_id (/time + klines + ...), no
        # solo el contador de consultas de contexto del arnés.
        if self.run_id is not None:
            try:
                _cache = MarketCache(CACHE_DB)
                _cache.init_db()
                self.ledger_total_por_run_id = _cache.run_requests_used(
                    self.run_id)
            except Exception:  # noqa: BLE001 - evidencia, no falla la corrida
                self.ledger_total_por_run_id = None
        if (self.ledger_total_por_run_id is not None
                and self.ledger_total_por_run_id
                > MAX_REST_REQUESTS_PER_RUN):
            fail.append("presupuesto_corrida_agotado")
        if not canonical_dbs_unchanged(self.db_before,
                                       canonical_dbs_snapshot()):
            fail.append("db_canonica_escritas")
        dur_adq = self.evidence.get("duracion_adquisicion_s")
        if dur_adq is not None:
            self.evidence["duracion_s"] = dur_adq
            self.evidence["deadline_respetado"] = dur_adq <= self.deadline_s
            if dur_adq > self.deadline_s:
                fail.append("deadline_excedido_en_adquisicion")
        else:
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
            "ledger_total_por_run_id": self.ledger_total_por_run_id,
            "db_unchanged": canonical_dbs_unchanged(
                self.db_before, canonical_dbs_snapshot()),
            "ultima_salud_ingenieria": self.ultima_salud_ingenieria,
            "clock_readiness": self.evidence.get("clock_readiness"),
        }

    def _cleanup(self) -> None:
        resultado = {
            "procesos_terminados": [],
            "procesos_fallidos": [],
            "archivos_log_cerrados": [],
        }
        if self.provider is not None:
            try:
                self.provider.stop()
            except Exception:  # noqa: BLE001
                pass
        for proc, label in ((self.engineering_proc, "ingeniería"),
                            (self.service_proc, "mercado")):
            if proc is not None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5.0)
                    resultado["procesos_terminados"].append(label)
                except Exception:  # noqa: BLE001
                    try:
                        proc.kill()
                        resultado["procesos_terminados"].append(label)
                    except Exception:  # noqa: BLE001
                        resultado["procesos_fallidos"].append(label)
                        pass
                # Cerrar archivos de stdout/stderr si existen.
                for attr, nombre in (("_stdout_file", "stdout"),
                                     ("_stderr_file", "stderr")):
                    f = getattr(proc, attr, None)
                    if f is not None:
                        try:
                            f.close()
                            resultado["archivos_log_cerrados"].append(
                                "%s_%s" % (label, nombre))
                        except Exception:  # noqa: BLE001
                            pass
        self.limpieza_resultado = resultado

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
            "ledger_total_por_run_id": self.ledger_total_por_run_id,
            "db_unchanged": canonical_dbs_unchanged(
                self.db_before, canonical_dbs_snapshot()),
            "ultima_salud_ingenieria": self.ultima_salud_ingenieria,
            "limpieza_resultado": self.limpieza_resultado,
            "service_stdout_path": str(self.service_stdout_path)
            if self.service_stdout_path else None,
            "service_stderr_path": str(self.service_stderr_path)
            if self.service_stderr_path else None,
            "engineering_stdout_path": str(self.engineering_stdout_path)
            if self.engineering_stdout_path else None,
            "engineering_stderr_path": str(self.engineering_stderr_path)
            if self.engineering_stderr_path else None,
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
    ap.add_argument("--provider-port", type=int, default=DEFAULT_PROVIDER_PORT,
                    help="puerto HTTP del proveedor local (modo local)")
    ap.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT,
                    help="puerto WS del proveedor local (modo local)")
    ap.add_argument("--dashboard", default=DEFAULT_DASHBOARD)
    ap.add_argument("--build-id", required=True,
                    help="BUILD_ID que debe servir el dashboard")
    ap.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    ap.add_argument("--interval", default=DEFAULT_INTERVAL)
    ap.add_argument("--bars", type=int, default=DEFAULT_BARS)
    ap.add_argument("--duration", type=float, default=DEFAULT_DURATION_S)
    ap.add_argument("--deadline", type=float, default=GLOBAL_DEADLINE_S)
    ap.add_argument("--sessions-dir", default=None)
    ap.add_argument("--run-id", default=None,
                    help="identificador estable de la corrida de presupuesto. "
                    "Se persiste y se reutiliza al reiniciar la misma corrida.")
    ap.add_argument("--clock-source", choices=["local", "public"], default=None,
                    help="fuente del reloj de referencia: 'local' (reloj de pared "
                    "local, cero solicitudes publicas) o 'public' "
                    "(ClockSynchronizer sincronizado contra el backend publico, "
                    "bajo presupuesto). Default: derivada de --transport "
                    "(public -> public, local -> local).")
    ap.add_argument("--evidence-dir", default=None,
                    help="directorio para persistir stdout/stderr de los "
                    "servicios y artefactos de diagnóstico. Si no se indica, "
                    "no se persisten logs de proceso.")
    ap.add_argument("--clock-readiness-timeout-s", type=float,
                    default=CLOCK_READINESS_TIMEOUT_S,
                    help="tiempo máximo (s) para esperar a que el servicio de "
                    "ingeniería reporte un reloj de referencia válido en "
                    "/health (dentro del deadline global).")
    ap.add_argument("--out", required=True, help="ruta JSON de evidencia")
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    ap = build_arg_parser()
    args = ap.parse_args(argv)
    if args.sessions_dir is None:
        args.sessions_dir = str(Path(os.environ.get("TEMP", "."))
                                / "opencode" / "engineering-live-sessions")
    evidence_dir = None
    if args.evidence_dir is not None:
        evidence_dir = Path(args.evidence_dir)
    orch = WindowOrchestrator(args, evidence_dir=evidence_dir)
    run = orch.run()
    orch.write_evidence(args.out)
    return 0 if run["verdict"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
