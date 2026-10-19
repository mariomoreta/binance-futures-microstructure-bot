"""Tests CLI con fixtures completos (EVAL-CENSUS-V2).

Ejecuta el CLI (ledger.main) con un fixture mínimo autocontenido (6
combos) y verifica reporte + exit. Cada alteración produce FAIL o
INCOMPLETE con exit no exitoso; el control íntegro produce PASS y
exit 0.

Casos:
  1. Referencia inexistente (celda en artefacto sin manifiesto)
  2. E_net alterado manteniendo los conteos
  3. Campo obligatorio ausente en manifiesto
  4. Escenario inesperado (escala 4.0)
  5. Duplicación indebida (event_id duplicado en manifiesto)
  6. Entrada efectiva anterior a disponibilidad
  7. H2 entrando antes de conocerse su confirmación
  8. Operación sin candidato (event_id no en manifiesto)
  9. Input faltante (funding ausente)
 10. Control íntegro válido
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
          fam="H1", ver="H1-v1"):
    return {"event_id": eid, "group": grp, "segmento": "dev",
            "escala": 1.0, "res": "15m", "symbol": sym,
            "direction": direction, "family": fam, "rules_version": ver,
            "event_time_ms": et, "entry_ms": entry, "exit_ms": entry + 1000,
            "entry_px": 100.0, "exit_px": 99.0, "exit_reason": "horizon",
            "open_at_end": False, "exit_executed": True,
            "estado": "realizada", "net_pnl": en, "gross_pnl": -0.5,
            "fees": 0.5, "funding": 0.0, "mfe_pct": 0.5, "mae_pct": 0.2}


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
                           "dev": {"1.0": _seg(2, -1.0)}},
                       "correction-exhaustion": {
                           "family": "H2", "rules_version": "H2-v1",
                           "event_ids": ["%s:2000:SHORT:H2:H2-v1:2" % sym],
                           "dev": {"1.0": _seg(1, -2.0)}},
                       "baseline": {
                           "family": "H1", "rules_version": "H1-v1",
                           "event_ids": [
                               "%s:5000:LONG:H1:H1-v1:3" % sym,
                               "%s:5000:SHORT:H1:H1-v1:4" % sym,
                               "%s:5000:LONG:H1:H1-v1:5" % sym],
                           "dev": {"1.0": _seg(3, -1.0)}}}}
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
        for d, sym, res in COMBOS:
            trades = [
                _trade("%s:1000:LONG:H1:H1-v1:0" % sym, "continuation",
                       1000, 3000, -1.0, sym=sym),
                _trade("%s:1000:LONG:H1:H1-v1:1" % sym, "continuation",
                       1000, 3000, -1.0, sym=sym),
                _trade("%s:2000:SHORT:H2:H2-v1:2" % sym,
                       "correction-exhaustion", 2000, 3000, -2.0,
                       sym=sym, direction="SHORT", fam="H2", ver="H2-v1"),
                _trade("%s:5000:LONG:H1:H1-v1:3" % sym, "baseline",
                       5000, 5000, -1.0, sym=sym),
                _trade("%s:5000:SHORT:H1:H1-v1:4" % sym, "baseline",
                       5000, 5000, -1.0, sym=sym, direction="SHORT"),
                _trade("%s:5000:LONG:H1:H1-v1:5" % sym, "baseline",
                       5000, 5000, -1.0, sym=sym),
            ]
            (self.trades_dir / ("trades_%s_%s.json" % (sym, res))).write_text(
                json.dumps({"equivalencia": "fixture", "trades": trades}),
                encoding="utf-8")

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

    def _trades(self, sym="BTCUSDT", res="15m"):
        return json.loads((self.trades_dir
                           / ("trades_%s_%s.json" % (sym, res))).read_text())

    # 10. Control íntegro válido
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
        for d, s, r in COMBOS:
            if s == "BTCUSDT" and r == "15m":
                (self.tmp / d / "manifest_BTCUSDT_15m.json").write_text(
                    json.dumps(man))
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("FAIL", rep["veredicto"]["estado"])
        self.assertTrue(any(d["seccion"] == "referencias"
                            for d in rep["veredicto"]["discrepancias"]))

    # 4. Escenario inesperado
    def test_escenario_inesperado_fail(self):
        man = self._manifiesto()
        man["groups"]["continuation"]["dev"]["4.0"] = _seg(2, -1.0)
        for d, s, r in COMBOS:
            if s == "BTCUSDT" and r == "15m":
                (self.tmp / d / "manifest_BTCUSDT_15m.json").write_text(
                    json.dumps(man))
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
        for d, s, r in COMBOS:
            if s == "BTCUSDT" and r == "15m":
                (self.tmp / d / "manifest_BTCUSDT_15m.json").write_text(
                    json.dumps(man))
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("FAIL", rep["veredicto"]["estado"])
        self.assertTrue(any(d["seccion"] == "trazabilidad_operaciones"
                            for d in rep["veredicto"]["discrepancias"]))

    # 6. Entrada efectiva anterior a disponibilidad
    def test_entry_antes_de_disponibilidad_fail(self):
        t = self._trades()
        for tr in t["trades"]:
            if tr["event_id"] == "BTCUSDT:1000:LONG:H1:H1-v1:0":
                tr["entry_ms"] = 1500
        (self.trades_dir / "trades_BTCUSDT_15m.json").write_text(
            json.dumps(t))
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("FAIL", rep["veredicto"]["estado"])
        self.assertTrue(any("disponibilidad" in d["motivo"]
                            for d in rep["veredicto"]["discrepancias"]))

    # 7. H2 entrando antes de conocerse su confirmación
    def test_h2_antes_de_confirmacion_fail(self):
        t = self._trades()
        for tr in t["trades"]:
            if tr["event_id"] == "BTCUSDT:2000:SHORT:H2:H2-v1:2":
                tr["entry_ms"] = 2000
        (self.trades_dir / "trades_BTCUSDT_15m.json").write_text(
            json.dumps(t))
        rc, rep = self._run_cli()
        self.assertNotEqual(rc, 0)
        self.assertIn("FAIL", rep["veredicto"]["estado"])
        self.assertTrue(any("confirmaci" in d["motivo"].lower()
                            for d in rep["veredicto"]["discrepancias"]))

    # 8. Operación sin candidato
    def test_operacion_sin_candidato_fail(self):
        t = self._trades()
        t["trades"].append(_trade("BTCUSDT:9999:LONG:H1:H1-v9",
                                  "continuation", 9999, 9999, -1.0))
        (self.trades_dir / "trades_BTCUSDT_15m.json").write_text(
            json.dumps(t))
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


if __name__ == "__main__":
    unittest.main()
