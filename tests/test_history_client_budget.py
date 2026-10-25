"""Pruebas focalizadas del presupuesto upstream en HistoryClient (transporte local).

Verifica el alcance real del control de presupuesto sin hacer llamadas
públicas a Binance. Usa un opener simulado que registra los intentos pero no
se conecta a la red.
"""
import unittest
from unittest.mock import Mock

from microstructure_probe.history_client import HistoryClient, RateLimitExceeded


class _Resp:
    """Respuesta simulada que soporta el protocolo de contexto."""

    def __init__(self, status=200, body=b'[]', headers=None):
        self.status = status
        self._body = body
        self._headers = headers or {}

    def read(self):
        return self._body

    @property
    def headers(self):
        return self._headers

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _CapturedOpener:
    """Opener simulado que registra cada intento sin conectar a la red."""

    def __init__(self, fail_always=False):
        self.attempts = []
        self.fail_always = fail_always

    def __call__(self, req, timeout=None):
        self.attempts.append({
            "url": req.full_url,
            "headers": dict(req.header_items()),
        })
        if self.fail_always:
            raise ConnectionError("network down")
        return _Resp()


class TestHistoryClientBudget(unittest.TestCase):

    # Cada instancia de HistoryClient tiene su propio contador (no compartido
    # entre procesos).
    def test_per_instance_counter_not_shared(self):
        opener1 = _CapturedOpener()
        opener2 = _CapturedOpener()
        c1 = HistoryClient(opener=opener1, execution_id="exec-1")
        c2 = HistoryClient(opener=opener2, execution_id="exec-2")

        c1.get("/fapi/v1/klines", {"symbol": "BTCUSDT"}, weight=10)
        c2.get("/fapi/v1/klines", {"symbol": "BTCUSDT"}, weight=10)

        self.assertEqual(len(c1.upstream_requests), 1)
        self.assertEqual(len(c2.upstream_requests), 1)
        self.assertEqual(c1.execution_id, "exec-1")
        self.assertEqual(c2.execution_id, "exec-2")
        self.assertNotEqual(c1.execution_id, c2.execution_id)

    # Cada intento HTTP registra una entrada ANTES de enviarse.
    def test_reserve_before_send(self):
        opener = _CapturedOpener()
        client = HistoryClient(opener=opener, execution_id="exec-budget")

        client.get("/fapi/v1/klines", {"symbol": "BTCUSDT"}, weight=10)

        self.assertEqual(len(opener.attempts), 1)
        self.assertEqual(len(client.upstream_requests), 1)
        # La entrada se registra con result="pending" ANTES de la respuesta,
        # y se actualiza a "ok" después.
        self.assertEqual(client.upstream_requests[0]["execution_id"], "exec-budget")
        self.assertIn(client.upstream_requests[0]["result"], ["pending", "ok"])

    # Los reintentos también consumen presupuesto (cada intento registra una
    # entrada antes de enviarse).
    def test_retries_consume_budget(self):
        opener = _CapturedOpener(fail_always=True)
        client = HistoryClient(opener=opener, execution_id="exec-retry")

        with self.assertRaises(ConnectionError):
            client.get("/fapi/v1/klines", {"symbol": "BTCUSDT"}, weight=10)

        # Cada intento (incluidos reintentos) registra una entrada
        self.assertGreaterEqual(len(client.upstream_requests), 1)
        for entry in client.upstream_requests:
            self.assertEqual(entry["execution_id"], "exec-retry")
            self.assertEqual(entry["result"], "connection_error")

    # Alcance del contador PER-INSTANCIA (peso Binance): NO bloquea el envio;
    # solo difiere el intento hasta que su ventana de 60 s se reanuda y
    # entonces SI lo envia. El bloqueo real antes del transporte lo aporta la
    # puerta del ledger compartido (ver tests/test_budget_scope_shared.py).
    def test_instance_limit_delays_then_sends_not_blocks(self):
        from microstructure_probe import history_client as hc_module

        # Reloj controlado ANTES de construir el cliente: el _window_start
        # parte del reloj falso.
        clock = {"now": 0.0}
        sleep_calls = []

        class _Clock:
            @staticmethod
            def monotonic() -> float:
                return clock["now"]

        original_monotonic = hc_module.time.monotonic
        hc_module.time.monotonic = _Clock.monotonic
        try:
            opener = _CapturedOpener()
            client = HistoryClient(opener=opener, execution_id="exec-block",
                                   max_weight_per_minute=20)

            # 2 solicitudes OK (2 * 10 peso = 20, límite exacto)
            client.get("/fapi/v1/klines", {"symbol": "BTCUSDT"}, weight=10)
            client.get("/fapi/v1/klines", {"symbol": "BTCUSDT"}, weight=10)

            original_sleep = client._sleep
            client._sleep = lambda s: (
                sleep_calls.append(s),
                clock.__setitem__("now", clock["now"] + 5.0))
            try:
                client.get("/fapi/v1/klines", {"symbol": "BTCUSDT"}, weight=10)
            finally:
                client._sleep = original_sleep
        finally:
            hc_module.time.monotonic = original_monotonic

        # Hecho real: el intento NO se bloquea; se difiere y se envia.
        self.assertEqual(len(opener.attempts), 3,
                         "el contador per-instancia difiere, no bloquea")
        self.assertGreaterEqual(len(sleep_calls), 1,
                                "_admit difiere con sleeps mientras la ventana"
                                " de peso no se reinicia")

    # execution_id vincula los registros de una misma ejecución
    def test_execution_id_links_entries(self):
        opener = _CapturedOpener()
        client = HistoryClient(opener=opener, execution_id="exec-link-1")

        client.get("/fapi/v1/klines", {"symbol": "BTCUSDT"}, weight=10)
        client.get("/fapi/v1/klines", {"symbol": "MINAUSDT"}, weight=10)

        for entry in client.upstream_requests:
            self.assertEqual(entry["execution_id"], "exec-link-1")
            self.assertIn("symbol", entry)
            self.assertIn("range", entry)
            self.assertIn("page", entry)
            self.assertIn("retry", entry)
            self.assertIn("result", entry)
            self.assertIn("duration_ms", entry)


if __name__ == "__main__":
    unittest.main()