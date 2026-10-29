"""Productor WS LOCAL para la DEMOSTRACIÓN de ingeniería (datos simulados).

Este script NO toca Binance y NO es una fuente de mercado real: emite un
ticker kline 1m determinista por loopback para que la sesión de ingeniería
pueda operar en modo ``market_stream`` sin servicios preexistentes ni
transporte público. Es una pieza de DEMOSTRACIÓN, claramente separada de la
futura fuente Binance pública (esa es otra ruta, con autorización separada).

Reutiliza el productor local ya acreditado (``FakeKlineServer`` del arnés
``scripts/market_stream_local_acceptance.py``); solo añade un ciclo de
precios determinista y parada automática acotada.

Uso (desde la raíz del repo; lo arranca el BFF, no a mano):

  python scripts/local_demo_producer.py --base 0.1234 \
      --log data/engineering-demo/producer.log.jsonl \
      --pid-file data/engineering-demo/producer.json \
      --max-runtime-s 2700

Al estar listo escribe UNA línea JSON en stdout (identidad del productor:
pid, puerto real del WS, base, límite de duración) y un pid-file con el
mismo contenido. A los ``--max-runtime-s`` se detiene solo, retira su
pid-file y avisa por stdout. Sin ``--base`` no arranca (exit 2): el precio
base debe venir del cache local (el mismo del contexto de la sesión).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from market_stream_local_acceptance import (  # noqa: E402
    STEP_MS, FakeKlineServer, now_ms,
)

PRODUCER_SERVICE = "local-demo-producer/v1"
DEMO_SYMBOL = "MINAUSDT"
# Ciclo de closes sobre el base (fracciones del precio base). idx % len:
# con cualquier base del cache, el ciclo alcanza closes > base (favor de
# LONG, regla RULE-CAUSAL-V1) y nunca baja al stop (base*0.985 con step 1.5%).
CYCLE = (0.9990, 1.0005, 1.0010, 1.0020, 1.0025)
# Velas PREVIAS al ancla (backfill del primer connect): bajo el base, sin
# senal contra entry_px = base.
PRE_CYCLE = 0.9990


def free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class DemoKlineServer(FakeKlineServer):
    """Ticker determinista en ciclo (sin guion de guion, sin pausa).

    Estado COMPARTIDO por simbolo entre reconexiones: el servicio de
    mercado recicla su socket cada pocos segundos (churn observado); con
    estado por conexion la vela en curso se reiniciaria en cada reciclaje y
    ninguna frontera cerraria jamas (cada reconnect llega a mitad de vela).
    """

    BACKFILL_BOUNDARIES = 2
    # Tope de backfill por connect (memoria/tiempo acotados): 7 dias de 1m.
    MAX_BACKFILL_BARS = 10_080
    # Ritmo de envio del backfill (segundos por vela). Debe ser lo bastante
    # lento para que el consumidor (market_stream_service) reciba cada vela
    # antes de que el productor avance al siguiente open: de otro modo, si el
    # socket se recicla (churn), state["open"] quedaria por delante de lo que
    # el consumidor recibio y el catch-up saltaria velas (GRID_GAP). 1.0 s
    # (1 vela/segundo) elimina la saturacion del socket WS y permite que el
    # consumidor reciba cada vela del backfill sin huecos (~42 h en ~42 min;
    # el tope de duracion acortada detiene al productor a los 5 min, lo que
    # ya basta para cubrir las primeras velas de operacion y la senal).
    BACKFILL_PACE_S = 1.0

    def __init__(self, port: int, log_path: Path, base: float,
                 backfill_from_ms: Optional[int] = None) -> None:
        super().__init__(port, log_path)
        self.base = float(base)
        # Primera frontera a backfillar (cache_end + paso) para reparar el
        # tramo cache->conexion SIN reparacion REST en local.
        self.backfill_from_ms = backfill_from_ms
        self.anchor_open: Optional[int] = None
        self.shared_state: Dict[str, Dict[str, Any]] = {}

    def close_of(self, symbol: str, open_ms: int) -> float:
        if symbol != DEMO_SYMBOL:
            return 100000.0
        anchor = self.anchor_open
        if anchor is None:
            return round(self.base * PRE_CYCLE, 8)
        idx = int((int(open_ms) - anchor) // STEP_MS)
        if idx < 0:
            return round(self.base * PRE_CYCLE, 8)
        return round(self.base * CYCLE[idx % len(CYCLE)], 8)

    async def _ticker(self, ws, symbol: str) -> None:  # type: ignore[override]
        state = self.shared_state.setdefault(symbol, {
            "open": None, "open_price": None, "high": None, "low": None,
            "close": None, "last_event": 0, "volume": 0.0})
        try:
            while True:
                now = now_ms()
                current_open = (now // STEP_MS) * STEP_MS
                if state["open"] is None:
                    # Primer connect (o reconecta tras caída): backfill de las
                    # fronteras cerradas EN ORDEN desde backfill_from_ms para
                    # reparar el tramo cache->conexion SIN reparacion REST.
                    # Cada reconexion reenvia desde backfill_from_ms: el
                    # consumidor (market_stream_service) deduplica por marca de
                    # agua (ot <= watermark se ignora), de modo que nunca se
                    # pierde continuidad aunque el socket se recicle (churn).
                    # Evitamos confiar en state["open"] avanzado por una
                    # conexion previa, porque al reconectar el catch-up
                    # empezaria desde ahi y saltaria las velas que el
                    # productor ya puso en el buffer del WS pero el consumidor
                    # nunca recibio (causa del GRID_GAP en la corrida 4).
                    ev = now
                    if self.backfill_from_ms is not None:
                        start_open = self.backfill_from_ms
                    else:
                        start_open = current_open - (
                            self.BACKFILL_BOUNDARIES * STEP_MS)
                    min_open = current_open - (
                        self.MAX_BACKFILL_BARS * STEP_MS)
                    if start_open < min_open:
                        start_open = min_open
                    # Ancla del ciclo de precios: la PRIMERA frontera del
                    # backfill (no current_open). Si se anclara a current_open,
                    # todas las velas del backfill (open_ms < anchor_open)
                    # tendrían idx < 0 y close = PRE_CYCLE (0.999*base),
                    # por debajo de entry_px, y nunca habría señal.
                    if symbol == DEMO_SYMBOL and self.anchor_open is None:
                        self.anchor_open = start_open
                    back_open = start_open
                    while back_open < current_open:
                        state["open"] = back_open
                        state["open_price"] = self.close_of(
                            symbol, back_open - STEP_MS)
                        state["close"] = self.close_of(symbol, back_open)
                        state["high"] = max(state["open_price"],
                                            state["close"]) * 1.0005
                        state["low"] = min(state["open_price"],
                                           state["close"]) * 0.9995
                        state["last_event"] = ev
                        state["volume"] = 1.0
                        await self._send(ws, symbol, state, closed=True,
                                         event_ms=ev)
                        ev += 1
                        back_open += STEP_MS
                        # Pace: entrega ordenada sin saturar la cola del
                        # consumidor SSE. Cada vela se envia con un retardo
                        # acotado para que el adaptador las consuma todas.
                        if self.BACKFILL_PACE_S > 0:
                            await asyncio.sleep(self.BACKFILL_PACE_S)
                    state["open"] = current_open
                    state["open_price"] = self.close_of(symbol,
                                                        current_open - STEP_MS)
                    state["close"] = self.close_of(symbol, current_open)
                    state["high"] = max(state["open_price"], state["close"])
                    state["low"] = min(state["open_price"], state["close"])
                    state["last_event"] = max(now, ev)
                    state["volume"] = 1.0
                    await self._send(ws, symbol, state, closed=False,
                                     event_ms=state["last_event"])
                elif current_open > state["open"]:
                    # Cierres en frontera (todas las omitidas, en orden).
                    # Defecto corregido (corrida 2, 2026-10-28): el marco del
                    # payload lo arma `_send` desde `state["open"]`; si el
                    # backfill aborto a mitad (churn del servicio) y la
                    # reconexion entra por aqui, el bucle avanzaba `op`
                    # local SIN tocar `state["open"]` y TODOS los frames
                    # salian con el open de la primera barra pisando la
                    # misma fila en el servicio (huecos de rejilla ->
                    # GRID_GAP permanente, sin senal). Ahora cada frame
                    # lleva su propio open.
                    ev = max(now, int(state["last_event"]) + 1)
                    op = int(state["open"])
                    while op < current_open:
                        state["open"] = op
                        state["close"] = self.close_of(symbol, op)
                        state["open_price"] = self.close_of(symbol,
                                                            op - STEP_MS)
                        state["high"] = max(state["open_price"],
                                            state["close"]) * 1.0005
                        state["low"] = min(state["open_price"],
                                           state["close"]) * 0.9995
                        state["last_event"] = ev
                        state["volume"] = 1.0
                        await self._send(ws, symbol, state, closed=True,
                                         event_ms=ev)
                        ev += 1
                        op += STEP_MS
                    state["open"] = current_open
                    state["open_price"] = self.close_of(symbol,
                                                        current_open - STEP_MS)
                    state["close"] = self.close_of(symbol, current_open)
                    state["high"] = max(state["open_price"], state["close"])
                    state["low"] = min(state["open_price"], state["close"])
                    state["last_event"] = max(now, state["last_event"] + 2)
                    state["volume"] = 1.0
                    await self._send(ws, symbol, state, closed=False,
                                     event_ms=state["last_event"])
                else:
                    state["last_event"] = max(now, state["last_event"] + 1)
                    state["close"] = self.close_of(symbol, state["open"])
                    state["high"] = max(state["high"], state["close"])
                    state["low"] = min(state["low"], state["close"])
                    state["volume"] = round(state["volume"] + 0.4, 4)
                    await self._send(ws, symbol, state, closed=False,
                                     event_ms=state["last_event"])
                await asyncio.sleep(2.0)
        except (asyncio.CancelledError, ConnectionError, OSError):
            raise
        except Exception:  # noqa: BLE001 - el peer cerro
            return


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0,
                        help="puerto WS (0 = efimero elegido aqui)")
    parser.add_argument("--symbol", default=DEMO_SYMBOL)
    parser.add_argument("--base", type=float, default=None,
                        help="precio base (ultimo close del cache local)")
    parser.add_argument("--btc-base", type=float, default=100000.0)
    parser.add_argument("--log", required=True)
    parser.add_argument("--pid-file", required=True)
    parser.add_argument("--max-runtime-s", type=float, default=2700.0,
                        help="parada automatica acotada (default 45 min)")
    parser.add_argument("--backfill-from-ms", type=int, default=None,
                        help="primera frontera del backfill inicial "
                             "(cache_end + paso); si falta, solo las "
                             "ultimas 2 fronteras")
    args = parser.parse_args(argv)

    if args.base is None:
        print(json.dumps({"service": PRODUCER_SERVICE,
                          "error": "BASE_REQUIRED",
                          "detail": "sin --base no arranca (el precio base "
                                    "debe venir del cache local)"}),
              file=sys.stderr)
        return 2

    # asyncio lo usa el bucle del servidor WS heredado; importado a nivel de
    # modulo para que el import del paquete no dependa del orden de ejecucion.
    global asyncio  # noqa: PLW0603 - heredado del patron del arnes
    import asyncio  # noqa: PLC0415

    log_path = Path(args.log)
    pid_path = Path(args.pid_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.parent.mkdir(parents=True, exist_ok=True)

    port = args.port if args.port > 0 else free_port()
    server = DemoKlineServer(port, log_path, args.base,
                             backfill_from_ms=args.backfill_from_ms)
    server.start()

    identity = {
        "service": PRODUCER_SERVICE,
        "pid": os.getpid(),
        "port": port,
        "host": "127.0.0.1",
        "symbol": args.symbol,
        "base": args.base,
        "max_runtime_s": args.max_runtime_s,
        "started_at_ms": now_ms(),
    }
    pid_path.write_text(json.dumps(identity) + "\n", encoding="utf-8")
    print(json.dumps(identity, ensure_ascii=False), flush=True)

    def expire() -> None:
        # Duracion acotada: el productor se detiene SOLO, retira su pid-file
        # y avisa. El gestor de la demo ve el pid-file ausente y reporta la
        # demostracion como expirada (sin matar procesos desconocidos).
        try:
            server.stop()
        except Exception:  # noqa: BLE001 - la parada no debe enmascarar nada
            pass
        try:
            pid_path.unlink(missing_ok=True)
        except OSError:
            pass
        print(json.dumps({"service": PRODUCER_SERVICE,
                          "event": "EXPIRED",
                          "max_runtime_s": args.max_runtime_s}),
              flush=True)
        os._exit(0)

    timer = threading.Timer(max(args.max_runtime_s, 1.0), expire)
    timer.daemon = True
    timer.start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        timer.cancel()
        try:
            server.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            pid_path.unlink(missing_ok=True)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
