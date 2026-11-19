"""Pruebas puras del registro acotado de cotizaciones (sin red, sin piloto).

Criterios congelados: docs/evidence/cotizaciones-local-20261119/PREDECLARACION.md
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import quote_tape as qt  # noqa: E402


class Store:
    """Sustituto minimo de PilotStore: solo cuenta escrituras."""

    def __init__(self, *, admitir: bool = True) -> None:
        self.rows = []
        self.admitir = admitir

    def write(self, row):
        if not self.admitir:
            return False
        self.rows.append(dict(row))
        return True


def features(bid=100.0, ask=100.2, qbid=10.0, qask=10.0, **kw):
    out = {
        "best_bid": bid, "best_ask": ask, "top_bid_qty": qbid,
        "top_ask_qty": qask, "mid": (bid + ask) / 2.0,
        "spread_bps": (ask - bid) / ((bid + ask) / 2.0) * 10_000.0,
        "crossed": bool(kw.get("crossed", bid >= ask)),
        "bid_levels": kw.get("bid_levels", 2),
        "ask_levels": kw.get("ask_levels", 2),
    }
    return out


def tape(rows, path: Path) -> Path:
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n"
                            for r in rows), encoding="utf-8")
    return path


def episodio(rows, lado="LONG", size=1.0, entrada=1_000_000,
             salida=1_400_000, **kw):
    return qt.evaluar_episodio("AAAUSDT", entrada, salida, lado, size,
                               rows, **kw)


class TestRegistro(unittest.TestCase):
    def test_desactivado_no_define_archivo(self):
        st = qt.status_desactivado()
        self.assertFalse(st["enabled"])
        self.assertEqual(st["rows_written"], 0)

    def test_primera_fila_por_segundo_de_recepcion(self):
        store = Store()
        t = qt.QuoteTape(store, "run-a", cadencia_ms=1_000)
        f = features()
        self.assertTrue(t.record_quote("AAAUSDT", 1_000_000, 1_000_000, f))
        self.assertFalse(t.record_quote("AAAUSDT", 1_000_500, 1_000_500, f))
        self.assertTrue(t.record_quote("AAAUSDT", 1_001_000, 1_001_000, f))
        self.assertEqual(t.quotes_written, 2)
        self.assertEqual(t.duplicated_seconds, 1)
        self.assertEqual([r["received_ms"] for r in store.rows],
                         [1_000_000, 1_001_000])

    def test_fila_contiene_campos_congelados(self):
        store = Store()
        t = qt.QuoteTape(store, "run-a")
        t.record_quote("aaaUSDT", 1_000_000, 999_000,
                       features(), degraded=False, gap=False)
        fila = store.rows[0]
        for campo in ("run_id", "symbol", "event_ms", "received_ms", "seq",
                      "best_bid", "best_ask", "bid_qty", "ask_qty",
                      "degraded", "gap", "crossed", "valida",
                      "motivos_invalidez", "cadencia_ms"):
            self.assertIn(campo, fila)
        self.assertEqual(fila["symbol"], "AAAUSDT")
        self.assertEqual(fila["run_id"], "run-a")
        self.assertEqual(fila["bid_qty"], 10.0)
        self.assertTrue(fila["valida"])

    def test_cruzada_se_registra_como_invalida(self):
        store = Store()
        t = qt.QuoteTape(store, "run-a")
        t.record_quote("AAAUSDT", 1_000_000, 1_000_000,
                       features(bid=101.0, ask=100.0), crossed=True)
        self.assertFalse(store.rows[0]["valida"])
        self.assertIn("LIBRO_CRUZADO", store.rows[0]["motivos_invalidez"])

    def test_degradada_y_salto_de_secuencia(self):
        store = Store()
        t = qt.QuoteTape(store, "run-a")
        t.record_quote("AAAUSDT", 1_000_000, 1_000_000, features(),
                       degraded=True, gap=True)
        self.assertEqual(store.rows[0]["motivos_invalidez"],
                         ["SALTO_SECUENCIA", "LIBRO_DEGRADADO"])

    def test_precio_cantidad_y_niveles_invalidos(self):
        store = Store()
        t = qt.QuoteTape(store, "run-a")
        t.record_quote("AAAUSDT", 1, 1, features(bid=0.0, qbid=0.0,
                                                  bid_levels=0))
        self.assertEqual(store.rows[0]["motivos_invalidez"],
                         ["PRECIO_NO_VALIDO", "CANTIDAD_NO_VALIDA",
                          "SIN_NIVELES"])

    def test_faltante_por_rotacion(self):
        store = Store()
        t = qt.QuoteTape(store, "run-a")
        self.assertTrue(t.record_missing("AAAUSDT", 1_200_000,
                                         "simbolo_fuera_de_seguimiento",
                                         "ciclo 2"))
        fila = store.rows[0]
        self.assertEqual(fila["kind"], "faltante")
        self.assertEqual(fila["motivo"], "simbolo_fuera_de_seguimiento")
        self.assertEqual(fila["detalle"], "ciclo 2")

    def test_tope_de_filas_y_fila_limite(self):
        store = Store()
        t = qt.QuoteTape(store, "run-a", max_rows=2)
        for segundo in (1_000_000, 1_001_000, 1_002_000, 1_003_000):
            t.record_quote("AAAUSDT", segundo, segundo, features())
        self.assertEqual(t.cap_reason, "limite_filas")
        self.assertTrue(t.cap_reached)
        self.assertEqual(t.quotes_written, 2)
        self.assertEqual(store.rows[-1]["kind"], "limite")
        self.assertEqual(sum(1 for r in store.rows
                             if r["kind"] == "cotizacion"), 2)

    def test_tope_de_bytes(self):
        store = Store()
        t = qt.QuoteTape(store, "run-a", max_bytes=1)
        t.record_quote("AAAUSDT", 1, 1, features())
        self.assertEqual(t.cap_reason, "limite_bytes")
        self.assertEqual(store.rows, [])

    def test_presupuesto_global_rechaza_escritura(self):
        store = Store(admitir=False)
        t = qt.QuoteTape(store, "run-a")
        self.assertFalse(t.record_quote("AAAUSDT", 1, 1, features()))
        self.assertEqual(t.cap_reason, "presupuesto_global")


class TestSeleccion(unittest.TestCase):
    def test_ultima_valida_ya_recibida(self):
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_000, "event_ms": 999_000, "seq": 1,
             "valida": True},
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_500, "event_ms": 999_500, "seq": 2,
             "valida": True},
        ]
        sel = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a")
        self.assertEqual(sel["cotizacion"]["seq"], 2)
        self.assertIsNone(sel["motivo"])

    def test_run_id_distinto_no_cuenta(self):
        filas = [{"kind": "cotizacion", "run_id": "b", "symbol": "AAAUSDT",
                  "received_ms": 999_000, "event_ms": 999_000, "seq": 1,
                  "valida": True}]
        sel = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a")
        self.assertEqual(sel["motivo"], "SIN_COTIZACION")

    def test_cotizacion_posterior_se_rechaza(self):
        filas = [{"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
                  "received_ms": 1_001_000, "event_ms": 1_001_000, "seq": 1,
                  "valida": True}]
        sel = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a")
        self.assertEqual(sel["motivo"], "COTIZACION_FUTURA")

    def test_evento_posterior_al_instante_se_rechaza(self):
        filas = [{"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
                  "received_ms": 999_999, "event_ms": 1_000_001, "seq": 1,
                  "valida": True}]
        sel = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a")
        self.assertEqual(sel["motivo"], "COTIZACION_FUTURA")

    def test_cotizacion_vieja_se_rechaza(self):
        filas = [{"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
                  "received_ms": 979_000, "event_ms": 979_000, "seq": 1,
                  "valida": True}]
        sel = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a")
        self.assertEqual(sel["motivo"], "COTIZACION_VIEJA")
        self.assertEqual(sel["rechazadas_viejas"], 1)

    def test_frontera_de_antiguedad_exacta(self):
        filas = [{"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
                  "received_ms": 995_000, "event_ms": 995_000, "seq": 1,
                  "valida": True}]
        sel = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a")
        self.assertIsNone(sel["motivo"])

    def test_calidad_invalida_devuelve_codigo(self):
        filas = [{"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
                  "received_ms": 999_000, "event_ms": 999_000, "seq": 1,
                  "valida": False,
                  "motivos_invalidez": ["SALTO_SECUENCIA"]}]
        sel = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a")
        self.assertEqual(sel["motivo"], "SALTO_SECUENCIA")

    def test_rotacion_devuelve_motivo_explicito(self):
        filas = [{"kind": "faltante", "run_id": "a", "symbol": "AAAUSDT",
                  "received_ms": 900_000, "event_ms": None, "seq": 1,
                  "motivo": "simbolo_fuera_de_seguimiento"}]
        sel = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a")
        self.assertEqual(sel["motivo"], "SIMBOLO_FUERA_DE_SEGUIMIENTO")

    def test_faltante_posterior_rompe_cobertura(self):
        """Una fila faltante (rotacion) despues de una cotizacion valida
        rompe la cobertura: no se retrocede a la cotizacion previa."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_000, "event_ms": 999_000, "seq": 1,
             "valida": True},
            {"kind": "faltante", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_500, "event_ms": None, "seq": 2,
             "motivo": "simbolo_fuera_de_seguimiento"},
        ]
        sel = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a")
        self.assertEqual(sel["motivo"], "SIMBOLO_FUERA_DE_SEGUIMIENTO")
        self.assertIsNone(sel["cotizacion"])

    def test_calidad_invalida_rompe_cobertura_y_valida_posterior_restaura(self):
        """Una cotizacion invalida rompe la cobertura; una valida posterior
        la restablece y se usa esa (no la previa a la invalidez)."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 998_000, "event_ms": 998_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_000, "event_ms": 999_000, "seq": 2,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": False,
             "motivos_invalidez": ["SALTO_SECUENCIA"]},
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_500, "event_ms": 999_500, "seq": 3,
             "best_bid": 101.0, "best_ask": 101.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 101.1, "valida": True},
        ]
        sel = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a")
        self.assertIsNone(sel["motivo"])
        self.assertEqual(sel["cotizacion"]["seq"], 3)

    def test_invalidacion_despues_de_T_no_altera_cotizacion_en_T(self):
        """Una invalidez ocurrida DESPUES de T no afecta la cotizacion valida
        en T (no se usan filas futuras)."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_000, "event_ms": 999_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 1_001_000, "event_ms": 1_001_000, "seq": 2,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": False,
             "motivos_invalidez": ["SALTO_SECUENCIA"]},
        ]
        sel = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a")
        self.assertIsNone(sel["motivo"])
        self.assertEqual(sel["cotizacion"]["seq"], 1)
        self.assertEqual(sel["rechazadas_posteriores"], 1)

    def test_invalidacion_dentro_del_mismo_segundo_rompe_cobertura(self):
        """Una cotizacion valida al inicio del segundo seguida de una
        invalidez dentro del mismo segundo: la cobertura se rompe en ese
        segundo (el muestreo 1 fila/segundo no la oculta)."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 1_000_000, "event_ms": 1_000_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 1_000_700, "event_ms": 1_000_700, "seq": 2,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": False,
             "motivos_invalidez": ["LIBRO_DEGRADADO"]},
        ]
        sel = qt.seleccionar("AAAUSDT", 1_000_900, filas, run_id="a")
        self.assertEqual(sel["motivo"], "LIBRO_DEGRADADO")
        self.assertIsNone(sel["cotizacion"])

    def test_cinta_agotada_distinguible_de_sin_cotizacion(self):
        """Una fila limite (cinta agotada) antes del instante se reporta como
        LIMITE_ALCANZADO, no como SIN_COTIZACION."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 998_000, "event_ms": 998_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
            {"kind": "limite", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_000, "event_ms": None, "seq": 2,
             "motivo": "limite_filas"},
        ]
        sel = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a")
        self.assertEqual(sel["motivo"], "LIMITE_ALCANZADO")
        self.assertIsNone(sel["cotizacion"])

    def test_rotacion_y_limite_mismo_ms_que_cotizacion(self):
        """Rotacion y limite en el mismo received_ms que una cotizacion valida.
        Orden: received_ms primero, desempate por seq. La rotacion (seq mayor)
        va despues de la cotizacion y rompe la cobertura."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 1_000_000, "event_ms": 1_000_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
            {"kind": "faltante", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 1_000_000, "event_ms": None, "seq": 2,
             "motivo": "simbolo_fuera_de_seguimiento"},
        ]
        # La cotizacion (seq=1) va antes de la rotacion (seq=2): cobertura rota.
        sel = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a")
        self.assertEqual(sel["motivo"], "SIMBOLO_FUERA_DE_SEGUIMIENTO")
        self.assertIsNone(sel["cotizacion"])

    def test_agotamiento_persistido_consulta_despues_del_corte(self):
        """Evidencia de agotamiento en artefacto persistido (fuera del JSONL):
        consulta despues del corte devuelve LIMITE_ALCANZADO."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 998_000, "event_ms": 998_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
        ]
        # No hay fila limite en el JSONL (no cabio), pero el artefacto
        # persistido dice que se agoto en 999_000.
        agotamiento = {"instante_ms": 999_000, "motivo": "limite_bytes"}

        # Consulta ANTES del corte: cotizacion valida.
        sel_antes = qt.seleccionar("AAAUSDT", 998_500, filas, run_id="a",
                                   agotamiento=agotamiento)
        self.assertIsNone(sel_antes["motivo"], sel_antes)
        self.assertEqual(sel_antes["cotizacion"]["seq"], 1)

        # Consulta DESPUES del corte: LIMITE_ALCANZADO.
        sel_despues = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a",
                                     agotamiento=agotamiento)
        self.assertEqual(sel_despues["motivo"], "LIMITE_ALCANZADO")
        self.assertIsNone(sel_despues["cotizacion"])
        self.assertEqual(sel_despues.get("agotamiento"), "limite_bytes")

    def test_agotamiento_sin_instante_cobertura_unknown(self):
        """Se sabe que se agoto pero no cuando, y no hay cotizacion valida
        para el instante consultado: cobertura UNKNOWN para el tramo."""
        filas = []
        agotamiento = {"instante_ms": None, "motivo": "limite_bytes"}

        sel = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a",
                             agotamiento=agotamiento)
        self.assertEqual(sel["motivo"], "COBERTURA_UNKNOWN")
        self.assertIsNone(sel["cotizacion"])
        self.assertEqual(sel.get("agotamiento"), "limite_bytes")

    def test_invalidez_posterior_a_T_no_altera_entrada(self):
        """Invalidez ocurrida DESPUES de T no afecta la cotizacion valida en T."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_000, "event_ms": 999_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 1_001_000, "event_ms": 1_001_000, "seq": 2,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": False,
             "motivos_invalidez": ["SALTO_SECUENCIA"]},
        ]
        sel = qt.seleccionar("AAAUSDT", 1_000_000, filas, run_id="a")
        self.assertIsNone(sel["motivo"])
        self.assertEqual(sel["cotizacion"]["seq"], 1)
        self.assertEqual(sel["rechazadas_posteriores"], 1)

    def test_evaluar_episodio_con_agotamiento_entrada_valida_salida_rechazada(self):
        """evaluar_episodio con agotamiento: entrada antes del corte se
        conserva, salida despues del corte se rechaza con LIMITE_ALCANZADO."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_000, "event_ms": 999_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
        ]
        # La cinta se agoto en 1_000_000 (despues de la entrada en 999_000,
        # pero antes de la salida en 1_500_000).
        agotamiento = {"instante_ms": 1_000_000, "motivo": "limite_bytes"}

        ev = qt.evaluar_episodio(
            "AAAUSDT", 999_000, 1_500_000, "LONG", qt.TAMANO_SIMULADO,
            filas, run_id="a", agotamiento=agotamiento)
        self.assertFalse(ev["evaluable"])
        # La entrada esta antes del corte: se conserva.
        self.assertIsNotNone(ev["fila_entrada"])
        self.assertEqual(ev["motivo_entrada"], None)
        # La salida esta despues del corte: rechazada.
        self.assertIsNone(ev["fila_salida"])
        self.assertEqual(ev["motivo_salida"], "LIMITE_ALCANZADO")
        self.assertTrue(ev["motivo"].startswith("SIN_COTIZACION_SALIDA:"),
                        ev)

    def test_evaluar_episodio_con_agotamiento_sin_instante_unknown(self):
        """evaluar_episodio con agotamiento sin instante conocido:
        COBERTURA_UNKNOWN para el tramo no acreditado."""
        # Sin filas: no hay cotizacion para ningun extremo.
        filas = []
        agotamiento = {"instante_ms": None, "motivo": "limite_bytes"}

        ev = qt.evaluar_episodio(
            "AAAUSDT", 999_000, 1_500_000, "LONG", qt.TAMANO_SIMULADO,
            filas, run_id="a", agotamiento=agotamiento)
        self.assertFalse(ev["evaluable"])
        # Sin filas y sin instante de agotamiento conocido: UNKNOWN para entrada.
        self.assertEqual(ev["motivo_entrada"], "COBERTURA_UNKNOWN")
        self.assertTrue(ev["motivo"].startswith("SIN_COTIZACION_ENTRADA:"),
                        ev)

    def test_evaluar_episodio_sin_agotamiento_evaluable(self):
        """evaluar_episodio sin agotamiento: entrada y salida son evaluables
        normalmente (regresion del comportamiento previo)."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_000, "event_ms": 999_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 1_500_000, "event_ms": 1_500_000, "seq": 2,
             "best_bid": 100.4, "best_ask": 100.6, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.5, "valida": True},
        ]

        ev = qt.evaluar_episodio(
            "AAAUSDT", 999_000, 1_500_000, "LONG", qt.TAMANO_SIMULADO,
            filas, run_id="a")
        self.assertTrue(ev["evaluable"], ev)
        self.assertEqual(ev["precio_entrada"], 100.2)
        self.assertEqual(ev["precio_salida"], 100.4)

    def _escribir_corrida(self, tmp: Path, filas, cinta: dict) -> Path:
        """Escribe resumen.json y cotizaciones_investigacion.jsonl en tmp."""
        (tmp / "resumen.json").write_text(
            json.dumps({"cotizaciones_investigacion": cinta},
                       ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8")
        (tmp / qt.NOMBRE_ARCHIVO).write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in filas),
            encoding="utf-8")
        return tmp

    def test_replay_desde_corrida_agotamiento_sin_hora_unknown(self):
        """Agotamiento sin instante verificable (cap_instante_ms ausente):
        replay devuelve COBERTURA_UNKNOWN aunque la cita siga fresca."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_000, "event_ms": 999_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._escribir_corrida(tmp, filas, {
                "run_id": "a", "cap_reached": True,
                "cap_instante_ms": None, "cap_reason": "limite_bytes",
            })
            ev = qt.replay_episodio_desde_corrida(
                tmp, "AAAUSDT", 999_000, 999_500, "LONG",
                qt.TAMANO_SIMULADO, run_id="a")
        self.assertFalse(ev["evaluable"])
        self.assertEqual(ev["motivo_entrada"], "COBERTURA_UNKNOWN")
        self.assertEqual(ev["motivo_salida"], "COBERTURA_UNKNOWN")
        self.assertTrue(ev["motivo"].startswith("SIN_COTIZACION_ENTRADA:"),
                        ev)

    def test_replay_desde_corrida_resumen_ausente_no_evaluable(self):
        """Resumen ausente: resultado explicito y no evaluable, sin asumir
        que la cinta nunca se agoto."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_000, "event_ms": 999_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # Solo el JSONL, sin resumen.json.
            (tmp / qt.NOMBRE_ARCHIVO).write_text(
                "".join(json.dumps(r, sort_keys=True) + "\n" for r in filas),
                encoding="utf-8")
            ev = qt.replay_episodio_desde_corrida(
                tmp, "AAAUSDT", 999_000, 999_500, "LONG",
                qt.TAMANO_SIMULADO, run_id="a")
        self.assertFalse(ev["evaluable"])
        self.assertEqual(ev["motivo"], "RESUMEN_AUSENTE")

    def test_replay_desde_corrida_raiz_no_es_objeto_no_evaluable(self):
        """Raiz del resumen en forma de lista (no objeto): no evaluable,
        sin lanzar excepcion."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_000, "event_ms": 999_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "resumen.json").write_text(
                "[1, 2, 3]", encoding="utf-8")
            (tmp / qt.NOMBRE_ARCHIVO).write_text(
                "".join(json.dumps(r, sort_keys=True) + "\n" for r in filas),
                encoding="utf-8")
            ev = qt.replay_episodio_desde_corrida(
                tmp, "AAAUSDT", 999_000, 999_500, "LONG",
                qt.TAMANO_SIMULADO, run_id="a")
        self.assertFalse(ev["evaluable"])
        self.assertEqual(ev["motivo"], "RESUMEN_AUSENTE")

    def test_replay_desde_corrida_run_id_resumen_faltante_no_evaluable(self):
        """run_id del resumen faltante: no evaluable, sin sustituirlo por
        el del llamador."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_000, "event_ms": 999_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._escribir_corrida(tmp, filas, {
                "cap_reached": False,  # sin run_id
            })
            ev = qt.replay_episodio_desde_corrida(
                tmp, "AAAUSDT", 999_000, 999_500, "LONG",
                qt.TAMANO_SIMULADO, run_id="a")
        self.assertFalse(ev["evaluable"])
        self.assertEqual(ev["motivo"], "RESUMEN_INVALIDO")

    def test_replay_desde_corrida_cap_reached_ausente_no_evaluable(self):
        """cap_reached ausente: no evaluable (no se interpreta como
        ausencia de agotamiento)."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_000, "event_ms": 999_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._escribir_corrida(tmp, filas, {
                "run_id": "a",
                # sin cap_reached
            })
            ev = qt.replay_episodio_desde_corrida(
                tmp, "AAAUSDT", 999_000, 999_500, "LONG",
                qt.TAMANO_SIMULADO, run_id="a")
        self.assertFalse(ev["evaluable"])
        self.assertEqual(ev["motivo"], "RESUMEN_INVALIDO")

    def test_replay_desde_corrida_cap_reached_tipos_incorrectos_no_evaluables(self):
        """cap_reached con valor null, 0, 1 o "false": no evaluable. Solo
        false explícito acredita que no hubo agotamiento."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_000, "event_ms": 999_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
        ]
        for valor in (None, 0, 1, "false"):
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                self._escribir_corrida(tmp, filas, {
                    "run_id": "a", "cap_reached": valor,
                })
                ev = qt.replay_episodio_desde_corrida(
                    tmp, "AAAUSDT", 999_000, 999_500, "LONG",
                    qt.TAMANO_SIMULADO, run_id="a")
            self.assertFalse(ev["evaluable"], f"valor={valor!r}: {ev}")
            self.assertEqual(ev["motivo"], "RESUMEN_INVALIDO", f"valor={valor!r}")

    def test_replay_desde_corrida_cap_reached_false_explicito_evaluable(self):
        """cap_reached false explícito: episodio evaluable normalmente
        (no hubo agotamiento)."""
        filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 999_000, "event_ms": 999_000, "seq": 1,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "received_ms": 1_500_000, "event_ms": 1_500_000, "seq": 2,
             "best_bid": 100.4, "best_ask": 100.6, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.5, "valida": True},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._escribir_corrida(tmp, filas, {
                "run_id": "a", "cap_reached": False,
            })
            ev = qt.replay_episodio_desde_corrida(
                tmp, "AAAUSDT", 999_000, 1_500_000, "LONG",
                qt.TAMANO_SIMULADO, run_id="a")
        self.assertTrue(ev["evaluable"], ev)
        self.assertEqual(ev["precio_entrada"], 100.2)
        self.assertEqual(ev["precio_salida"], 100.4)


class TestEvaluacion(unittest.TestCase):
    def setUp(self):
        self.filas = [
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "seq": 1, "received_ms": 999_000, "event_ms": 999_000,
             "best_bid": 100.0, "best_ask": 100.2, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.1, "valida": True},
            {"kind": "cotizacion", "run_id": "a", "symbol": "AAAUSDT",
             "seq": 2, "received_ms": 1_399_000, "event_ms": 1_399_000,
             "best_bid": 100.4, "best_ask": 100.6, "bid_qty": 10.0,
             "ask_qty": 10.0, "mid": 100.5, "valida": True},
        ]

    def test_long_entra_ask_sale_bid(self):
        r = episodio(self.filas, "LONG", run_id="a")
        self.assertTrue(r["evaluable"])
        self.assertEqual(r["precio_entrada"], 100.2)
        self.assertEqual(r["precio_salida"], 100.4)
        self.assertGreater(r["retorno_cruce_bps"], 0)

    def test_short_entra_bid_sale_ask(self):
        r = episodio(self.filas, "SHORT", run_id="a")
        self.assertTrue(r["evaluable"])
        self.assertEqual(r["precio_entrada"], 100.0)
        self.assertEqual(r["precio_salida"], 100.6)

    def test_spread_una_sola_resta(self):
        r = episodio(self.filas, "LONG", run_id="a")
        self.assertAlmostEqual(r["coste_spread_bps"],
                               r["retorno_referencia_mid_bps"]
                               - r["retorno_cruce_bps"], places=9)
        self.assertAlmostEqual(r["coste_spread_bps"], 19.99996, places=3)

    def test_referencia_de_precio_separada(self):
        r = episodio(self.filas, "LONG", run_id="a",
                     precio_ref_entrada=100.0, precio_ref_salida=100.5)
        self.assertAlmostEqual(r["retorno_referencia_precio_bps"], 50.0,
                               places=2)
        self.assertNotEqual(r["retorno_referencia_precio_bps"],
                            r["retorno_referencia_mid_bps"])

    def test_costes_desconocidos_y_precios_no_fills(self):
        r = episodio(self.filas, "LONG", run_id="a")
        for campo in ("comision_bps", "slippage_adicional_bps",
                      "funding_bps", "retorno_neto_bps"):
            self.assertEqual(r[campo], "UNKNOWN")
        self.assertFalse(r["precios_son_fills"])

    def test_punta_insuficiente_no_atribuye_precio(self):
        r = episodio(self.filas, "LONG", size=50.0, run_id="a")
        self.assertFalse(r["evaluable"])
        self.assertEqual(r["motivo"], "TAMANO_INSUFICIENTE")
        self.assertIsNone(r["retorno_cruce_bps"])

    def test_sin_cotizacion_de_entrada(self):
        r = episodio([], "LONG", run_id="a")
        self.assertFalse(r["evaluable"])
        self.assertTrue(r["motivo"].startswith("SIN_COTIZACION_ENTRADA:"))

    def test_sin_cotizacion_de_salida(self):
        r = episodio(self.filas[:1], "LONG", run_id="a")
        self.assertFalse(r["evaluable"])
        self.assertTrue(r["motivo"].startswith("SIN_COTIZACION_SALIDA:"))

    def test_lado_invalido(self):
        with self.assertRaises(ValueError):
            episodio(self.filas, "SIDE", run_id="a")

    def test_lectura_desde_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = tape(self.filas, Path(tmp) / "cotizaciones.jsonl")
            filas = qt.leer_tape(path)
        r = episodio(filas, "SHORT", run_id="a")
        self.assertTrue(r["evaluable"])
        self.assertEqual(r["fila_entrada"]["seq"], 1)


if __name__ == "__main__":
    unittest.main()
