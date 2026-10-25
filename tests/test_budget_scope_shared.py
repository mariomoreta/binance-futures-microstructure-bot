"""Alcance del presupuesto REST compartido: reserva por intento ANTES del envio.

Sin Binance: transporte local (servidor 127.0.0.1 temporario), procesos reales
del CLI ``scripts/market_explorer.py`` y una cache aislada temporaria.

Verifica y documenta:
  1. El contador vive en ``market_fetch_ledger`` (SQLite) y es COMPARTIDO
     entre procesos que apuntan a la misma cache; la reserva es
     transaccional (BEGIN IMMEDIATE), no un registro de postenvio.
  2. Cada intento HTTP (incluidos reintentos y paginas) reserva 1 cupo
     justo antes del transporte; el intento denegado muere SIN abrir
     conexion y queda auditado con requests=0 (no consume).
  3. Las filas persisten tras la terminacion de cada proceso y quedan
     vinculadas a execution_id, lo que permite reconstruir el consumo.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from microstructure_probe.history_client import (  # noqa: E402
    HistoryClient,
    UpstreamBudgetExceeded,
)
from microstructure_probe.market_cache import MarketCache  # noqa: E402
from microstructure_probe.market_explorer import LedgerAttemptGate  # noqa: E402
import rest_budget_scope_demo as demo  # noqa: E402


class _Resp:
    """Respuesta local que soporta el protocolo de contexto."""

    def __init__(self, body=b'[]'):
        self.status = 200
        self._body = body

    def read(self):
        return self._body

    @property
    def headers(self):
        return {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _ScriptedOpener:
    """Opener que nunca abre socket y puede fallar segun guion (500)."""

    def __init__(self, script=None):
        self.attempts = []
        self.script = script or {}

    def __call__(self, req, timeout=None):
        index = len(self.attempts)
        self.attempts.append(req.full_url)
        if index in self.script:
            raise urllib.error.HTTPError(req.full_url, 500, "server error",
                                         None, None)
        return _Resp()

    def set_500_on_attempt(self, index):
        self.script[index] = "500"


class TestGateBeforeSendInProcess(unittest.TestCase):
    """La puerta actua por intento, antes del transporte, sin procesos."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="budget-gate-")
        self.cache = MarketCache(Path(self._tmp.name) / "cache.db")
        self.cache.init_db()

    def tearDown(self):
        self._tmp.cleanup()

    def _client(self, opener, execution_id, max_requests=2):
        return HistoryClient(
            opener=opener, execution_id=execution_id,
            attempt_gate=LedgerAttemptGate(self.cache, execution_id,
                                           max_requests=max_requests))

    def test_granted_attempts_recorded_and_consumed(self):
        opener = _ScriptedOpener()
        client = self._client(opener, "gate-1")
        client.get("/fapi/v1/klines", {"symbol": "GT1USDT"}, 10)
        client.get("/fapi/v1/klines", {"symbol": "GT1USDT"}, 10)
        self.assertEqual(len(opener.attempts), 2)
        rows = self.cache.fetch_rows_by_execution("gate-1")
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["requests"], 1)
            self.assertEqual(row["status"], "ok")
            self.assertEqual(row["execution_id"], "gate-1")
            detail = json.loads(row["detail"])
            self.assertTrue(detail["endpoint"].startswith(
                "https://fapi.binance.com/fapi/v1/klines"))
            self.assertEqual(detail["symbol"], "GT1USDT")
        self.assertEqual(self.cache.requests_in_window(
            int(time.time() * 1000)), 2)

    def test_third_attempt_blocked_before_transport(self):
        opener = _ScriptedOpener()
        client = self._client(opener, "gate-block", max_requests=2)
        client.get("/fapi/v1/klines", {"symbol": "GBUSDT"}, 10)
        client.get("/fapi/v1/klines", {"symbol": "GBUSDT"}, 10)
        self.assertEqual(len(opener.attempts), 2)

        with self.assertRaises(UpstreamBudgetExceeded):
            client.get("/fapi/v1/klines", {"symbol": "GBUSDT"}, 10)

        # El opener NO recibio el tercer intento: no hubo transporte.
        self.assertEqual(len(opener.attempts), 2)
        # Las filas concedidas siguen en 2 cupos; el intento denegado queda
        # auditado en el ledger con requests=0 (no consume).
        granted = [r for r in self.cache.fetch_rows_by_execution("gate-block")
                   if r["requests"] == 1]
        self.assertEqual(len(granted), 2)
        blocked = [r for r in self.cache.fetch_rows_by_execution("gate-block")
                   if r["requests"] == 0 and r["status"] == "budget_blocked"]
        self.assertTrue(blocked)

    def test_retry_consumes_a_second_reservation(self):
        opener = _ScriptedOpener()
        opener.set_500_on_attempt(0)
        client = self._client(opener, "gate-retry", max_requests=2)
        payload, _ = client.get("/fapi/v1/klines", {"symbol": "GRUSDT"}, 10)
        self.assertIsNotNone(payload)
        self.assertEqual(len(opener.attempts), 2)  # 500 + reintento OK
        rows = self.cache.fetch_rows_by_execution("gate-retry")
        self.assertEqual([r["status"] for r in rows],
                         ["http_5xx_retry_1", "ok"])
        self.assertEqual(self.cache.requests_in_window(
            int(time.time() * 1000)), 2)

    def test_retry_blocked_when_no_reservation_left(self):
        opener = _ScriptedOpener()
        opener.set_500_on_attempt(0)
        client = self._client(opener, "gate-retry-block", max_requests=1)
        with self.assertRaises(UpstreamBudgetExceeded):
            client.get("/fapi/v1/klines", {"symbol": "GRBUSDT"}, 10)
        # Solo el primer intento llego al transporte.
        self.assertEqual(len(opener.attempts), 1)
        rows = self.cache.fetch_rows_by_execution("gate-retry-block")
        self.assertEqual([r["requests"] for r in rows], [1, 0])
        self.assertEqual(rows[0]["status"], "http_5xx_retry_1")
        self.assertEqual(rows[1]["status"], "budget_blocked")


