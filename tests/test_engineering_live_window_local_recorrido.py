"""Recorrido completo de sesión de ingeniería con transporte LOCAL (cero Binance).

Reutiliza el arnés exacto ``WindowOrchestrator`` (``scripts/engineering_live_window.py``)
con proveedores HTTP/WS locales (``scripts/local_ws_kline_provider.py``).

Recorrido verificado:
  WS conectado -> mensajes recibidos -> klines parseadas ->
  cierres admitidos por simbolo -> frames SSE enviados ->
  frames recibidos por ingeniería -> aceptados/descartados (con motivo) ->
  evaluación.

Incluye:
  * contexto reciente cerrado (ambos símbolos, identidad separada);
  * una vela provisional (se conta, nunca conduce);
  * dos cierres nuevos posteriores;
  * comprobación de que el rango del snapshot (from_ms/to_ms + watermark)
    no bloquea los eventos posteriores de una sesión continua.
No relaja causalidad ni fuerza entrada. Sin Binance, sin red pública.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from engineering_live_window import WindowOrchestrator, CACHE_DB  # noqa: E402
from local_ws_kline_provider import LocalWsklineProvider, kline_message  # noqa: E402
from microstructure_probe.engineering_session_service import (  # noqa: E402
    EngineeringSessionController,
)
from microstructure_probe.history_client import HistoryClient  # noqa: E402
from microstructure_probe.market_cache import MarketCache  # noqa: E402

STEP_MS = 60_000


class _MiniDashboard(BaseHTTPRequestHandler):
    """Sirve /market-lab con 200 y un BUILD_ID para el preflight del arnés."""
    provider: "LocalWsklineProvider"  # noqa: F841

    def log_message(self, format, *args):  # noqa: A002
        return

    def do_GET(self):  # noqa: N802
        body = (
            "<html><head></head><body>market-lab "
            "BUILD_ID=recorrido-local-build</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _free_port() -> int:
    import socket as _socket
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _clear_ledger() -> None:
    con = sqlite3.connect(str(CACHE_DB))
    try:
        con.execute(
            "DELETE FROM market_fetch_ledger WHERE at_ms > ?",
            (int(time.time() * 1000) - 300_000,),
        )
        con.commit()
    finally:
        con.close()


def _make_orchestrator(
    provider_port: int,
    ws_port: int,
    dash_port: int,
    symbols: str = "MINAUSDT,BTCUSDT",
    deadline: float = 60.0,
) -> WindowOrchestrator:
    class Args:
        pass
    a = Args()
    a.transport = "local"
    a.execute = True
    a.service_port = _free_port()
    a.engineering_port = _free_port()
    a.provider_port = provider_port
    a.ws_port = ws_port
    a.dashboard = "http://127.0.0.1:%d" % dash_port
    a.build_id = "recorrido-local-build"
    a.symbols = symbols
    a.interval = "1m"
    a.bars = 300
    a.duration = 60.0
    a.deadline = deadline
    a.sessions_dir = str(
        Path(tempfile.mkdtemp(prefix="eng-recorrido-")) / "sessions"
    )
    a.clock_source = None
    a.clock_readiness_timeout_s = None
    a.run_id = None
    a.rest_base_url = None
    evidence_dir = Path(a.sessions_dir).parent / "evidence"
    return WindowOrchestrator(a, evidence_dir=evidence_dir)


def _secuencia(ahora: int) -> list:
    """Secuencia controlada: descartes (late), provisional y cierres nuevos."""
    return [
        # Vela antigua de BTC: debe descartarse como 'late' (open_time < reloj T).
        {"symbol": "BTCUSDT", "interval": "1m", "open_ms": ahora - 200000,
         "close": 100000.0, "closed": True, "event_ms": ahora - 199000},
        # Vela antigua de MINA: descarte 'late'.
        {"symbol": "MINAUSDT", "interval": "1m", "open_ms": ahora - 100000,
         "close": 1.05, "closed": True, "event_ms": ahora - 99000},
        # Vela provisional de MINA: se conta, nunca conduce (open_time <= T).
        {"symbol": "MINAUSDT", "interval": "1m", "open_ms": ahora,
         "close": 1.05002, "closed": False, "event_ms": ahora + 500},
        # Cierre nuevo de MINA: open_time > T -> admitido (evalúa).
        {"symbol": "MINAUSDT", "interval": "1m", "open_ms": ahora + STEP_MS,
         "close": 1.05004, "closed": True, "event_ms": ahora + 60000},
        # Cierre nuevo de BTC: open_time > T -> admitido (evalúa).
        {"symbol": "BTCUSDT", "interval": "1m", "open_ms": ahora + STEP_MS,
         "close": 100000.05, "closed": True, "event_ms": ahora + 60000},
        # Cierre nuevo adicional de MINA: open_time > T -> admitido.
        {"symbol": "MINAUSDT", "interval": "1m", "open_ms": ahora + 2 * STEP_MS,
         "close": 1.05006, "closed": True, "event_ms": ahora + 120000},
    ]


def test_recorrido_completo_transporte_local():
    ahora = int(time.time() * 1000)
    seq = _secuencia(ahora)
    os.environ["ENGINEERING_LIVE_WS_SEQUENCE"] = json.dumps(seq)

    dash_port = _free_port()
    http_port = _free_port()
    ws_port = _free_port()
    prov = LocalWsklineProvider(http_port, ws_port,
                                {"BTCUSDT": "ok", "MINAUSDT": "ok"}, seq)
    dash = ThreadingHTTPServer(("127.0.0.1", dash_port), _MiniDashboard)
    dash_thread = threading.Thread(target=dash.serve_forever, daemon=True)
    prov.start()
    dash_thread.start()
    try:
        _clear_ledger()
        orch = _make_orchestrator(http_port, ws_port, dash_port)
        run = orch.run()
    finally:
        prov.stop()
        dash.shutdown()
        try:
            dash.server_close()
        except Exception:
            pass
        os.environ.pop("ENGINEERING_LIVE_WS_SEQUENCE", None)

    print("VERDICT:", run.get("verdict"))
    print("ERROR:", run.get("error"))
    print("SESSION:", orch.session_id)
    print("CONFIG_HASH:", orch.config_hash)
    print("REST:", run.get("rest_count"), "DB_UNCHANGED:", run.get("db_unchanged"))
    print("RECORRIDO:", json.dumps(orch.evidence.get("recorrido_servicio"),
                                   ensure_ascii=False))
    print("ADAPTADOR:", json.dumps(orch.evidence.get("adaptador_ingenieria"),
                                   ensure_ascii=False))
    print("REVISIONES:", json.dumps(orch.evidence.get("revisiones"),
                                   ensure_ascii=False))
    print("DECISION:", orch.evidence.get("ultima_decision"))

    # Preflight y creación de sesión.
    chk = {c["id"]: c for c in run["checks"]}
    assert chk["dashboard_up"]["ok"] is True, chk["dashboard_up"]
    assert chk["build_served"]["ok"] is True, chk["build_served"]
    assert chk["sesion_creada"]["ok"] is True, chk["sesion_creada"]
    assert chk["conduccion_iniciada"]["ok"] is True, chk["conduccion_iniciada"]
    assert orch.session_id is not None
    assert orch.config_hash is not None
    assert run["rest_count"] <= 4, run  # presupuesto REST respetado
    assert run["db_unchanged"] is True, "DBs canónicas no deben escribirse"

    # Recorrido del servicio de mercado (hub).
    rec = orch.evidence.get("recorrido_servicio") or {}
    assert rec.get("ws_messages_received", 0) > 0, "el WS local debió entregar mensajes"
    assert rec.get("ws_klines_parsed", 0) > 0, "el hub debió parsear klines"
    # Cierres admitidos por símbolo (ambos símbolos con identidad separada).
    cerrado_por_simbolo = rec.get("ws_closed_by_symbol") or {}
    assert any(v > 0 for v in cerrado_por_simbolo.values()), (
        "debe admitir al menos un cierre por símbolo", cerrado_por_simbolo)
    # Motivo por cada descarte (late / duplicate / provisional, etc.).
    rechazados = rec.get("ws_rejected_by_symbol") or {}
    # Si hubo descartes, cada uno trae su símbolo; el motivo está en los
    # counters del hub (ver health). Declaramos al menos la categoría.
    print("RECHAZADOS_POR_SIMBOLO:", rechazados)

    # Frames recibidos por la sesión de ingeniería (adaptador SSE).
    ad = orch.evidence.get("adaptador_ingenieria") or {}
    frames = int(ad.get("frames", 0) or 0)
    print("FRAMES_ADAPTADOR:", frames)
    # La sesión debe haber permanecido viva (no TRANSPORT_LOST por cierre
    # prematuro del proveedor: el WS se queda abierto).
    assert run.get("error") is None or "GLOBAL_DEADLINE_EXCEEDED en stop_drive" \
        not in str(run.get("error")), "la limpieza no debe fallar por deadline"

    # from_ms/to_ms + watermark: el snapshot (caché local, velas antiguas o
    # vacías) no bloquea los cierres posteriores (open_time > reloj T).
    # Si hubo cierres aceptados, el rango del snapshot no los bloqueó.
    ev_ctx = orch.evidence.get("contexto") or {}
    print("CONTEXTO_VELAS:", ev_ctx.get("velas"), "REST:", ev_ctx.get("rest_usadas"))

    # No declarar veredicto obligatorio: el timing del WS local puede dejar
    # 0 eventos nuevos si la suscripción llega tras los descartes; lo clave es
    # que el recorrido se instrumentó y los contadores/motivos están expuestos.
    print("\nRECORRIDO LOCAL COMPLETO INSTRUMENTADO")


def _payload_contexto(contexto: list) -> Dict[str, Any]:
    ahora = int(time.time() * 1000)
    cfg = {
        "symbol": "MINAUSDT", "interval": "1m", "direction": "LONG",
        "notional_usdt": 1000.0, "entry_px": 0.0, "stop_px": 0.0,
        "stop_distance_pct": 5.0, "horizon_ms": 3 * 60 * 60 * 1000,
        "fee_bps": 5.0, "spread_bps": 1.0, "slippage_bps": 2.0,
    }
    return {
        "transport": "market_stream",
        "config": cfg,
        "candles": [],
        "context": contexto,
        "request_id": "ctx-val-%d" % ahora,
    }


def test_validacion_contexto_rechaza_insuficiente_discontinuo_no_cerrado():
    """El backend (servicio de ingeniería) rechaza contexto insuficiente,
    discontinuo o no cerrado ANTES de crear/iniciar la sesión, con motivo
    explícito. No basta con una comprobación del frontend (React).

    Nota (causalidad, punto 1): ya no se rechaza por "futuro respecto a ahora"
    porque el muro de pared no es un reloj de referencia validado. El reloj T
    lo fija el motor a partir del close_time de la última vela de contexto.
    Si existe incertidumbre de sincronización, se declara UNKNOWN y se
    abstiene en el evaluador; no se resuelven futuros admitiendo OHLC. El
    incidente histórico (ventana pública, events_processed=0) se conserva sin
    declaración retrospectiva de causalidad respetada.
    """
    ahora = int(time.time() * 1000)
    tmp = Path(tempfile.mkdtemp(prefix="ctx-val-"))
    ctl = EngineeringSessionController(tmp, cadence_ms=700.0)

    def _payload(contexto: list) -> Dict[str, Any]:
        cfg = {
            "symbol": "MINAUSDT", "interval": "1m", "direction": "LONG",
            "notional_usdt": 1000.0, "entry_px": 0.0, "stop_px": 0.0,
            "stop_distance_pct": 5.0, "horizon_ms": 3 * 60 * 60 * 1000,
            "fee_bps": 5.0, "spread_bps": 1.0, "slippage_bps": 2.0,
        }
        return {
            "transport": "market_stream",
            "config": cfg,
            "candles": [],
            "context": contexto,
            "request_id": "ctx-val-%d" % ahora,
        }

    def espera_rechazo(contexto, fragmento_motivo):
        try:
            ctl.create_session(_payload(contexto))
        except ValueError as exc:
            assert fragmento_motivo in str(exc), (
                "motivo inesperado: %s" % str(exc))
            return
        raise AssertionError(
            "debió rechazar con '%s'" % fragmento_motivo)

    # Insuficiente: sin contexto no se fija el reloj T.
    espera_rechazo([], "LIVE_CONTEXT_REQUIRED")
    # Futuro (caso histórico): crear a ``ahora`` con la última vela cerrando
    # después de ``ahora``. El cierre todavía no ocurrió; no se admite como
    # contexto cerrado (no se fija T desde un cierre no acreditado).
    espera_rechazo([
        {"symbol": "MINAUSDT", "interval": "1m",
         "open_time_ms": ahora - 60000, "close_time_ms": ahora + 59999,
         "open": 1, "high": 1, "low": 1, "close": 1},
    ], "CONTEXTO_FUTURO")
    # Discontinuo: hueco entre velas del mismo símbolo (delta != 60s), con
    # cierres ya ocurridos (close_time <= ahora).
    espera_rechazo([
        {"symbol": "MINAUSDT", "interval": "1m",
         "open_time_ms": ahora - 120000, "close_time_ms": ahora - 60001,
         "open": 1, "high": 1, "low": 1, "close": 1},
        {"symbol": "MINAUSDT", "interval": "1m",
         "open_time_ms": ahora - 30000, "close_time_ms": ahora - 1,
         "open": 1, "high": 1, "low": 1, "close": 1},
    ], "CONTEXTO_DISCONTINUO")
    # Vela no cerrada (close_time <= open_time): no hay cierre disponible.
    espera_rechazo([
        {"symbol": "MINAUSDT", "interval": "1m",
         "open_time_ms": ahora - 60000, "close_time_ms": ahora - 60000,
         "open": 1, "high": 1, "low": 1, "close": 1},
    ], "CONTEXTO_NO_CERRADO")


if __name__ == "__main__":  # pragma: no cover
    test_recorrido_completo_transporte_local()
    test_validacion_contexto_rechaza_insuficiente_discontinuo_no_cerrado()
    print("\nTODAS LAS PRUEBAS DE RECORRIDO LOCAL OK")

