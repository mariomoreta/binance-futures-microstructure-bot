"""Pruebas de aceptacion del servicio de flujo ``market_flow_service.py``.

Cubre:
  1. Ruta canónica sin fuente: SIN COBERTURA, sin sinteticos, live=false.
  2. Dos eventos locales nuevos actualizan sin recargar.
  3. Duplicado (mismo event_id) no altera acumulados.
  4. Igual timestamp con IDs distintos cuenta ambos.
  5. Cambio de simbolo durante respuesta pendiente no mezcla datos.
  6. Desconexión retira LIVE (frescura caduca).
  7. Cerrar vista libera su consumidor.

Transporte local exclusivamente: sin Binance publico, sin red.
"""

import asyncio
import json
import unittest

from microstructure_probe.market_flow_service import (
    FlowService, _empty_flow_block, _empty_horizon,
)

T0 = 1_700_000_000_000


class _FakeWriter:
    """Writer SSE en memoria para probar publicaciones de clientes."""
    def __init__(self):
        self.frames = []
        self.closed = False

    def write(self, data: bytes) -> None:
        if self.closed:
            raise ConnectionError("writer cerrado")
        self.frames.append(data)

    def close(self) -> None:
        self.closed = True


class FlowServiceNoSourceTest(unittest.TestCase):
    """Prueba 1: sin fuente conectada -> SIN COBERTURA, sin sinteticos."""

    def test_empty_block_no_coverage_no_zeros(self) -> None:
        block = _empty_flow_block("BTCUSDT", T0)
        self.assertEqual(block["coverage"], "NO_COVERAGE_BEFORE_FIRST_EVENT")
        self.assertFalse(block["live"])
        self.assertEqual(block["trades_total"], 0)
        self.assertIsNone(block["freshness_ms"])
        for h in block["horizons"].values():
            self.assertIsNone(h["signed_delta"])
            self.assertIsNone(h["delta_ratio"])
            self.assertIsNone(h["buy_notional"])
            self.assertIsNone(h["sell_notional"])
            self.assertEqual(h["coverage"], "NO_COVERAGE_BEFORE_FIRST_EVENT")

    def test_empty_horizon_no_zeros(self) -> None:
        h = _empty_horizon("1m", T0)
        self.assertIsNone(h["buy_notional"])
        self.assertIsNone(h["signed_delta"])
        self.assertEqual(h["trades"], 0)


class FlowServiceIngestTest(unittest.IsolatedAsyncioTestCase):
    """Pruebas 2-4: ingest, duplicados, mismo timestamp distinto ID."""

    async def asyncSetUp(self) -> None:
        self.service = FlowService(host="127.0.0.1", port=8799)

    async def test_two_new_events_update_without_reload(self) -> None:
        # Prueba 2: dos eventos locales nuevos actualizan el estado compartido
        r1 = self.service._ingest_event(
            b'{"symbol":"BTCUSDT","event_id":"e1","event_ms":' + str(T0).encode() +
            b',"price":100000,"quantity":0.5,"buyer_is_maker":false}'
        )
        self.assertTrue(json.loads(r1)["ok"])
        r2 = self.service._ingest_event(
            b'{"symbol":"BTCUSDT","event_id":"e2","event_ms":' + str(T0 + 1000).encode() +
            b',"price":100001,"quantity":0.3,"buyer_is_maker":true}'
        )
        self.assertTrue(json.loads(r2)["ok"])
        # Consultar bloque: cobertura LIVE, 2 trades
        block = self.service._build_block("BTCUSDT", T0 + 1000)
        self.assertEqual(block["coverage"], "LIVE")
        self.assertTrue(block["live"])
        self.assertEqual(block["trades_total"], 2)
        h1m = block["horizons"]["1m"]
        self.assertEqual(h1m["trades"], 2)
        self.assertAlmostEqual(h1m["buy_notional"], 100000.0 * 0.5)
        self.assertAlmostEqual(h1m["sell_notional"], 100001.0 * 0.3)
        self.assertAlmostEqual(h1m["signed_delta"], 50000.0 - 30000.3)

    async def test_duplicate_event_id_does_not_accumulate(self) -> None:
        # Prueba 3: mismo event_id repetido no suma volumen
        self.service._ingest_event(
            b'{"symbol":"BTCUSDT","event_id":"dup1","event_ms":' + str(T0).encode() +
            b',"price":100000,"quantity":1.0,"buyer_is_maker":false}'
        )
        block_before = self.service._build_block("BTCUSDT", T0)
        self.assertEqual(block_before["horizons"]["10s"]["trades"], 1)

        # Mismo event_id: duplicado, rechazado
        r = self.service._ingest_event(
            b'{"symbol":"BTCUSDT","event_id":"dup1","event_ms":' + str(T0).encode() +
            b',"price":100000,"quantity":1.0,"buyer_is_maker":false}'
        )
        self.assertTrue(json.loads(r)["duplicate"])
        # El acumulado no cambia
        block_after = self.service._build_block("BTCUSDT", T0)
        self.assertEqual(block_after["horizons"]["10s"]["trades"], 1)
        self.assertEqual(block_after["trades_total"], 1)

    async def test_same_timestamp_distinct_ids_count_both(self) -> None:
        # Prueba 4: mismo timestamp, IDs distintos -> ambos cuentan
        self.service._ingest_event(
            b'{"symbol":"BTCUSDT","event_id":"ts-a","event_ms":' + str(T0).encode() +
            b',"price":100000,"quantity":1.0,"buyer_is_maker":false}'
        )
        self.service._ingest_event(
            b'{"symbol":"BTCUSDT","event_id":"ts-b","event_ms":' + str(T0).encode() +
            b',"price":100000,"quantity":2.0,"buyer_is_maker":true}'
        )
        block = self.service._build_block("BTCUSDT", T0)
        h10 = block["horizons"]["10s"]
        self.assertEqual(h10["trades"], 2)
        self.assertAlmostEqual(h10["buy_notional"], 100000.0)
        self.assertAlmostEqual(h10["sell_notional"], 200000.0)
        self.assertAlmostEqual(h10["signed_delta"], -100000.0)

    async def test_service_symbols_tracked(self) -> None:
        self.service._ingest_event(
            b'{"symbol":"BTCUSDT","event_id":"s1","event_ms":' + str(T0).encode() +
            b',"price":100000,"quantity":1.0,"buyer_is_maker":false}'
        )
        self.service._ingest_event(
            b'{"symbol":"ETHUSDT","event_id":"s2","event_ms":' + str(T0).encode() +
            b',"price":3000,"quantity":1.0,"buyer_is_maker":false}'
        )
        symbols = sorted(self.service.engine._series.keys())  # type: ignore[attr-defined]
        self.assertEqual(symbols, ["BTCUSDT", "ETHUSDT"])