class TestConcurrentReservationFairness(unittest.TestCase):
    """Tres contendientes, limite=2: BEGIN IMMEDIATE serializa la reserva.

    Equivalente a procesos concurrentes apuntando a la misma DB (SQLite
    serializa writers con BEGIN IMMEDIATE independiente del proceso); los
    procesos del CLI reales se demuestran en TestSharedBudgetAcrossProcesses.
    """

    def test_three_racers_limit_two_two_granted_one_denied(self):
        import threading
        import time as time_module

        with tempfile.TemporaryDirectory(prefix="budget-race-") as tmp:
            cache = MarketCache(Path(tmp) / "race.db")
            cache.init_db()
            hits_lock = threading.Lock()
            opener_state = {"hits": 0}

            def slow_opener(req, timeout=None):
                with hits_lock:
                    opener_state["hits"] += 1
                time_module.sleep(0.15)  # intento "en vuelo" durante la carrera
                return _Resp()

            start = threading.Barrier(3)
            outcomes: list = []

            def racer(i):
                client = HistoryClient(
                    opener=slow_opener, execution_id=f"race-{i}",
                    attempt_gate=LedgerAttemptGate(
                        cache, f"race-{i}", max_requests=2))
                start.wait()
                try:
                    client.get("/fapi/v1/klines",
                               {"symbol": f"RC{i}USDT"}, 10)
                    outcomes.append(("ok", i))
                except UpstreamBudgetExceeded:
                    outcomes.append(("blocked", i))

            threads = [threading.Thread(target=racer, args=(i,)) for i in range(3)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)

            granted = sorted(i for status, i in outcomes if status == "ok")
            denied = [i for status, i in outcomes if status == "blocked"]
            self.assertEqual(len(granted), 2, outcomes)
            self.assertEqual(len(denied), 1, outcomes)
            # Solo 2 intentos llegaron al transporte abierto.
            self.assertEqual(opener_state["hits"], 2)
            # El ledger reconstruye: 2 cupos concedidos, denegacion sin consumo.
            rows = cache.fetch_ledger(limit=50)
            requests = sum(int(r["requests"] or 0) for r in rows)
            self.assertEqual(requests, 2)
            self.assertTrue(all(int(r["requests"] or 0) == 1
                                for r in rows if r["status"] != "budget_blocked"))


