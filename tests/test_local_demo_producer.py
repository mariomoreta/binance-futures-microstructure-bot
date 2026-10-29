"""Productor de la demostración local: ciclo determinista y guardas.

Sin servidores WS en estas pruebas: solo el patrón de precios (lo que hace
que la demo produzca señal sin tocar el stop) y las guardas del CLI.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "local_demo_producer.py"

_spec = importlib.util.spec_from_file_location("local_demo_producer", SCRIPT)
producer = importlib.util.module_from_spec(_spec)
sys.modules["local_demo_producer"] = producer
assert _spec and _spec.loader
_spec.loader.exec_module(producer)


def test_ciclo_determinista_da_senal_long_sin_tocar_el_stop():
    base = 0.1234
    server = producer.DemoKlineServer(0, Path("nul"), base)
    anchor = 1_793_200_000_000
    server.anchor_open = anchor
    step = producer.STEP_MS
    closes = [server.close_of("MINAUSDT", anchor + i * step) for i in range(10)]
    # El ciclo alcanza closes POR ENCIMA del base (favor de LONG, regla
    # RULE-CAUSAL-V1): la demo produce señal de ingeniería sin guion ad hoc.
    assert any(c > base for c in closes)
    # Y ningun low del ciclo toca el stop (base * 0.985, step 1.5%):
    # el minimo close del ciclo es base*0.999 y el low es close*0.9995.
    assert min(closes) > base * 0.985
    # Velas previas al ancla (backfill): bajo el base, sin senal prematura.
    assert server.close_of("MINAUSDT", anchor - step) < base
    # Otras series planas (solo contexto BTC).
    assert server.close_of("BTCUSDT", anchor + step) == 100000.0


def test_cli_sin_base_no_arranca():
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--log", "nul", "--pid-file", "nul"],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT))
    assert r.returncode == 2
    assert "BASE_REQUIRED" in (r.stderr or "")


class _FakeWs:
    """WS falso: registra payloads; puede fallar en el envio N."""

    def __init__(self, fail_on: int, exc: Exception) -> None:
        self.sent: list[str] = []
        self._fail_on = fail_on
        self._exc = exc

    async def send(self, payload: str) -> None:
        if len(self.sent) + 1 >= self._fail_on:
            raise self._exc
        self.sent.append(payload)


def _opens_of(ws: _FakeWs, *, closed_only: bool = True) -> list[int]:
    opens = []
    for raw in ws.sent:
        data = json.loads(raw)["data"]["k"]
        if closed_only and not data["x"]:
            continue
        opens.append(int(data["t"]))
    return opens


def test_catchup_tras_churn_manda_cada_barra_con_su_propio_open():
    """Regresion del defecto de la corrida 2 (2026-10-28).

    El marco lo arma `_send` desde `state["open"]`; si el backfill aborta
    a mitad (churn del servicio de mercado) y la reconexion entra por la
    rama de catch-up, el bucle avanzaba `op` local sin actualizar
    `state["open"]`: TODOS los frames salian con el open de la primera
    barra (2071 envios pisando la misma fila en la corrida 2) -> huecos
    de rejilla -> GRID_GAP permanente -> sin senal. Ahora cada frame
    lleva su propio open y la cadena cerrada queda continua.
    """
    import tempfile

    step = producer.STEP_MS
    fixed_now = 1_793_230_740_000  # dentro del minuto ancla
    producer_now = producer.now_ms
    producer_asyncio = getattr(producer, "asyncio", None)
    producer.now_ms = lambda: fixed_now  # type: ignore[assignment]
    # main() inyecta asyncio en el modulo (global asyncio); el test carga el
    # modulo sin main y necesita el mismo binding para el bucle del ticker.
    producer.asyncio = asyncio  # type: ignore[attr-defined]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            server = producer.DemoKlineServer(
                0, Path(tmp) / "producer.log.jsonl", 0.06285,
                backfill_from_ms=fixed_now - 4 * step)
            # Run 1: backfill aborta en la 3a barra (churn = desconexion).
            ws1 = _FakeWs(fail_on=3, exc=ConnectionError("peer closed"))
            with pytest.raises(ConnectionError):
                asyncio.run(server._ticker(ws1, "MINAUSDT"))
            # La barra 3 quedo apuntada en el estado compartido.
            assert server.shared_state["MINAUSDT"]["open"] == fixed_now - 2 * step
            # Run 2: reconexion -> catch-up desde la barra abortada; el ws
            # falla en el 4o envio (2 cerradas + 1 live) para cortar el
            # bucle infinito del ticker (sin colgar la prueba 2 s por ronda).
            ws2 = _FakeWs(fail_on=4, exc=RuntimeError("fin de prueba"))
            asyncio.run(server._ticker(ws2, "MINAUSDT"))
        opens1 = _opens_of(ws1)
        opens2 = _opens_of(ws2)
        # Run 1: barras 1-2 del backfill, opens correctos y ordenados.
        assert opens1 == [fixed_now - 4 * step, fixed_now - 3 * step]
        # Run 2: catch-up con open PROPIO por frame, continuo y sin duplicar.
        assert opens2 == [fixed_now - 2 * step, fixed_now - step]
        # La cadena cerrada completa no tiene huecos ni repeticiones.
        full = opens1 + opens2
        assert full == [full[0] + i * step for i in range(len(full))]
        assert len(set(full)) == len(full)
    finally:
        producer.now_ms = producer_now  # type: ignore[assignment]
        if producer_asyncio is None:
            del producer.asyncio  # type: ignore[attr-defined]
        else:
            producer.asyncio = producer_asyncio  # type: ignore[attr-defined]