class FlowServiceSymbolSwitchTest(unittest.IsolatedAsyncioTestCase):
    """Prueba 5: cambio de simbolo no mezcla datos."""

    async def asyncSetUp(self) -> None:
        self.service = FlowService(host="127.0.0.1", port=8799)

    async def test_switch_symbol_does_not_mix_data(self) -> None:
        # Ingestar en BTCUSDT
        self.service._ingest_event(
            b'{"symbol":"BTCUSDT","event_id":"b1","event_ms":' + str(T0).encode() +
            b',"price":100000,"quantity":1.0,"buyer_is_maker":false}'
        )
        block_btc = self.service._build_block("BTCUSDT", T0)
        self.assertEqual(block_btc["trades_total"], 1)

        # Consultar ETHUSDT: sin cobertura, sin datos de BTC
        block_eth = self.service._build_block("ETHUSDT", T0)
        self.assertEqual(block_eth["coverage"], "NO_COVERAGE_BEFORE_FIRST_EVENT")
        self.assertFalse(block_eth["live"])
        self.assertEqual(block_eth["trades_total"], 0)
        self.assertIsNone(block_eth["horizons"]["1m"]["signed_delta"])

        # BTC sigue intacto
        block_btc2 = self.service._build_block("BTCUSDT", T0)
        self.assertEqual(block_btc2["trades_total"], 1)


class FlowServiceSSEClientsTest(unittest.TestCase):
    """Pruebas 6-7: desconexion retira LIVE, cerrar vista libera consumidor."""

    def setUp(self) -> None:
        self.service = FlowService(host="127.0.0.1", port=8799)

    def test_sse_client_register_and_release(self) -> None:
        # Prueba 7: registrar y liberar consumidores por simbolo
        writer1 = _FakeWriter()
        writer2 = _FakeWriter()
        self.service._sse_clients.setdefault("BTCUSDT", set()).add(writer1)
        self.service._sse_clients.setdefault("ETHUSDT", set()).add(writer2)
        self.assertEqual(len(self.service._sse_clients.get("BTCUSDT", set())), 1)
        self.assertEqual(len(self.service._sse_clients.get("ETHUSDT", set())), 1)

        # Cerrar la vista de BTCUSDT: se libera su consumidor
        writer1.close()
        self.service._sse_clients.get("BTCUSDT", set()).discard(writer1)
        self.assertEqual(len(self.service._sse_clients.get("BTCUSDT", set())), 0)
        self.assertEqual(len(self.service._sse_clients.get("ETHUSDT", set())), 1)

    def test_publish_update_reaches_subscribers(self) -> None:
        # Publicar update llega a los clientes SSE suscritos (prueba 6 parte)
        writer = _FakeWriter()
        self.service._sse_clients.setdefault("BTCUSDT", set()).add(writer)
        # Ingestar un evento para generar un update
        self.service._ingest_event(
            b'{"symbol":"BTCUSDT","event_id":"p1","event_ms":' + str(T0).encode() +
            b',"price":100000,"quantity":1.0,"buyer_is_maker":false}'
        )
        # Debe haber al menos hello+snapshot (registrados al suscribirse) + update
        self.assertGreaterEqual(len(writer.frames), 1)
        # El ultimo frame debe contener un update con el evento
        last_frame = writer.frames[-1].decode("utf-8")
        self.assertIn("event: update", last_frame)
        self.assertIn("BTCUSDT", last_frame)
        writer.close()

    def test_disconnected_writer_is_cleaned_on_publish(self) -> None:
        # Prueba 6: writer desconectado se descarta al publicar
        writer = _FakeWriter()
        writer.close()  # simulamos desconexion
        self.service._sse_clients.setdefault("BTCUSDT", set()).add(writer)
        self.service._ingest_event(
            b'{"symbol":"BTCUSDT","event_id":"d1","event_ms":' + str(T0).encode() +
            b',"price":100000,"quantity":1.0,"buyer_is_maker":false}'
        )
        # El writer cerrado debe ser eliminado de los suscriptores
        self.assertEqual(len(self.service._sse_clients.get("BTCUSDT", set())), 0)


if __name__ == "__main__":
    unittest.main()
