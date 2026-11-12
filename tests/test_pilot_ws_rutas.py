"""Contrato de rutas WS del piloto: construccion, rechazo, recepcion y cierre.

Reutiliza el cliente productivo (``StreamFeed`` + el CLI real del piloto con
``BookEngine``/``FlowEngine``), el constructor de URL y los proveedores
loopback existentes. Todo es 127.0.0.1: no se abre ningun socket publico ni
se toca mercado, cuentas ni datasets.

Verifica:
A. Construccion exacta de ambas URLs (categoria por conexion, minusculas, sin
   duplicar '/public', '/market' ni '/stream').
B. Rechazo de categorias cruzadas y bases publicas incorrectas (error
   explicito antes de conectar).
C. Recepcion de frames validos mediante el cliente productivo.
D. Desempaquetado combinado y procesamiento por BookEngine/FlowEngine.
E. Contadores separados de conexion, frames recibidos y eventos validos.
F. Cierre efectivo de sockets y procesos propios.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import research_pilot as rp  # noqa: E402
from tests.test_research_pilot import (  # noqa: E402
    MINUTE,
    T0,
    UNIVERSE,
    PilotRun,
    WsProvider,
    find_free_port,
    start_ws_server,
)


# ---------------------------------------------------------------------------
# A. Construccion exacta de las URLs
# ---------------------------------------------------------------------------


def test_urls_exactas_por_categoria() -> None:
    libro = rp.build_stream_url(
        "wss://fstream.binance.com/public",
        ["btcusdt@depth20@100ms"], rp.WS_CATEGORIA_LIBRO)
    assert libro == ("wss://fstream.binance.com/public/stream"
                     "?streams=btcusdt@depth20@100ms")

    flujo = rp.build_stream_url(
        "wss://fstream.binance.com/market",
        ["btcusdt@aggTrade"], rp.WS_CATEGORIA_FLUJO)
    assert flujo == ("wss://fstream.binance.com/market/stream"
                     "?streams=btcusdt@aggTrade")

    # Raiz sin categoria: el constructor anade la categoria del feed.
    assert rp.build_stream_url(
        "wss://fstream.binance.com", ["btcusdt@aggTrade"],
        rp.WS_CATEGORIA_FLUJO) == (
            "wss://fstream.binance.com/market/stream?streams=btcusdt@aggTrade")

    # Loopback: mismo contrato de ruta, sin tocar la venue.
    assert rp.build_stream_url(
        "ws://127.0.0.1:62000", ["btcusdt@depth20@100ms"],
        rp.WS_CATEGORIA_LIBRO) == (
            "ws://127.0.0.1:62000/public/stream?streams=btcusdt@depth20@100ms")

    # Combinado: una sola conexion por categoria, streams en minusculas.
    combinado = rp.build_stream_url(
        "wss://fstream.binance.com/market",
        ["btcusdt@aggTrade", "ethusdt@aggTrade"], rp.WS_CATEGORIA_FLUJO)
    assert combinado == ("wss://fstream.binance.com/market/stream"
                         "?streams=btcusdt@aggTrade/ethusdt@aggTrade")


def test_simbolo_no_lowercase_se_rechaza() -> None:
    with pytest.raises(ValueError) as exc:
        rp.build_stream_url("wss://fstream.binance.com/market",
                            ["BTCUSDT@aggTrade"], rp.WS_CATEGORIA_FLUJO)
    assert "lowercase" in str(exc.value)


# ---------------------------------------------------------------------------
# B. Rechazo de categorias cruzadas y bases invalidas
# ---------------------------------------------------------------------------


def _cli(args):
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{ROOT / 'src'};{ROOT / 'scripts'};{ROOT}"
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "research_pilot.py"), *args],
        cwd=str(ROOT), capture_output=True, text=True, timeout=180, env=env)


def test_categoria_cruzada_se_rechaza() -> None:
    with pytest.raises(ValueError) as exc:
        rp.normalizar_base_ws("wss://fstream.binance.com/market",
                               rp.WS_CATEGORIA_LIBRO, contexto="prueba")
    assert "categoria cruzada" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        rp.normalizar_base_ws("wss://fstream.binance.com/public",
                               rp.WS_CATEGORIA_FLUJO, contexto="prueba")
    assert "categoria cruzada" in str(exc.value)


def test_stream_y_ruta_no_compatible_se_rechazan() -> None:
    with pytest.raises(ValueError) as exc:
        rp.normalizar_base_ws("wss://fstream.binance.com/stream",
                               rp.WS_CATEGORIA_LIBRO, contexto="prueba")
    assert "/stream" in str(exc.value)

    with pytest.raises(ValueError):
        rp.normalizar_base_ws("wss://fstream.binance.com/otro",
                               rp.WS_CATEGORIA_LIBRO, contexto="prueba")

    with pytest.raises(ValueError):
        rp.normalizar_base_ws("https://fstream.binance.com/public",
                               rp.WS_CATEGORIA_LIBRO, contexto="prueba")

    with pytest.raises(ValueError):
        rp.normalizar_base_ws("wss://fstream.binance.com/public",
                               "privada", contexto="prueba")


# ---------------------------------------------------------------------------
# B (estricto). Validacion exacta de la base: solo raiz o ruta exacta
# ---------------------------------------------------------------------------

BASES_VALIDAS = [
    # (base, categoria, base canonica esperada)
    ("wss://fstream.binance.com", rp.WS_CATEGORIA_LIBRO,
     "wss://fstream.binance.com/public"),
    ("wss://fstream.binance.com/", rp.WS_CATEGORIA_LIBRO,
     "wss://fstream.binance.com/public"),
    ("wss://fstream.binance.com/public", rp.WS_CATEGORIA_LIBRO,
     "wss://fstream.binance.com/public"),
    ("wss://fstream.binance.com/public/", rp.WS_CATEGORIA_LIBRO,
     "wss://fstream.binance.com/public"),
    ("wss://fstream.binance.com", rp.WS_CATEGORIA_FLUJO,
     "wss://fstream.binance.com/market"),
    ("wss://fstream.binance.com/market", rp.WS_CATEGORIA_FLUJO,
     "wss://fstream.binance.com/market"),
    ("wss://fstream.binance.com/market/", rp.WS_CATEGORIA_FLUJO,
     "wss://fstream.binance.com/market"),
    ("ws://127.0.0.1:62000", rp.WS_CATEGORIA_LIBRO,
     "ws://127.0.0.1:62000/public"),
    ("ws://127.0.0.1:62000/market", rp.WS_CATEGORIA_FLUJO,
     "ws://127.0.0.1:62000/market"),
]


@pytest.mark.parametrize("base,categoria,esperada", BASES_VALIDAS)
def test_bases_validas_exactas(base, categoria, esperada) -> None:
    assert rp.normalizar_base_ws(base, categoria, contexto="prueba") == esperada


BASES_INVALIDAS = [
    "wss://fstream.binance.com/otra/market",     # prefijo adicional
    "wss://fstream.binance.com/public/market",   # prefijo adicional
    "wss://fstream.binance.com/MARKET",          # mayusculas
    "wss://fstream.binance.com/Market",
    "wss://fstream.binance.com/PUBLIC",
    "wss://fstream.binance.com//public",         # barra duplicada
    "wss://fstream.binance.com/public/extra",    # sufijo
    "wss://fstream.binance.com/public/stream",   # /stream preincluido
    "wss://fstream.binance.com/stream",
    "wss://fstream.binance.com/public?streams=x",  # query
    "wss://fstream.binance.com/public#frag",       # fragmento
    "wss://user:pass@fstream.binance.com/public",  # credenciales
    "wss://fstream.binance.com/otra",
]


@pytest.mark.parametrize("base", BASES_INVALIDAS)
def test_bases_invalidas_se_rechazan(base) -> None:
    with pytest.raises(ValueError):
        rp.normalizar_base_ws(base, rp.WS_CATEGORIA_LIBRO, contexto="prueba")
    with pytest.raises(ValueError):
        rp.normalizar_base_ws(base, rp.WS_CATEGORIA_FLUJO, contexto="prueba")


def test_url_construida_no_puede_contener_ruta_incompatible() -> None:
    """La URL efectiva nunca hereda prefijos ni mayusculas de la base."""
    with pytest.raises(ValueError):
        rp.build_stream_url("wss://fstream.binance.com/otra/market",
                            ["btcusdt@aggTrade"], rp.WS_CATEGORIA_FLUJO)
    with pytest.raises(ValueError):
        rp.build_stream_url("wss://fstream.binance.com/MARKET",
                            ["btcusdt@aggTrade"], rp.WS_CATEGORIA_FLUJO)
    url = rp.build_stream_url("wss://fstream.binance.com/MARKET".lower(),
                              ["btcusdt@aggTrade"], rp.WS_CATEGORIA_FLUJO)
    assert url == ("wss://fstream.binance.com/market/stream"
                   "?streams=btcusdt@aggTrade")


def test_cli_rechaza_ws_en_modo_publico(tmp_path: Path) -> None:
    """Modo publico: se exige wss (no ws) y el host autorizado."""
    proc = _cli([
        "--mode", "public", "--activar-publico",
        "--run-id", "ws-rutas", "--out-dir", str(tmp_path / "out"),
        "--ws-public-base", "ws://fstream.binance.com/public",
        "--ws-market-base", "wss://fstream.binance.com/market",
    ])
    assert proc.returncode != 0
    assert "base publica incompatible" in proc.stderr


def test_cli_rechaza_base_publica_incorrecta(tmp_path: Path) -> None:
    """Host distinto del venue USD-M documentado -> error explicito."""
    proc = _cli([
        "--mode", "public", "--activar-publico",
        "--run-id", "ws-rutas", "--out-dir", str(tmp_path / "out"),
        "--ws-public-base", "wss://example.com/public",
        "--ws-market-base", "wss://example.com/market",
    ])
    assert proc.returncode != 0
    assert "base publica incompatible" in proc.stderr


def test_cli_rechaza_categoria_cruzada(tmp_path: Path) -> None:
    proc = _cli([
        "--mode", "local",
        "--run-id", "ws-rutas", "--out-dir", str(tmp_path / "out"),
        "--rest-base", "http://127.0.0.1:1",
        "--ws-public-base", "ws://127.0.0.1:1/market",
        "--ws-market-base", "ws://127.0.0.1:1/market",
    ])
    assert proc.returncode != 0
    assert "categoria cruzada" in proc.stderr


# ---------------------------------------------------------------------------
# C/D/E. Cliente productivo: recepcion, desempaquetado y motores
# ---------------------------------------------------------------------------


@pytest.fixture()
def piloto_local(tmp_path: Path):
    """Piloto real (CLI) contra los proveedores loopback existentes."""
    run = PilotRun(tmp_path, universe=UNIVERSE, duration_s=180, settle_s=300,
                   selection_s=3600, max_symbols=5)
    try:
        yield run
    finally:
        run.shutdown()


def test_recepcion_y_procesamiento_por_categoria(piloto_local) -> None:
    """C+D+E: frames validos, desempaquetado combinado y motores del repo."""
    run = piloto_local
    run.wait_ready(expected_followed=5)
    state_inicial = run.status()

    # Las dos conexiones se abren por categoria y con contadores separados.
    feeds = state_inicial["feeds"]
    assert set(feeds) == {"public", "market"}
    assert run.ws.connections_by_category["public"] == 1
    assert run.ws.connections_by_category["market"] == 1

    e0 = T0 + MINUTE
    serie = list(range(e0 - 62_000, e0 + 1, 1_000))
    run.step(e0, depth_symbols=UNIVERSE,
             trade_events={s: serie for s in UNIVERSE}, evaluate=False)

    estado = run.status()
    # BookEngine: un evento de libro por simbolo.
    for simbolo in UNIVERSE:
        assert estado["book_events"][simbolo] >= 1
        assert estado["book"][simbolo]["event_ms"] == e0
    # FlowEngine: un evento de flujo por trade de la serie.
    for simbolo in UNIVERSE:
        assert estado["flow_events"][simbolo] >= len(serie)
    # Conteos de transporte separados por conexion.
    assert estado["feeds"]["public"]["messages"] > 0
    assert estado["feeds"]["market"]["messages"] > 0
    assert run.ws.frames_by_category["public"] >= len(UNIVERSE)
    assert run.ws.frames_by_category["market"] >= len(UNIVERSE) * len(serie)


def test_control_no_es_flujo_agresor(piloto_local) -> None:
    """Un ACK/ping cuenta como frame recibido, nunca como evento de flujo."""
    run = piloto_local
    run.wait_ready(expected_followed=5)
    antes = run.status()
    flow_antes = dict(antes["flow_events"])
    mensajes_antes = antes["feeds"]["market"]["messages"]

    enviados = run.ws.publish_control(
        json.dumps({"result": None, "id": 1}), categoria="market")
    assert enviados == 1

    deadline = time.monotonic() + 15.0
    despues = antes
    while time.monotonic() < deadline:
        despues = run.status()
        if despues["feeds"]["market"]["messages"] > mensajes_antes:
            break
        time.sleep(0.05)
    assert despues["feeds"]["market"]["messages"] > mensajes_antes
    assert despues["flow_events"] == flow_antes


def test_proveedor_rechaza_categoria_cruzada(tmp_path: Path) -> None:
    """B en el proveedor: una conexion de la categoria equivocada no se sirve."""
    provider = WsProvider(UNIVERSE)
    port = find_free_port()
    stop = start_ws_server(provider, port)
    try:
        import asyncio

        import websockets

        async def _conectar(ruta: str, stream: str):
            url = f"ws://127.0.0.1:{port}{ruta}?streams={stream}"
            async with websockets.connect(url, open_timeout=10) as ws:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=2.0)
                except Exception:
                    return None
                return "dato"

        # Libro pedido en la ruta de mercado: el proveedor no sirve libro.
        assert asyncio.run(_conectar("/market/stream",
                                      "aaausdt@depth20@100ms")) is None
        # Flujo pedido en la ruta de libro: el proveedor no sirve trades.
        assert asyncio.run(_conectar("/public/stream",
                                      "aaausdt@aggTrade")) is None
        # Ruta inexistente: rechazada.
        assert asyncio.run(_conectar("/stream", "aaausdt@aggTrade")) is None
        assert provider.rejected_paths
        assert provider.rejected_streams
        assert provider.frames_by_category == {"public": 0, "market": 0}
    finally:
        stop()


# ---------------------------------------------------------------------------
# F. Cierre efectivo de sockets y procesos propios
# ---------------------------------------------------------------------------


def test_cierre_de_sockets_y_procesos(piloto_local) -> None:
    run = piloto_local
    run.wait_ready(expected_followed=5)
    assert run.ws.open_connections == 2

    rc = run.stop()
    assert rc == 0, run.stderr
    # El proceso propio termino y sus sockets quedaron cerrados: el
    # proveedor deja de ver conexiones vivas.
    assert run.proc.poll() is not None
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline and run.ws.open_connections:
        time.sleep(0.05)
    assert run.ws.open_connections == 0

    # Al cerrar los recursos propios el puerto del proveedor deja de aceptar.
    run.shutdown()
    import socket
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            try:
                probe.connect(("127.0.0.1", run.ws_port))
            except OSError:
                break
        time.sleep(0.1)
    else:
        raise AssertionError("el puerto propio sigue aceptando conexiones")