class TestSharedBudgetAcrossProcesses(unittest.TestCase):
    """Demostracion con procesos REALES del CLI + transporte LOCAL."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="budget-scope-t-")
        cls._server = demo._start_server(fail_first_request=False)
        cls._api = f"http://127.0.0.1:{cls._server.server_port}"
        cls._cache = Path(cls._tmp.name) / "shared.db"
        # Dos procesos CONCURRENTES comparten limite=2.
        bg_p1 = demo._run_cli_bg(cls._cache, "scope-P1", cls._api)
        bg_p2 = demo._run_cli_bg(cls._cache, "scope-P2", cls._api)
        cls._r1 = demo._wait_cli(bg_p1)
        cls._r2 = demo._wait_cli(bg_p2)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        cls._server.server_close()
        cls._tmp.cleanup()

    def _rows(self, execution_id):
        cache = MarketCache(self._cache)
        cache.init_db()
        return cache.fetch_rows_by_execution(execution_id)

    def test_a_both_processes_granted_one_cupo_each(self):
        for name, result in (("P1", self._r1), ("P2", self._r2)):
            payload = result["output"]
            self.assertTrue(payload.get("ok"), f"{name}: {payload}")
            self.assertEqual(payload["data"]["fetch"]["status"], "ok")
            budget = payload["data"]["budget"]
            self.assertEqual(budget["max_requests_per_window"], 2)
            self.assertEqual(budget["enforcement"],
                             "ledger_shared_reserve_before_send")

    def test_b_upstream_saw_exactly_two_requests(self):
        # Dos procesos, limite=2 compartido: el transporte local vio Solo 2.
        self.assertEqual(len(self._server.hits), 2)

    def test_c_third_attempt_blocked_before_transport(self):
        # P3 corre despues: la ventana compartida ya esta en 2/2, asi que el
        # pre chequeo (antes de planificar) la bloquea SIN transporte.
        p3 = demo._run_cli(self._cache, "scope-P3", self._api)
        payload = p3["output"]
        self.assertTrue(payload.get("ok"), payload)
        fetch = payload["data"]["fetch"]
        self.assertEqual(fetch["status"], "budget_exhausted")
        self.assertEqual(fetch["error"], "RATE_BUDGET_EXHAUSTED")
        # El transporte local no recibio NADA nuevo.
        self.assertEqual(len(self._server.hits), 2)
        # El ledger no tenia cupo para P3: cero filas concedidas.
        self.assertTrue(
            all(r["requests"] == 0 for r in self._rows("scope-P3")))

    def test_d_records_survive_process_exit_and_reconstruct_consumption(self):
        # Los procesos P1/P2/P3 ya TERMINARON; el ledger persiste y permite
        # reconstruir cuantos cupos consumio cada execution_id.
        cache = MarketCache(self._cache)
        cache.init_db()
        rebuilt = {}
        for eid in ("scope-P1", "scope-P2", "scope-P3"):
            rebuilt[eid] = cache.fetch_rows_by_execution(eid)
        # P1/P2: una fila ok cada uno, 1 cupo, con endpoint/resultado reales.
        for eid in ("scope-P1", "scope-P2"):
            rows = rebuilt[eid]
            self.assertTrue(rows, f"sin filas para {eid}")
            for row in rows:
                self.assertEqual(row["execution_id"], eid)
            ok_rows = [r for r in rows if r["status"] == "ok"]
            self.assertEqual(len(ok_rows), 1, eid)
            self.assertEqual(ok_rows[0]["requests"], 1)
            detail = json.loads(ok_rows[0]["detail"])
            self.assertIn("/fapi/v1/klines", detail["endpoint"])
            self.assertIsNotNone(detail["duration_ms"])
        # P3 no dejo ningun cupo concedido (bloqueado antes del transporte).
        self.assertTrue(
            all(r["requests"] == 0 for r in rebuilt["scope-P3"]))
        # El consumo reconstruido de la ventana suma exactamente el limite
        # que recibio el CLI (--max-upstream 2; el default persistente es 30).
        usage = cache.window_usage()
        self.assertEqual(usage["used_in_window"], 2)

    def test_e_retry_processes_consume_budget_too(self):
        # Escenario aparte con servidor que falla el 1er intento (HTTP 500).
        server = demo._start_server(fail_first_request=True)
        try:
            api = f"http://127.0.0.1:{server.server_port}"
            cache_b = Path(self._tmp.name) / "retry.db"
            result = demo._run_cli(cache_b, "scope-R1", api)
            payload = result["output"]
            self.assertTrue(payload.get("ok"), payload)
            self.assertEqual(payload["data"]["fetch"]["status"], "ok")
            # El upstream local vio exactamente 2 intentos (500 + reintento).
            self.assertEqual(len(server.hits), 2)
            rows = MarketCache(cache_b).fetch_rows_by_execution("scope-R1")
            rows = [r for r in rows if r["requests"] > 0]
            self.assertEqual([r["status"] for r in rows],
                             ["http_5xx_retry_1", "ok"])
            # Con los 2 cupos agotados, un tercer proceso queda bloqueado
            # ANTES del transporte (aqui por el pre-chequeo de la ventana
            # compartida: no hay cupos, no hay enlace).
            blocked = demo._run_cli(cache_b, "scope-R2", api)
            blocked_status = blocked["output"]["data"]["fetch"]["status"]
            self.assertIn(blocked_status, ("budget_exhausted", "budget_blocked"),
                          blocked)
            # En ambos caminos de bloqueo NO hay transporte adicional.
            self.assertEqual(len(server.hits), 2)
            rows_r2 = MarketCache(cache_b).fetch_rows_by_execution("scope-R2")
            self.assertTrue(
                all(int(r["requests"] or 0) == 0 for r in rows_r2))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
