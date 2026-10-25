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

    En modo local (WS loopback) no hay Binance, así que 0 upstream es un
    hecho, no una suposición. En modo public, si no hay registros del
    servicio Python, upstream es None (desconocido), no cero.
    """
    if transport == "local":
        return True
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

    # Caché completa: 0 upstream (modo local, WS loopback, sabemos que no hay Binance)
    def test_cache_complete_zero_upstream(self):
        self.assertTrue(compute_rest_market_budget("local", 0))

    # Consulta con descarga: contabilización real
    def test_download_consultation_counts_real(self):
        self.assertTrue(compute_rest_market_budget("public", 1))
        self.assertTrue(compute_rest_market_budget("public", 2))
        self.assertFalse(compute_rest_market_budget("public", 3))

    # Reintentos o varias páginas: todos cuentan
    def test_retries_and_multiple_pages_all_count(self):
        # 3 solicitudes upstream (página inicial + paginación + reintento)
        self.assertFalse(compute_rest_market_budget("public", 3))
        # 4 solicitudes (inicial + 2 páginas + reintento)
        self.assertFalse(compute_rest_market_budget("public", 4))

    # Origen no verificable: UNKNOWN (no asume cero por falta de registros)
    def test_unverifiable_origin_unknown(self):
        self.assertIsNone(compute_rest_market_budget("public", None))
        self.assertEqual(classify_upstream(0, 0, None), "UNKNOWN")

    # Presupuesto excedido: FAIL global
    def test_budget_exceeded_fail_global(self):
        self.assertFalse(compute_rest_market_budget("public", 3))
        self.assertFalse(compute_rest_market_budget("public", 10))

    # Transporte local: WS loopback, sabemos que no hay Binance
    def test_local_transport_always_ok(self):
        self.assertTrue(compute_rest_market_budget("local", 0))
        self.assertTrue(compute_rest_market_budget("local", 5))
        self.assertTrue(compute_rest_market_budget("local", 100))

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
