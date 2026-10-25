"""Regresiones locales del presupuesto REST (market-stream acceptance).

Prueban la lógica de presupuesto sin arrancar servicio ni navegador:
- caché completa: 0 upstream → OK
- consulta con descarga: contabilización real
- reintentos o varias páginas: todos cuentan
- origen no verificable: UNKNOWN (no asume cero por falta de registros)
- presupuesto excedido: FAIL global
"""
import unittest


def compute_rest_market_budget(transport: str,
                               upstream_binance_requests: int | None) -> bool | None:
    """Réplica de la lógica de presupuesto del arnés.

    En modo local (WS loopback) no hay Binance. upstream=0 es un hecho
    (caché completa). upstream=None es desconocido (no hay registros).
    En modo public, upstream=None también es UNKNOWN.
    """
    if upstream_binance_requests is None:
        return None
    return upstream_binance_requests <= 2


def classify_upstream(bff_market_requests: int,
                      cache_reads: int,
                      upstream_binance_requests: int | None) -> str:
    """Clasifica el origen de las solicitudes de velas."""
    if upstream_binance_requests is None:
        return "UNKNOWN"
    if upstream_binance_requests > 2:
        return "EXCEEDED"
    return "OK"


class TestRestBudget(unittest.TestCase):

    # Caché completa: 0 upstream → OK (modo local y public)
    def test_cache_complete_zero_upstream(self):
        self.assertTrue(compute_rest_market_budget("local", 0))
        self.assertTrue(compute_rest_market_budget("public", 0))

    # Consulta con descarga: contabilización real
    def test_download_consultation_counts_real(self):
        self.assertTrue(compute_rest_market_budget("public", 1))
        self.assertTrue(compute_rest_market_budget("public", 2))
        self.assertFalse(compute_rest_market_budget("public", 3))

    # Reintentos o varias páginas: todos cuentan
    def test_retries_and_multiple_pages_all_count(self):
        self.assertFalse(compute_rest_market_budget("public", 3))
        self.assertFalse(compute_rest_market_budget("public", 4))

    # Origen no verificable: UNKNOWN (no asume cero por falta de registros)
    def test_unverifiable_origin_unknown(self):
        self.assertIsNone(compute_rest_market_budget("public", None))
        self.assertEqual(classify_upstream(0, 0, None), "UNKNOWN")

    # Presupuesto excedido: FAIL global
    def test_budget_exceeded_fail_global(self):
        self.assertFalse(compute_rest_market_budget("public", 3))
        self.assertFalse(compute_rest_market_budget("public", 10))

    # Transporte local: caché completa = 0 upstream attempts
    def test_local_cache_zero_upstream(self):
        self.assertTrue(compute_rest_market_budget("local", 0))

    # Transporte local: descarga = 1 upstream attempt
    def test_local_download_one_upstream(self):
        self.assertTrue(compute_rest_market_budget("local", 1))

    # Transporte local: reintentos contabilizados (2 upstream = OK, 3 = EXCEEDED)
    def test_local_retries_counted(self):
        self.assertTrue(compute_rest_market_budget("local", 2))
        self.assertFalse(compute_rest_market_budget("local", 3))

    # Transporte local: tercera solicitud bloqueada (3 = FAIL)
    def test_local_third_blocked(self):
        self.assertFalse(compute_rest_market_budget("local", 3))
        self.assertFalse(compute_rest_market_budget("local", 4))

    # Transporte local: evidencia ausente = UNKNOWN
    def test_local_evidence_absent_unknown(self):
        self.assertIsNone(compute_rest_market_budget("local", None))
        self.assertEqual(classify_upstream(0, 0, None), "UNKNOWN")

    # Tres métricas distintas: BFF vs caché vs upstream
    def test_three_distinct_metrics(self):
        # 3 llamadas al BFF, 2 desde caché, 0 upstream → OK
        self.assertEqual(classify_upstream(3, 2, 0), "OK")
        # 1 llamada al BFF, 0 desde caché, 1 upstream → OK
        self.assertEqual(classify_upstream(1, 0, 1), "OK")
        # 1 llamada al BFF, 0 desde caché, 3 upstream → EXCEEDED
        self.assertEqual(classify_upstream(1, 0, 3), "EXCEEDED")
        # upstream desconocido → UNKNOWN, sin importar BFF o caché
        self.assertEqual(classify_upstream(0, 0, None), "UNKNOWN")
        self.assertEqual(classify_upstream(3, 2, None), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()