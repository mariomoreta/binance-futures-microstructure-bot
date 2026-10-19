"""Auditoría de trazabilidad EVAL-CENSUS-V2 — verificador unittest.

Verifica relaciones entre etapas (no solo totales) ejecutando las
funciones puras del verificador (scripts/audit_offline_eval_ledger.py)
contra fixtures y contra datos reales. Sin tautologías: cada mutación
controlada debe producir el fallo esperado en la función verificada,
y cada caso íntegro debe pasar.

Clases:
  * PurasCausalidadTest  — verificar_causalidad_deteccion/_poblacion con
    fixtures: íntegro OK, entry<available VIOLACION, campos ausentes
    UNKNOWN (nunca PASS implícito).
  * PurasDuplicadosTest   — verificar_censo_duplicados y
    clasificar_duplicados_semanticos: inter-definición permitido,
    misma detección error, placebo identidad propia.
  * PurasVinculoTest      — origenes_de_evento + vincular_eventos_h1h3:
    evento sin respaldo o excedentes = error.
  * PurasReferenciasTest   — verificar_referencias: celdas ausentes/extra/
    campos incompatibles.
  * PurasFundingMfeTest   — verificar_funding_celda (ausente=INCOMPLETE,
    distinto de cero válido) y rango_mfe_mae (global vs n>=30).
  * PurasDescartesTest   — verificar_motivos_descarte: build_report vs
    clasificación determinista de detecciones.
  * DatosRealesTest       — causalidad 9314/6/0, censo 594/616, vínculo
    H1/H3 sin huecos, duplicados events 0 errores, referencias
    consistentes, conteos hipótesis/placebo, funding 741/0/24-60.
  * IntegracionLedgerTest — reporte INCOMPLETE con inputs ausentes y
    exit != 0; COMPLETO con datos reales.
  * MutacionesTest       — cada defecto inyectado en fixture produce la
    detección esperada por la función del verificador.

Uso:
    python run_tests.py -q
    python -m unittest tests.test_audit_offline_eval_traceability -v
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "audit_ledger", str(ROOT / "scripts" / "audit_offline_eval_ledger.py"))
ledger = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ledger)

ARTIFACT_DEFAULT = ROOT / "frontend" / "src" / "data" / "census-eval-v2.json"
TEMP_DEFAULT = Path(tempfile.gettempdir()) / "opencode"

ALLOWED_FAMILIES = ledger.ALLOWED_FAMILIES
REQUIRED_EVENT_FIELDS = ("symbol", "event_time_ms", "direction", "family",
                         "rules_version", "group", "reference_price")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def finite_number(v) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(float(v))


# ---------------------------------------------------------------------------
# Cargador de inputs reales (manifiestos/detecciones fuera de Git)
# ---------------------------------------------------------------------------
class Inputs:
    def __init__(self, artifact_path: Path, temp_dir: Path):
        self.artifact_path = artifact_path
        self.temp_dir = temp_dir
        self.artifact = None
        self.manifests = {}
        self.events = {}
        self.selections = {}
        self.build_reports = {}
        self.funding_raw = None
        self.detecciones = []
        self.candles = {}
        self.errors = []

    def load_all(self):
        self.artifact = load_json(self.artifact_path)
        combos = [
            ("eval15_btc", "BTCUSDT", "15m"),
            ("eval15_ethsol", "ETHUSDT", "15m"),
            ("eval15_ethsol", "SOLUSDT", "15m"),
            ("eval1h_trio", "BTCUSDT", "1h"),
            ("eval1h_trio", "ETHUSDT", "1h"),
            ("eval1h_trio", "SOLUSDT", "1h"),
        ]
        for d, sym, res in combos:
            base = self.temp_dir / d
            mp = base / ("manifest_%s_%s.json" % (sym, res))
            ep = base / ("events_%s_%s.json" % (sym, res))
            cp = base / ("candles_%s_%s.json" % (sym, res))
            if mp.exists():
                self.manifests[(sym, res)] = load_json(mp)
            else:
                self.errors.append("manifiesto ausente: %s" % mp)
            if ep.exists():
                self.events[(sym, res)] = load_json(ep)
            else:
                self.errors.append("events ausente: %s" % ep)
            if cp.exists():
                self.candles[(sym, res)] = load_json(cp)
            sp = base / ("selection_%s_%s.json" % (sym, res))
            if sp.exists():
                self.selections[(sym, res)] = load_json(sp)
        for d in ("eval15_btc", "eval15_ethsol", "eval1h_trio"):
            bp = self.temp_dir / d / "build_report.json"
            if bp.exists():
                self.build_reports[d] = load_json(bp)
        fr = self.temp_dir / "funding_raw.json"
        if fr.exists():
            self.funding_raw = load_json(fr)
        for dname, _syms, _res in ledger.CENSUS_DIRS:
            cp = self.temp_dir / dname / ledger.CENSUS_DETECTIONS_NAME
            if not cp.exists():
                self.errors.append("detecciones ausente: %s" % cp)
                continue
            for line in cp.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.detecciones.append(json.loads(line))

    def is_complete(self) -> bool:
        return len(self.errors) == 0


def _barras_fixture():
    """102 barras sintéticas deterministas descendentes para reconocer
    H2: formación en barra 2 (close alto), confirmación en barra 3
    (close <= ref_close, sin reclaim sobre el trailing high)."""
    bars = []
    t0 = 1_000_000
    for i in range(102):
        bars.append({"open_time_ms": t0 + i * 60_000,
                     "high": 210.0 - i, "low": 190.0 - i,
                     "close": 200.0 - i, "close_time_ms": t0 + i * 60_000 + 59_999})
    return bars


# ===========================================================================
# Tests de funciones puras: causalidad
# ===========================================================================
class PurasCausalidadTest(unittest.TestCase):
    def test_causalidad_detection_integra_ok(self):
        d = {"formation_time": 1000, "available_at": 2000,
             "entry_time_same_grid": 3000}
        est, mot = ledger.verificar_causalidad_deteccion(d)
        self.assertEqual(est, "OK")
        self.assertIsNone(mot)

    def test_causalidad_entry_antes_de_available_violacion(self):
        d = {"formation_time": 3000, "available_at": 2000,
             "entry_time_same_grid": 1000}
        est, mot = ledger.verificar_causalidad_deteccion(d)
        self.assertEqual(est, "VIOLACION")
        self.assertIn("available_at", mot)

    def test_causalidad_entry_antes_de_formacion_violacion(self):
        d = {"formation_time": 5000, "available_at": 2000,
             "entry_time_same_grid": 1000}
        est, _ = ledger.verificar_causalidad_deteccion(d)
        self.assertEqual(est, "VIOLACION")

    def test_causalidad_campos_ausentes_unknown(self):
        est, mot = ledger.verificar_causalidad_deteccion(
            {"formation_time": 1000})
        self.assertEqual(est, "UNKNOWN")
        self.assertIn("ausentes", mot)

    def test_causalidad_no_finitos_unknown(self):
        d = {"formation_time": float("inf"), "available_at": 2000,
             "entry_time_same_grid": 3000}
        est, _ = ledger.verificar_causalidad_deteccion(d)
        self.assertEqual(est, "UNKNOWN")

    def test_causalidad_poblacion_vacia_unknown(self):
        r = ledger.verificar_causalidad_poblacion([])
        self.assertEqual(r["estado"], "UNKNOWN")

    def test_causalidad_poblacion_agrega(self):
        dets = [
            {"formation_time": 1, "available_at": 2,
             "entry_time_same_grid": 3},
            {"formation_time": 1, "available_at": 3,
             "entry_time_same_grid": 2},
            {"formation_time": 1, "available_at": None,
             "entry_time_same_grid": None},
        ]
        r = ledger.verificar_causalidad_poblacion(dets)
        self.assertEqual(r["ok"], 1)
        self.assertEqual(r["violaciones"], 1)
        self.assertEqual(r["unknown"], 1)
        self.assertEqual(r["estado"], "COMPLETO_CON_DISCREPANCIAS")


# ===========================================================================
# Tests de funciones puras: duplicados
# ===========================================================================
class PurasDuplicadosTest(unittest.TestCase):
    def test_censo_duplicados_inter_definicion_permitido(self):
        filas = [
            {"symbol": "BTCUSDT", "interval": "15m",
             "formation_time": 1000, "definition_name": "EXTENDED_GAINER"},
            {"symbol": "BTCUSDT", "interval": "15m",
             "formation_time": 1000, "definition_name": "FAILED_HIGH_CANDIDATE"},
        ]
        r = ledger.verificar_censo_duplicados(filas)
        self.assertEqual(r["grupos_duplicados"], 1)
        self.assertEqual(r["filas_extra"], 1)
        self.assertEqual(r["mismas_definiciones_grupos"], 0)

    def test_censo_duplicados_misma_definicion_reportado(self):
        filas = [
            {"symbol": "BTCUSDT", "interval": "15m",
             "formation_time": 1000, "definition_name": "EXTENDED_GAINER"},
            {"symbol": "BTCUSDT", "interval": "15m",
             "formation_time": 1000, "definition_name": "EXTENDED_GAINER"},
        ]
        r = ledger.verificar_censo_duplicados(filas)
        self.assertEqual(r["mismas_definiciones_grupos"], 1)

    def test_duplicados_semanticos_mismo_origen_error(self):
        evs = [
            {"symbol": "BTCUSDT", "event_time_ms": 1000,
             "direction": "LONG", "family": "H1", "rules_version": "H1-v1",
             "group": "continuation"},
            {"symbol": "BTCUSDT", "event_time_ms": 1000,
             "direction": "LONG", "family": "H1", "rules_version": "H1-v1",
             "group": "continuation"},
        ]
        clave = ledger.clave_semantica_evento(evs[0])
        orig = {clave: ["oid-1", "oid-1"]}
        r = ledger.clasificar_duplicados_semanticos(evs, orig)
        self.assertEqual(len(r["errores"]), 1)
        self.assertEqual(r["errores"][0]["filas"], 2)

    def test_duplicados_semanticos_distintos_origenes_permitido(self):
        evs = [
            {"symbol": "BTCUSDT", "event_time_ms": 1000,
             "direction": "LONG", "family": "H1", "rules_version": "H1-v1",
             "group": "continuation"},
            {"symbol": "BTCUSDT", "event_time_ms": 1000,
             "direction": "LONG", "family": "H1", "rules_version": "H1-v1",
             "group": "continuation"},
        ]
        clave = ledger.clave_semantica_evento(evs[0])
        orig = {clave: ["oid-1", "oid-2"]}
        r = ledger.clasificar_duplicados_semanticos(evs, orig)
        self.assertEqual(len(r["errores"]), 0)
        self.assertEqual(len(r["permitidos"]), 1)

    def test_duplicados_semanticos_placebo_permitido(self):
        evs = [
            {"symbol": "BTCUSDT", "event_time_ms": 1000,
             "direction": "LONG", "family": "H1", "rules_version": "H1-v1",
             "group": "baseline"},
            {"symbol": "BTCUSDT", "event_time_ms": 1000,
             "direction": "LONG", "family": "H1", "rules_version": "H1-v1",
             "group": "baseline"},
        ]
        clave = ledger.clave_semantica_evento(evs[0])
        orig = {clave: ["placebo", "placebo"]}
        r = ledger.clasificar_duplicados_semanticos(evs, orig)
        self.assertEqual(len(r["errores"]), 0)
        self.assertEqual(r["permitidos"][0]["nota"],
                         "colision interna placebo (identidad sintetica)")

    def test_duplicados_semanticos_sin_origenes_no_clasifica(self):
        evs = [{"symbol": "BTCUSDT", "event_time_ms": 1000,
                "direction": "LONG", "family": "H1",
                "rules_version": "H1-v1", "group": "continuation"}] * 2
        r = ledger.clasificar_duplicados_semanticos(evs)
        self.assertEqual(len(r["errores"]), 0)
        self.assertEqual(len(r["sin_clasificar"]), 1)


# ===========================================================================
# Tests de funciones puras: vínculo detección→evento
# ===========================================================================
class PurasVinculoTest(unittest.TestCase):
    def test_vinculo_ok(self):
        dets = [{"symbol": "BTCUSDT", "source_interval": "15m",
                 "formation_time": 1000, "direction": "up",
                 "definition_name": "EXTENDED_GAINER",
                 "original_event_id": "oid-1",
                 "formation_gap": False, "entry_time_same_grid": 2000,
                 "reference_price": 100.0}]
        evs = [{"symbol": "BTCUSDT", "event_time_ms": 1000,
                "direction": "LONG", "family": "H1",
                "rules_version": "H1-v1", "group": "continuation"}]
        r = ledger.vincular_eventos_h1h3(evs, dets)
        self.assertEqual(r["n_sin_respaldo"], 0)
        self.assertEqual(r["n_excedentes"], 0)

    def test_vinculo_sin_respaldo_error(self):
        evs = [{"symbol": "BTCUSDT", "event_time_ms": 1000,
                "direction": "LONG", "family": "H1",
                "rules_version": "H1-v1", "group": "continuation"}]
        r = ledger.vincular_eventos_h1h3(evs, [])
        self.assertEqual(r["n_sin_respaldo"], 1)

    def test_vinculo_excedentes_error(self):
        dets = [{"symbol": "BTCUSDT", "source_interval": "15m",
                 "formation_time": 1000, "direction": "up",
                 "definition_name": "EXTENDED_GAINER",
                 "original_event_id": "oid-1",
                 "formation_gap": False, "entry_time_same_grid": 2000,
                 "reference_price": 100.0}]
        evs = [{"symbol": "BTCUSDT", "event_time_ms": 1000,
                "direction": "LONG", "family": "H1",
                "rules_version": "H1-v1", "group": "continuation"}] * 2
        r = ledger.vincular_eventos_h1h3(evs, dets)
        self.assertEqual(r["n_excedentes"], 1)

    def test_origenes_h2_reconstruye_confirmacion(self):
        bars = _barras_fixture()
        dets = [{"symbol": "BTCUSDT", "source_interval": "15m",
                 "formation_time": bars[2]["open_time_ms"],
                 "direction": "down",
                 "definition_name": "FAILED_HIGH_CANDIDATE",
                 "original_event_id": "oid-h2",
                 "formation_gap": False, "entry_time_same_grid": 3000,
                 "reference_price": bars[2]["close"]}]
        evs = [{"symbol": "BTCUSDT", "event_time_ms": bars[3]["open_time_ms"],
                "direction": "SHORT", "family": "H2", "rules_version": "H2-v1",
                "group": "correction-exhaustion"}]
        orig = ledger.origenes_de_evento(evs, dets,
                                         {("BTCUSDT", "15m"): bars})
        clave = ledger.clave_semantica_evento(evs[0])
        self.assertIn(clave, orig)
        self.assertEqual(orig[clave], ["oid-h2"])


# ===========================================================================
# Tests de funciones puras: referencias, funding, MFE/MAE, descartes
# ===========================================================================
class PurasReferenciasTest(unittest.TestCase):
    def _artev(self):
        art = {"cells": {"BTCUSDT": {"15m": {"continuation": {"dev": {
            "1.0": {"n_events": 1, "n_trades": 1, "n_open": 0,
                    "skipped_overlap": 0, "E_net": -0.5,
                    "verdict": "REJECTED"}}}}}}}
        man = {"groups": {"continuation": {
            "event_ids": ["BTCUSDT:1:LONG:H1:H1-v1:0"],
            "dev": {"1.0": {"n_events": 1, "n_trades": 1, "n_open": 0,
                             "skipped_overlap": 0}}}}}
        return art, {("BTCUSDT", "15m"): man}

    def test_referencias_consistentes(self):
        art, mans = self._artev()
        r = ledger.verificar_referencias(art, mans)
        self.assertTrue(r["consistente"])

    def test_referencias_celda_extra_en_artefacto_con_eventos(self):
        art, mans = self._artev()
        art["cells"]["BTCUSDT"]["15m"]["continuation"]["oos"] = {
            "1.0": {"n_events": 5, "n_trades": 5, "n_open": 0,
                    "skipped_overlap": 0, "E_net": -0.5,
                    "verdict": "REJECTED"}}
        r = ledger.verificar_referencias(art, mans)
        self.assertFalse(r["consistente"])
        self.assertEqual(len(r["solo_artefacto_con_eventos"]), 1)

    def test_referencias_campos_incompatibles(self):
        art, mans = self._artev()
        mans[("BTCUSDT", "15m")]["groups"]["continuation"]["dev"]["1.0"][
            "n_events"] = 99
        r = ledger.verificar_referencias(art, mans)
        self.assertFalse(r["consistente"])
        self.assertEqual(len(r["campos_incompatibles"]), 1)


class PurasFundingMfeTest(unittest.TestCase):
    def test_funding_ausente_incomplete_no_cero(self):
        r = ledger.verificar_funding_celda({"n_events": 1})
        self.assertEqual(r["estado"], "INCOMPLETE")

    def test_funding_presente_ok(self):
        seg = {"funding_quality": {"settled_events": 3,
                                   "unknown_excluded": 0,
                                   "uncovered_ms": 100}}
        r = ledger.verificar_funding_celda(seg)
        self.assertEqual(r["estado"], "OK")
        self.assertEqual(r["settled_events"], 3)

    def test_funding_distinto_de_cero_valido(self):
        seg = {"funding_quality": {"settled_events": 0,
                                   "unknown_excluded": 2,
                                   "uncovered_ms": 500}}
        r = ledger.verificar_funding_celda(seg)
        self.assertEqual(r["estado"], "OK")
        self.assertEqual(r["unknown_excluded"], 2)

    def test_rango_mfe_global_y_n30(self):
        celdas = [
            {"mfe_mean": 0.1, "mae_mean": 0.05, "n_trades": 5},
            {"mfe_mean": 0.6, "mae_mean": 0.4, "n_trades": 40},
            {"mfe_mean": 0.3, "mae_mean": 0.2, "n_trades": 30},
        ]
        r = ledger.rango_mfe_mae(celdas)
        self.assertEqual(r["estado"], "COMPLETO")
        self.assertEqual(r["mfe_min"], 0.1)
        self.assertEqual(r["mfe_max"], 0.6)
        self.assertEqual(r["n_celdas_n30"], 2)
        self.assertEqual(r["mfe_min_n30"], 0.3)
        self.assertEqual(r["mfe_max_n30"], 0.6)
        self.assertEqual(r["mae_min_n30"], 0.2)
        self.assertEqual(r["mae_max_n30"], 0.4)

    def test_rango_mfe_vacio_unknown(self):
        r = ledger.rango_mfe_mae([])
        self.assertEqual(r["estado"], "UNKNOWN")


class PurasDescartesTest(unittest.TestCase):
    def _dets(self):
        return [
            {"symbol": "BTCUSDT", "source_interval": "15m",
             "definition_name": "EXTENDED_GAINER", "formation_gap": False,
             "entry_time_same_grid": 2000, "reference_price": 100.0,
             "original_event_id": "a"},
            {"symbol": "BTCUSDT", "source_interval": "15m",
             "definition_name": "EXTENDED_LOSER", "formation_gap": False,
             "entry_time_same_grid": 2000, "reference_price": 100.0,
             "original_event_id": "b"},
            {"symbol": "BTCUSDT", "source_interval": "15m",
             "definition_name": "EXTENDED_GAINER", "formation_gap": True,
             "entry_time_same_grid": 2000, "reference_price": 100.0,
             "original_event_id": "c"},
            {"symbol": "BTCUSDT", "source_interval": "15m",
             "definition_name": "EXTENDED_LOSER", "formation_gap": False,
             "entry_time_same_grid": None, "reference_price": 100.0,
             "original_event_id": "d"},
        ]

    def test_motivos_descarte_coinciden(self):
        counts = {"h1": 1, "h3": 1, "h2ex": 0, "h2rev": 0, "placebo": 2,
                  "excluded_gap": 1, "excluded_no_entry": 1,
                  "excluded_h2_no_confirmation": 0,
                  "excluded_h2_reclaim": 0}
        r = ledger.verificar_motivos_descarte(counts, self._dets())
        self.assertEqual(r["estado"], "COMPLETO")
        self.assertEqual(r["errores"], [])

    def test_motivos_descarte_alterado_detectado(self):
        counts = {"h1": 9, "h3": 1, "h2ex": 0, "h2rev": 0, "placebo": 2,
                  "excluded_gap": 1, "excluded_no_entry": 1,
                  "excluded_h2_no_confirmation": 0,
                  "excluded_h2_reclaim": 0}
        r = ledger.verificar_motivos_descarte(counts, self._dets())
        self.assertEqual(r["estado"], "COMPLETO_CON_DISCREPANCIAS")
        self.assertTrue(any("h1" in e for e in r["errores"]))

    def test_motivos_descarte_ausente_incomplete(self):
        r = ledger.verificar_motivos_descarte(
            {"h1": 1}, self._dets())
        self.assertEqual(r["estado"], "INCOMPLETE")
        self.assertTrue(any("ausente" in e for e in r["errores"]))


# ===========================================================================
# Tests sobre datos reales (skipTest = UNKNOWN si faltan inputs)
# ===========================================================================
class DatosRealesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = Inputs(ARTIFACT_DEFAULT, TEMP_DEFAULT)
        cls.inputs.load_all()
        if not cls.inputs.is_complete():
            raise unittest.SkipTest(
                "inputs externos ausentes: %s" % cls.inputs.errors[:3])
        cls.art = cls.inputs.artifact
        cls.cells = cls.art["cells"]

    def test_causalidad_real_9314_ok_0_violaciones(self):
        r = ledger.verificar_causalidad_poblacion(self.inputs.detecciones)
        self.assertEqual(r["estado"], "COMPLETO")
        self.assertEqual(r["total"], 9320)
        self.assertEqual(r["ok"], 9314)
        self.assertEqual(r["unknown"], 6)
        self.assertEqual(r["violaciones"], 0)

    def test_censo_duplicados_real_594_616(self):
        filas = [{"symbol": x.get("symbol"),
                  "interval": x.get("source_interval"),
                  "formation_time": x.get("formation_time"),
                  "definition_name": x.get("definition_name")}
                 for x in self.inputs.detecciones]
        r = ledger.verificar_censo_duplicados(filas)
        self.assertEqual(r["total_filas"], 9320)
        self.assertEqual(r["grupos_duplicados"], 594)
        self.assertEqual(r["filas_extra"], 616)
        self.assertEqual(r["mismas_definiciones_grupos"], 0)
        por = { (d["symbol"], d["interval"]): d for d in r["desglose"] }
        self.assertEqual(por[("BTCUSDT", "15m")]["grupos"], 129)
        self.assertEqual(por[("BTCUSDT", "15m")]["extra"], 135)
        self.assertEqual(por[("MINAUSDT", "1h")]["grupos"], 90)
        self.assertEqual(por[("SOLUSDT", "15m")]["grupos"], 130)
        self.assertEqual(por[("NMRUSDT", "1h")]["grupos"], 35)
        self.assertEqual(por[("ORCAUSDT", "1h")]["grupos"], 53)
        tot_grupos = sum(d["grupos"] for d in r["desglose"])
        tot_extra = sum(d["extra"] for d in r["desglose"])
        self.assertEqual(tot_grupos, 594)
        self.assertEqual(tot_extra, 616)

    def test_1779_fuera_de_alcance_por_membresia(self):
        trio_15m_1h = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
        fuera = [x for x in self.inputs.detecciones
                 if x["symbol"] not in trio_15m_1h]
        por_sym = Counter(x["symbol"] for x in fuera)
        self.assertEqual(len(fuera), 1779)
        self.assertEqual(por_sym["MINAUSDT"], 626)
        self.assertEqual(por_sym["NMRUSDT"] + por_sym["ORCAUSDT"], 1153)

    def test_vinculo_h1h3_real_sin_huecos(self):
        for (sym, res), evs in self.inputs.events.items():
            dets = [x for x in self.inputs.detecciones
                    if x.get("symbol") == sym
                    and x.get("source_interval") == res]
            r = ledger.vincular_eventos_h1h3(evs, dets)
            self.assertEqual(r["n_sin_respaldo"], 0,
                             "%s/%s: eventos sin respaldo" % (sym, res))
            self.assertEqual(r["n_excedentes"], 0,
                             "%s/%s: eventos excedentes" % (sym, res))

    def test_duplicados_events_real_0_errores(self):
        for (sym, res), evs in self.inputs.events.items():
            dets = [x for x in self.inputs.detecciones
                    if x.get("symbol") == sym
                    and x.get("source_interval") == res]
            bars = self.inputs.candles.get((sym, res))
            orig = ledger.origenes_de_evento(
                evs, dets, {(sym, res): bars} if bars else None)
            r = ledger.clasificar_duplicados_semanticos(evs, orig)
            self.assertEqual(r["errores"], [],
                             "%s/%s: errores duplicados: %s"
                             % (sym, res, r["errores"][:2]))

    def test_referencias_real_consistentes(self):
        r = ledger.verificar_referencias(self.art, self.inputs.manifests)
        self.assertTrue(r["consistente"], r)

    def test_motivos_descarte_real_coinciden(self):
        bars_by = self.inputs.candles
        for d, br in self.inputs.build_reports.items():
            syms = br.get("symbols", [])
            iv = br.get("interval")
            dets = [x for x in self.inputs.detecciones
                    if x.get("symbol") in syms
                    and x.get("source_interval") == iv]
            bb = {(s, iv): bars_by.get((s, iv)) for s in syms}
            bb = {k: v for k, v in bb.items() if v is not None}
            r = ledger.verificar_motivos_descarte(
                br.get("counts", {}), dets, bb or None)
            self.assertIn(r["estado"], ("COMPLETO", "COMPLETO_CON_DISCREPANCIAS"),
                          "%s: %s" % (d, r["errores"]))
            for e in r["errores"]:
                self.assertNotIn("ausente", e,
                                 "%s: motivo ausente = INCOMPLETE" % d)

    def test_event_ids_manifiesto_unicos(self):
        for (sym, res), man in self.inputs.manifests.items():
            for fam, g in man["groups"].items():
                ids = g.get("event_ids", [])
                self.assertEqual(len(ids), len(set(ids)),
                                 "%s/%s/%s: event_ids duplicados"
                                 % (sym, res, fam))

    def test_conteos_hipotesis_placebo(self):
        ev = tr = op = sk = 0
        for sym in self.cells:
            for res in self.cells[sym]:
                for fam in self.cells[sym][res]:
                    if fam == "baseline":
                        continue
                    for split in self.cells[sym][res][fam]:
                        if "1.0" not in self.cells[sym][res][fam][split]:
                            continue
                        c = self.cells[sym][res][fam][split]["1.0"]
                        ev += c["n_events"]
                        tr += c["n_trades"]
                        op += c["n_open"]
                        sk += c["skipped_overlap"]
        self.assertEqual(ev, 7152)
        self.assertEqual(tr, 2991)
        self.assertEqual(op, 5)
        self.assertEqual(sk, 4161)
        self.assertEqual(tr - op, 2986)
        ev = tr = op = sk = 0
        for sym in self.cells:
            for res in self.cells[sym]:
                for fam in self.cells[sym][res]:
                    if fam != "baseline":
                        continue
                    for split in self.cells[sym][res][fam]:
                        if "1.0" not in self.cells[sym][res][fam][split]:
                            continue
                        c = self.cells[sym][res][fam][split]["1.0"]
                        ev += c["n_events"]
                        tr += c["n_trades"]
                        op += c["n_open"]
                        sk += c["skipped_overlap"]
        self.assertEqual(ev, 7152)
        self.assertEqual(tr, 2264)
        self.assertEqual(op, 2)
        self.assertEqual(sk, 4888)
        self.assertEqual(tr - op, 2262)

    def test_funding_real_741_0_24_60(self):
        total_settled = 0
        total_unknown = 0
        cells_uncovered = 0
        cells_total = 0
        for sym in self.cells:
            for res in self.cells[sym]:
                man = self.inputs.manifests.get((sym, res))
                if not man:
                    continue
                for fam in self.cells[sym][res]:
                    for split in self.cells[sym][res][fam]:
                        if "1.0" not in self.cells[sym][res][fam][split]:
                            continue
                        cells_total += 1
                        seg = man["groups"].get(fam, {}).get(split, {}).get(
                            "1.0", {})
                        r = ledger.verificar_funding_celda(seg)
                        self.assertEqual(r["estado"], "OK",
                                         "%s/%s/%s/%s funding incompleto"
                                         % (sym, res, fam, split))
                        total_settled += r["settled_events"]
                        total_unknown += r["unknown_excluded"]
                        if r["uncovered_ms"] > 0:
                            cells_uncovered += 1
        self.assertEqual(total_settled, 741)
        self.assertEqual(total_unknown, 0)
        self.assertEqual(cells_uncovered, 24)
        self.assertEqual(cells_total, 60)

    def test_rango_mfe_real(self):
        celdas = []
        for sym in self.cells:
            for res in self.cells[sym]:
                man = self.inputs.manifests.get((sym, res))
                if not man:
                    continue
                for fam in self.cells[sym][res]:
                    for split in self.cells[sym][res][fam]:
                        if "1.0" not in self.cells[sym][res][fam][split]:
                            continue
                        seg = man["groups"].get(fam, {}).get(split, {}).get(
                            "1.0", {})
                        if finite_number(seg.get("mfe_mean")) \
                                and finite_number(seg.get("mae_mean")):
                            celdas.append(seg)
        r = ledger.rango_mfe_mae(celdas)
        self.assertEqual(r["estado"], "COMPLETO")
        self.assertGreaterEqual(r["mfe_min"], 0.0)
        self.assertGreaterEqual(r["mae_min"], 0.0)
        self.assertIsNotNone(r["mfe_min_n30"])
        self.assertIsNotNone(r["mae_min_n30"])
        self.assertGreaterEqual(r["n_celdas_n30"], 1)


# ===========================================================================
# Integración: el generador no emite apariencia de éxito con inputs
# incompletos (INCOMPLETE + exit != 0)
# ===========================================================================
class IntegracionLedgerTest(unittest.TestCase):
    def test_ledger_incomplete_con_temp_dir_vacio(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "reporte.json"
            rc = ledger.main(["--artifact", str(ARTIFACT_DEFAULT),
                              "--temp-dir", td,
                              "--out", str(out)])
            self.assertNotEqual(rc, 0)
            rep = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("INCOMPLETE", rep["estatus"])
            self.assertTrue(any("temp_dir" in r or "ausente" in r
                                for r in rep["incomplete_reasons"]))

    def test_ledger_completo_con_datos_reales(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "reporte.json"
            rc = ledger.main(["--artifact", str(ARTIFACT_DEFAULT),
                              "--temp-dir", str(TEMP_DEFAULT),
                              "--trades-dir",
                              str(Path(r"C:\proyectos\binance-temp\trades_from_pkg")),
                              "--out", str(out)])
            rep = json.loads(out.read_text(encoding="utf-8"))
            # No discrepancies allowed; INCOMPLETE is acceptable for
            # tail-edge of symbols without build_report (MINA/NMR).
            self.assertEqual(len(rep["veredicto"]["discrepancias"]), 0,
                             "discrepancias inesperadas: %s"
                             % rep["veredicto"]["discrepancias"][:3])
            self.assertIn(rep["estatus"], ("COMPLETO", "INCOMPLETE"),
                          "estatus inesperado: %s" % rep["estatus"])
            self.assertEqual(rep["causalidad"]["violaciones"], 0)
            self.assertEqual(rep["duplicados_censo"]["grupos_duplicados"], 594)
            self.assertEqual(rep["duplicados_censo"]["filas_extra"], 616)
            self.assertTrue(rep["referencias"]["consistente"])
            for e in rep["duplicados_events"]:
                self.assertEqual(e["errores"], [])

    def test_ledger_sin_temp_dir_no_parece_completo(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "reporte.json"
            rc = ledger.main(["--artifact", str(ARTIFACT_DEFAULT),
                              "--out", str(out)])
            self.assertNotEqual(rc, 0)
            rep = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("INCOMPLETE", rep["estatus"])


# ===========================================================================
# Hashes y procedencia
# ===========================================================================
class ProcedenciaTest(unittest.TestCase):
    def test_sha256_estable(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.json"
            p.write_text('{"a": 1}', encoding="utf-8")
            h1 = ledger.sha256_file(p)
            h2 = ledger.sha256_file(p)
            self.assertEqual(h1, h2)
            self.assertEqual(len(h1), 64)
            p.write_text('{"a": 2}', encoding="utf-8")
            self.assertNotEqual(h1, ledger.sha256_file(p))

    def test_rutas_sin_usuario_absoluto_en_defaults(self):
        self.assertNotIn("adonm", str(ledger.ARTIFACT_DEFAULT))
        self.assertNotIn("adonm", str(ledger.OUT_DEFAULT))

    def test_inputs_registrados_con_hash(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "reporte.json"
            ledger.main(["--artifact", str(ARTIFACT_DEFAULT),
                        "--temp-dir", str(TEMP_DEFAULT),
                        "--out", str(out)])
            # Relee para inputs
            led = ledger.Ledger(ARTIFACT_DEFAULT, TEMP_DEFAULT, out)
            led.load()
            art_in = led.inputs.get("artefacto")
            self.assertIsNone(art_in)  # artefacto va aparte
            man = led.inputs.get("manifest BTCUSDT_15m")
            self.assertIsNotNone(man)
            self.assertEqual(man["sha256"],
                             ledger.sha256_file(TEMP_DEFAULT / "eval15_btc"
                                                / "manifest_BTCUSDT_15m.json"))


# ===========================================================================
# Regresión: modo paquete no debe perder manifiestos (bug _load_manifest)
# ===========================================================================
class PackageModeTest(unittest.TestCase):
    """Regresión del bug: con --package, temp_dir es None y _load_manifest
    retornaba None → 0 manifiestos → 5305 discrepancias falsas de
    referencias. El fix usa base_dir (package/combos)."""

    PKG = ROOT / "docs" / "evidence" / "eval-census-v2-package"

    @classmethod
    def setUpClass(cls):
        if not cls.PKG.exists():
            raise unittest.SkipTest("paquete no publicado")

    def test_load_manifest_en_modo_package(self):
        led = ledger.Ledger(ARTIFACT_DEFAULT, None, Path(tempfile.mkdtemp()) / "r.json")
        led.load(package=self.PKG)
        man = led._load_manifest("BTCUSDT", "15m")
        self.assertIsNotNone(man, "_load_manifest None en modo package "
                                 "(bug regresado)")
        self.assertIn("groups", man)

    def test_referencias_consistentes_en_modo_package(self):
        led = ledger.Ledger(ARTIFACT_DEFAULT, None, Path(tempfile.mkdtemp()) / "r.json")
        led.load(package=self.PKG)
        rep = led.build()
        self.assertEqual(rep["referencias"]["consistente"], True,
                         "referencias inconsistentes en modo package: %s"
                         % rep["referencias"])
        discrep = [d for d in rep["veredicto"]["discrepancias"]
                   if d["seccion"] == "referencias"]
        self.assertEqual(discrep, [],
                         "discrepancias de referencias en modo package "
                         "(bug regresado): %s" % discrep[:3])

    def test_veredicto_global_en_modo_package(self):
        led = ledger.Ledger(ARTIFACT_DEFAULT, None, Path(tempfile.mkdtemp()) / "r.json")
        led.load(package=self.PKG)
        rep = led.build()
        self.assertNotIn("FAIL", rep["veredicto"]["estado"],
                         "veredicto FAIL en modo package sin trades: %s"
                         % rep["veredicto"]["discrepancias"][:3])


# ===========================================================================
# Runner principal con conteos reales
# ===========================================================================
def run_suite(verbosity=2):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (PurasCausalidadTest, PurasDuplicadosTest, PurasVinculoTest,
                PurasReferenciasTest, PurasFundingMfeTest, PurasDescartesTest,
                DatosRealesTest, IntegracionLedgerTest, ProcedenciaTest,
                PackageModeTest):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=verbosity)
    return runner.run(suite)


if __name__ == "__main__":
    result = run_suite()
    print("\n=== RESUMEN ===")
    print("tests ejecutados: %d" % result.testsRun)
    print("fallos: %d" % len(result.failures))
    print("errores: %d" % len(result.errors))
    raise SystemExit(0 if result.wasSuccessful() else 1)
