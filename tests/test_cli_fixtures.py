"""Tests CLI de integración EVAL-CENSUS-V2 — cadena reconstructor → archivos → ledger.

Valida que el ledger consume solo trazas cuya reconstruction_manifest.json
tenga veredicto COMPLETO, cobertura completa y hashes que coincidan, y que
cualquier traza fallida, ausente, extra, obsoleta o alterada sea rechazada.

Cada alteración controlada debe producir FAIL o INCOMPLETE con exit != 0;
el control íntegro produce PASS y exit 0.

Casos:
  control. Control íntegro válido → PASS, exit 0
  1. Referencia inexistente (celda en artefacto sin manifiesto) → FAIL
  2. E_net alterado manteniendo los conteos → FAIL
  3. Campo obligatorio ausente en manifiesto → FAIL
  4. Escenario inesperado (escala 4.0) → FAIL
  5. Duplicación indebida (event_id duplicado en manifiesto) → FAIL
  6. Entrada efectiva anterior a disponibilidad → FAIL
  7. H2 entrando antes de conocerse su confirmación → FAIL
  8. Operación sin candidato (event_id no en manifiesto) → FAIL
  9. Input faltante (funding ausente) → INCOMPLETE
 10. entry_ms ausente → INCOMPLETE (nunca aceptación implícita)
 11. entry_ms no finito → INCOMPLETE
 12. H2 con close_time_ms ausente → INCOMPLETE
 13. Respaldo de resolución incompatible → INCOMPLETE
 14. reconstruction_manifest con FAIL → ledger rechaza → INCOMPLETE
 15. Archivo de trades alterado después de reconstruir (hash mismatch) → FAIL
 16. Archivo de trades obsoleto de ejecución previa (extra) → FAIL
 17. Archivo esperado ausente → INCOMPLETE
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import importlib.util

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "audit_ledger", str(ROOT / "scripts" / "audit_offline_eval_ledger.py"))
ledger = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ledger)

COMBOS = [
    ("eval15_btc", "BTCUSDT", "15m"),
    ("eval15_ethsol", "ETHUSDT", "15m"),
    ("eval15_ethsol", "SOLUSDT", "15m"),
    ("eval1h_trio", "BTCUSDT", "1h"),
    ("eval1h_trio", "ETHUSDT", "1h"),
    ("eval1h_trio", "SOLUSDT", "1h"),
]


def _seg(n, en, extra=None):
    d = {"n_events": n, "n_trades": n, "n_realized": n, "n_open": 0,
         "skipped_overlap": 0, "n_expired": 0, "n_mismatched": 0,
         "exit_reasons": {"horizon": n, "stop": 0, "open_at_end": 0},
         "expectancy_net": en, "expectancy_gross": 0.5,
         "total_net": en * n, "total_net_realized": en * n,
         "total_fees": 0.5 * n, "total_funding": 0.0,
         "funding_quality": {"settled_events": n, "unknown_excluded": 0,
                             "uncovered_ms": 0},
         "max_drawdown": 1.0, "max_drawdown_realized": 1.0,
         "mfe_mean": 0.5, "mae_mean": 0.2, "config_hash": "fixture"}
    if extra:
        d.update(extra)
    return d


def _trade(eid, grp, et, entry, en, sym="BTCUSDT", direction="LONG",
           fam="H1", ver="H1-v1", res="15m", segmento="dev", escala=1.0,
           estado="realizada", exit_executed=True):
    return {"event_id": eid, "group": grp, "segmento": segmento,
            "escala": escala, "res": res, "symbol": sym,
            "direction": direction, "family": fam, "rules_version": ver,
            "event_time_ms": et, "entry_ms": entry, "exit_ms": entry + 1000,
            "entry_px": 100.0, "exit_px": 99.0, "exit_reason": "horizon",
            "open_at_end": False, "exit_executed": exit_executed,
            "estado": estado, "net_pnl": en, "gross_pnl": -0.5,
            "fees": 0.5, "funding": 0.0, "mfe_pct": 0.5, "mae_pct": 0.2}


def _manifest_seg(n, en):
    return _seg(n, en)


class CliFixturesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cli_fixture_"))
        self.addCleanup(self._rmtree)
        self._build_fixture()

    def _rmtree(self):
        for child in sorted(self.tmp.rglob("*"), reverse=True):
            try:
                child.unlink() if child.is_file() else child.rmdir()
            except OSError:
                pass
        try:
            self.tmp.rmdir()
        except OSError:
            pass

    def _build_fixture(self):
        t = self.tmp
        self.art = t / "artifact.json"
        celda = {"n_events": 2, "n_trades": 2, "n_open": 0,
                 "skipped_overlap": 0, "E_net": -1.0, "placebo_E_net": -1.0,
                 "verdict": "REJECTED", "exit_stop": 0}
        celda_h2 = {"n_events": 1, "n_trades": 1, "n_open": 0,
                    "skipped_overlap": 0, "E_net": -2.0,
                    "placebo_E_net": -1.0, "verdict": "REJECTED",
                    "exit_stop": 0}
        celda_bl = {"n_events": 3, "n_trades": 3, "n_open": 0,
                    "skipped_overlap": 0, "E_net": -1.0,
                    "placebo_E_net": -1.0, "verdict": "REJECTED",
                    "exit_stop": 0}
        cells = {}
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            cells[sym] = {
                "15m": {
                    "continuation": {"dev": {"1.0": celda}},
                    "correction-exhaustion": {"dev": {"1.0": celda_h2}},
                    "baseline": {"dev": {"1.0": celda_bl}}},
                "1h": {
                    "continuation": {"dev": {"1.0": celda}},
                    "correction-exhaustion": {"dev": {"1.0": celda_h2}},
                    "baseline": {"dev": {"1.0": celda_bl}}}}
        self.art.write_text(json.dumps({
            "schema_version": 1, "artifact_version": "FIXTURE",
            "cells": cells}), encoding="utf-8")
        det_lines = []
        for d, sym, res in COMBOS:
            base = t / d
            base.mkdir(parents=True, exist_ok=True)
            evs = [
                {"symbol": sym, "event_time_ms": 1000, "direction": "LONG",
                 "reference_price": 100.0, "family": "H1",
                 "rules_version": "H1-v1", "group": "continuation"},
                {"symbol": sym, "event_time_ms": 1000, "direction": "LONG",
                 "reference_price": 100.0, "family": "H1",
                 "rules_version": "H1-v1", "group": "continuation"},
                {"symbol": sym, "event_time_ms": 2000, "direction": "SHORT",
                 "reference_price": 100.0, "family": "H2",
                 "rules_version": "H2-v1",
                 "group": "correction-exhaustion"},
                {"symbol": sym, "event_time_ms": 5000, "direction": "LONG",
                 "reference_price": 100.0, "family": "H1",
                 "rules_version": "H1-v1", "group": "baseline"},
                {"symbol": sym, "event_time_ms": 5000, "direction": "SHORT",
                 "reference_price": 100.0, "family": "H1",
                 "rules_version": "H1-v1", "group": "baseline"},
                {"symbol": sym, "event_time_ms": 5000, "direction": "LONG",
                 "reference_price": 100.0, "family": "H1",
                 "rules_version": "H1-v1", "group": "baseline"},
            ]
            (base / ("events_%s_%s.json" % (sym, res))).write_text(
                json.dumps(evs), encoding="utf-8")
            man = {"cutoff_ms": 100000, "exit_horizon_ms": 3600000,
                   "groups": {
                       "continuation": {
                           "family": "H1", "rules_version": "H1-v1",
                           "event_ids": [
                               "%s:1000:LONG:H1:H1-v1:0" % sym,
                               "%s:1000:LONG:H1:H1-v1:1" % sym],
                           "dev": {"1.0": _manifest_seg(2, -1.0)}},
                       "correction-exhaustion": {
                           "family": "H2", "rules_version": "H2-v1",
                           "event_ids": ["%s:2000:SHORT:H2:H2-v1:2" % sym],
                           "dev": {"1.0": _manifest_seg(1, -2.0)}},
                       "baseline": {
                           "family": "H1", "rules_version": "H1-v1",
                           "event_ids": [
                               "%s:5000:LONG:H1:H1-v1:3" % sym,
                               "%s:5000:SHORT:H1:H1-v1:4" % sym,
                               "%s:5000:LONG:H1:H1-v1:5" % sym],
                           "dev": {"1.0": _manifest_seg(3, -1.0)}}}}
            (base / ("manifest_%s_%s.json" % (sym, res))).write_text(
                json.dumps(man), encoding="utf-8")
            (base / ("selection_%s_%s.json" % (sym, res))).write_text(
                json.dumps({"cutoff_ms": 100000, "horizon_ms": 3600000,
                            "n_in": 6, "n_dev": 6, "n_oos": 0,
                            "n_purged_dev_crossing": 0}), encoding="utf-8")
            (base / "build_report.json").write_text(
                json.dumps({"interval": res, "symbols": [sym],
                            "counts": {"h1": 2, "h3": 0, "h2ex": 1,
                                       "h2rev": 0, "placebo": 3,
                                       "excluded_gap": 0,
                                       "excluded_no_entry": 0,
                                       "excluded_h2_no_confirmation": 0,
                                       "excluded_h2_reclaim": 0,
                                       "excluded_other_symbol": 0}}),
                encoding="utf-8")
            (base / ("candles_%s_%s.json" % (sym, res))).write_text(
                json.dumps([{"symbol": sym, "open_time_ms": o,
                             "open": 100.0, "high": 110.0, "low": 90.0,
                             "close": 100.0, "close_time_ms": o + 1}
                            for o in (0, 1000, 2000, 3000, 4000, 5000)]),
                encoding="utf-8")
            (t / ("funding_%s.json" % sym)).write_text(json.dumps([
                {"symbol": sym, "fundingTime": 4000000,
                 "fundingRate": "0.0001", "markPrice": 100.0,
                 "rateType": "Regular"}]), encoding="utf-8")
            det_lines.append(json.dumps({
                "formation_time": 1000, "available_at": 2000,
                "entry_time_same_grid": 3000, "direction": "up",
                "definition_name": "EXTENDED_GAINER",
                "original_event_id": "oid-%s-1" % sym,
                "formation_gap": False, "reference_price": 100.0,
                "symbol": sym, "source_interval": res,
                "census_id": "c-%s-1" % sym}))
            det_lines.append(json.dumps({
                "formation_time": 1000, "available_at": 2000,
                "entry_time_same_grid": 3000, "direction": "up",
                "definition_name": "MOMENTUM_ACCELERATION_UP",
                "original_event_id": "oid-%s-2" % sym,
                "formation_gap": False, "reference_price": 100.0,
                "symbol": sym, "source_interval": res,
                "census_id": "c-%s-2" % sym}))
            det_lines.append(json.dumps({
                "formation_time": 1000, "available_at": 2000,
                "entry_time_same_grid": 3000, "direction": "down",
                "definition_name": "FAILED_HIGH_CANDIDATE",
                "original_event_id": "oid-%s-3" % sym,
                "formation_gap": False, "reference_price": 105.0,
                "symbol": sym, "source_interval": res,
                "census_id": "c-%s-3" % sym}))
        for dname in ("census_btc15", "census_ethsol15", "census_1h"):
            (t / dname).mkdir(exist_ok=True)
        (t / "census_btc15" / "detections.jsonl").write_text(
            "\n".join(l for l in det_lines if '"15m"' in l
                      and "BTCUSDT" in l) + "\n", encoding="utf-8")
        (t / "census_ethsol15" / "detections.jsonl").write_text(
            "\n".join(l for l in det_lines if '"15m"' in l
                      and ("ETHUSDT" in l or "SOLUSDT" in l)) + "\n",
            encoding="utf-8")
        (t / "census_1h" / "detections.jsonl").write_text(
            "\n".join(l for l in det_lines if '"1h"' in l) + "\n",
            encoding="utf-8")
        self.trades_dir = t / "trades"
        self.trades_dir.mkdir()
        self._escribir_traces_iniciales()

    def _trades_por_sym_res(self, sym, res):
        return json.loads((self.trades_dir
                           / ("trades_%s_%s.json" % (sym, res))).read_text())

    def _escribir_traces_iniciales(self):
        """Escribe trades_*.json (equivalencia verificada/consumible) y
        reconstruye reconstruction_manifest.json con los hashes actuales."""
        trades_sha = {}
        for d, sym, res in COMBOS:
            trades = [
                _trade("%s:1000:LONG:H1:H1-v1:0" % sym, "continuation",
                       1000, 3000, -1.0, sym=sym, res=res),
                _trade("%s:1000:LONG:H1:H1-v1:1" % sym, "continuation",
                       1000, 3000, -1.0, sym=sym, res=res),
                _trade("%s:2000:SHORT:H2:H2-v1:2" % sym,
                       "correction-exhaustion", 2000, 3000, -2.0,
                       sym=sym, direction="SHORT", fam="H2", ver="H2-v1",
                       res=res),
                _trade("%s:5000:LONG:H1:H1-v1:3" % sym, "baseline",
                       5000, 5000, -1.0, sym=sym, res=res),
                _trade("%s:5000:SHORT:H1:H1-v1:4" % sym, "baseline",
                       5000, 5000, -1.0, sym=sym, direction="SHORT", res=res),
                _trade("%s:5000:LONG:H1:H1-v1:5" % sym, "baseline",
                       5000, 5000, -1.0, sym=sym, res=res),
            ]
            tdata = {"equivalencia": "verificada", "etiqueta":
                     "RECONSTRUCCION_POSTERIOR", "modo": "fixture",
                     "consumible": True, "celdas_ok": 1, "celdas_fail": 0,
                     "trades": trades}
            tp = self.trades_dir / ("trades_%s_%s.json" % (sym, res))
            tp.write_text(json.dumps(tdata), encoding="utf-8")
            trades_sha["trades_%s_%s.json" % (sym, res)] = \
                ledger.sha256_file(tp)
        self._escribir_manifest_desde_hashes(trades_sha)

    def _escribir_manifest_desde_hashes(self, trades_sha=None,
                                        veredicto="COMPLETO",
                                        n_celdas_fail=0):
        """Escribe (o reescribe) reconstruction_manifest.json a partir de los
        trades_*.json actuales. Usado tras modificar un trade para mantener
        el hash del manifiesto consistente (el único fallo debe ser la
        alteración inyectada, no un desajuste de hash)."""
        if trades_sha is None:
            trades_sha = {}
            for (_, sym, res) in COMBOS:
                tp = self.trades_dir / ("trades_%s_%s.json" % (sym, res))
                trades_sha["trades_%s_%s.json" % (sym, res)] = \
                    ledger.sha256_file(tp)
        combos_out = []
        celdas_ok = 0
        for (_, sym, res) in COMBOS:
            tp = self.trades_dir / ("trades_%s_%s.json" % (sym, res))
            consumible = tp.exists() and tp.is_file()
            if consumible:
                try:
                    td = json.loads(tp.read_text(encoding="utf-8"))
                    consumible = td.get("equivalencia") == "verificada" and td.get("consumible")
                except (ValueError, OSError):
                    consumible = False
            if consumible:
                celdas_ok += 1
            combos_out.append({"symbol": sym, "res": res,
                               "celdas_ok": 1 if consumible else 0,
                               "celdas_fail": 0 if consumible else 1,
                               "equivalencia": "verificada" if consumible else "fallida",
                               "consumible": consumible})
        man = {
            "etiqueta": "RECONSTRUCCION_POSTERIOR fixture",
            "modo": "fixture", "tolerancia": 1e-9,
            "veredicto": veredicto,
            "celdas_fail": [], "n_celdas_fail": n_celdas_fail,
            "cobertura": {
                "combos": combos_out,
                "celdas_totales": len(COMBOS), "celdas_ok": celdas_ok,
                "celdas_fail": n_celdas_fail},
            "trades_sha256": trades_sha,
            "inputs_sha256": {},
            "diagnostico_sha256": None,
            "parametros": {},
            "purga": {}}
        (self.trades_dir / "reconstruction_manifest.json").write_text(
            json.dumps(man), encoding="utf-8")

    def _remanifiesto(self):
        """Regenera reconstruction_manifest.json tras modificar trades
        (sin reescribir los trades)."""
        self._escribir_manifest_desde_hashes()

    def _run_cli(self, art=None, temp=None, trades=None):
        out = self.tmp / "reporte.json"
        args = ["--artifact", str(art or self.art),
                "--temp-dir", str(temp or self.tmp),
                "--trades-dir", str(trades or self.trades_dir),
                "--out", str(out)]
        rc = ledger.main(args)
        rep = json.loads(out.read_text(encoding="utf-8"))
        return rc, rep

    def _manifiesto(self, sym="BTCUSDT", res="15m"):
        for d, s, r in COMBOS:
            if s == sym and r == res:
                return json.loads((self.tmp / d
                                   / ("manifest_%s_%s.json" % (sym, res))
                                   ).read_text())
        raise KeyError((sym, res))

    def _guardar_manifiesto(self, sym, res, man):
        for d, s, r in COMBOS:
            if s == sym and r == res:
                (self.tmp / d / ("manifest_%s_%s.json" % (sym, res))
                 ).write_text(json.dumps(man), encoding="utf-8")
                return

    # control. Control íntegro válido
    def test_control_integro_pass_exit0(self):
        rc, rep = self._run_cli()
        self.assertEqual(rc, 0, "control debe dar exit 0: %s"
                         % rep["veredicto"]["discrepancias"][:3])
        self.assertEqual(rep["veredicto"]["estado"], "PASS",
                         "control debe dar PASS: %s"
                         % rep["veredicto"]["discrepancias"][:3])

    # 1. Referencia inexistente
    def test_referencia_inexistente_fail(self):
        art = json.loads(self.art.read_text())
        art["cells"]["ETHUSDT"]["15m"]["continuation"]["dev"]["1.0"]["n_events"] = 9
        self.art.write_text(json.dumps(art))
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("FAIL", rep["veredicto"]["estado"])
        self.assertTrue(any(d["seccion"] == "referencias"
                            for d in rep["veredicto"]["discrepancias"]))

    # 2. E_net alterado manteniendo los conteos
    def test_enet_alterado_fail(self):
        art = json.loads(self.art.read_text())
        art["cells"]["BTCUSDT"]["15m"]["continuation"]["dev"]["1.0"]["E_net"] = 999.0
        self.art.write_text(json.dumps(art))
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("FAIL", rep["veredicto"]["estado"])
        self.assertTrue(any(d["seccion"] == "campos_economicos"
                            for d in rep["veredicto"]["discrepancias"]))

    # 3. Campo obligatorio ausente en manifiesto
    def test_campo_ausente_manifiesto_fail(self):
        man = self._manifiesto()
        del man["groups"]["continuation"]["dev"]["1.0"]["n_events"]
        self._guardar_manifiesto("BTCUSDT", "15m", man)
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("FAIL", rep["veredicto"]["estado"])
        self.assertTrue(any(d["seccion"] == "referencias"
                            for d in rep["veredicto"]["discrepancias"]))

    # 4. Escenario inesperado
    def test_escenario_inesperado_fail(self):
        man = self._manifiesto()
        man["groups"]["continuation"]["dev"]["4.0"] = _seg(2, -1.0)
        self._guardar_manifiesto("BTCUSDT", "15m", man)
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("FAIL", rep["veredicto"]["estado"])
        self.assertTrue(any("escenario" in d["motivo"].lower()
                            for d in rep["veredicto"]["discrepancias"]))

    # 5. Duplicación indebida
    def test_duplicacion_indebida_fail(self):
        man = self._manifiesto()
        man["groups"]["continuation"]["event_ids"].append(
            "BTCUSDT:1000:LONG:H1:H1-v1:0")
        self._guardar_manifiesto("BTCUSDT", "15m", man)
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("FAIL", rep["veredicto"]["estado"])
        self.assertTrue(any(d["seccion"] == "trazabilidad_operaciones"
                            for d in rep["veredicto"]["discrepancias"]))

    # 6. Entrada efectiva anterior a disponibilidad
    def test_entry_antes_de_disponibilidad_fail(self):
        t = self._trades_por_sym_res("BTCUSDT", "15m")
        for tr in t["trades"]:
            if tr["event_id"] == "BTCUSDT:1000:LONG:H1:H1-v1:0":
                tr["entry_ms"] = 1500
        self.trades_dir.joinpath("trades_BTCUSDT_15m.json").write_text(
            json.dumps(t), encoding="utf-8")
        self._remanifiesto()
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("FAIL", rep["veredicto"]["estado"])
        self.assertTrue(any("disponibilidad" in d["motivo"]
                            for d in rep["veredicto"]["discrepancias"]))

    # 7. H2 entrando antes de conocerse su confirmación
    def test_h2_antes_de_confirmacion_fail(self):
        t = self._trades_por_sym_res("BTCUSDT", "15m")
        for tr in t["trades"]:
            if tr["event_id"] == "BTCUSDT:2000:SHORT:H2:H2-v1:2":
                tr["entry_ms"] = 2000
        self.trades_dir.joinpath("trades_BTCUSDT_15m.json").write_text(
            json.dumps(t), encoding="utf-8")
        self._remanifiesto()
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("FAIL", rep["veredicto"]["estado"])
        self.assertTrue(any("confirmaci" in d["motivo"].lower()
                            for d in rep["veredicto"]["discrepancias"]))

    # 8. Operación sin candidato
    def test_operacion_sin_candidato_fail(self):
        t = self._trades_por_sym_res("BTCUSDT", "15m")
        t["trades"].append(_trade("BTCUSDT:9999:LONG:H1:H1-v9",
                                  "continuation", 9999, 9999, -1.0,
                                  sym="BTCUSDT", res="15m"))
        self.trades_dir.joinpath("trades_BTCUSDT_15m.json").write_text(
            json.dumps(t), encoding="utf-8")
        self._remanifiesto()
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("FAIL", rep["veredicto"]["estado"])
        self.assertTrue(any("sin candidato" in d["motivo"]
                            for d in rep["veredicto"]["discrepancias"]))

    # 9. Input faltante
    def test_input_faltante_incomplete(self):
        rc, rep = self._run_cli(temp=self.tmp / "vacio_inexistente")
        self.assertNotEqual(rc, 0)
        self.assertIn("INCOMPLETE", rep["veredicto"]["estado"])

    # 10. entry_ms ausente → INCOMPLETE
    def test_entry_ms_ausente_incomplete(self):
        t = self._trades_por_sym_res("BTCUSDT", "15m")
        for tr in t["trades"]:
            if tr["event_id"] == "BTCUSDT:1000:LONG:H1:H1-v1:0":
                tr["entry_ms"] = None
        self.trades_dir.joinpath("trades_BTCUSDT_15m.json").write_text(
            json.dumps(t), encoding="utf-8")
        self._remanifiesto()
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("INCOMPLETE", rep["veredicto"]["estado"])
        self.assertTrue(any("entry_ms" in d.get("motivo", "")
                            for d in rep["veredicto"]["incompleto"]))

    # 11. entry_ms no finito → INCOMPLETE
    def test_entry_ms_no_finito_incomplete(self):
        t = self._trades_por_sym_res("BTCUSDT", "15m")
        for tr in t["trades"]:
            if tr["event_id"] == "BTCUSDT:1000:LONG:H1:H1-v1:0":
                tr["entry_ms"] = float("inf")
        self.trades_dir.joinpath("trades_BTCUSDT_15m.json").write_text(
            json.dumps(t, default=str), encoding="utf-8")
        self._remanifiesto()
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("INCOMPLETE", rep["veredicto"]["estado"])

    # 12. H2 con close_time_ms ausente → INCOMPLETE
    def test_h2_close_time_ms_ausente_incomplete(self):
        cp = self.tmp / "eval15_btc" / "candles_BTCUSDT_15m.json"
        bars = json.loads(cp.read_text(encoding="utf-8"))
        for b in bars:
            if b["open_time_ms"] == 2000:
                b["close_time_ms"] = None
        cp.write_text(json.dumps(bars), encoding="utf-8")
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("INCOMPLETE", rep["veredicto"]["estado"])

    # 13. Respaldo de resolución incompatible → INCOMPLETE
    def test_respaldo_resolucion_incompatible_incomplete(self):
        # Añade una detección H1 de 1h con el mismo símbolo/timestamp/dirección
        # que una operación de 15m, SIN detección de 15m compatible.
        # El ledger no debe cruzar resoluciones: la operación de 15m se queda
        # sin respaldo compatible.
        det = {
            "formation_time": 1000, "available_at": 2000,
            "entry_time_same_grid": 3000, "direction": "up",
            "definition_name": "EXTENDED_GAINER",
            "original_event_id": "oid-res-1", "formation_gap": False,
            "reference_price": 100.0, "symbol": "BTCUSDT",
            "source_interval": "1h", "census_id": "c-res-1"}
        (self.tmp / "census_1h" / "detections.jsonl").write_text(
            json.dumps(det) + "\n", encoding="utf-8")
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("INCOMPLETE", rep["veredicto"]["estado"])

    # 14. reconstruction_manifest con FAIL → ledger rechaza → INCOMPLETE
    def test_manifest_traces_fail_rechazado_incomplete(self):
        man = json.loads((self.trades_dir / "reconstruction_manifest.json")
                         .read_text(encoding="utf-8"))
        man["veredicto"] = "FAIL"
        man["n_celdas_fail"] = 1
        man["celdas_fail"] = [{"symbol": "BTCUSDT", "res": "15m",
                               "motivos": ["sintetico"]}]
        (self.trades_dir / "reconstruction_manifest.json").write_text(
            json.dumps(man), encoding="utf-8")
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        # Un manifiesto con veredicto FAIL = trazas no equivalentes: FAIL
        # (demostrable), nunca aceptación implícita.
        self.assertEqual(rep["veredicto"]["estado"], "FAIL",
                         "manifest FAIL debe ser rechazado con FAIL: %s"
                         % rep["veredicto"]["discrepancias"][:3])

    # 15. Archivo de trades alterado después de reconstruir (hash mismatch) → FAIL
    def test_trades_alterado_despues_hash_fail(self):
        t = self._trades_por_sym_res("BTCUSDT", "15m")
        t["trades"][0]["net_pnl"] = 9999.0
        # Se altera el trade PERO NO se regenera el manifiesto:
        self.trades_dir.joinpath("trades_BTCUSDT_15m.json").write_text(
            json.dumps(t), encoding="utf-8")
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("FAIL", rep["veredicto"]["estado"])

    # 16. Archivo de trades obsoleto de ejecución previa (extra) → FAIL
    def test_trades_obsoleto_extra_fail(self):
        (self.trades_dir / "trades_OBSOLETO_99.json").write_text(
            json.dumps({"equivalencia": "verificada", "consumible": True,
                        "trades": []}), encoding="utf-8")
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("FAIL", rep["veredicto"]["estado"])

    # 17. Archivo esperado ausente → INCOMPLETE
    def test_trades_esperado_ausente_incomplete(self):
        (self.trades_dir / "trades_ETHUSDT_15m.json").unlink()
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("INCOMPLETE", rep["veredicto"]["estado"])


if __name__ == "__main__":
    unittest.main()
