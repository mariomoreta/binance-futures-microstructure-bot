"""Diagnostico de recepcion WS: comprobacion publica MINIMA (NO EJECUTADA).

Abre dos conexiones del transporte productivo (``StreamFeed``) y distingue la
escalera de evidencia del venue:

  1. conexion establecida,
  2. frames de datos recibidos (y frames de control, que NO acreditan flujo),
  3. eventos validos recibidos (aggTrade / depth con sus campos),
  4. eventos procesados por ``BookEngine`` / ``FlowEngine``,
  5. errores y reconexiones.

No genera dataset de investigacion: solo un JSON compacto de evidencia. Cero
REST, cero ordenes, cero ejecucion del experimento operativo. Las bases se
validan con los helpers productivos (``normalizar_base_ws`` y
``build_stream_url``) ANTES de abrir ningun socket, y contra el venue publico
exige ``--autorizar-publico``: sin esa autorizacion explicita el proceso
falla cerrado sin abrir conexiones.

Veredicto:
  PASS        feed de trades con frames validos y eventos procesados por
              FlowEngine, feed de libro con frames validos y eventos procesados
              por BookEngine, dos conexiones iniciales, cero reconexiones y
              cero errores.
  INSUFICIENTE  sin errores ni reconexiones, pero sin frames validos (o sin
              eventos procesados): no se demuestra recepcion.
  FAIL        error de conexion, reconexionintentada o limite excedido.

Codigos de salida: 0 PASS, 10 INSUFICIENTE, 11 FAIL, 2 error de uso.
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import research_pilot as rp  # noqa: E402
from microstructure_probe.book import BookEngine  # noqa: E402
from microstructure_probe.flow import FlowEngine  # noqa: E402

DURACION_MAX_S = 60.0
WS_HOST_PUBLICO = rp.WS_HOST_PUBLICO
EXIT_PASS = 0
EXIT_INSUFICIENTE = 10
EXIT_FAIL = 11
EXIT_USO = 2


# ---------------------------------------------------------------------------
# Reutilizacion del camino productivo (sin refactorizarlo)
# ---------------------------------------------------------------------------


class _GrabadorNulo:
    """El piloto persiste en DB/JSONL; aqui no se genera dataset."""

    def record_trade(self, *args: Any, **kwargs: Any) -> None:
        return None

    def record_book(self, *args: Any, **kwargs: Any) -> None:
        return None


class _ProcesadorPiloto:
    """Reutiliza ``ResearchPilot.handle_message`` tal cual.

    No se refactoriza el camino productivo: se toma el metodo tal cual y se
    le suministra el estado que utiliza. Si el piloto anade dependencias al
    manejador, la comprobacion de arranque falla ANTES de conectar (no en
    silencio).
    """

    handle_message = rp.ResearchPilot.handle_message
    _is_duplicate_trade = rp.ResearchPilot._is_duplicate_trade

    def __init__(self, simbolo: str) -> None:
        self.followed = {simbolo}
        self.clock = rp.SystemClock()
        self.book = BookEngine(symbols=(simbolo,))
        self.flow = FlowEngine(symbols=(simbolo,))
        self.recorder = _GrabadorNulo()
        self.flow_seen_ids: Dict[str, set] = {}
        self.flow_seen_order: Dict[str, list] = {}
        self.dedupe_flow: Dict[str, int] = {}
        self.last_flow_recv: Dict[str, int] = {}
        self.last_flow_event: Dict[str, int] = {}
        self.symbol_first_flow_ms: Dict[str, int] = {}
        self.flow_events: Dict[str, int] = {}
        self.last_book_u: Dict[str, int] = {}
        self.dedupe_book: Dict[str, int] = {}
        self.book_gaps: Dict[str, int] = {}
        self.last_book_recv: Dict[str, int] = {}
        self.last_book_event: Dict[str, int] = {}
        self.symbol_first_book_ms: Dict[str, int] = {}
        self.book_events: Dict[str, int] = {}

    def comprobar_contrato(self) -> None:
        """Falla ruidosamente si el manejador del piloto cambio."""
        fuente = (inspect.getsource(rp.ResearchPilot.handle_message)
                  + inspect.getsource(rp.ResearchPilot._is_duplicate_trade))
        requeridos = set(re.findall(r"self\.([A-Za-z_][A-Za-z0-9_]*)", fuente))
        disponibles = set(dir(self))
        faltan = sorted(requeridos - disponibles)
        if faltan:
            raise RuntimeError(
                "el manejador del piloto requiere atributos que este "
                f"diagnostico no suministra: {faltan}. Actualizar el "
                "diagnostico antes de usarlo.")


# ---------------------------------------------------------------------------
# Conteo de evidencia
# ---------------------------------------------------------------------------


class _Contador:
    """Clasifica frames: datos validos, datos invalidos y control."""

    def __init__(self, simbolo: str, clase: str) -> None:
        self.simbolo = simbolo
        self.clase = clase  # "market" (aggTrade) | "public" (depth)
        self.frames_total = 0
        self.frames_control = 0
        self.frames_datos = 0
        self.frames_datos_fuera = 0
        self.eventos_validos = 0
        self.frames_invalidos = 0

    def clasificar(self, raw: Any) -> str:
        self.frames_total += 1
        try:
            envelope = json.loads(raw)
        except Exception:
            self.frames_control += 1
            return "control"
        if not isinstance(envelope, dict):
            self.frames_control += 1
            return "control"
        data = envelope.get("data")
        if not isinstance(data, dict):
            # ACK, ping o mensaje de control: NO acredita flujo agresor.
            self.frames_control += 1
            return "control"
        self.frames_datos += 1
        simbolo = str(data.get("s") or "").upper()
        if simbolo != self.simbolo:
            self.frames_datos_fuera += 1
            return "otro"
        if self.clase == "market":
            valido = all(k in data for k in ("a", "E", "m", "p", "q", "s"))
        else:
            valido = all(k in data for k in ("E", "a", "b", "s", "u"))
        if valido:
            self.eventos_validos += 1
            return "valido"
        self.frames_invalidos += 1
        return "invalido"

    def estado(self) -> Dict[str, Any]:
        return {
            "frames_total": self.frames_total,
            "frames_datos": self.frames_datos,
            "frames_control": self.frames_control,
            "frames_datos_fuera_de_simbolo": self.frames_datos_fuera,
            "eventos_validos": self.eventos_validos,
            "frames_invalidos": self.frames_invalidos,
        }


# ---------------------------------------------------------------------------
# Ejecucion
# ---------------------------------------------------------------------------


async def _correr(args, urls: Dict[str, str], simbolo: str) -> Dict[str, Any]:
    contador_market = _Contador(simbolo, "market")
    contador_public = _Contador(simbolo, "public")
    procesador = _ProcesadorPiloto(simbolo)
    procesador.comprobar_contrato()

    def _handler_market(raw: Any) -> None:
        contador_market.clasificar(raw)
        procesador.handle_message(raw)

    def _handler_public(raw: Any) -> None:
        contador_public.clasificar(raw)
        procesador.handle_message(raw)

    feeds = {
        "market": rp.StreamFeed("market", urls["market"], _handler_market),
        "public": rp.StreamFeed("public", urls["public"], _handler_public),
    }
    stop = asyncio.Event()
    tasks = [asyncio.create_task(feed.run(stop)) for feed in feeds.values()]
    inicio = time.time()
    limite_mensajes = int(args.max_messages)
    limite_excedido = False
    while not stop.is_set():
        await asyncio.sleep(0.05)
        total = sum(feed.messages for feed in feeds.values())
        if total >= limite_mensajes:
            limite_excedido = True
            stop.set()
            break
        if any(feed.reconnects > 0 for feed in feeds.values()):
            # Cero reconexiones automaticas: se corta antes del reintento.
            stop.set()
            break
        if time.time() - inicio >= args.duracion_seconds:
            stop.set()
            break
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    fin = time.time()
    return {
        "inicio_iso_utc": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(inicio)),
        "fin_iso_utc": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(fin)),
        "duracion_s": round(fin - inicio, 3),
        "limite_mensajes_alcanzado": limite_excedido,
        "feeds": {name: feed.status() for name, feed in feeds.items()},
        "evidencia": {
            "market": contador_market.estado(),
            "public": contador_public.estado(),
        },
        "eventos_procesados": {
            "book_events": dict(procesador.book_events),
            "flow_events": dict(procesador.flow_events),
        },
    }


def _veredicto(args, resultado: Dict[str, Any]) -> tuple:
    """(veredicto, motivos) segun los criterios definidos en el modulo."""
    feeds = resultado["feeds"]
    market = feeds["market"]
    public = feeds["public"]
    ev = resultado["evidencia"]
    flow = resultado["eventos_procesados"]["flow_events"]
    book = resultado["eventos_procesados"]["book_events"]
    simbolo = args.simbolo

    motivos = []
    if resultado["limite_mensajes_alcanzado"]:
        motivos.append("limite de mensajes alcanzado")
    reconexiones = sum(f["reconnects"] for f in feeds.values())
    if reconexiones:
        motivos.append(f"reconexiones: {reconexiones}")
    errores = sum(f["errors"] for f in feeds.values())
    if errores:
        motivos.append(f"errores de feed: {errores}")
    conexiones = sum(f["connections"] for f in feeds.values())
    if conexiones != 2:
        motivos.append(f"aperturas iniciales: {conexiones} (se esperaban 2)")

    trade_ok = (ev["market"]["eventos_validos"] > 0
                and flow.get(simbolo, 0) > 0)
    libro_ok = (ev["public"]["eventos_validos"] > 0
                and book.get(simbolo, 0) > 0)
    if not trade_ok:
        motivos.append(
            "sin recepcion valida de trades (aggTrade): "
            f"validos={ev['market']['eventos_validos']} "
            f"flujo_procesado={flow.get(simbolo, 0)}")
    if not libro_ok:
        motivos.append(
            "sin recepcion valida de libro (depth20@100ms): "
            f"validos={ev['public']['eventos_validos']} "
            f"libro_procesado={book.get(simbolo, 0)}")

    if resultado["limite_mensajes_alcanzado"] or reconexiones or errores:
        return "FAIL", motivos
    if not (trade_ok and libro_ok):
        return "INSUFICIENTE", motivos
    return "PASS", motivos


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diagnostico de recepcion WS (sin REST, sin ordenes).")
    parser.add_argument("--diagnostico-id", default="diag-ws-recepcion")
    parser.add_argument("--simbolo", required=True,
                        help="simbolo explicito (perpetuo USD-M), p.ej. BTCUSDT")
    parser.add_argument("--duracion-seconds", type=float, default=DURACION_MAX_S,
                        help=f"duracion global maxima ({DURACION_MAX_S:.0f} s)")
    parser.add_argument("--out-dir", required=True,
                        help="directorio aislado de la evidencia compacta")
    parser.add_argument("--ws-public-base", default=f"wss://{WS_HOST_PUBLICO}/public")
    parser.add_argument("--ws-market-base", default=f"wss://{WS_HOST_PUBLICO}/market")
    parser.add_argument("--autorizar-publico", action="store_true",
                        help="exigido si las bases apuntan al venue publico")
    parser.add_argument("--max-messages", type=int, default=200_000,
                        help="tope de frames recibidos en toda la comprobacion")
    parser.add_argument("--max-bytes", type=int, default=1_048_576,
                        help="tope de almacenamiento de la evidencia compacta")
    args = parser.parse_args(list(argv) if argv is not None else sys.argv[1:])

    simbolo = str(args.simbolo).strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,20}USDT", simbolo):
        print(json.dumps({
            "error": f"simbolo invalido {args.simbolo!r}: se espera un "
                     "perpetuo USD-M explicito (p.ej. BTCUSDT)"}),
            file=sys.stderr)
        return EXIT_USO
    args.simbolo = simbolo
    if args.duracion_seconds <= 0 or args.duracion_seconds > DURACION_MAX_S:
        print(json.dumps({
            "error": f"duracion fuera de rango: {args.duracion_seconds} "
                     f"(0 < duracion <= {DURACION_MAX_S:.0f} s)"}),
            file=sys.stderr)
        return EXIT_USO

    # Validacion ANTES de abrir conexiones, con los helpers productivos.
    try:
        url_public = rp.build_stream_url(
            args.ws_public_base, [f"{simbolo.lower()}@depth20@100ms"],
            rp.WS_CATEGORIA_LIBRO)
        url_market = rp.build_stream_url(
            args.ws_market_base, [f"{simbolo.lower()}@aggTrade"],
            rp.WS_CATEGORIA_FLUJO)
    except ValueError as exc:
        print(json.dumps({"error": f"base WS invalida: {exc}"}), file=sys.stderr)
        return EXIT_USO
    es_publico = WS_HOST_PUBLICO in url_public and WS_HOST_PUBLICO in url_market
    if es_publico and not args.autorizar_publico:
        print(json.dumps({
            "error": "las bases apuntan al venue publico: hace falta "
                     "--autorizar-publico (no se abre ninguna conexion)"}),
            file=sys.stderr)
        return EXIT_USO

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    evidencia = {
        "diagnostico_id": args.diagnostico_id,
        "simbolo": simbolo,
        "simbolo_fuente": "indicado explicitamente; no se consulto el mercado",
        "autorizado_publico": bool(args.autorizar_publico),
        "modo": "publico" if es_publico else "loopback",
        "rest": "ninguna peticion REST",
        "ordenes": "ninguna",
        "dataset_investigacion": "no se genera",
        "urls": {"public": url_public, "market": url_market},
        "limites": {
            "duracion_s": args.duracion_seconds,
            "duracion_max_s": DURACION_MAX_S,
            "max_messages": args.max_messages,
            "max_bytes": args.max_bytes,
            "aperturas_iniciales": 2,
            "reconexiones_automaticas": 0,
        },
    }
    resultado = asyncio.run(_correr(args, {"public": url_public,
                                           "market": url_market}, simbolo))
    veredicto, motivos = _veredicto(args, resultado)
    evidencia["resultado"] = resultado
    evidencia["veredicto"] = veredicto
    evidencia["motivos"] = motivos
    evidencia["criterio"] = {
        "PASS": "trades: eventos validos > 0 y flow_events > 0; libro: "
                "eventos validos > 0 y book_events > 0; 2 conexiones, 0 "
                "reconexiones, 0 errores",
        "INSUFICIENTE": "sin errores ni reconexiones pero sin recepcion valida",
        "FAIL": "error de conexion, reconexion o limite excedido",
        "nota": "un frame de control (ACK/ping) no acredita flujo agresor",
    }
    destino = out_dir / "diagnostico.json"
    texto = json.dumps(evidencia, ensure_ascii=False, indent=1)
    if len(texto.encode("utf-8")) > args.max_bytes:
        print(json.dumps({
            "error": "la evidencia supera --max-bytes; no se escribe"}),
            file=sys.stderr)
        return EXIT_FAIL
    destino.write_text(texto, encoding="utf-8")
    print(json.dumps({
        "diagnostico_id": args.diagnostico_id,
        "simbolo": simbolo,
        "veredicto": veredicto,
        "motivos": motivos,
        "evidencia": str(destino),
    }, ensure_ascii=False))
    if veredicto == "PASS":
        return EXIT_PASS
    if veredicto == "INSUFICIENTE":
        return EXIT_INSUFICIENTE
    return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
