"""Tests unitarios del reconstructor de trazas (reconstruct_replay_traces.py).

Contrato fail-closed:
- una celda fallida no genera trazas consumibles como verificadas;
- las operaciones de celdas falladas van a diagnostico_celdas_fallidas.json,
  etiquetado FALLIDA_NO_CONSUMIBLE, y el ledger debe rechazarlas;
- veredicto COMPLETO solo si todas las celdas equivalen, else FAIL (exit != 0);
- no quedan archivos antiguos que parezcan de la nueva reconstrucción.

Modo temp:
- --package: inputs ya post-purge, sin segunda purga.
- --temp-dir: se repite la purga determinista; n_in_pre_purge documentado.
- exactamente uno de --package/--temp-dir obligatorio (ambos o ninguno →
  error de uso, exit != 0).
- Equivalencia entre modos sobre inputs correspondientes (orden, identidades,
  purga, resultados).

No toca la red ni DBs canónicas; usa fixtures sintéticos autocontenidos.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import sys as _sys
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in _sys.path:
    _sys.path.insert(0, str(SRC))

from microstructure_probe.backtest_offline import (  # noqa: E402
    BacktestConfig, Candle, FundingCalendar, FundingSettlement, StudyEvent,
    run_backtest)

_spec = importlib.util.spec_from_file_location(
    "recon", str(ROOT / "scripts" / "reconstruct_replay_traces.py"))
recon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(recon)

COMBOS = [
    ("eval15_btc", "BTCUSDT", "15m"),
    ("eval15_ethsol", "ETHUSDT", "15m"),
    ("eval15_ethsol", "SOLUSDT", "15m"),
    ("eval1h_trio", "BTCUSDT", "1h"),
    ("eval1h_trio", "ETHUSDT", "1h"),
    ("eval1h_trio", "SOLUSDT", "1h"),
]
CUTOFF = 100_000_000
HORIZON = 3_600_000


def _make_events(sym):
    return [
        StudyEvent(symbol=sym, event_time_ms=1000, direction="LONG",
                   reference_price=100.0, family="H1", rules_version="H1-v1"),
        StudyEvent(symbol=sym, event_time_ms=2000, direction="LONG",
                   reference_price=100.0, family="H1", rules_version="H1-v1"),
    ]


def _make_candles(sym):
    return [Candle(symbol=sym, open_time_ms=o, open=100.0, high=101.0,
                   low=99.0, close=100.0, close_time_ms=o + 1)
            for o in (0, 900000, 1800000, 2700000, 3600000, 4500000,
                      5400000, 6300000, 7200000)]


def _make_calendar(sym):
    return FundingCalendar(
        version="FUNDING-CAL-v1",
        source="exchange-funding-history (Binance USD-M fundingRate)",
        interval_ms=28_800_000,
        symbol=sym,
        settlements=())


def _build_replay_result(events, candles, calendar):
    """Ejecuta run_backtest con la misma configuración que el reconstructor
    (incluido funding_calendar, que entra en config_hash)."""
    gev = [e for e in events]
    cfg = BacktestConfig(family="H1", rules_version="H1-v1",
                         exit_horizon_ms=HORIZON, cost_scale=1.0,
                         funding_calendar=calendar)
    r = run_backtest(gev, candles, cfg, dataset_id="caller-supplied",
                     segment="dev")
    admitidos = sorted(range(len(gev)),
                       key=lambda j: (gev[j].event_time_ms, gev[j].symbol))
    pos_en_gev = {id(e): k for k, e in enumerate(gev)}
    eids = []
    for k, pos in enumerate(r["admitted_positions"]):
        e_seg = gev[admitidos[pos]]
        i_global = pos_en_gev[id(e_seg)]
        eids.append("%s:%d:%s:%s:%s:%d" % (e_seg.symbol, e_seg.event_time_ms,
                                           e_seg.direction, e_seg.family,
                                           e_seg.rules_version, i_global))
    return r, eids


def _manifest_from_r(r, eids):
    return {"cutoff_ms": CUTOFF, "exit_horizon_ms": HORIZON,
            "groups": {"continuation": {"family": "H1",
                                        "rules_version": "H1-v1",
                                        "event_ids": eids,
                                        "dev": {"1.0": r}}}}


def _selection(n_dev, n_oos, purged):
    return {"cutoff_ms": CUTOFF, "horizon_ms": HORIZON,
            "n_dev": n_dev, "n_oos": n_oos,
            "n_purged_dev_crossing": purged}


def _escribir_combo(base, sym, res):
    """Crea un combo completo (events, candles, manifest, selection) cuyo
    manifiesto es autoconsistente con el replay (equivalencia pasa)."""
    base.mkdir(parents=True, exist_ok=True)
    events = _make_events(sym)
    candles = _make_candles(sym)
    calendar = _make_calendar(sym)
    r, eids = _build_replay_result(events, candles, calendar)
    man = _manifest_from_r(r, eids)
    ev_rows = [{"symbol": e.symbol, "event_time_ms": e.event_time_ms,
                "direction": e.direction, "reference_price": e.reference_price,
                "family": e.family, "rules_version": e.rules_version,
                "group": "continuation"} for e in events]
    (base / ("events_%s_%s.json" % (sym, res))).write_text(
        json.dumps(ev_rows), encoding="utf-8")
    ca_rows = [{"symbol": c.symbol, "open_time_ms": c.open_time_ms,
                "open": c.open, "high": c.high, "low": c.low, "close": c.close,
                "close_time_ms": c.close_time_ms} for c in candles]
    (base / ("candles_%s_%s.json" % (sym, res))).write_text(
        json.dumps(ca_rows), encoding="utf-8")
    (base / ("manifest_%s_%s.json" % (sym, res))).write_text(
        json.dumps(man, default=str), encoding="utf-8")
    (base / ("selection_%s_%s.json" % (sym, res))).write_text(
        json.dumps(_selection(2, 0, 0)), encoding="utf-8")
    return events


class ReconstructTempModeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="recon_"))
        self.addCleanup(self._rmtree)
        self.base = self.tmp / "combos_root"
        self.events_por_combo = {}
        for d, sym, res in COMBOS:
            self.events_por_combo[(sym, res)] = _escribir_combo(
                self.base / d, sym, res)
        # funding en la raíz del temp (modo temp lee fund_dir=temp)
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            (self.base / ("funding_%s.json" % sym)).write_text(
                json.dumps([]), encoding="utf-8")

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

    def test_control_temp_exit0_completo_consumible(self):
        out = self.tmp / "out"
        rc = recon.main(["--temp-dir", str(self.tmp / "combos_root"),
                         "--out-dir", str(out)])
        self.assertEqual(rc, 0)
        man = json.loads((out / "reconstruction_manifest.json").read_text())
        self.assertEqual(man["veredicto"], "COMPLETO")
        self.assertEqual(man["n_celdas_fail"], 0)
        trades = json.loads((out / ("trades_BTCUSDT_15m.json")).
                            read_text(encoding="utf-8"))
        self.assertEqual(trades["equivalencia"], "verificada")
        self.assertTrue(trades["consumible"])
        self.assertFalse((out / "diagnostico_celdas_fallidas.json").exists())

    def test_events_pre_documentado_temp(self):
        out = self.tmp / "out"
        recon.main(["--temp-dir", str(self.tmp / "combos_root"),
                    "--out-dir", str(out)])
        man = json.loads((out / "reconstruction_manifest.json").read_text())
        pc = man["purga"]["BTCUSDT/15m"]
        self.assertEqual(pc["modo"], "temp")
        self.assertEqual(pc["segunda_purga"], False)
        self.assertEqual(pc["n_in_pre_purge"], 2)
        self.assertEqual(pc["n_events_post_purge"], 2)
        self.assertEqual(pc["n_dev"], 2)
        self.assertEqual(pc["n_oos"], 0)
        self.assertEqual(pc["n_purged"], 0)

    def test_args_ambiguos_error(self):
        out = self.tmp / "out"
        rc = recon.main(["--out-dir", str(out)])
        self.assertNotEqual(rc, 0)
        rc = recon.main(["--package", str(self.tmp), "--temp-dir", str(self.tmp),
                         "--out-dir", str(out)])
        self.assertNotEqual(rc, 0)

    def test_fail_closed_celda_falla_no_verificada(self):
        # Altera un manifiesto (n_trades distinto) → equivalencia falla.
        mp = self.base / "eval15_btc" / "manifest_BTCUSDT_15m.json"
        man_fail = json.loads(mp.read_text(encoding="utf-8"))
        seg = man_fail["groups"]["continuation"]["dev"]["1.0"]
        seg["n_trades"] = seg["n_trades"] + 1
        mp.write_text(json.dumps(man_fail), encoding="utf-8")
        out = self.tmp / "out"
        rc = recon.main(["--temp-dir", str(self.tmp / "combos_root"),
                         "--out-dir", str(out)])
        self.assertNotEqual(rc, 0)
        self.assertEqual(rc, 1)
        man = json.loads((out / "reconstruction_manifest.json").read_text())
        self.assertEqual(man["veredicto"], "FAIL")
        self.assertGreater(man["n_celdas_fail"], 0)
        trades = json.loads((out / ("trades_BTCUSDT_15m.json")).
                            read_text(encoding="utf-8"))
        self.assertEqual(trades["equivalencia"], "fallida")
        self.assertFalse(trades["consumible"])
        diag = out / "diagnostico_celdas_fallidas.json"
        self.assertTrue(diag.exists())
        diag_data = json.loads(diag.read_text(encoding="utf-8"))
        self.assertEqual(diag_data["estado"], "FALLIDA_NO_CONSUMIBLE")
        self.assertIn("no son aptas para consumo", diag_data["motivo"])

    def test_package_modio_post_purge(self):
        pkg = self.tmp / "pkg"
        pkg_combos = pkg / "combos"
        for d, sym, res in COMBOS:
            _escribir_combo(pkg_combos / d, sym, res)
        (pkg / "funding").mkdir(exist_ok=True)
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            (pkg / "funding" / ("funding_%s.json" % sym)).write_text(
                json.dumps([]), encoding="utf-8")
        (pkg / "detections").mkdir(exist_ok=True)
        out = self.tmp / "out_pkg"
        rc = recon.main(["--package", str(pkg), "--out-dir", str(out)])
        self.assertEqual(rc, 0)
        man = json.loads((out / "reconstruction_manifest.json").read_text())
        self.assertEqual(man["veredicto"], "COMPLETO")
        self.assertEqual(man["modo"], "package")
        pc = man["purga"]["BTCUSDT/15m"]
        self.assertEqual(pc["segunda_purga"], False)
        trades = json.loads((out / ("trades_BTCUSDT_15m.json")).
                            read_text(encoding="utf-8"))
        self.assertEqual(trades["equivalencia"], "verificada")

    def test_equivalencia_modos(self):
        pkg = self.tmp / "pkg"
        pkg_combos = pkg / "combos"
        for d, sym, res in COMBOS:
            _escribir_combo(pkg_combos / d, sym, res)
        (pkg / "funding").mkdir(exist_ok=True)
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            (pkg / "funding" / ("funding_%s.json" % sym)).write_text(
                json.dumps([]), encoding="utf-8")
        (pkg / "detections").mkdir(exist_ok=True)
        out_temp = self.tmp / "out_temp"
        out_pkg = self.tmp / "out_pkg"
        rc_t = recon.main(["--temp-dir", str(self.tmp / "combos_root"),
                           "--out-dir", str(out_temp)])
        rc_p = recon.main(["--package", str(pkg), "--out-dir", str(out_pkg)])
        self.assertEqual(rc_t, 0)
        self.assertEqual(rc_p, 0)
        t_t = json.loads((out_temp / ("trades_BTCUSDT_15m.json")).
                         read_text(encoding="utf-8"))
        t_p = json.loads((out_pkg / ("trades_BTCUSDT_15m.json")).
                         read_text(encoding="utf-8"))
        self.assertEqual(t_t["trades"], t_p["trades"])
        self.assertEqual(t_t["equivalencia"], t_p["equivalencia"])
        m_t = json.loads((out_temp / "reconstruction_manifest.json").read_text())
        m_p = json.loads((out_pkg / "reconstruction_manifest.json").read_text())
        self.assertEqual(m_t["veredicto"], m_p["veredicto"])
        self.assertEqual(m_t["n_celdas_fail"], m_p["n_celdas_fail"])
        self.assertEqual(m_t["cobertura"], m_p["cobertura"])


if __name__ == "__main__":
    unittest.main()
